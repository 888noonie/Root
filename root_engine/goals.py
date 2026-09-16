"""Durable, bounded capability goals and objective-specific GitHub discovery."""

import json
import math
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .collector import NoRedirect, read_json
from .local_models import DEFAULT_MODEL, RESERVED_TOKENS_PER_CALL, classify, inference_plan, research_inference_plan
from .research import validate_research_output
from .retry_component import COMPONENT, candidate_delay, extract_parser
from .screen import screen_packet
from .store import BudgetError, RootError, digest, encode

PROJECT = Path(__file__).resolve().parents[1]
GOAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS goals (id TEXT PRIMARY KEY, spec TEXT NOT NULL, created REAL NOT NULL,
 deadline REAL NOT NULL, state TEXT NOT NULL, requests INTEGER NOT NULL DEFAULT 0,
 downloaded_bytes INTEGER NOT NULL DEFAULT 0, inference_reserved INTEGER NOT NULL DEFAULT 0,
 result TEXT, mode TEXT);
CREATE TABLE IF NOT EXISTS goal_events (goal_id TEXT NOT NULL REFERENCES goals(id), stage TEXT NOT NULL,
 created REAL NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(goal_id,stage));
CREATE TABLE IF NOT EXISTS repo_evidence (id TEXT PRIMARY KEY, goal_id TEXT NOT NULL REFERENCES goals(id),
 url TEXT NOT NULL, mode TEXT NOT NULL, retrieved REAL NOT NULL, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS components (id TEXT PRIMARY KEY, name TEXT NOT NULL, goal_id TEXT NOT NULL REFERENCES goals(id),
 revision TEXT NOT NULL, source TEXT NOT NULL, license TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 0);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_component ON components(name) WHERE active=1;
"""


class Goals:
    def __init__(self, store):
        self.store = store
        present = store.db.execute("SELECT 1 FROM sqlite_master WHERE name='goals'").fetchone()
        if not present:
            store.check(32768)
            store.db.executescript(GOAL_SCHEMA)

    def row(self, goal_id):
        row = self.store.db.execute("SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone()
        if not row:
            raise RootError("Unknown capability goal")
        value = dict(row)
        value["spec"] = json.loads(value["spec"])
        value["result"] = json.loads(value["result"]) if value["result"] else None
        return value

    def create(self, spec):
        if not isinstance(spec, dict):
            raise RootError("Goal must be a JSON object")
        for field in ("id", "objective", "parent_objective", "bottleneck", "search_query", "acceptance"):
            if not isinstance(spec.get(field), str) or not spec[field].strip():
                raise RootError(f"Goal requires {field}")
        if spec.get("adapter") not in ("retry_after_v1", "research_component_v1"):
            raise RootError("Only the curated retry_after_v1 and research_component_v1 adapters are supported")
        if "fallback_search_query" in spec and (not isinstance(spec["fallback_search_query"], str) or not 0 < len(spec["fallback_search_query"]) <= 400):
            raise RootError("Fallback search must be a bounded query string")
        policy = self.store.portfolio()["policy"]
        spec = dict(spec)
        if "model_path" in spec:
            if not isinstance(spec["model_path"], str) or not spec["model_path"].strip():
                raise RootError("Model path must be a nonempty string")
            model = Path(spec["model_path"]).resolve()
            spec["model_path"] = str(model)
            spec["model_bytes"] = model.stat().st_size
            if spec.get("adapter") == "research_component_v1":
                cap = spec.pop("research_generation_cap", 512)
                if type(cap) is not int:
                    raise RootError("research_generation_cap must be an integer")
                spec["inference_plan"] = research_inference_plan(model, generation_cap=cap)
            else:
                spec["inference_plan"] = inference_plan(model)
        elif "inference_plan" in spec or "model_bytes" in spec:
            raise RootError("A declared inference plan requires an explicit model path")
        spec.setdefault("max_money_gbp", 0)
        spec.setdefault("max_storage_bytes", policy["max_storage_bytes"])
        spec.setdefault("max_concurrent_jobs", 1)
        if spec["max_money_gbp"] != 0 or spec["max_concurrent_jobs"] != 1:
            raise RootError("A capability goal has zero spending and one job only")
        if type(spec["max_storage_bytes"]) is not int or not 16384 <= spec["max_storage_bytes"] <= policy["max_storage_bytes"]:
            raise RootError("Goal storage allowance must be at least 16 KiB and fit portfolio storage")
        eval_stem = "research_component" if spec["adapter"] == "research_component_v1" else "retry_after"
        custom_files = spec.get("evaluation_files")
        if custom_files is not None:
            if not isinstance(custom_files, dict) or not custom_files or len(custom_files) > 2 \
               or any(name not in ("development", "holdout") for name in custom_files):
                raise RootError("evaluation_files must map development/holdout to example filenames")
            names = ("development", "holdout")
            file_map = {}
            for name in names:
                fname = custom_files.get(name, eval_stem + "." + name + ".json")
                if not isinstance(fname, str) or "/" in fname or ".." in fname or not fname.endswith(".json") or not (PROJECT / "examples" / fname).is_file():
                    raise RootError("evaluation_files names must resolve to example JSON files")
                file_map[name] = fname
            spec["evaluation_files"] = file_map
            spec["evaluation_manifest"] = {name: digest(read_json(PROJECT / "examples" / file_map[name])) for name in names}
        else:
            spec["evaluation_manifest"] = {name: digest(read_json(PROJECT / f"examples/{eval_stem}.{name}.json")) for name in ("development", "holdout")}
        for key in ("max_requests", "max_download_bytes", "max_elapsed_seconds", "max_inference_tokens"):
            if type(spec.get(key)) is not int or spec[key] < 0 or spec[key] > policy[key]:
                raise RootError(f"Goal allowance must fit portfolio: {key}")
        if not 0 < spec["max_elapsed_seconds"] <= 900:
            raise RootError("Goal must stop within 900 seconds")
        with self.store.transaction():
            self.store.check(len(encode(spec).encode()) * 2 + 16384)
            if self.store.db.execute("SELECT 1 FROM goals WHERE id=?", (spec["id"],)).fetchone():
                raise RootError("Goal already exists; allowances and criteria cannot be reset by overwrite")
            now = self.store.now()
            self.store.db.execute("INSERT INTO goals(id,spec,created,deadline,state) VALUES(?,?,?,?,?)",
                                  (spec["id"], encode(spec), now, min(now + spec["max_elapsed_seconds"], self.store.portfolio()["deadline"]), "created"))
        return self.row(spec["id"])

    def payload_bytes(self, goal_id):
        total = self.store.db.execute("SELECT length(CAST(spec AS BLOB))+coalesce(length(CAST(result AS BLOB)),0)+512 FROM goals WHERE id=?", (goal_id,)).fetchone()[0]
        for table, fields in (("goal_events", ("payload", "stage")), ("repo_evidence", ("body", "url")), ("components", ("source", "license", "revision"))):
            expression = "+".join(f"length(CAST({field} AS BLOB))" for field in fields)
            total += self.store.db.execute(f"SELECT coalesce(sum({expression}+512),0) FROM {table} WHERE goal_id=?", (goal_id,)).fetchone()[0]
        return total

    def check(self, goal_id, extra_storage=0):
        self.store.check()
        row = self.row(goal_id)
        if self.store.now() >= row["deadline"]:
            raise BudgetError("Capability goal deadline reached")
        if self.payload_bytes(goal_id) + extra_storage > row["spec"].get("max_storage_bytes", self.store.portfolio()["policy"]["max_storage_bytes"]):
            raise BudgetError("Capability goal record-storage budget reached")
        return row

    def record(self, goal_id, stage, payload):
        with self.store.transaction():
            self.check(goal_id, len(encode(payload).encode()) + len(stage.encode()) + 512)
            self.store.check(len(encode(payload).encode()) * 2 + 8192)
            self.store.db.execute("INSERT INTO goal_events VALUES(?,?,?,?)", (goal_id, stage, self.store.now(), encode(payload)))
            self.check(goal_id)
            self.store.check()

    def reserve_request(self, goal_id):
        with self.store.transaction():
            row = self.check(goal_id)
            portfolio = self.store.portfolio()
            if row["requests"] >= row["spec"]["max_requests"] or portfolio["requests"] >= portfolio["policy"]["max_requests"]:
                raise BudgetError("Goal or portfolio request budget reached")
            if self.remaining_bytes(goal_id) <= 0:
                raise BudgetError("Goal or portfolio download budget reached")
            self.store.db.execute("UPDATE goals SET requests=requests+1 WHERE id=?", (goal_id,))
            self.store.db.execute("UPDATE portfolio SET requests=requests+1 WHERE id=1")

    def remaining_bytes(self, goal_id):
        row = self.check(goal_id)
        return min(row["spec"]["max_download_bytes"] - row["downloaded_bytes"], self.store.remaining_bytes())

    def charge_bytes(self, goal_id, count):
        # Record bytes already received, even if the deadline expired in the read.
        with self.store.transaction():
            row, portfolio = self.row(goal_id), self.store.portfolio()
            if count < 0 or count + row["downloaded_bytes"] > row["spec"]["max_download_bytes"] or count + portfolio["downloaded_bytes"] > portfolio["policy"]["max_download_bytes"]:
                raise BudgetError("Goal or portfolio download budget reached")
            self.store.db.execute("UPDATE goals SET downloaded_bytes=downloaded_bytes+? WHERE id=?", (count, goal_id))
            self.store.db.execute("UPDATE portfolio SET downloaded_bytes=downloaded_bytes+? WHERE id=1", (count,))
        self.check(goal_id)

    def reserve_inference(self, goal_id, tokens=RESERVED_TOKENS_PER_CALL):
        if type(tokens) is not int or tokens <= 0:
            raise RootError("Inference reservation must be a positive integer")
        with self.store.transaction():
            row = self.check(goal_id)
            total = self.store.db.execute("SELECT coalesce(sum(inference_reserved),0) FROM goals").fetchone()[0]
            if row["inference_reserved"] + tokens > row["spec"]["max_inference_tokens"] or total + tokens > self.store.portfolio()["policy"]["max_inference_tokens"]:
                raise BudgetError("Goal or portfolio local inference reservation reached")
            self.store.db.execute("UPDATE goals SET inference_reserved=inference_reserved+? WHERE id=?", (tokens, goal_id))

    def evidence(self, goal_id, url, body, mode):
        reference = digest([goal_id, url, mode, body])
        with self.store.transaction():
            self.check(goal_id, len(body.encode()) + len(url.encode()) + 512)
            self.store.check(len(body.encode()) * 2 + 8192)
            self.store.db.execute("INSERT OR IGNORE INTO repo_evidence VALUES(?,?,?,?,?,?)", (reference, goal_id, url, mode, self.store.now(), body))
            self.check(goal_id)
            self.store.check()
        return reference

    def view(self, goal_id):
        value = self.row(goal_id)
        value["events"] = [{"stage": row[0], "created": row[1], "payload": json.loads(row[2])}
                           for row in self.store.db.execute("SELECT stage,created,payload FROM goal_events WHERE goal_id=? ORDER BY created,rowid", (goal_id,))]
        value["evidence"] = [dict(row) for row in self.store.db.execute("SELECT id,url,mode,retrieved,length(body) AS characters FROM repo_evidence WHERE goal_id=?", (goal_id,))]
        value["components"] = [dict(row) for row in self.store.db.execute("SELECT id,name,revision,active FROM components WHERE goal_id=?", (goal_id,))]
        value["record_storage_bytes"] = self.payload_bytes(goal_id)
        return value

    def rollback(self, goal_id):
        with self.store.transaction():
            # Cleanup remains available after experimental deadlines expire.
            row = self.row(goal_id)
            result = row["result"]
            if not result or not result.get("component_id"):
                raise RootError("Goal has no adopted component to roll back")
            active = self.store.db.execute("SELECT id FROM components WHERE name=? AND active=1", (COMPONENT,)).fetchone()
            if not active or active[0] != result["component_id"]:
                raise RootError("This goal's component is not active; rollback would overwrite a later decision")
            self.store.db.execute("UPDATE components SET active=0 WHERE id=?", (active[0],))
            if result.get("previous_component_id"):
                self.store.db.execute("UPDATE components SET active=1 WHERE id=?", (result["previous_component_id"],))
            self.store.db.execute("UPDATE goals SET state='rolled_back' WHERE id=?", (goal_id,))
        return {"goal_id": goal_id, "state": "rolled_back", "restored_component_id": result.get("previous_component_id")}


class GitHub:
    def __init__(self, goals, goal_id, fixture=None, opener=None):
        self.goals, self.goal_id = goals, goal_id
        self.fixture = fixture
        self.mode = "fixture" if fixture is not None else "live"
        self.opener = opener or urllib.request.build_opener(NoRedirect()).open

    def get(self, url, fixture_key, json_body=False):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc not in ("api.github.com", "raw.githubusercontent.com") or parsed.fragment:
            raise RootError("Repository discovery is restricted to exact GitHub HTTPS hosts")
        if self.fixture is not None:
            value = self.fixture[fixture_key]
            body = encode(value) if json_body else value
        else:
            self.goals.store.ready("github")
            self.goals.reserve_request(self.goal_id)
            req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json" if json_body else "text/plain", "Accept-Encoding": "identity", "User-Agent": "ROOT-capability-goal/0.1"})
            deadline = self.goals.row(self.goal_id)["deadline"]
            try:
                with self.opener(req, timeout=max(0.01, min(10, deadline - self.goals.store.now()))) as response:
                    chunks = []
                    while True:
                        remaining = self.goals.remaining_bytes(self.goal_id)
                        if remaining <= 0:
                            raise BudgetError("Discovery byte budget exhausted; partial body discarded")
                        data = getattr(response, "read1", response.read)(min(65536, remaining))
                        if not data:
                            break
                        self.goals.charge_bytes(self.goal_id, len(data))
                        chunks.append(data)
                    body = b"".join(chunks).decode("utf-8")
            except urllib.error.HTTPError as exc:
                if exc.code in (403, 429):
                    delay = 300
                    reset = exc.headers.get("X-RateLimit-Reset", "")
                    retry = exc.headers.get("Retry-After", "")
                    if reset.isdigit() and len(reset) < 16:
                        delay = max(delay, int(reset) - self.goals.store.now())
                    if retry.isdigit() and len(retry) < 16:
                        delay = max(delay, int(retry))
                    self.goals.store.cooldown("github", delay)
                exc.close()
                raise RootError(f"GitHub returned HTTP {exc.code}; no automatic retry") from exc
            except (urllib.error.URLError, OSError, UnicodeError) as exc:
                raise RootError(f"GitHub retrieval failed: {exc}") from exc
        if not isinstance(body, str) or len(body.encode()) > 256 * 1024:
            raise RootError("Repository response exceeds per-document storage limit")
        self.goals.evidence(self.goal_id, url, body, self.mode)
        if json_body:
            value = json.loads(body)
            if not isinstance(value, dict):
                raise RootError("Expected a GitHub JSON object")
            return value
        return body

    def discover(self, query, fallback_query=None):
        candidates, searches = [], []
        supported = None
        for index, search_query in enumerate([query] + ([fallback_query] if fallback_query and fallback_query != query else []), 1):
            search_url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode({"q": search_query, "sort": "stars", "per_page": 5})
            search = self.get(search_url, "search" if index == 1 else "fallback_search", True)
            items = search.get("items", [])
            if not isinstance(items, list):
                raise RootError("Repository search returned malformed items")
            candidates.extend({"repository": item["full_name"], "description": item.get("description"), "stars": item.get("stargazers_count"), "license": (item.get("license") or {}).get("spdx_id")}
                              for item in items[:5])
            searches.append({"query": search_query, "returned": len(items), "url": search_url})
            self.goals.record(self.goal_id, f"repository_search_{index}", searches[-1])
            supported = next((item for item in candidates if item["repository"] == "urllib3/urllib3"), None)
            if supported:
                break
        if not supported:
            raise RootError("No discovered candidate matches the currently supported curated adapter")
        repo = self.get("https://api.github.com/repos/urllib3/urllib3", "repository", True)
        if (repo.get("license") or {}).get("spdx_id") != "MIT" or repo.get("archived") is True:
            raise RootError("Candidate requires a confirmed MIT license and maintained repository")
        branch = urllib.parse.quote(repo["default_branch"], safe="")
        commit = self.get(f"https://api.github.com/repos/urllib3/urllib3/commits/{branch}", "commit", True)
        revision = commit.get("sha", "")
        if not re.fullmatch(r"[a-f0-9]{40}", revision):
            raise RootError("Candidate needs an exact 40-character upstream revision")
        prefix = f"https://raw.githubusercontent.com/urllib3/urllib3/{revision}/"
        readme = self.get(prefix + "README.md", "readme")
        license_text = self.get(prefix + "LICENSE.txt", "license")
        if "Permission is hereby granted" not in license_text or "THE SOFTWARE IS PROVIDED" not in license_text:
            raise RootError("Retained license does not match the expected MIT grant")
        source = self.get(prefix + "src/urllib3/util/retry.py", "source")
        return {"candidates": candidates, "searches": searches, "selected_repository": "urllib3/urllib3", "revision": revision,
                "source_url": prefix + "src/urllib3/util/retry.py", "source": source, "license": license_text,
                "readme": readme, "mode": self.mode,
                "integration": "Restricted parser only; standard-library dependencies, zero package install; full HTTP client not adopted"}


def benchmark(source, baseline_source=None):
    output = {}
    for name in ("development", "holdout"):
        cases = read_json(PROJECT / f"examples/retry_after.{name}.json")
        baseline = []
        for case in cases:
            value = candidate_delay(baseline_source, case["header"], case["now"]) if baseline_source else 300
            baseline.append({"id": case["id"], "actual": value, "expected": case["expected"], "pass": value == case["expected"]})
        if source is None:
            candidate = []
        else:
            extract_parser(source)
            result = subprocess.run([sys.executable, "-I", "-S", str(PROJECT / "root_engine/evaluate_component.py")],
                                    input=encode({"source": source, "cases": cases}), capture_output=True, text=True, timeout=5,
                                    env={"PATH": "/usr/bin", "LANG": "C.UTF-8"})
            if result.returncode:
                raise RootError("Isolated candidate evaluation failed: " + result.stderr[-500:])
            candidate = json.loads(result.stdout)
        output[name] = {"baseline": baseline, "candidate": candidate,
                        "baseline_passes": sum(case["pass"] for case in baseline), "candidate_passes": sum(case["pass"] for case in candidate), "total": len(cases)}
    return output


def _research_case_pass(case, output):
    if case["expectation"] == "refuse":
        return isinstance(output, dict) and "refuse" in output
    # Grounding vs refusal is enforced by the packet validator; a proposal case needs a
    # non-refusal that matched the packet (validate_research_proposal already ran).
    return isinstance(output, dict) and "refuse" not in output


def _independent_component_pass(packet):
    """Independent component test: does the packet's pinned source actually help the named
    bottleneck? Grades the engine's retry benchmark with the candidate source; the model never
    sees this test and cannot game it."""
    source = packet.get("test_source")
    if not source:
        return False
    measured = benchmark(source, baseline_source=None)
    return all(data["candidate_passes"] == data["total"] and data["candidate_passes"] > data["baseline_passes"]
               for data in measured.values())


def _run_research_goal(goals, row):
    """Advisory research-role evaluation, packet-grounded. A collector supplies a pinned
    candidate packet (repository, revision, licence, README/source excerpts); the model proposes
    or refuses using only that packet; the validator checks URL/licence identity and output shape against the packet;
    an independent component test decides whether the candidate is actually useful. No repository
    download, no adoption. Evaluation is manifest-pinned at creation."""
    goal_id = row["id"]
    declared = row["spec"]["evaluation_manifest"]
    custom_files = row["spec"].get("evaluation_files")
    current = {}
    for name in ("development", "holdout"):
        filename = custom_files.get(name) if custom_files else "research_component." + name + ".json"
        current[name] = digest(read_json(PROJECT / "examples" / filename))
    if declared != current:
        raise RootError("Evaluation cases changed after goal creation; success cannot be redefined")
    model = Path(row["spec"].get("model_path", DEFAULT_MODEL)).resolve()
    # The plan was validated and pinned at creation (including any bounded generation-cap
    # override); model bytes is the resource-drift guard. Re-deriving with the default cap
    # would mismatch a pinned 1024-token control plan, so the pinned plan is authoritative.
    plan = row["spec"].get("inference_plan", research_inference_plan(model))
    if "model_path" in row["spec"] and model.stat().st_size != row["spec"]["model_bytes"]:
        raise RootError("Configured model resources changed after goal creation")
    all_cases = []
    subset_ids = row["spec"].get("research_case_ids")
    if subset_ids is not None and (not isinstance(subset_ids, list) or not subset_ids
                                   or any(not isinstance(x, str) or not x.strip() for x in subset_ids)
                                   or len(subset_ids) > 4):
        raise RootError("research_case_ids must be a nonempty list of at most 4 case ids")
    custom_files = row["spec"].get("evaluation_files")
    for name in ("development", "holdout"):
        filename = custom_files.get(name) if custom_files else f"research_component.{name}.json"
        path = PROJECT / "examples" / filename
        for case in read_json(path)["cases"]:
            if subset_ids is None or case["id"] in subset_ids:
                all_cases.append(dict(case, split=name))
    if subset_ids is not None and {c["id"] for c in all_cases} != set(subset_ids):
        raise RootError("research_case_ids references unknown cases")
    # Deterministic keyword prefilter first: abstained packets never reach the model and
    # reserve nothing. The prefilter is a cheap gate, NOT a capability test - it establishes
    # nothing about actual capability; the model review and independent benchmark still do.
    # Reserve only for cases that pass the prefilter (per-call tokens).
    results = []
    eligible_cases = []
    screened_reasons = {}
    for case in all_cases:
        screen = screen_packet(case["packet"])
        screened_reasons[case["id"]] = screen
        if screen["decision"] == "refuse":
            results.append({"case_id": case["id"], "split": case["split"], "expectation": case["expectation"],
                            "screen": screen, "output": None, "grounded": False, "independently_useful": False,
                            "case_pass": _research_case_pass(case, {"refuse": screen["reason"]}),
                            "elapsed_seconds": 0.0, "model_called": False})
        else:
            eligible_cases.append(case)
    per_call = plan["context"] + plan["generation"]
    eligible_total = len(eligible_cases) * per_call
    if eligible_total:
        goals.reserve_inference(goal_id, eligible_total)
    goals.record(goal_id, "inference_reservation", {"model_path": str(model), "model_bytes": model.stat().st_size,
                 "plan": plan, "calls": len(eligible_cases), "reserved_tokens": eligible_total,
                 "case_ids": subset_ids, "screened_refused": len(results),
                 "note": "deterministic keyword prefilter ran before any model call; abstained packets reserved nothing; prefilter establishes nothing about actual capability"})
    for case in eligible_cases:
        goals.check(goal_id)
        remaining_time = goals.row(goal_id)["deadline"] - goals.store.now()
        prompt_case = {"task": case["task"], "packet": case["packet"]}
        review = classify(prompt_case, model=model, plan=plan, timeout=remaining_time, prompt_kind="research")
        grounded = isinstance(review["output"], dict) and "refuse" not in review["output"]
        independent = _independent_component_pass(case["packet"]) if grounded else False
        case_pass = _research_case_pass(case, review["output"]) and (not grounded or independent)
        results.append({"case_id": case["id"], "split": case["split"], "expectation": case["expectation"],
                        "screen": screened_reasons[case["id"]], "output": review["output"], "grounded": grounded,
                        "independently_useful": independent, "case_pass": case_pass,
                        "elapsed_seconds": review["elapsed_seconds"], "model_called": True,
                        "raw_stdout_tail": review.get("raw_stdout_tail", review.get("runtime_log_tail", ""))[-500:],
                        "execution": review.get("execution", "")})
    goals.record(goal_id, "research_review", {"cases": results, "authority": "advisory only; no download, no adoption authorized"})
    passed = all(r["case_pass"] for r in results)
    result = {"evaluation": "pass" if passed else "fail",
              "evidence_scope": "packet URL/licence identity fidelity and output shape plus independent component usefulness; not market advantage or adoption",
              "cases_passed": sum(1 for r in results if r["case_pass"]), "cases_total": len(results)}
    goals.record(goal_id, "evaluation", result)
    goals.store.db.execute("UPDATE goals SET state='completed',result=? WHERE id=?", (encode(result), goal_id))

def run_goal(goals, goal_id, *, fixture=None, opener=None, local_review=False):
    row = goals.row(goal_id)
    if row["state"] in ("completed", "evaluated_fixture", "rolled_back", "stopped"):
        return goals.view(goal_id)
    if row["state"] != "created":
        raise RootError("An interrupted running goal is paused; create a separately budgeted goal instead of silently restarting it")
    goals.check(goal_id)
    with goals.store.collector_lease(seconds=row["deadline"] - goals.store.now() + 15):
        goals.store.db.execute("UPDATE goals SET state='running',mode=? WHERE id=?", ("fixture" if fixture is not None else "live", goal_id))
        try:
            declared_manifest = row["spec"].get("evaluation_manifest")
            if row["spec"]["adapter"] == "research_component_v1":
                _run_research_goal(goals, row)
                return goals.view(goal_id)
            current_manifest = {name: digest(read_json(PROJECT / f"examples/retry_after.{name}.json")) for name in ("development", "holdout")}
            if declared_manifest is not None and declared_manifest != current_manifest:
                raise RootError("Evaluation cases changed after goal creation; no discovery or adoption permitted")
            active = goals.store.db.execute("SELECT source FROM components WHERE name=? AND active=1", (COMPONENT,)).fetchone()
            baseline_source = active[0] if active else None
            initial = benchmark(None, baseline_source=baseline_source)
            goals.record(goal_id, "baseline", initial)
            if all(data["baseline_passes"] == data["total"] for data in initial.values()):
                result = {"evaluation": "already_satisfied", "adoption": "no_change", "measurements": initial}
                goals.store.db.execute("UPDATE goals SET state='completed',result=? WHERE id=?", (encode(result), goal_id))
                return goals.view(goal_id)
            if local_review:
                model = Path(row["spec"].get("model_path", DEFAULT_MODEL)).resolve()
                plan = inference_plan(model)
                if "model_path" in row["spec"] and (model.stat().st_size != row["spec"]["model_bytes"] or plan != row["spec"]["inference_plan"]):
                    raise RootError("Configured model resources changed after goal creation")
                # Reserve both controls atomically before discovery or model execution.
                # Reservations remain consumed on failure, independently of model output.
                goals.reserve_inference(goal_id, 2 * (plan["context"] + plan["generation"]))
                goals.record(goal_id, "inference_reservation", {"model_path": str(model), "model_bytes": model.stat().st_size,
                             "plan": plan, "calls": 2, "reserved_tokens": 2 * (plan["context"] + plan["generation"])})
            discovery = GitHub(goals, goal_id, fixture=fixture, opener=opener).discover(row["spec"]["search_query"], row["spec"].get("fallback_search_query"))
            goals.record(goal_id, "discovery", {key: value for key, value in discovery.items() if key not in ("source", "license", "readme")})
            if local_review:
                reviews = []
                selected = next(item for item in discovery["candidates"] if item["repository"] == "urllib3/urllib3")
                review_cases = [dict(selected, expected_fit=True),
                                {"repository": "synthetic-control/wallpaper-gallery", "description": "A wallpaper image gallery and visual theme collection; no HTTP client or retry component", "expected_fit": False}]
                for item in review_cases:
                    try:
                        goals.check(goal_id)
                        remaining_time = goals.row(goal_id)["deadline"] - goals.store.now()
                        review = classify(item.get("description"), model=model, plan=plan, timeout=remaining_time)
                        reviews.append({"repository": item["repository"], "review": review, "expected_fit": item["expected_fit"],
                                        "classification_pass": review["output"]["fit"] == item["expected_fit"]})
                    except RootError as exc:
                        reviews.append({"repository": item["repository"], "uncertain": str(exc)})
                goals.record(goal_id, "advisory_review", reviews)
            measured = benchmark(discovery["source"], baseline_source=baseline_source)
            passed = all(data["candidate_passes"] == data["total"] and data["candidate_passes"] > data["baseline_passes"] for data in measured.values())
            result = {"evaluation": "pass" if passed else "fail", "measurements": measured, "mode": discovery["mode"],
                      "adoption": "not_adopted", "upstream_revision": discovery["revision"], "source_url": discovery["source_url"],
                      "evidence_scope": "collector correctness on saved cases; not market advantage or revenue"}
            goals.record(goal_id, "evaluation", result)
            if passed and discovery["mode"] == "live":
                with goals.store.transaction():
                    goals.check(goal_id, len(discovery["source"].encode()) + len(discovery["license"].encode()) + len(encode(result).encode()) + 2048)
                    goals.store.check(len(discovery["source"].encode()) * 2 + len(discovery["license"].encode()) + 16384)
                    previous = goals.store.db.execute("SELECT id FROM components WHERE name=? AND active=1", (COMPONENT,)).fetchone()
                    component_id = digest([COMPONENT, discovery["revision"], discovery["source"]])
                    goals.store.db.execute("UPDATE components SET active=0 WHERE name=?", (COMPONENT,))
                    goals.store.db.execute("INSERT INTO components VALUES(?,?,?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET active=1",
                                           (component_id, COMPONENT, goal_id, discovery["revision"], discovery["source"], discovery["license"]))
                    result.update(adoption="enabled_restricted_adapter", component_id=component_id, previous_component_id=previous[0] if previous else None)
                    goals.store.check()
                    goals.store.db.execute("UPDATE goals SET state='completed',result=? WHERE id=?", (encode(result), goal_id))
            else:
                goals.store.db.execute("UPDATE goals SET state=?,result=? WHERE id=?", ("evaluated_fixture" if fixture is not None else "completed", encode(result), goal_id))
        except (RootError, OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.TimeoutExpired, SyntaxError) as exc:
            # A bounded terminal audit is kept even after a time/request gate stops work.
            result = {"evaluation": "uncertain", "adoption": "not_adopted", "error": str(exc)[:1000]}
            goals.store.db.execute("UPDATE goals SET state='stopped',result=? WHERE id=?", (encode(result), goal_id))
    return goals.view(goal_id)
