"""World Monitor observation-ingest gate (fixture-protocol only; future live adapter).

Move #2 of the b298ab3 follow-up: route a future observation source through the SAME
pending/explicit-allow authority boundary that components already use, instead of letting an
ingest path write authoritative observations directly.

Authority contract (mirrors the promotion brake):
  - A validated fixture batch is retained as exact bytes in a DEDICATED pending table and is
    permanently NON-AUTHORITATIVE. It can never become an authoritative observation, never
    feeds `collect`, `screen`, or `brief`, and no allow path exists for fixture mode.
  - An explicit operator `world-allow` on a genuine live (currently fixture-gated) pending batch
    would be the only way a future live adapter moves bytes into the authoritative observations
    table. No live network host is added here; live...mode raises.
  - The gate never touches the hardened `promotion.py` core, the goals store, or collector
    behavior. It is a self-contained, resource-bounded, standard-library module.

Scope honesty: this is the GATE + SPEC for wiring World Monitor ingest; it is not a real live
World Monitor crawler. It ingests bounded fixture evidence and holds it pending by default.
"""

import json
import re
import urllib.parse

from .store import RootError, digest, encode

KIND = "world_monitor_ingest_v1"
SOURCE = "world_monitor_fixture"
PENDING_OBSERVATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS world_pending_observations (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind = 'world_monitor_ingest_v1'),
    ocid TEXT NOT NULL,
    release_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('live', 'fixture')),
    payload TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL CHECK(length(payload_sha256) = 64 AND payload_sha256 NOT GLOB '*[^0-9a-f]*'),
    state TEXT NOT NULL CHECK(state IN ('pending', 'allowed', 'denied', 'expired')),
    created REAL NOT NULL,
    expires REAL NOT NULL,
    decided REAL,
    decision_actor TEXT,
    decision_reason TEXT
)
"""
PENDING_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS world_pending_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observation_id TEXT NOT NULL REFERENCES world_pending_observations(id),
    created REAL NOT NULL,
    stage TEXT NOT NULL,
    payload TEXT NOT NULL
)
"""

MAX_FIXTURE_BYTES = 256 * 1024
MAX_FIXTURE_OBSERVATIONS = 50
ROW_OVERHEAD = 512
TERMINAL = frozenset({"allowed", "denied", "expired"})


def _ensure_gate_schema(store):
    store.db.execute(PENDING_OBSERVATIONS_TABLE)
    store.db.execute(PENDING_EVENTS_TABLE)


def _validate_ocid(value):
    if not isinstance(value, str) or len(value) > 500 or not value.strip():
        raise RootError("world-monitor observations need a nonempty ocid string")
    if not re.fullmatch(r"[\w\-.:]+", value.strip()):
        raise RootError("ocid contains unsupported characters")
    return value.strip()


def _validate_source_url(value):
    if not isinstance(value, str) or not value.strip():
        raise RootError("source_url is required")
    parsed = urllib.parse.urlsplit(value.strip())
    if parsed.scheme not in ("https", "fixture") or parsed.fragment:
        raise RootError("source_url must be an HTTPS URL or a fixture: scheme URL without a fragment")
    if parsed.scheme == "https" and not parsed.netloc:
        raise RootError("source_url needs a host")
    return value.strip()


def _record(store, observation_id, stage, payload):
    store.db.execute(
        "INSERT INTO world_pending_events(observation_id, created, stage, payload) VALUES(?,?,?,?)",
        (observation_id, store.now(), stage, encode(payload)),
    )


