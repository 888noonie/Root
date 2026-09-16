"""Promotion lifecycle: pending operator allow after independent evaluation."""

import hashlib
import json
import math
import re
import subprocess
import sys
import tempfile
import urllib.parse
import uuid
from contextlib import contextmanager

from .constitution import TRUSTED_RELATIVE_PATHS, assert_trusted_manifest, trusted_manifest
from .goals import Goals
from .retry_component import COMPONENT
from .store import BudgetError, RootError, digest, encode
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
TARGET_RETRY_AFTER = "retry_after_parser"
ARTIFACT_KIND = "restricted_retry_after_source"
TERMINAL = frozenset({"promoted", "denied", "expired", "failed", "superseded"})
OPEN_STATES = frozenset({"pending", "evaluating"})
EVAL_LEASE_SECONDS = 30
ROW_OVERHEAD = 512
MAX_ACTOR_BYTES = 120
MAX_REASON_BYTES = 500
SOURCE_SUFFIX = "/src/urllib3/util/retry.py"


class PromotionClosed(RootError):
    """A terminal or non-promotable decision. CLI exit 1."""

    def __init__(self, message, projection=None):
        super().__init__(message)
        self.projection = projection


def _parse_json(value):
    import json
    return json.loads(value) if isinstance(value, str) else value


def _blob(value):
    if isinstance(value, memoryview):
        return value.tobytes()
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    return bytes(value)


def _text_len(value):
    if value is None:
        return 0
    if isinstance(value, (bytes, memoryview)):
        return len(_blob(value))
    return len(str(value).encode("utf-8"))


def _bounded_text(value, label, maximum):
    if not isinstance(value, str) or not value.strip():
        raise RootError(f"{label} is required")
    if len(value.encode("utf-8")) > maximum:
        raise RootError(f"{label} exceeds {maximum} UTF-8 bytes")
    return value.strip()


def _validate_curated_provenance(source_url, revision, license_text):
    if not isinstance(revision, str) or not re.fullmatch(r"[a-f0-9]{40}", revision):
        raise RootError("Promotion requires an exact 40-character upstream revision")
    parsed = urllib.parse.urlsplit(source_url)
    expected_path = f"/urllib3/urllib3/{revision}{SOURCE_SUFFIX}"
    if parsed.scheme != "https" or parsed.netloc != "raw.githubusercontent.com" or parsed.path != expected_path \
       or parsed.query or parsed.fragment:
        raise RootError("Promotion source URL does not match the pinned curated artifact")
    if not isinstance(license_text, str) or "Permission is hereby granted" not in license_text \
       or "THE SOFTWARE IS PROVIDED" not in license_text:
        raise RootError("Promotion requires the retained MIT license grant")


def _immutable_fingerprint(row):
    artifact = _blob(row["artifact"])
    artifact_sha256 = hashlib.sha256(artifact).hexdigest()
    if artifact_sha256 != row["artifact_sha256"]:
        raise RootError("Artifact integrity failure")
    return digest({
        "id": row["id"],
        "goal_id": row["goal_id"],
        "target": row["target"],
        "artifact_kind": row["artifact_kind"],
        "artifact_sha256": artifact_sha256,
        "source_url": row["source_url"],
        "upstream_revision": row["upstream_revision"],
        "license_sha256": hashlib.sha256(row["license"].encode("utf-8")).hexdigest(),
        "mode": row["mode"],
        "evaluation_manifest": row["evaluation_manifest"],
        "evaluation_receipt": row["evaluation_receipt"],
        "trusted_manifest": row["trusted_manifest"],
        "baseline_component_id": row["baseline_component_id"],
        "created": row["created"],
        "expires": row["expires"],
    })


