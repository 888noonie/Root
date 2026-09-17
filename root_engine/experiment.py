"""Local tender-experiment runner (Task G). No outreach, no send.

Stores one predeclared experiment from `EXPERIMENT_TENDER_PREVIEW.md`: a hypothesis, an
explicitly declared baseline metric (held as unknown rather than zero-filled), and a
pass/fail/uncertain outcome with evidence refs. An experiment can never create a component,
promotion, or collector change, and it never contacts anyone.
"""

from .store import RootError, encode

KIND = "tender_preview_usefulness_v1"
OUTCOMES = ("pass", "fail", "uncertain")
MAX_BASELINE_BYTES = 4096
MAX_NOTE_BYTES = 4096
MAX_EVIDENCE = 50


def _require(spec, field):
    if not isinstance(spec.get(field), str) or not spec[field].strip():
        raise RootError(f"Experiment requires a nonempty {field}")
    if len(spec[field].encode("utf-8")) > 8192:
        raise RootError(f"Experiment {field} too long")
    return spec[field].strip()


class Experiments:
    def __init__(self, store):
        self.store = store

    def _ensure_schema(self):
        self.store.db.execute(
            "CREATE TABLE IF NOT EXISTS experiments ("
            " id TEXT PRIMARY KEY, kind TEXT NOT NULL, spec TEXT NOT NULL,"
            " state TEXT NOT NULL, created REAL NOT NULL, deadline REAL NOT NULL,"
            " outcome TEXT, evidence_refs TEXT, note TEXT, ran_at REAL)")

    def row(self, eid):
        row = self.store.db.execute("SELECT * FROM experiments WHERE id=?", (eid,)).fetchone()
        if not row:
            raise RootError("Unknown experiment")
        value = dict(row)
        value["spec"] = json_loads(value["spec"])
        value["baseline_metric"] = value["spec"].get("baseline_metric", {})
        value["evidence_refs"] = json_loads(value["evidence_refs"]) if value["evidence_refs"] else []
        value["token_issue"] = value["outcome"]  # alias used by CLI/reporting
        return value

    def create(self, spec):
        if not isinstance(spec, dict):
            raise RootError("Experiment must be a JSON object")
        eid = _require(spec, "id")
        kind = _require(spec, "kind")
        if kind != KIND:
            raise RootError(f"Only {KIND} experiments are supported")
        _require(spec, "hypothesis")
        baseline = spec.get("baseline_metric", {})
        if not isinstance(baseline, dict) or baseline.get("value") is not None:
            raise RootError("Baseline metric must be an object whose value is declared unknown (None)")
        if len(encode(baseline).encode("utf-8")) > MAX_BASELINE_BYTES:
            raise RootError("Baseline metric too large")
        self._ensure_schema()
        with self.store.transaction():
            if self.store.db.execute("SELECT 1 FROM experiments WHERE id=?", (eid,)).fetchone():
                raise RootError("Experiment already exists")
            self.store.check(len(encode(spec).encode("utf-8")) + 8192)
            now = self.store.now()
            deadline = now + spec.get("max_elapsed_seconds", 3600)
            self.store.db.execute(
                "INSERT INTO experiments(id,kind,spec,state,created,deadline,outcome,evidence_refs,note,ran_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (eid, kind, encode(spec), "created", now, deadline, None, None, None, None))
        return self.row(eid)

    def run(self, eid, *, outcome, evidence_refs=None, note=""):
        if outcome not in OUTCOMES:
            raise RootError(f"Outcome must be one of {', '.join(OUTCOMES)}")
        evidence = list(evidence_refs or [])
        if len(evidence) > MAX_EVIDENCE:
            raise RootError("Too many evidence refs")
        if not isinstance(note, str) or len(note.encode("utf-8")) > MAX_NOTE_BYTES:
            raise RootError("Note must be a string of at most 4096 UTF-8 bytes")
        self._ensure_schema()
        with self.store.transaction():
            row = self.store.db.execute("SELECT state FROM experiments WHERE id=?", (eid,)).fetchone()
            if not row:
                raise RootError("Unknown experiment")
            if row["state"] != "created":
                raise RootError("Experiment already completed")
            self.store.check(len(encode(evidence).encode("utf-8")) + len(note.encode("utf-8")) + 8192)
            now = self.store.now()
            self.store.db.execute(
                "UPDATE experiments SET state='completed', outcome=?, evidence_refs=?, note=?, ran_at=? WHERE id=?",
                (outcome, encode(evidence) if evidence else None, note or None, now, eid))
        return self.row(eid)

    def show(self, eid):
        return self.row(eid)


def json_loads(value):
    import json
    return json.loads(value)