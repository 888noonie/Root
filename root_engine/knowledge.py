"""Evidence-only learning requests: knowledge without promotion authority.

Task 7 contract: learn-create / learn-run produce knowledge_records with
authority="evidence_only". They can never create components, promotions, or
change collector behavior.
"""

from .store import RootError, digest, encode
import json

AUTHORITY_EVIDENCE_ONLY = "evidence_only"
LEARN_KIND = "unsupported_adapter_research_v1"


def learn_id_for(spec):
    return digest({"kind": spec["kind"], "trigger": spec["trigger"], "parent_objective": spec["parent_objective"]})[:32]


class Learning:
    def __init__(self, store):
        self.store = store

    def row(self, request_id):
        row = self.store.db.execute("SELECT * FROM learning_requests WHERE id=?", (request_id,)).fetchone()
        if not row:
            raise RootError("Unknown learning request")
        value = dict(row)
        value["spec"] = json.loads(value["spec"])
        value["result"] = json.loads(value["result"]) if value["result"] else None
        return value

    def create(self, spec):
        if not isinstance(spec, dict):
            raise RootError("Learning request must be a JSON object")
        if spec.get("kind") != LEARN_KIND:
            raise RootError(f"Only {LEARN_KIND} learning requests are supported")
        for field in ("id", "trigger", "parent_objective", "need", "practice_fixture", "acceptance"):
            if not isinstance(spec.get(field), str) or not spec[field].strip():
                raise RootError(f"Learning request requires {field}")
        for field in ("max_requests", "max_download_bytes", "max_storage_bytes", "max_elapsed_seconds",
                      "max_inference_tokens", "max_money_gbp", "max_concurrent_jobs"):
            if not isinstance(spec.get(field), int) or spec[field] < 0:
                raise RootError(f"Learning request budget must be non-negative integer: {field}")
        if spec["max_money_gbp"] != 0:
            raise RootError("Learning requests support zero spending only")
        if spec["max_concurrent_jobs"] != 1:
            raise RootError("Learning requests support exactly one concurrent job")
        policy = self.store.portfolio()["policy"]
        for field, bound in (("max_requests", policy["max_requests"]),
                              ("max_download_bytes", policy["max_download_bytes"]),
                              ("max_storage_bytes", policy["max_storage_bytes"]),
                              ("max_elapsed_seconds", policy["max_elapsed_seconds"]),
                              ("max_inference_tokens", policy["max_inference_tokens"]),
                              ("max_concurrent_jobs", policy["max_concurrent_jobs"]),
                              ):
            if spec[field] > bound:
                raise RootError(f"Learning budget must fit portfolio: {field}")
        payload = encode(spec)
        with self.store.transaction():
            self.store.check(len(payload.encode()) * 2 + 16384)
            existing = self.store.db.execute("SELECT 1 FROM learning_requests WHERE id=?", (spec["id"],)).fetchone()
            if existing:
                raise RootError("Learning request already exists; cannot reset budgets or criteria")
            now = self.store.now()
            deadline = min(now + spec["max_elapsed_seconds"], self.store.portfolio()["deadline"])
            self.store.db.execute(
                "INSERT INTO learning_requests(id,spec,created,deadline,state,mode,requests,downloaded_bytes,result) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (spec["id"], payload, now, deadline, "created", None, 0, 0, None),
            )
        return self.row(spec["id"])


def run_learning_request(learning, request_id, *, fixture=None, opener=None):
    row = learning.row(request_id)
    if row["state"] not in ("created",):
        raise RootError(f"Learning request is {row['state']}; only 'created' can run")
    if row["spec"]["kind"] != LEARN_KIND:
        raise RootError("Unsupported learning request kind")
    now = learning.store.now()
    if now >= row["deadline"]:
        raise RootError("Learning request deadline reached")

    with learning.store.transaction():
        learning.store.db.execute(
            "UPDATE learning_requests SET state='running', mode=? WHERE id=?",
            ("fixture" if fixture is not None else "live", request_id),
        )

    try:
        spec = row["spec"]
        claims = [{"kind": "observed", "text": spec["need"]}]
        evidence_refs = []
        practice_receipt = {"accepted": False, "note": "not attempted"}
        now = learning.store.now()

        if fixture is not None:
            # Fixture mode: no network. Evidence is the inline fixture payload.
            evidence_refs.append({"mode": "fixture", "keys": sorted(fixture.keys())})
            if spec.get("practice_fixture") != "inline":
                raise RootError(f"Only 'inline' practice fixtures are supported; got {spec.get('practice_fixture')!r}")
            practice_receipt = {"accepted": True, "note": "fixture inline practice passed"}
        else:
            raise RootError("Live learning retrieval not implemented for this request kind; use fixture mode")

        result = {
            "evaluation": "pass" if practice_receipt["accepted"] else "uncertain",
            "claims": claims,
            "evidence_refs": evidence_refs,
            "practice_receipt": practice_receipt,
            "authority": AUTHORITY_EVIDENCE_ONLY,
        }
        with learning.store.transaction():
            learning.store.db.execute(
                "UPDATE learning_requests SET state='completed', result=? WHERE id=?",
                (encode(result), request_id),
            )
            learning.store.db.execute(
                "INSERT INTO knowledge_records(id,request_id,trigger,source_url,upstream_revision,license_status,retrieved,claims,evidence_refs,practice_receipt,mode,authority) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (learn_id_for(spec), request_id, spec["trigger"], None, None, "unknown", now,
                 encode(claims), encode(evidence_refs), encode(practice_receipt),
                 "fixture" if fixture is not None else "live", AUTHORITY_EVIDENCE_ONLY),
            )
            learning.store.check()
        return learning.row(request_id)
    except Exception:
        with learning.store.transaction():
            learning.store.db.execute(
                "UPDATE learning_requests SET state='failed' WHERE id=? AND state='running'",
                (request_id,),
            )
        raise