def _validate_promotion_binding(store, row):
    if row["mode"] != "live":
        raise RootError("Fixture promotions are never eligible")
    if row["target"] != TARGET_RETRY_AFTER or row["artifact_kind"] != ARTIFACT_KIND:
        raise RootError("Unsupported promotion target")
    _validate_curated_provenance(row["source_url"], row["upstream_revision"], row["license"])
    goals = Goals(store)
    goal = goals.row(row["goal_id"])
    result = goal["result"] or {}
    if goal["state"] != "pending_promotion" or goal["mode"] != "live" \
       or goal["spec"].get("adapter") != "retry_after_v1":
        raise RootError("Promotion is not bound to an eligible live goal")
    if result.get("promotion_id") != row["id"] or result.get("evaluation") != "pass" \
       or result.get("promotable") is not True or result.get("adoption") != "pending_operator":
        raise RootError("Promotion does not match the parent goal decision")
    if result.get("source_url") != row["source_url"] or result.get("upstream_revision") != row["upstream_revision"]:
        raise RootError("Promotion provenance does not match the parent goal")
    manifest = _parse_json(row["evaluation_manifest"])
    if manifest != goal["spec"].get("evaluation_manifest"):
        raise RootError("Promotion evaluation manifest does not match the parent goal")
    receipt = _parse_json(row["evaluation_receipt"])
    if receipt.get("evaluation") != "pass" or receipt.get("mode") != "live" \
       or receipt.get("measurements") != result.get("measurements"):
        raise RootError("Promotion evaluation receipt is not the accepted live result")
    source_evidence = store.db.execute(
        "SELECT body, mode FROM repo_evidence WHERE goal_id=? AND url=?",
        (row["goal_id"], row["source_url"]),
    ).fetchone()
    license_url = row["source_url"][:-len(SOURCE_SUFFIX)] + "/LICENSE.txt"
    license_evidence = store.db.execute(
        "SELECT body, mode FROM repo_evidence WHERE goal_id=? AND url=?",
        (row["goal_id"], license_url),
    ).fetchone()
    if not source_evidence or source_evidence["mode"] != "live" \
       or source_evidence["body"].encode("utf-8") != _blob(row["artifact"]):
        raise RootError("Promotion artifact is not retained live source evidence")
    if not license_evidence or license_evidence["mode"] != "live" or license_evidence["body"] != row["license"]:
        raise RootError("Promotion license is not retained live evidence")
    return goal


def promotion_id_for(goal_id, artifact_sha256, baseline_component_id):
    return digest(
        {
            "goal_id": goal_id,
            "artifact_sha256": artifact_sha256,
            "target": TARGET_RETRY_AFTER,
            "baseline_component_id": baseline_component_id,
        }
    )[:32]


def estimate_promotion_storage(discovery, manifest, receipt, trusted, result):
    artifact = discovery["source"].encode("utf-8")
    fields = (
        artifact,
        discovery["license"].encode("utf-8"),
        discovery["source_url"].encode("utf-8"),
        discovery["revision"].encode("utf-8"),
        encode(manifest).encode("utf-8"),
        encode(receipt).encode("utf-8"),
        encode(trusted).encode("utf-8"),
        encode(result).encode("utf-8"),
        TARGET_RETRY_AFTER.encode(),
        ARTIFACT_KIND.encode(),
        discovery["mode"].encode("utf-8"),
    )
    return sum(len(item) for item in fields) + ROW_OVERHEAD * 8


def _activation_storage_estimate(row, actor):
    return (
        len(_blob(row["artifact"]))
        + _text_len(row["license"])
        + _text_len(row["evaluation_receipt"])
        + len(actor.encode("utf-8"))
        + 16384
    )


def _event(store, promotion_id, stage, payload):
    store.db.execute(
        "INSERT INTO promotion_events(promotion_id, created, stage, payload) VALUES(?,?,?,?)",
        (promotion_id, store.now(), stage, encode(payload)),
    )


def _goal_not_adopted(store, goal_id, decision):
    goals = Goals(store)
    result = dict(goals.row(goal_id)["result"] or {})
    result["adoption"] = "not_adopted"
    result["promotable"] = False
    result["promotion_decision"] = decision
    store.db.execute(
        "UPDATE goals SET state='completed', result=? WHERE id=? AND state IN ('pending_promotion','running')",
        (encode(result), goal_id),
    )


def _check_persisted_storage(store, goal_id):
    goals = Goals(store)
    goal = goals.row(goal_id)
    limit = goal["spec"].get("max_storage_bytes", store.portfolio()["policy"]["max_storage_bytes"])
    if goals.payload_bytes(goal_id) > limit:
        raise BudgetError("Capability goal record-storage budget reached")
    pages = store.db.execute("PRAGMA page_count").fetchone()[0]
    page_size = store.db.execute("PRAGMA page_size").fetchone()[0]
    if pages * page_size > store.portfolio()["policy"]["max_storage_bytes"]:
        raise BudgetError("SQLite storage budget reached")


