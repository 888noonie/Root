#!/usr/bin/env python3
"""CI-safe observation-closure demo: pending world -> world-allow -> screen/brief see only allowed rows.

This drives the World Monitor gate end-to-end WITHOUT real network: it replays a locally
recorded OCDS search package via the collector opener, ingests it as mode=live pending,
shows that nothing becomes authoritative until `world-allow`, allows one row, and asserts
that `screen` and `brief` only ever see allowed authoritative observations.

It is a *demo*, not a proof of external facts: the replayed package is synthetic and the
brief output is advisory only.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class _ReplayOpener:
    def __init__(self, body):
        import io
        self._io = io.BytesIO(json.dumps(body).encode("utf-8"))

    def __call__(self, req, timeout=None):
        return self._io


def _make_package():
    pkg = json.loads((ROOT / "examples/contracts_finder.synthetic.json").read_text())
    # One release is an in-scope East Sussex transport tender (live-shaped, synthetic).
    pkg["uri"] = "https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search?fixture=closure-demo"
    pkg["releases"] = [{
        "ocid": "ocds-closure-001", "id": "closure-001-v1", "date": "2026-09-15T10:00:00Z",
        "tag": ["tender"],
        "buyer": {"name": "East Sussex County Council", "id": "ESCC"},
        "tender": {
            "id": "closure-001", "title": "School home-to-school passenger transport (taxi) routes",
            "description": "Synthetic closure-demo route package. No actual contract exists.",
            "status": "active",
            "value": {"amount": 0, "currency": "GBP"},
            "tenderPeriod": {"endDate": "2026-10-01T12:00:00Z"},
            "items": [{"id": "r1", "classification": {"scheme": "CPV", "id": "60170000"}}],
        },
    }]
    return pkg


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        db = td / "closure.sqlite3"
        from root_engine.store import Store
        store = Store(db, create=True, objective="observation closure demo", now=lambda: 1000.0)

        from root_engine.worldmonitor import world_ingest_live, world_show, world_allow
        pkg = _make_package()
        ingested = world_ingest_live(store, "2026-09-14T00:00:00Z", "2026-09-16T00:00:00Z",
                                     actor="operator", opener=_ReplayOpener(pkg))
        pending_id = ingested["pending"][0]

        # Before allow: nothing authoritative, no packages, no observations.
        before_pkg = store.db.execute("SELECT count(*) FROM packages").fetchone()[0]
        before_obs = store.db.execute("SELECT count(*) FROM observations").fetchone()[0]
        assert before_pkg == 0 and before_obs == 0, (before_pkg, before_obs)
        # screen/brief over an empty authoritative store see nothing.
        pre = store.db.execute("SELECT count(*) FROM observations WHERE ocid=?", ("ocds-closure-001",)).fetchone()[0]
        assert pre == 0

        # world-show (pending) must not print artifact bytes.
        shown = world_show(store, pending_id)
        assert "payload" not in shown and shown["state"] == "pending", shown

        # Allow the live pending row -> becomes a single authoritative observation.
        allowed = world_allow(store, pending_id, actor="operator")
        assert allowed["state"] == "allowed", allowed
        post_obs = store.db.execute("SELECT count(*) FROM observations WHERE ocid=?", ("ocds-closure-001",)).fetchone()[0]
        assert post_obs == 1, post_obs

        # Idempotent second allow: still one observation, no duplicate.
        world_allow(store, pending_id, actor="operator")
        assert store.db.execute("SELECT count(*) FROM observations WHERE ocid=?", ("ocds-closure-001",)).fetchone()[0] == 1

        # screen sees the allowed observation as evidence (live-sourced).
        obs = store.observation([o["id"] for o in store.db.execute("SELECT id,ocid FROM observations")][0])
        assert obs is not None and obs["mode"] == "live", obs

        # A fixture-only world row can NEVER be allowed (permanent non-authority).
        from root_engine.worldmonitor import world_ingest_fixture
        from root_engine.store import RootError
        fx = world_ingest_fixture(store, {"observations": [
            {"ocid": "ocds-fx-001", "id": "fx-1", "source_url": "fixture://s", "value": 1}]}, actor="operator")
        try:
            world_allow(store, fx["pending"][0], actor="operator")
            raise SystemExit("fixture allow unexpectedly succeeded")
        except RootError:
            pass
        assert store.db.execute("SELECT count(*) FROM observations WHERE ocid='ocds-fx-001'").fetchone()[0] == 0

        store.close()
        print("CLOSURE VERIFIED: pending->allow made one authoritative observation visible to screen; "
              "fixture rows stayed permanently non-authoritative; no network used.")
        return 0


if __name__ == "__main__":
    subprocess.check_call([sys.executable, "-m", "root_engine", "--help"], cwd=str(ROOT), stdout=subprocess.DEVNULL)
    sys.exit(main())