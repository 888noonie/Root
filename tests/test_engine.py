import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

from datetime import datetime, timezone

from root_engine.collector import Collector, ENDPOINT, SOURCE, read_json, search_url, validate_package, validate_url
from root_engine.goals import Goals, run_goal
from root_engine.local_models import inference_plan, classify
from root_engine.brief import (extract_requirements, generate_brief, hours_until, render_preview,
                               resolve_latest, score_release)
from root_engine.research import validate_research_output
from root_engine.screen import screen
from root_engine.store import BudgetError, DEFAULT_POLICY, digest, RootError, Store

from unittest import mock
from unittest.mock import patch as mpatch

PROJECT = Path(__file__).resolve().parents[1]
FIXTURE = PROJECT / "examples/contracts_finder.synthetic.json"

def read_text(p):
    return Path(p).read_text()


class Response(io.BytesIO):
    pass


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "root.db"
        self.clock = [1000.0]
        self.store = Store(self.path, create=True, objective="Test bounded discovery", now=lambda: self.clock[0])
        self.package = json.loads(FIXTURE.read_text())

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def reopen(self):
        self.store.close()
        self.store = Store(self.path, now=lambda: self.clock[0])

    def custom_store(self, **overrides):
        self.store.close()
        policy = dict(DEFAULT_POLICY, **overrides)
        self.path = Path(self.tmp.name) / "custom.db"
        self.store = Store(self.path, create=True, objective="Limited", policy=policy, now=lambda: self.clock[0])

    def fetcher(self, packages):
        responses = iter(packages)
        def open_response(req, timeout):
            return Response(json.dumps(next(responses)).encode())
        return Collector(self.store, opener=open_response)

    def candidate(self, evidence=None):
        value = json.loads((PROJECT / "examples/opportunity.json").read_text())
        value["distribution"]["within_policy"] = True
        value["costs"].update(owner_minutes_per_week=10, owner_capacity_minutes_per_week=30)
        value["evidence_refs"] = [] if evidence is None else [evidence]
        return value

    def test_offline_replay_preserves_provenance_and_no_duplicates(self):
        first = Collector(self.store).fixture(FIXTURE)
        self.reopen()
        second = Collector(self.store).fixture(FIXTURE)
        self.assertEqual(first["inserted"], 2)
        self.assertEqual(second["inserted"], 0)
        self.assertEqual(self.store.status()["counts"]["observations"], 2)
        raw = self.store.db.execute("SELECT payload,mode,source_url FROM packages").fetchone()
        self.assertEqual(json.loads(raw[0]), self.package)
        self.assertEqual(raw[1], "fixture")
        self.assertEqual(raw[2], ENDPOINT)
        self.assertEqual(self.store.portfolio()["requests"], 0)

    def test_changed_release_is_retained_as_a_new_version(self):
        self.store.save_package(self.package, ENDPOINT, "fixture")
        revised = copy.deepcopy(self.package)
        revised["releases"][0]["tender"]["title"] = "Changed test title"
        self.store.save_package(revised, ENDPOINT, "fixture")
        self.assertEqual(self.store.status()["counts"]["observations"], 3)

    def test_invalid_fixture_leaves_no_partial_import(self):
        self.package["releases"][1].pop("ocid")
        path = Path(self.tmp.name) / "broken.json"
        path.write_text(json.dumps(self.package))
        with self.assertRaises(RootError):
            Collector(self.store).fixture(path)
        self.assertEqual(self.store.status()["counts"]["observations"], 0)
        self.assertEqual(self.store.status()["counts"]["packages"], 0)

    def test_transaction_rolls_back_an_unexpected_import_failure(self):
        self.package["releases"][1].pop("ocid")
        with self.assertRaises(KeyError):
            self.store.save_package(self.package, ENDPOINT, "fixture")
        self.assertEqual(self.store.status()["counts"]["observations"], 0)
        self.assertEqual(self.store.status()["counts"]["packages"], 0)

    def test_403_cooldown_survives_restart_and_does_not_send_retry(self):
        calls = []
        def forbidden(req, timeout):
            calls.append(req.full_url)
            raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)
        with self.assertRaisesRegex(RootError, "five-minute"):
            Collector(self.store, forbidden).live(ENDPOINT)
        self.reopen()
        with self.assertRaisesRegex(RootError, "cooldown"):
            Collector(self.store, forbidden).live(ENDPOINT)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.store.portfolio()["requests"], 1)
        self.clock[0] += 301
        self.store.ready(SOURCE)

    def test_pagination_checkpoint_resumes_after_restart(self):
        next_url = ENDPOINT + "?cursor=next"
        self.package["links"] = {"next": next_url}
        result = self.fetcher([self.package]).live(ENDPOINT, max_pages=1)
        self.assertFalse(result["complete"])
        self.reopen()
        calls = []
        def page_two(req, timeout):
            calls.append(req.full_url)
            return Response(json.dumps({**self.package, "links": {}, "releases": []}).encode())
        result = Collector(self.store, page_two).live(ENDPOINT)
        self.assertEqual(calls, [next_url])
        self.assertTrue(result["complete"])
        self.assertEqual(Collector(self.store, page_two).live(ENDPOINT)["pages"], [])
        self.assertEqual(len(calls), 1)

    def test_unsafe_pagination_is_rejected_without_import(self):
        self.package["links"] = {"next": "https://evil.example/steal"}
        with self.assertRaises(RootError):
            self.fetcher([self.package]).live(ENDPOINT)
        self.assertEqual(self.store.status()["counts"]["packages"], 0)
        for url in ("http://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search", ENDPOINT + "#bad", "https://user:pass@www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search", ENDPOINT + "/extra"):
            with self.assertRaises(RootError):
                validate_url(url)

    def test_self_referencing_pagination_is_rejected(self):
        self.package["links"] = {"next": ENDPOINT}
        with self.assertRaisesRegex(RootError, "cycle"):
            self.fetcher([self.package]).live(ENDPOINT)
        self.assertEqual(self.store.status()["counts"]["packages"], 0)

    def test_request_cap_is_cumulative_across_restarts(self):
        self.custom_store(max_requests=1)
        self.fetcher([self.package]).live(ENDPOINT)
        self.reopen()
        with self.assertRaisesRegex(BudgetError, "Request"):
            self.fetcher([self.package]).live(ENDPOINT + "?cursor=other")
        self.assertEqual(self.store.portfolio()["requests"], 1)

    def test_download_cap_stops_reading_and_discards_partial_response(self):
        self.custom_store(max_download_bytes=20)
        response = Response(b"x" * 100)
        # BytesIO closes on exit; preserve its read count independently.
        read_bytes = []
        original_read = response.read
        def read(count):
            result = original_read(count)
            read_bytes.append(len(result))
            return result
        response.read = read
        response.read1 = read
        with self.assertRaises(BudgetError):
            Collector(self.store, lambda req, timeout: response).live(ENDPOINT)
        self.assertEqual(sum(read_bytes), 20)
        self.assertEqual(self.store.portfolio()["downloaded_bytes"], 20)
        self.assertEqual(self.store.status()["counts"]["packages"], 0)

    def test_storage_budget_rejects_large_payload_without_records(self):
        self.custom_store(max_storage_bytes=65536)
        candidate = self.candidate()
        candidate["large"] = "x" * 65536
        with self.assertRaisesRegex(BudgetError, "storage"):
            self.store.put_opportunity(candidate)
        self.assertEqual(self.store.status()["counts"]["opportunities"], 0)

    def test_deadline_stops_mutations_but_status_remains_available(self):
        self.clock[0] = self.store.portfolio()["deadline"]
        with self.assertRaisesRegex(BudgetError, "deadline"):
            Collector(self.store).fixture(FIXTURE)
        with self.assertRaises(BudgetError):
            self.store.put_opportunity(self.candidate())
        self.assertEqual(self.store.status()["budget_state"], "expired")

    def test_only_one_collector_and_recovery_of_expired_lease(self):
        with self.store.collector_lease():
            with self.assertRaisesRegex(RootError, "already running"):
                Collector(self.store).fixture(FIXTURE)
        self.store.db.execute("INSERT INTO lease VALUES(1,?,?)", (self.clock[0] + 60, "crashed"))
        with self.assertRaises(RootError):
            Collector(self.store).fixture(FIXTURE)
        self.clock[0] += 61
        self.assertEqual(Collector(self.store).fixture(FIXTURE)["inserted"], 2)

    def test_bytes_are_recorded_if_deadline_expires_during_a_read(self):
        class ExpiringResponse(Response):
            def read1(inner, count):
                self.clock[0] = self.store.portfolio()["deadline"]
                return super(ExpiringResponse, inner).read(count)
        response = ExpiringResponse(b"some bytes")
        with self.assertRaises(BudgetError):
            Collector(self.store, lambda req, timeout: response).live(ENDPOINT)
        self.assertEqual(self.store.portfolio()["downloaded_bytes"], 10)
        self.assertEqual(self.store.status()["counts"]["observations"], 0)

    def test_fixture_and_missing_evidence_cannot_qualify(self):
        Collector(self.store).fixture(FIXTURE)
        ref = self.store.db.execute("SELECT id FROM observations LIMIT 1").fetchone()[0]
        value = self.candidate(ref)
        value["claims"] = [{"text": "People will pay", "status": "observed", "observation_id": ref}]
        result = screen(self.store, value)
        self.assertEqual(result["decision"], "gather_evidence")
        codes = {r["code"] for r in result["reasons"]}
        self.assertIn("external_evidence", codes)
        self.assertIn("unsupported_observed_claim", codes)
        self.assertEqual(result["evidence"][0]["mode"], "fixture")

    def test_mock_live_evidence_only_qualifies_for_research(self):
        self.fetcher([self.package]).live(ENDPOINT)
        ref = self.store.db.execute("SELECT id FROM observations LIMIT 1").fetchone()[0]
        candidate = self.candidate(ref)
        result = screen(self.store, candidate)
        self.assertEqual(result["decision"], "eligible_for_review")
        self.assertIn("no demand", result["qualification_scope"])
        self.assertEqual(result["revision"], self.store.db.execute("SELECT revision FROM screens").fetchone()[0])

    def test_distribution_autonomy_and_external_experiment_required(self):
        candidate = self.candidate()
        candidate["distribution"].pop("owner_steps")
        candidate["distribution"].pop("autonomy")
        candidate["experiment"].pop("external_evidence_method")
        result = screen(self.store, candidate)
        codes = {r["code"] for r in result["reasons"]}
        self.assertIn("distribution_autonomy", codes)
        self.assertIn("experiment_external_evidence_method", codes)

    def test_workload_and_money_over_budget_are_rejected(self):
        candidate = self.candidate()
        candidate["costs"]["owner_minutes_per_week"] = 31
        candidate["experiment"]["max_money_gbp"] = 1
        result = screen(self.store, candidate)
        self.assertEqual(result["decision"], "reject")
        self.assertIn("owner_capacity", {r["code"] for r in result["reasons"]})

    def test_zero_is_preserved_and_unknown_is_not_replaced(self):
        Collector(self.store).fixture(FIXTURE)
        values = [json.loads(row[0]) for row in self.store.db.execute("SELECT payload FROM observations ORDER BY release_id")]
        self.assertEqual(values[0]["tender"]["value"]["amount"], 0)
        self.assertNotIn("value", values[1]["tender"])

    def test_reinitialization_never_overwrites_data(self):
        with self.assertRaisesRegex(RootError, "already exists"):
            Store(self.path, create=True, objective="Overwrite")
        self.assertEqual(self.store.portfolio()["objective"], "Test bounded discovery")

    def test_policy_cannot_enable_spending(self):
        with self.assertRaises(RootError):
            Store(Path(self.tmp.name) / "money", create=True, objective="Unsafe", policy=dict(DEFAULT_POLICY, max_money_gbp=1))

    def test_url_bounds_and_limit(self):
        url = search_url("2026-09-14T00:00:00Z", "2026-09-14T23:59:59Z", 1)
        self.assertTrue(url.startswith(ENDPOINT + "?"))
        self.assertIn("stages=tender", url)
        with self.assertRaises(RootError):
            search_url("2026-09-15", "2026-09-14")
        with self.assertRaises(RootError):
            search_url("2026-09-14", "2026-09-15", 101)

    def test_cli_end_to_end_offline(self):
        path = str(Path(self.tmp.name) / "cli.sqlite3")
        def cli(*args):
            run = subprocess.run([sys.executable, "-m", "root_engine", "--db", path, *args], cwd=PROJECT, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            return json.loads(run.stdout)
        cli("init", "--objective", "A bounded offline demonstration")
        cli("collect", "--fixture", str(FIXTURE))
        cli("opportunity-add", "--file", str(PROJECT / "examples/opportunity.json"))
        self.assertEqual(cli("screen")[0]["decision"], "gather_evidence")
        self.assertEqual(cli("collect", "--fixture", str(FIXTURE))["inserted"], 0)
        self.assertEqual(cli("status")["counts"]["observations"], 2)


class InferencePlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.qwen = Path(self.temp.name) / "small.gguf"
        self.gemma = Path(self.temp.name) / "mid.gguf"
        self.binary = Path(self.temp.name) / "llama-cli"
        self.binary.write_text("not executed: subprocess is mocked")
        self.qwen.write_bytes(b"placeholder")
        with self.gemma.open("wb") as handle:
            handle.truncate(600 * 1024 * 1024)

    def test_sub_512mib_model_uses_baseline_plan(self):
        plan = inference_plan(self.qwen)
        self.assertEqual(plan["class"], "sub-512MiB")
        self.assertEqual(plan["context"], 1024)
        self.assertEqual(plan["generation"], 128)
        self.assertEqual(plan["address_space_bytes"], 2 * 1024 ** 3)
        self.assertEqual(plan["timeout_seconds"], 90)

    def test_mid_model_scales_address_space_for_mmap(self):
        plan = inference_plan(self.gemma)
        self.assertEqual(plan["class"], "mid")
        self.assertGreaterEqual(plan["address_space_bytes"], self.gemma.stat().st_size)
        self.assertGreater(plan["context"], 1024)
        self.assertGreater(plan["generation"], 128)
        self.assertGreater(plan["timeout_seconds"], 90)

    def test_unplanned_size_is_refused_without_loading(self):
        with tempfile.NamedTemporaryFile(suffix=".gguf") as tmp:
            tmp.truncate(8 * 1024 ** 3 + 1)
            with self.assertRaisesRegex(RootError, "No bounded inference plan"):
                inference_plan(tmp.name)

    def test_classify_clamps_caller_timeout_to_plan(self):
        with mpatch("root_engine.local_models.subprocess.Popen") as popen:
            proc = mock.Mock()
            proc.communicate.return_value = ('{"fit": true, "reason": "parses retry headers"}', "")
            proc.returncode = 0
            proc.pid = 12345
            popen.return_value = proc
            with mpatch("root_engine.local_models.os.killpg"):
                result = classify("urllib3 retry module", binary=self.binary, model=self.gemma, timeout=9999)
        self.assertEqual(result["output"], {"fit": True, "reason": "parses retry headers"})
        self.assertEqual(result["reserved_tokens"], 2240)
        self.assertIn("context 2048", result["execution"])
        args, kwargs = popen.call_args
        command = args[0]
        self.assertIn(str(self.gemma), command)
        self.assertIn("2048", command)
        self.assertNotIn("--json-schema", command)  # grammar sampler broken at build 10182; strict post-hoc validator enforces schema
        self.assertEqual(kwargs["env"].get("CUDA_VISIBLE_DEVICES"), "-1")
        proc.communicate.assert_called_once_with(timeout=480)

    def test_caller_cannot_override_bounded_plan(self):
        plan = dict(inference_plan(self.qwen), generation=100000)
        with mpatch("root_engine.local_models.subprocess.Popen") as popen:
            with self.assertRaisesRegex(RootError, "does not match"):
                classify("retry", binary=self.binary, model=self.qwen, plan=plan)
        popen.assert_not_called()

    def test_classify_rejects_output_that_fails_strict_schema(self):
        with mpatch("root_engine.local_models.subprocess.Popen") as popen:
            proc = mock.Mock()
            proc.communicate.return_value = ('{"fit": "yes", "extra": 1}', "llama load ok")
            proc.returncode = 0
            proc.pid = 12345
            popen.return_value = proc
            with mpatch("root_engine.local_models.os.killpg"):
                with self.assertRaisesRegex(RootError, "did not validate"):
                    classify("something", binary=self.binary, model=self.qwen, timeout=5)

    def test_classify_accepts_pinned_research_plan_with_1024_cap(self):
        from root_engine.local_models import research_inference_plan
        pinned = research_inference_plan(self.gemma, generation_cap=1024)
        with mpatch("root_engine.local_models.subprocess.Popen") as popen:
            proc = mock.Mock()
            proc.communicate.return_value = ('{"pinned_source_url": "https://github.com/urllib3/urllib3", '
                                            '"license_spdx": "MIT", "integration_proposal": "restricted adapter", '
                                            '"measurable_benefit": "gain", "rejection_conditions": "fail"}', "")
            proc.returncode = 0
            proc.pid = 12345
            popen.return_value = proc
            with mpatch("root_engine.local_models.os.killpg"):
                case = {"task": "test", "packet": {"repository": "https://github.com/urllib3/urllib3",
                        "revision": "abc", "license_spdx": "MIT", "readme_excerpt": "r", "source_excerpt": "s"}}
                result = classify(case, binary=self.binary, model=self.gemma, plan=pinned, prompt_kind="research")
        self.assertEqual(result["reserved_tokens"], 2048 + 1024)


class ResearchRoleBenchmarkTests(unittest.TestCase):
    """research_component_v1: an advisory research role returns a structured component proposal
    (pinned source, license, integration proposal, measurable benefit, rejection conditions).
    The proposing model must refuse task-mismatched cases instead of fabricating evidence.
    No repository download or adoption occurs; the artifact is advisory only.
    Grading is packet fidelity, not recall: every cited field must match the collector-supplied
    candidate packet, and an independent component test decides actual usefulness."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(str(Path(self.tmp.name) / "r.sqlite3"), create=True, objective="research benchmark test",
                           policy=read_json(PROJECT / "examples/research-benchmark-policy.json"))
        self.addCleanup(self.store.close)
        self.goals = Goals(self.store)

    def _goal_spec(self, **overrides):
        spec = json.loads(read_text(PROJECT / "examples/research_component_goal.json"))
        spec.update(overrides)
        return spec

    def test_validate_research_proposal_grounds_cited_fields(self):
        from root_engine.research import validate_research_proposal
        packet = {
            "repository": "https://github.com/psf/requests",
            "revision": "abc123",
            "license_spdx": "Apache-2.0",
        }
        proposal = {
            "pinned_source_url": "https://github.com/psf/requests",
            "license_spdx": "Apache-2.0",
            "integration_proposal": "Evaluate behind a restricted adapter; revision abc123.",
            "measurable_benefit": "x",
            "rejection_conditions": "x",
        }
        validate_research_proposal(proposal, packet)  # must not raise
        for field in ("pinned_source_url", "license_spdx"):
            bad = dict(proposal)
            bad[field] = "https://github.com/evil/repo" if field == "pinned_source_url" else "GPL-3.0"
            with self.assertRaises(RootError, msg=field):
                validate_research_proposal(bad, packet)
        # A guessed-but-different URL must not pass even if it is a valid repository URL.
        guessed = dict(proposal, pinned_source_url="https://github.com/urllib3/urllib3")
        with self.assertRaises(RootError):
            validate_research_proposal(guessed, packet)

    def test_validate_research_output_accepts_exact_proposal_shape(self):
        proposal = {
            "pinned_source_url": "https://github.com/psf/requests",
            "license_spdx": "Apache-2.0",
            "integration_proposal": "Wrap its session retry adapter behind the existing request boundary; no package install.",
            "measurable_benefit": "Removes hand-rolled retry logic; expected gain measured on the declared evaluation set.",
            "rejection_conditions": "Reject if the URL is not an exact pinned repository or evaluation does not improve on baseline.",
        }
        validate_research_output(proposal)  # must not raise
        for key in list(proposal):
            mutated = dict(proposal)
            mutated[key + "_extra"] = "unexpected"
            with self.assertRaises(RootError):
                validate_research_output(mutated)
            break
        for key in proposal:
            mutated = dict(proposal)
            mutated[key] = ""
            with self.assertRaises(RootError, msg=key):
                validate_research_output(mutated)

    def test_validate_research_output_accepts_refusal(self):
        validate_research_output({"refuse": "Task is out of scope; no reliable component identified."})

    def test_validate_research_output_rejects_bad_pins(self):
        base = {
            "pinned_source_url": "https://evil.example.com/repo",
            "license_spdx": "MIT",
            "integration_proposal": "x",
            "measurable_benefit": "x",
            "rejection_conditions": "x",
        }
        with self.assertRaises(RootError):
            validate_research_output(base)
        with self.assertRaises(RootError):
            validate_research_output({"fit": True, "reason": "old schema shape must not pass"})

    def test_research_goal_creation_requires_research_eval_manifest(self):
        goals = self.goals
        spec = self._goal_spec()
        row = goals.create(spec)
        self.assertEqual(row["spec"]["adapter"], "research_component_v1")
        manifest = row["spec"]["evaluation_manifest"]
        self.assertEqual(set(manifest), {"development", "holdout"})
        self.assertNotEqual(manifest["development"], digest(read_json(PROJECT / "examples/retry_after.development.json")))

    def test_run_research_goal_with_mocked_model_marks_cases(self):
        goals = self.goals
        goals.create(self._goal_spec())

        all_cases = []
        for split in ("development", "holdout"):
            all_cases += read_json(PROJECT / f"examples/research_component.{split}.json")["cases"]

        def fake_classify(description, **kwargs):
            match = next(c for c in all_cases if description["task"] == c["task"] and description["packet"]["repository"] == c["packet"]["repository"])
            if match["expectation"] == "refuse":
                return {"output": {"refuse": "Packet component does not fit the task; declining to propose."}, "elapsed_seconds": 0.1, "execution": "mock"}
            packet = match["packet"]
            return {"output": {
                "pinned_source_url": packet["repository"],
                "license_spdx": packet["license_spdx"],
                "integration_proposal": "Evaluate behind a restricted adapter, no package install; revision " + packet["revision"][:8] + ".",
                "measurable_benefit": "Correct Retry-After handling for the collector.",
                "rejection_conditions": "Reject if evaluation does not beat the baseline."}, "elapsed_seconds": 0.1, "execution": "mock"}

        with mpatch("root_engine.goals.classify", side_effect=fake_classify), mpatch("root_engine.research.classify", side_effect=fake_classify, create=True):
            result = run_goal(goals, "research-retry-component", fixture=None, local_review=True)
        view = goals.view("research-retry-component")
        if view["result"]["evaluation"] != "pass":
            self.fail("research goal not completed: " + json.dumps(view["result"], indent=1)[:800])
        research = [e for e in view["events"] if e["stage"] == "research_review"][0]["payload"]
        self.assertTrue(all(c["case_pass"] for c in research["cases"]))
        for case in research["cases"]:
            if case["expectation"] == "propose":
                self.assertTrue(case["grounded"], case["case_id"])
            else:
                self.assertFalse(case["grounded"], case["case_id"])
        self.assertEqual(view["result"]["evaluation"], "pass")

    def test_research_plan_has_512_generation_cap_by_default(self):
        from root_engine.local_models import research_inference_plan
        plan = research_inference_plan(self._qwen_path())
        self.assertEqual(plan["generation"], 512)
        self.assertEqual(plan["class"], "research-512-sub-512MiB")

    def test_prefilter_does_not_refuse_domain_words_when_capability_present(self):
        """A desktop/image/wallpaper component with real retry evidence must NOT be refused."""
        from root_engine.screen import screen_packet
        decision = screen_packet({"readme_excerpt": "Desktop wallpaper slideshow; bundled HTTP client does exponential backoff with Retry-After parsing.",
                                  "source_excerpt": "def download(url): ... # exponential backoff on 429"})
        self.assertEqual(decision["decision"], "eligible")
        self.assertEqual(decision["confidence"], "low")
        self.assertIn("nothing about actual capability", decision["establishes"])

    def test_prefilter_abstains_without_retry_signals_and_says_why(self):
        from root_engine.screen import screen_packet
        decision = screen_packet({"readme_excerpt": "A picker for emoji glyphs.", "source_excerpt": "def pick(s): ..."})
        self.assertEqual(decision["decision"], "refuse")
        self.assertEqual(decision["confidence"], "none")
        self.assertIn("prefilter abstention only", decision["reason"])
        self.assertIn("may implement backoff without naming it", decision["reason"])

    def test_prefilter_confusion_matrix_is_exact_and_separates_error_types(self):
        """The matrix must be published as counts per error type, with the challenge set separate."""
        import json as _json
        from root_engine.screen import measure_prefilter
        corpus = _json.loads(read_text(PROJECT / "examples/prefilter_corpus.json"))
        summary = measure_prefilter(corpus["cases"])
        m = summary["confusion"]
        # Proceed-on-eligible (urllib3, requests, desktop-app, image-tool) = 4 true positives.
        self.assertEqual(sorted(m["tp"]), ["legit-desktop-app-with-retry-client", "legit-image-tool-with-retry",
                                           "legit-requests-retry", "legit-urllib3-retry"])
        # Abstain-on-mismatch (wallpaper, voice-clone, sms-gateway, csv-parser) = 4 true negatives.
        self.assertEqual(sorted(m["tn"]), ["mismatch-csv-parser", "mismatch-sms-gateway",
                                           "mismatch-voice-clone", "mismatch-wallpaper"])
        # One legitimate component genuinely refused: it implements backoff without naming it.
        # This is the dangerous error and it is reported, not hidden.
        self.assertEqual(m["fn"], ["legit-retry-capable-but-unnamed-in-excerpts"])
        self.assertEqual(m["fp"], [], "no mismatch in the main matrix mentions retry")
        self.assertEqual(summary["legitimate_total"], 5)
        self.assertEqual(summary["mismatch_total"], 4)
        self.assertAlmostEqual(summary["legitimate_refusal_rate"], 1 / 5)
        self.assertAlmostEqual(summary["mismatch_proceed_rate"], 0.0)
        # the hard negative lives in its own set and is NOT used to flatter any rate
        self.assertEqual(summary["challenge_set"], {"total": 1, "proceeded": 1})
        self.assertIn("truth x prediction", summary["truth_definition"])
        self.assertIn("separate counts per error type", summary["reported_as"])

    def test_prefilter_http_word_alone_is_not_a_capability_signal(self):
        from root_engine.screen import screen_packet
        decision = screen_packet({"readme_excerpt": "A tiny HTTP request helper.", "source_excerpt": "def get(url): ..."})
        self.assertEqual(decision["decision"], "refuse")
        self.assertEqual(decision["signals_found"], [])

    def test_screen_refuses_before_model_and_passes_refuse_case(self):
        goals = self.goals
        specs = json.loads(read_text(PROJECT / "examples/research_component.goal_screens.json"))
        # The fixture's model_path is machine-local. Supply any existing local file so the suite
        # stays runnable without any particular model: the runner only stats it (byte size pin)
        # and this case never reaches inference because the prefilter abstains first.
        specs["goal"]["model_path"] = str(PROJECT / "README.md")
        goals.create(specs["goal"])
        calls = {"n": 0}
        def fake_classify(description, **kwargs):
            calls["n"] += 1
            raise AssertionError("classify must not run for screened-refuse packet")
        with mpatch("root_engine.goals.classify", side_effect=fake_classify), \
             mpatch("root_engine.research.classify", side_effect=fake_classify, create=True):
            result = run_goal(goals, specs["goal"]["id"], fixture=None, local_review=True)
        view = goals.view(specs["goal"]["id"])
        self.assertEqual(calls["n"], 0, "screened-refuse packet must never reach the model")
        self.assertEqual(view["result"]["evaluation"], "pass")
        research = [e for e in view["events"] if e["stage"] == "research_review"][0]["payload"]
        self.assertTrue(all(c["case_pass"] for c in research["cases"]))
        self.assertTrue(all(c["screen"]["decision"] == "refuse" for c in research["cases"]))

    def test_single_case_research_goal_reserves_one_case_and_stops(self):
        goals = self.goals
        spec = self._goal_spec(id="gemma-control-1024",
                               model_path=str(Path(self.tmp.name) / "mid.gguf"),
                               research_generation_cap=1024,
                               research_case_ids=["urllib3-retry"],
                               max_inference_tokens=3072,
                               max_elapsed_seconds=180)
        (Path(self.tmp.name) / "mid.gguf").write_bytes(b"x")
        with open(Path(self.tmp.name) / "mid.gguf", "wb") as h:
            h.truncate(600 * 1024 * 1024)
        goals.create(spec)
        row = goals.row("gemma-control-1024")
        self.assertEqual(row["spec"]["inference_plan"]["generation"], 1024)

        calls = {"n": 0}
        def fake_classify(description, **kwargs):
            calls["n"] += 1
            assert description["task"] == "ROOT's collector must respect HTTP Retry-After cooldowns from GitHub and Contracts Finder."
            return {"output": {"pinned_source_url": "https://github.com/urllib3/urllib3", "license_spdx": "MIT",
                               "integration_proposal": "Evaluate behind a restricted adapter, no package install.",
                               "measurable_benefit": "Correct Retry-After handling.",
                               "rejection_conditions": "Reject if evaluation does not beat baseline."},
                    "elapsed_seconds": 0.1, "execution": "mock"}
        with mpatch("root_engine.goals.classify", side_effect=fake_classify),              mpatch("root_engine.research.classify", side_effect=fake_classify, create=True):
            run_goal(goals, "gemma-control-1024", fixture=None, local_review=True)
        view = goals.view("gemma-control-1024")
        self.assertEqual(calls["n"], 1, "single-case goal must stop after one case")
        research = [e for e in view["events"] if e["stage"] == "research_review"][0]["payload"]
        self.assertEqual(len(research["cases"]), 1)
        self.assertTrue(research["cases"][0]["case_pass"])
        self.assertTrue(research["cases"][0]["grounded"])
        self.assertTrue(research["cases"][0]["independently_useful"])
        self.assertEqual(view["inference_reserved"], 3072)
        self.assertEqual(view["result"]["evaluation"], "pass")
        self.assertEqual(view["result"]["cases_total"], 1)

    def _qwen_path(self):
        p = Path(self.tmp.name) / "qwen.gguf"
        p.write_bytes(b"placeholder")
        return p



class BriefGenerationTests(unittest.TestCase):
    """Phase 2: deterministic tender-intelligence brief for a narrowly defined buyer."""

    def setUp(self):
        self.now = datetime(2026, 9, 16, 12, 0, 0, tzinfo=timezone.utc)

    def _taxi_release(self, **overrides):
        release = {
            "ocid": "ocds-b5fd17-3cba68f1-test",
            "initiationType": "tender",
            "buyer": {"name": "East Sussex County Council"},
            "tender": {
                "title": "Taxi and MPV (1-8 seats) Passenger Assistant",
                "description": ("MVP Vehicle required\r\nVehicle type: 6 seat MPV  \r\nPassenger Assistant Required:  yes \r\n\r\n"
                                "Proposed Taxi Route:\r\nFrom:  TN39 5AR\r\nTo:   Torfield School, TN34 3JT\r\n\r\n"
                                "Frequency: Monday to Friday \r\nDaily School Time: 09:00-15:15\r\n\r\n"
                                "Comments for Operator:  \r\nASD\r\nNonverbal\r\nHearing Impairment \r\nHarness Required \r\nSpace Needed \r\n"
                                " This opportunity has been distributed on SProc.net"),
                "classification": {"id": "60000000", "description": "Transport services (excl. Waste transport)"},
                "suitability": {"sme": True},
                "tenderPeriod": {"endDate": "2026-09-17T10:00:00+01:00"},
                "datePublished": "2026-09-14T19:03:37+01:00",
                "status": "active",
                "documents": [{"documentType": "tenderNotice", "url": "https://www.contractsfinder.service.gov.uk/Notice/test123"}],
            },
        }
        release["tender"].update(overrides.pop("tender", {}))
        release.update(overrides)
        return release

    def test_score_release_transport_buyer_sme_soon_relevant(self):
        result = score_release(self._taxi_release(), now=self.now)
        self.assertTrue(result["relevant"])
        self.assertGreaterEqual(result["score"], 40)
        self.assertTrue(any("CPV" in r for r in result["reasons"]))
        self.assertTrue(any("buyer" in r for r in result["reasons"]))

    def test_score_release_irrelevant_buyer_scores_low(self):
        release = self._taxi_release()
        release["buyer"] = {"name": "Ministry of Defence"}
        result = score_release(release, now=self.now)
        self.assertFalse(result["relevant"])
        self.assertLess(result["score"], 40)

    def test_score_release_passed_deadline_not_relevant(self):
        release = self._taxi_release()
        release["tender"]["tenderPeriod"] = {"endDate": "2026-09-10T10:00:00+01:00"}
        self.assertFalse(score_release(release, now=self.now)["relevant"])

    def test_score_release_non_active_status_zero(self):
        release = self._taxi_release()
        release["tender"]["status"] = "cancelled"
        self.assertFalse(score_release(release, now=self.now)["relevant"])

    def test_resolve_latest_uses_newest_release_not_first_seen(self):
        old = self._taxi_release(ocid="ocds-x", tender={"tenderPeriod": {"endDate": "2026-09-16T12:00:00+01:00"}})
        new = self._taxi_release(ocid="ocds-x", tender={"tenderPeriod": {"endDate": "2026-09-18T10:00:00+01:00"}})
        old["date"] = "2026-09-14T10:00:00+01:00"
        new["date"] = "2026-09-15T10:00:00+01:00"
        resolved = resolve_latest([("ocds-x", "2026-09-14T10:00:00+01:00", json.dumps(old)),
                                   ("ocds-x", "2026-09-15T10:00:00+01:00", json.dumps(new))])
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]["payload"]["tender"]["tenderPeriod"]["endDate"], "2026-09-18T10:00:00+01:00")
        self.assertEqual(resolved[0]["superseded"], 1)

    def test_resolve_latest_uses_latest_even_when_seen_first(self):
        """Feed the newest release FIRST: resolution must still pick the latest by date."""
        old = self._taxi_release(ocid="ocds-w", tender={"tenderPeriod": {"endDate": "2026-09-16T12:00:00+01:00"}})
        new = self._taxi_release(ocid="ocds-w", tender={"tenderPeriod": {"endDate": "2026-09-18T10:00:00+01:00"}})
        old["date"] = "2026-09-14T10:00:00+01:00"
        new["date"] = "2026-09-15T10:00:00+01:00"
        resolved = resolve_latest([("ocds-w", "2026-09-15T10:00:00+01:00", json.dumps(new)),
                                   ("ocds-w", "2026-09-14T10:00:00+01:00", json.dumps(old))])
        self.assertEqual(resolved[0]["payload"]["tender"]["tenderPeriod"]["endDate"], "2026-09-18T10:00:00+01:00")

    def test_resolve_latest_reports_cancellation_instead_of_stale_deadline(self):
        first = self._taxi_release(ocid="ocds-y")
        first["date"] = "2026-09-14T10:00:00+01:00"
        cancelled = self._taxi_release(ocid="ocds-y", tender={"status": "cancelled"})
        cancelled["date"] = "2026-09-15T10:00:00+01:00"
        brief = generate_brief([("ocds-y", "2026-09-14T10:00:00+01:00", json.dumps(first)),
                                ("ocds-y", "2026-09-15T10:00:00+01:00", json.dumps(cancelled))], now=self.now)
        self.assertEqual(brief["relevant_count"], 0)
        self.assertEqual(len(brief["excluded"]), 1)
        self.assertIn("cancelled", brief["excluded"][0]["reason"])

    def test_expiry_is_precise_hours_not_coarse_window(self):
        release = self._taxi_release(tender={"tenderPeriod": {"endDate": "2026-09-16T21:00:00+01:00"}})
        result = score_release(release, now=self.now)
        self.assertEqual(result["urgency"], "expires_within_48h")
        self.assertAlmostEqual(result["hours_remaining"], 8.0, places=3)
        self.assertIn("8.0h remaining", " ".join(result["reasons"]))

    def test_publisher_sme_flag_does_not_change_score(self):
        flagged = self._taxi_release(tender={"suitability": {"sme": True}})
        unflagged = self._taxi_release(tender={"suitability": {"sme": False}})
        a = score_release(flagged, now=self.now)
        b = score_release(unflagged, now=self.now)
        self.assertEqual(a["score"], b["score"], "SME publisher flag must not affect the score")
        self.assertEqual(a["publisher_flags"]["sme_declared_by_publisher"], True)
        self.assertIn("does not establish", a["publisher_flags"]["sme_note"])

    def test_extract_requirements_pulls_route_vehicle_pa_and_registration(self):
        req = extract_requirements(self._taxi_release())
        self.assertEqual(req["route"]["from_postcode"], "TN39 5AR")
        self.assertEqual(req["route"]["to_postcode"], "TN34 3JT")
        self.assertEqual(req["vehicle"]["seats"], 6)
        self.assertEqual(req["passenger_assistant"]["requirement"], "required")
        self.assertIn("harness", req["operator_flags"])
        self.assertIn("SProc.net", req["supplier_registration_requirement"])
        self.assertTrue(req["missing"], "missing information must be enumerated")
        self.assertIn("estimated contract value", req["missing"])
        self.assertIn("insurance, vehicle licence and safeguarding/DBS requirements", req["missing"])

    def test_extract_requirements_marks_conditional_pa_and_unknowns(self):
        release = self._taxi_release()
        release["tender"]["description"] = ("Vehicle type: Saloon\r\nPassenger Assistant Required: PA required if travelling alone.\r\n"
                                            "Proposed Taxi Route: \r\nFrom: TN7 4JA\r\nTo:  Priory School, BN7 2XN")
        req = extract_requirements(release)
        self.assertEqual(req["passenger_assistant"]["requirement"], "conditional (as stated in the notice)")
        self.assertEqual(req["route"]["from_postcode"], "TN7 4JA")
        self.assertEqual(req["route"]["venue"], "Priory School")
        self.assertTrue(any("collection/delivery addresses" in m for m in req["missing"]),
                        "the address gap must be flagged even when postcodes are stated")

    def test_seat_count_never_read_from_title_band(self):
        """'1-8 seats' in the title is a framework band, not this route's vehicle."""
        req = extract_requirements(self._taxi_release(tender={"title": "Taxi and MPV (1-8 seats) Passenger Assistant",
                                                              "description": "Vehicle type: Saloon\r\nPassenger Assistant Required: No"}))
        self.assertIsNone(req["vehicle"]["seats"], "must not read 8 from the title band '1-8 seats'")
        self.assertIn("1-8 seats", req["vehicle"]["seat_band"])

    def test_preview_render_states_what_is_unknown_and_what_expires(self):
        brief = generate_brief([("ocds-z", "2026-09-15T16:33:38+01:00",
                                 json.dumps(self._taxi_release(ocid="ocds-z", tender={"tenderPeriod": {"endDate": "2026-09-17T10:00:00+01:00"}})))],
                               now=self.now)
        text = render_preview(brief)
        self.assertIn("Still unknown", text)
        self.assertIn("Expires:", text)
        self.assertNotIn("48-72", text)
        self.assertIn("not distributed", text)
        self.assertIn("h remaining", text)

    def test_expired_notices_excluded_from_current_preview(self):
        """An expired opportunity must not appear as actionable, and must be reported separately."""
        live = self._taxi_release(ocid="ocds-live", tender={"tenderPeriod": {"endDate": "2026-09-17T10:00:00+01:00"}})
        dead = self._taxi_release(ocid="ocds-dead", tender={"tenderPeriod": {"endDate": "2026-09-15T09:00:00+01:00"}})
        brief = generate_brief([("ocds-live", "2026-09-15T10:00:00+01:00", json.dumps(live)),
                                ("ocds-dead", "2026-09-14T10:00:00+01:00", json.dumps(dead))], now=self.now)
        self.assertEqual(brief["relevant_count"], 1)
        self.assertEqual([n["ocid"] for n in brief["notices"]], ["ocds-live"])

    def test_render_recomputes_remaining_time_at_render_moment(self):
        """Rendering later than generation must show updated hours, and drop newly-expired items."""
        release = self._taxi_release(ocid="ocds-t", tender={"tenderPeriod": {"endDate": "2026-09-16T14:00:00+01:00"}})
        generated_at = datetime(2026, 9, 16, 10, 0, tzinfo=timezone.utc)   # 14:00 BST = 13:00Z -> 3h remaining
        brief = generate_brief([("ocds-t", "2026-09-15T10:00:00+01:00", json.dumps(release))], now=generated_at)
        self.assertAlmostEqual(brief["notices"][0]["hours_remaining"], 3.0, places=3)
        early = render_preview(brief, now=generated_at)
        self.assertIn("3.0h remaining", early)
        late = render_preview(brief, now=datetime(2026, 9, 16, 15, 0, tzinfo=timezone.utc))  # 16:00 BST, expired
        self.assertIn("Expired", late)
        self.assertNotIn("3.0h remaining", late)
        self.assertIn("0 of 1 in-scope notices are still actionable", late)

    def test_carried_forward_fields_are_reported_not_silently_dropped(self):
        """A later release that omits a field an earlier one stated must not lose the statement."""
        first = self._taxi_release(ocid="ocds-c")
        first["date"] = "2026-09-14T10:00:00+01:00"
        first["tender"]["value"] = {"amount": 12500, "currency": "GBP"}
        amendment = self._taxi_release(ocid="ocds-c", tender={"tenderPeriod": {"endDate": "2026-09-19T10:00:00+01:00"}})
        amendment["date"] = "2026-09-15T10:00:00+01:00"
        resolved = resolve_latest([("ocds-c", "2026-09-14T10:00:00+01:00", json.dumps(first)),
                                   ("ocds-c", "2026-09-15T10:00:00+01:00", json.dumps(amendment))])
        merged = resolved[0]["payload"]
        self.assertEqual(merged["tender"]["tenderPeriod"]["endDate"], "2026-09-19T10:00:00+01:00")
        self.assertEqual(merged["tender"]["value"]["amount"], 12500, "earlier-stated value must carry forward")
        self.assertEqual([c["field"] for c in resolved[0]["carried_forward"]], ["tender.value"])

    def test_release_tags_are_recorded(self):
        amendment = self._taxi_release(ocid="ocds-tag")
        amendment["tag"] = ["tenderAmendment"]
        amendment["date"] = "2026-09-15T10:00:00+01:00"
        resolved = resolve_latest([("ocds-tag", "2026-09-15T10:00:00+01:00", json.dumps(amendment))])
        self.assertEqual(resolved[0]["tags"], ["tenderAmendment"])

    def test_snapshot_is_marked_historical(self):
        release = self._taxi_release(ocid="ocds-s")
        brief = generate_brief([("ocds-s", "2026-09-15T10:00:00+01:00", json.dumps(release))], now=self.now)
        self.assertIn("Timestamped historical snapshot", brief["snapshot_note"])
        self.assertIn("not a live feed", brief["snapshot_note"].lower())

    def test_generate_brief_empty(self):
        brief = generate_brief([], now=self.now)
        self.assertEqual(brief["notices"], [])
        self.assertEqual(brief["relevant_count"], 0)

    def test_nested_amendment_retains_deadline_currency_and_null_deletion(self):
        first = self._taxi_release(id="one", date="2026-09-14T10:00:00Z")
        first["tender"]["value"] = {"amount": 100, "currency": "GBP"}
        amendment = {"id": "two", "date": "2026-09-15T10:00:00Z",
                     "tender": {"value": {"amount": 200},
                                "tenderPeriod": {"startDate": "2026-09-15T10:00:00Z"},
                                "description": None}}
        rows = [("x", r["date"], json.dumps(r)) for r in (amendment, first)]
        resolved = resolve_latest(rows)[0]
        tender = resolved["payload"]["tender"]
        self.assertEqual(tender["value"], {"amount": 200, "currency": "GBP"})
        self.assertEqual(tender["tenderPeriod"]["endDate"], first["tender"]["tenderPeriod"]["endDate"])
        self.assertNotIn("description", tender)
        fields = {entry["field"] for entry in resolved["carried_forward"]}
        self.assertIn("tender.value.currency", fields)
        self.assertIn("tender.tenderPeriod.endDate", fields)

    def test_omitted_cancelled_status_is_not_reactivated_by_partial_update(self):
        old = self._taxi_release(id="one", date="2026-09-14T10:00:00Z", tender={"status": "cancelled"})
        new = {"id": "two", "date": "2026-09-15T10:00:00Z", "tender": {"title": "Taxi update"}}
        brief = generate_brief([("x", r["date"], r) for r in (old, new)], now=self.now)
        self.assertEqual(brief["relevant_count"], 0)
        self.assertIn("cancelled", brief["excluded"][0]["reason"])

    def test_negative_pa_empty_label_and_vehicle_band_do_not_invent_requirements(self):
        release = self._taxi_release(tender={"description": "Vehicle type: 4-8 seats MPV\nPassenger Assistant Required: not required\nComments for Operator: \nFrom: TN39 5AR"})
        req = extract_requirements(release)
        self.assertIsNone(req["vehicle"]["seats"])
        self.assertIsNone(req["vehicle"]["operator_notes"])
        self.assertEqual(req["passenger_assistant"]["requirement"], "not required")

    def test_unknown_deadline_and_exact_deadline_not_actionable(self):
        unknown = self._taxi_release(tender={"tenderPeriod": {}})
        brief = generate_brief([("x", None, unknown)], now=self.now)
        self.assertIn("Deadline unknown", render_preview(brief, now=self.now))
        self.assertIn("0 of 1", render_preview(brief, now=self.now))
        exact = self._taxi_release(tender={"tenderPeriod": {"endDate": self.now.isoformat()}})
        self.assertFalse(score_release(exact, now=self.now)["relevant"])

    def test_prefilter_combined_matrix_includes_challenge_mismatch(self):
        from root_engine.screen import measure_prefilter
        summary = measure_prefilter(json.loads(read_text(PROJECT / "examples/prefilter_corpus.json"))["cases"])
        self.assertEqual(summary["combined_counts"], {"tp": 4, "fp": 1, "fn": 1, "tn": 4})
        self.assertEqual(summary["combined_mismatch_proceed_rate"], 0.2)
        with self.assertRaises(RootError):
            measure_prefilter([{"id": "unlabelled", "packet": {}}])

if __name__ == "__main__":
    unittest.main()