def _canonical_goal_id(store, promotion_id):
    matches = []
    for row in store.db.execute("SELECT id, result FROM goals WHERE result IS NOT NULL"):
        try:
            if _parse_json(row["result"]).get("promotion_id") == promotion_id:
                matches.append(row["id"])
        except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return matches[0] if len(matches) == 1 else None


def _close_open_promotion(store, promotion_id, state, actor, reason, goal_id_override=None):
    now = store.now()
    row = store.db.execute("SELECT state, goal_id FROM promotions WHERE id=?", (promotion_id,)).fetchone()
    if not row:
        raise RootError("Unknown promotion")
    if row["state"] in TERMINAL:
        return row["state"]
    updated = store.db.execute(
        "UPDATE promotions SET state=?, decided=?, decision_actor=?, decision_reason=? WHERE id=? AND state IN ('pending','evaluating')",
        (state, now, actor, reason[:500], promotion_id),
    ).rowcount
    if updated:
        _event(store, promotion_id, state, {"actor": actor, "reason": reason[:500], "previous": row["state"]})
        goal_id = goal_id_override or row["goal_id"]
        _goal_not_adopted(store, goal_id, state)
        _check_persisted_storage(store, goal_id)
    return state


@contextmanager
def _terminalize_attempt_on_error(store, promotion_id, token, actor):
    try:
        yield
    except Exception as exc:
        with store.transaction():
            current = store.db.execute(
                "SELECT state, attempt_token FROM promotions WHERE id=?", (promotion_id,)
            ).fetchone()
            if current and current["state"] == "evaluating" and current["attempt_token"] == token:
                _event(
                    store,
                    promotion_id,
                    "activation_failed",
                    {"attempt_token": token, "error_tail": str(exc)[-500:]},
                )
                _close_open_promotion(store, promotion_id, "failed", actor, "activation_integrity_failed")
        raise


def _reconcile_expiry(store, promotion_id):
    row = store.db.execute("SELECT state, expires FROM promotions WHERE id=?", (promotion_id,)).fetchone()
    if not row:
        raise RootError("Unknown promotion")
    if row["state"] in TERMINAL:
        return row["state"]
    if store.now() >= row["expires"]:
        return _close_open_promotion(store, promotion_id, "expired", "system", "expired")
    return row["state"]


def _public_projection(store, row):
    now = store.now()
    artifact = _blob(row["artifact"])
    license_bytes = row["license"].encode("utf-8") if isinstance(row["license"], str) else _blob(row["license"])
    trusted = _parse_json(row["trusted_manifest"])
    return {
        "id": row["id"],
        "goal_id": row["goal_id"],
        "target": row["target"],
        "artifact_kind": row["artifact_kind"],
        "artifact_sha256": row["artifact_sha256"],
        "artifact_bytes": len(artifact),
        "license_sha256": hashlib.sha256(license_bytes).hexdigest(),
        "source_url": row["source_url"],
        "upstream_revision": row["upstream_revision"],
        "mode": row["mode"],
        "evaluation_manifest": _parse_json(row["evaluation_manifest"]),
        "evaluation_receipt": _parse_json(row["evaluation_receipt"]),
        "trusted_manifest_digest": digest(trusted),
        "baseline_component_id": row["baseline_component_id"],
        "state": row["state"],
        "created": row["created"],
        "expires": row["expires"],
        "seconds_remaining": max(0.0, row["expires"] - now),
        "decided": row["decided"],
        "decision_actor": row["decision_actor"],
        "decision_reason": row["decision_reason"],
        "component_id": row["component_id"],
        "attempt_token": row["attempt_token"],
        "attempt_expires": row["attempt_expires"],
    }


def show(store, promotion_id):
    with store.transaction():
        _reconcile_expiry(store, promotion_id)
        row = store.db.execute("SELECT * FROM promotions WHERE id=?", (promotion_id,)).fetchone()
        if not row:
            raise RootError("Unknown promotion")
        return _public_projection(store, row)