def world_ingest_fixture(store, batch, *, actor):
    """Ingest a bounded synthetic benchmark batch into the pending gate (fixture only).

    Returns the pending projection. The batch is authoritative NOWHERE; it cannot be
    allowed into observations because mode=fixture has no allow path.
    """
    _ensure_gate_schema(store)
    if not isinstance(batch, dict) or not isinstance(batch.get("observations"), list):
        raise RootError("World Monitor fixture must be a JSON object with an 'observations' list")
    observations = batch["observations"]
    if not observations or len(observations) > MAX_FIXTURE_OBSERVATIONS:
        raise RootError(f"World Monitor fixture needs 1..{MAX_FIXTURE_OBSERVATIONS} observations")
    if not isinstance(actor, str) or not actor.strip() or len(actor.encode("utf-8")) > 120:
        raise RootError("actor must be a nonempty label of at most 120 UTF-8 bytes")

    rows = []
    with store.transaction():
        store.check(len(encode(batch).encode("utf-8")) + (ROW_OVERHEAD + 4096) * len(observations))
        total = 0
        for raw in observations:
            if not isinstance(raw, dict):
                raise RootError("each World Monitor observation must be an object")
            ocid = _validate_ocid(raw.get("ocid"))
            release_id = _validate_ocid(raw.get("id"))
            source_url = _validate_source_url(raw.get("source_url"))
            payload = encode(raw)
            total += len(payload.encode("utf-8"))
            if total > MAX_FIXTURE_BYTES:
                raise RootError("World Monitor fixture batch exceeds the 256 KiB bound")
            now = store.now()
            # Fixture batches get an immutable id and a relative expiry aligned to the portfolio.
            observation_id = digest([KIND, SOURCE, ocid, release_id, payload])[:32]
            row = {
                "id": observation_id, "kind": KIND, "ocid": ocid, "release_id": release_id,
                "source_url": source_url, "mode": "fixture",
                "payload": payload, "payload_sha256": __import__("hashlib").sha256(payload.encode("utf-8")).hexdigest(),
                "state": "pending", "created": now, "expires": store.portfolio()["deadline"],
                "decided": None, "decision_actor": None, "decision_reason": None,
            }
            store.db.execute(
                "INSERT OR IGNORE INTO world_pending_observations("
                " id,kind,ocid,release_id,source_url,mode,payload,payload_sha256,state,created,expires,decided,decision_actor,decision_reason)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (row["id"], row["kind"], row["ocid"], row["release_id"], row["source_url"], row["mode"],
                 row["payload"], row["payload_sha256"], row["state"], row["created"], row["expires"],
                 row["decided"], row["decision_actor"], row["decision_reason"]),
            )
            _record(store, observation_id, "ingest", {"mode": "fixture", "actor": actor, "ocid": ocid})
            rows.append(row)
        store.check()
    return {"mode": "fixture", "ingested": len(rows), "pending": [r["id"] for r in rows]}


def world_show(store, observation_id):
    _ensure_gate_schema(store)
    row = store.db.execute("SELECT * FROM world_pending_observations WHERE id=?", (observation_id,)).fetchone()
    if not row:
        raise RootError("Unknown pending world observation")
    value = dict(row)
    value["events"] = [
        {"stage": r[0], "created": r[1], "payload": json.loads(r[2])}
        for r in store.db.execute("SELECT stage,created,payload FROM world_pending_events WHERE observation_id=? ORDER BY id", (observation_id,))
    ]
    value["seconds_remaining"] = value["expires"] - store.now()
    value.pop("payload", None)  # never print artifact source bytes in CLI output
    return value


def world_expire(store, observation_id, *, actor="operator"):
    """Terminalize an expired pending batch; reversible only by re-ingesting a new batch."""
    _ensure_gate_schema(store)
    with store.transaction():
        row = store.db.execute("SELECT state,expires FROM world_pending_observations WHERE id=?", (observation_id,)).fetchone()
        if not row:
            raise RootError("Unknown pending world observation")
        now = store.now()
        if now >= row["expires"] and row["state"] == "pending":
            store.db.execute("UPDATE world_pending_observations SET state='expired', decided=?, decision_actor=?, decision_reason=? WHERE id=?",
                             (now, actor, "expired", observation_id))
            _record(store, observation_id, "expire", {"actor": actor})
            return world_show(store, observation_id)
        return {"id": observation_id, "state": row["state"], "changed": False}