def create_pending_retry_after(goals, goal_id, discovery, measured, baseline_component_id, expires, result, fail_after=None):
    if discovery["mode"] != "live":
        raise RootError("Fixture artifacts cannot create promotions")
    _validate_curated_provenance(discovery["source_url"], discovery["revision"], discovery["license"])
    artifact = discovery["source"].encode("utf-8")
    artifact_sha256 = hashlib.sha256(artifact).hexdigest()
    manifest = {name: goals.row(goal_id)["spec"]["evaluation_manifest"][name] for name in ("development", "holdout")}
    promotion_id = promotion_id_for(goal_id, artifact_sha256, baseline_component_id)
    trusted = trusted_manifest()
    receipt = {"evaluation": "pass", "measurements": measured, "mode": discovery["mode"]}
    estimate = estimate_promotion_storage(discovery, manifest, receipt, trusted, result)
    goals.check(goal_id, estimate)
    goals.store.check(estimate)
    with goals.store.transaction():
        goals.check(goal_id, estimate)
        existing = goals.store.db.execute(
            "SELECT id FROM promotions WHERE target=? AND ifnull(baseline_component_id,'')=? AND state IN ('pending','evaluating')",
            (TARGET_RETRY_AFTER, baseline_component_id or ""),
        ).fetchone()
        if existing:
            raise RootError("Unresolved promotion already exists for this target and baseline")
        goals.store.db.execute(
            """INSERT INTO promotions(
                id, goal_id, target, artifact_kind, artifact, artifact_sha256, source_url, upstream_revision, license,
                mode, evaluation_manifest, evaluation_receipt, trusted_manifest, baseline_component_id,
                state, created, expires
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                promotion_id,
                goal_id,
                TARGET_RETRY_AFTER,
                ARTIFACT_KIND,
                artifact,
                artifact_sha256,
                discovery["source_url"],
                discovery["revision"],
                discovery["license"],
                discovery["mode"],
                encode(manifest),
                encode(receipt),
                encode(trusted),
                baseline_component_id,
                "pending",
                goals.store.now(),
                expires,
            ),
        )
        if fail_after == "promotion":
            raise RootError("injected failure after promotion insert")
        _event(goals.store, promotion_id, "created", {"actor": "engine", "artifact_sha256": artifact_sha256})
        if fail_after == "event":
            raise RootError("injected failure after promotion event")
        goals.store.db.execute(
            "UPDATE goals SET state='pending_promotion', result=? WHERE id=?",
            (encode(result), goal_id),
        )
        if fail_after == "goal":
            raise RootError("injected failure after goal update")
        pending_row = goals.store.db.execute("SELECT * FROM promotions WHERE id=?", (promotion_id,)).fetchone()
        _validate_promotion_binding(goals.store, pending_row)
        goals.check(goal_id)
        goals.store.check()
    return promotion_id


def _run_snapshot_evaluator(entrypoint, source, cases):
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-S", str(entrypoint)],
            input=encode({"source": source, "cases": cases}),
            capture_output=True,
            text=True,
            timeout=5,
            env={"PATH": "/usr/bin", "LANG": "C.UTF-8"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RootError(f"Isolated candidate evaluation failed: {str(exc)[-500:]}") from exc
    if result.returncode:
        raise RootError("Isolated candidate evaluation failed: " + result.stderr[-500:])
    try:
        output = json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RootError("Isolated candidate evaluation returned invalid JSON") from exc
    if not isinstance(output, list) or len(output) != len(cases):
        raise RootError("Isolated candidate evaluation returned an invalid receipt")
    for expected_case, measured_case in zip(cases, output):
        if (
            not isinstance(measured_case, dict)
            or measured_case.get("id") != expected_case["id"]
            or type(measured_case.get("pass")) is not bool
            or isinstance(measured_case.get("actual"), bool)
            or not isinstance(measured_case.get("actual"), (int, float))
            or not math.isfinite(measured_case["actual"])
        ):
            raise RootError("Isolated candidate evaluation returned an invalid receipt")
    return output


def _reevaluate_artifact(artifact_text, manifest, baseline_source=None, evaluation_files=None, trusted=None):
    from .collector import read_json

    trusted = trusted or trusted_manifest()
    assert_trusted_manifest(trusted)
    case_sets = {}
    for split in ("development", "holdout"):
        filename = evaluation_files.get(split) if evaluation_files else f"retry_after.{split}.json"
        cases = read_json(PROJECT / "examples" / filename)
        if digest(cases) != manifest[split]:
            raise RootError("Evaluation manifest drift")
        case_sets[split] = cases
    measured = {}
    with tempfile.TemporaryDirectory(prefix="root-promotion-tcb-") as directory:
        snapshot = Path(directory)
        for relative in TRUSTED_RELATIVE_PATHS:
            content = (PROJECT / relative).read_bytes()
            if hashlib.sha256(content).hexdigest() != trusted[relative]:
                raise RootError("Trusted code changed while creating evaluation snapshot")
            destination = snapshot / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        entrypoint = snapshot / "root_engine/evaluate_component.py"
        for split, cases in case_sets.items():
            if baseline_source is None:
                baseline = [
                    {"id": case["id"], "actual": 300, "expected": case["expected"], "pass": 300 == case["expected"]}
                    for case in cases
                ]
            else:
                baseline = _run_snapshot_evaluator(entrypoint, baseline_source, cases)
            candidate = _run_snapshot_evaluator(entrypoint, artifact_text, cases)
            measured[split] = {
                "baseline": baseline,
                "candidate": candidate,
                "baseline_passes": sum(case["pass"] for case in baseline),
                "candidate_passes": sum(case["pass"] for case in candidate),
                "total": len(cases),
            }
    passed = all(
        data["candidate_passes"] == data["total"] and data["candidate_passes"] > data["baseline_passes"]
        for data in measured.values()
    )
    if not passed:
        raise RootError("Stored artifact failed independent re-evaluation")
    return measured


def _current_baseline_component_id(store):
    row = store.db.execute("SELECT id FROM components WHERE name=? AND active=1", (COMPONENT,)).fetchone()
    return row[0] if row else None


def _captured_baseline_source(store, baseline_component_id):
    if baseline_component_id is None:
        return None
    row = store.db.execute(
        "SELECT source, active FROM components WHERE id=?",
        (baseline_component_id,),
    ).fetchone()
    if not row:
        raise RootError("Captured baseline component is missing")
    if row["active"] != 1:
        raise RootError("Captured baseline component is not active")
    return row["source"]


def _claim_evaluation(store, promotion_id, actor):
    now = store.now()
    token = uuid.uuid4().hex
    lease = now + EVAL_LEASE_SECONDS
    row = store.db.execute("SELECT * FROM promotions WHERE id=?", (promotion_id,)).fetchone()
    if row["state"] == "pending":
        updated = store.db.execute(
            "UPDATE promotions SET state='evaluating', attempt_token=?, attempt_expires=? WHERE id=? AND state='pending'",
            (token, lease, promotion_id),
        ).rowcount
    elif row["state"] == "evaluating" and (row["attempt_expires"] is None or row["attempt_expires"] < now):
        _event(
            store,
            promotion_id,
            "evaluation_abandoned",
            {"attempt_token": row["attempt_token"], "reason": "stale_lease"},
        )
        updated = store.db.execute(
            "UPDATE promotions SET attempt_token=?, attempt_expires=? WHERE id=? AND state='evaluating' AND (attempt_expires IS NULL OR attempt_expires < ?)",
            (token, lease, promotion_id, now),
        ).rowcount
    else:
        raise RootError("Promotion evaluation already in progress")
    if not updated:
        raise RootError("Promotion evaluation already in progress")
    _event(store, promotion_id, "evaluating", {"actor": actor, "attempt_token": token})
    return token, dict(row)


def allow(store, promotion_id, actor):
    actor = _bounded_text(actor, "Operator label", MAX_ACTOR_BYTES)
    closed = []
    claimed = {}
    integrity_error = []
    with store.transaction():
        state = _reconcile_expiry(store, promotion_id)
        row = store.db.execute("SELECT * FROM promotions WHERE id=?", (promotion_id,)).fetchone()
        if not row:
            raise RootError("Unknown promotion")
        projection = _public_projection(store, row)
        if state == "promoted":
            projection["idempotent"] = True
            claimed["return"] = projection
        elif state in TERMINAL:
            closed.append((f"Promotion is {state}", projection))
        else:
            try:
                goal = _validate_promotion_binding(store, row)
                manifest = _parse_json(row["evaluation_manifest"])
                trusted = _parse_json(row["trusted_manifest"])
                assert_trusted_manifest(trusted)
                fingerprint = _immutable_fingerprint(row)
                raw = _blob(row["artifact"])
            except RootError as exc:
                _close_open_promotion(
                    store,
                    promotion_id,
                    "failed",
                    actor,
                    "integrity_validation_failed",
                    goal_id_override=_canonical_goal_id(store, promotion_id),
                )
                integrity_error.append(str(exc))
            else:
                activation_estimate = _activation_storage_estimate(row, actor)
                Goals(store).check(row["goal_id"], activation_estimate)
                store.check(activation_estimate)
                baseline_now = _current_baseline_component_id(store)
                if baseline_now != row["baseline_component_id"]:
                    _close_open_promotion(store, promotion_id, "superseded", actor, "baseline_drift")
                    closed_row = store.db.execute("SELECT * FROM promotions WHERE id=?", (promotion_id,)).fetchone()
                    closed.append(("Active baseline changed; promotion superseded", _public_projection(store, closed_row)))
                else:
                    claimed["baseline_source"] = _captured_baseline_source(store, row["baseline_component_id"])
                    claimed["token"], _ = _claim_evaluation(store, promotion_id, actor)
                    claimed["artifact"] = raw.decode("utf-8")
                    claimed["manifest"] = manifest
                    claimed["trusted"] = trusted
                    claimed["fingerprint"] = fingerprint
                    claimed["expires"] = row["expires"]
                    claimed["revision"] = row["upstream_revision"]
                    claimed["license"] = row["license"]
                    claimed["goal_id"] = row["goal_id"]
                    claimed["baseline_id"] = row["baseline_component_id"]
                    claimed["evaluation_files"] = goal["spec"].get("evaluation_files")
    if claimed.get("return") is not None:
        return claimed["return"]
    if closed:
        raise PromotionClosed(*closed[0])
    if integrity_error:
        raise RootError(integrity_error[0])
    token = claimed["token"]
    try:
        measured = _reevaluate_artifact(
            claimed["artifact"],
            claimed["manifest"],
            baseline_source=claimed["baseline_source"],
            evaluation_files=claimed["evaluation_files"],
            trusted=claimed["trusted"],
        )
    except Exception as exc:
        expected_failure = isinstance(exc, RootError)
        error_tail = str(exc)[-500:]
        with store.transaction():
            current = store.db.execute(
                "SELECT state, attempt_token FROM promotions WHERE id=?", (promotion_id,)
            ).fetchone()
            if current and current["state"] == "evaluating" and current["attempt_token"] == token:
                _event(
                    store,
                    promotion_id,
                    "evaluation_failed",
                    {"attempt_token": token, "error_tail": error_tail, "expected": expected_failure},
                )
                _close_open_promotion(store, promotion_id, "failed", actor, "re_evaluation_failed")
            failed = store.db.execute("SELECT * FROM promotions WHERE id=?", (promotion_id,)).fetchone()
            projection = _public_projection(store, failed) if failed else None
        if expected_failure:
            raise PromotionClosed(str(exc), projection) from exc
        raise RootError("Promotion evaluation failed unexpectedly: " + error_tail) from exc
    outcome = []
    with _terminalize_attempt_on_error(store, promotion_id, token, actor), store.transaction():
        now = store.now()
        current = store.db.execute("SELECT * FROM promotions WHERE id=?", (promotion_id,)).fetchone()
        if not current or current["state"] != "evaluating" or current["attempt_token"] != token:
            raise RootError("Promotion evaluation attempt token mismatch")
        assert_trusted_manifest(claimed["trusted"])
        _validate_promotion_binding(store, current)
        if _immutable_fingerprint(current) != claimed["fingerprint"]:
            raise RootError("Promotion changed during independent evaluation")
        _event(
            store,
            promotion_id,
            "evaluation_passed",
            {"attempt_token": token, "measurements": measured, "stderr_tail": ""},
        )
        if now >= claimed["expires"]:
            _event(store, promotion_id, "evaluation_discarded", {"attempt_token": token, "reason": "expired"})
            _close_open_promotion(store, promotion_id, "expired", "system", "expired_during_evaluation")
            expired = store.db.execute("SELECT * FROM promotions WHERE id=?", (promotion_id,)).fetchone()
            outcome.append(("expired", _public_projection(store, expired)))
        elif _current_baseline_component_id(store) != claimed["baseline_id"]:
            _event(store, promotion_id, "evaluation_discarded", {"attempt_token": token, "reason": "baseline_drift"})
            _close_open_promotion(store, promotion_id, "superseded", actor, "baseline_drift")
            superseded = store.db.execute("SELECT * FROM promotions WHERE id=?", (promotion_id,)).fetchone()
            outcome.append(("superseded", _public_projection(store, superseded)))
        else:
            artifact = claimed["artifact"]
            component_id = digest([COMPONENT, claimed["revision"], artifact])
            previous = store.db.execute("SELECT id FROM components WHERE name=? AND active=1", (COMPONENT,)).fetchone()
            existing = store.db.execute(
                "SELECT name, goal_id, revision, source, license FROM components WHERE id=?",
                (component_id,),
            ).fetchone()
            expected_component = (COMPONENT, claimed["goal_id"], claimed["revision"], artifact, claimed["license"])
            if existing and tuple(existing) != expected_component:
                raise RootError("Existing component ID does not contain the evaluated artifact")
            store.db.execute("UPDATE components SET active=0 WHERE name=?", (COMPONENT,))
            if existing:
                store.db.execute("UPDATE components SET active=1 WHERE id=?", (component_id,))
            else:
                store.db.execute(
                    "INSERT INTO components(id,name,goal_id,revision,source,license,active) VALUES(?,?,?,?,?,?,1)",
                    (component_id, *expected_component),
                )
            store.db.execute(
                "UPDATE promotions SET state='promoted', decided=?, decision_actor=?, decision_reason='allowed', component_id=?, attempt_token=NULL, attempt_expires=NULL WHERE id=? AND state='evaluating' AND attempt_token=?",
                (now, actor, component_id, promotion_id, token),
            )
            if store.db.execute("SELECT changes()").fetchone()[0] != 1:
                raise RootError("Promotion activation lost the evaluation token")
            _event(store, promotion_id, "promoted", {"actor": actor, "attempt_token": token, "component_id": component_id})
            goals = Goals(store)
            result = dict(goals.row(claimed["goal_id"])["result"] or {})
            result.update(
                adoption="enabled_restricted_adapter",
                component_id=component_id,
                previous_component_id=previous[0] if previous else None,
                promotion_id=promotion_id,
                measurements=measured,
            )
            store.db.execute("UPDATE goals SET state='completed', result=? WHERE id=?", (encode(result), claimed["goal_id"]))
            goals.check(claimed["goal_id"])
            store.check()
    if outcome:
        kind, projection = outcome[0]
        raise PromotionClosed(f"Promotion {kind} during evaluation", projection)
    return show(store, promotion_id)


def deny(store, promotion_id, actor, reason):
    actor = _bounded_text(actor, "Operator label", MAX_ACTOR_BYTES)
    reason = _bounded_text(reason, "Denial reason", MAX_REASON_BYTES)
    closed = []
    result = []
    with store.transaction():
        state = _reconcile_expiry(store, promotion_id)
        row = store.db.execute("SELECT * FROM promotions WHERE id=?", (promotion_id,)).fetchone()
        if not row:
            raise RootError("Unknown promotion")
        projection = _public_projection(store, row)
        if state == "denied":
            if row["decision_actor"] == actor and row["decision_reason"] == reason:
                projection["idempotent"] = True
                result.append(projection)
            else:
                closed.append(("Promotion was already denied by a different decision", projection))
        elif state in TERMINAL:
            closed.append((f"Promotion is {state}", projection))
        else:
            _close_open_promotion(store, promotion_id, "denied", actor, reason)
            closed_row = store.db.execute("SELECT * FROM promotions WHERE id=?", (promotion_id,)).fetchone()
            result.append(_public_projection(store, closed_row))
    if closed:
        raise PromotionClosed(*closed[0])
    return result[0]


def promote_allow(store, promotion_id, actor):
    return allow(store, promotion_id, actor)
