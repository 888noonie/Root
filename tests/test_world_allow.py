""""world-allow" live-only observation gate contracts (Task C — RED first).

A live pending world row is the only kind that may be allowed into the authoritative
`observations` table. Fixture rows are permanently blocked. Mirrors `promote-allow`.
"""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from root_engine.goals import PROJECT
from root_engine.store import RootError, Store, digest, encode


def seed_live_pending(store, *, ocid="ocds-live-1", release_id="release-1", payload=None):
    """Insert a synthetic mode=live pending row (used until Task D wires real live ingest)."""
    from root_engine import worldmonitor as wm
    wm._ensure_gate_schema(store)
    payload = payload if payload is not None else {
        "ocid": ocid, "id": release_id, "source_url": "https://www.contractsfinder.service.gov.uk/x",
        "kind": "tender", "value": 123,
    }
    encoded = encode(payload)
    observation_id = digest([wm.KIND, "world_monitor_live", ocid, release_id, encoded])[:32]
    now = store.now()
    with store.transaction():
        store.db.execute(
            "INSERT INTO world_pending_observations("
            " id,kind,ocid,release_id,source_url,mode,payload,payload_sha256,state,created,expires,decided,decision_actor,decision_reason)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (observation_id, wm.KIND, ocid, release_id, payload["source_url"], "live",
             encoded, hashlib.sha256(encoded.encode()).hexdigest(), "pending", now, store.portfolio()["deadline"],
             None, None, None),
        )
    return observation_id


class WorldAllowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "world-allow.sqlite3"
        self.clock = [1000.0]
        self.store = Store(self.path, create=True, objective="world allow tests", now=lambda: self.clock[0])

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_fixture_allow_refused_failed_closed(self):
        from root_engine.worldmonitor import world_allow, world_ingest_fixture
        result = world_ingest_fixture(self.store, {"observations": [
            {"ocid": "ocds-f-1", "id": "r1", "source_url": "fixture://s", "value": 1}]}, actor="op")
        oid = result["pending"][0]
        with self.assertRaisesRegex(RootError, r"[Ff]ixture"):
            world_allow(self.store, oid, actor="operator")
        # state unchanged, no authoritative observation
        self.assertEqual(self.store.db.execute("SELECT state FROM world_pending_observations WHERE id=?", (oid,)).fetchone()[0], "pending")
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM observations").fetchone()[0], 0)

    def test_forged_sha_refused(self):
        from root_engine.worldmonitor import world_allow
        oid = seed_live_pending(self.store)
        self.store.db.execute("UPDATE world_pending_observations SET payload_sha256=? WHERE id=?", ("0" * 64, oid))
        with self.assertRaisesRegex(RootError, "integrity"):
            world_allow(self.store, oid, actor="operator")
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM observations").fetchone()[0], 0)

    def test_live_allow_inserts_single_observation(self):
        from root_engine.worldmonitor import world_allow
        oid = seed_live_pending(self.store)
        out = world_allow(self.store, oid, actor="operator")
        self.assertEqual(out["state"], "allowed")
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM observations").fetchone()[0], 1)
        # packages carries the authoritative source row
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM packages").fetchone()[0], 1)
        row = self.store.db.execute("SELECT ocid,source_date FROM observations").fetchone()
        self.assertEqual(row["ocid"], "ocds-live-1")

    def test_second_allow_idempotent_no_duplicate(self):
        from root_engine.worldmonitor import world_allow
        oid = seed_live_pending(self.store)
        world_allow(self.store, oid, actor="operator")
        world_allow(self.store, oid, actor="operator")
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM observations").fetchone()[0], 1)

    def test_deny_terminal_and_no_observation(self):
        from root_engine.worldmonitor import world_allow, world_deny
        oid = seed_live_pending(self.store)
        out = world_deny(self.store, oid, actor="operator", reason="not relevant")
        self.assertEqual(out["state"], "denied")
        with self.assertRaisesRegex(RootError, "denied|terminal|not"):
            world_allow(self.store, oid, actor="operator")
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM observations").fetchone()[0], 0)

    def test_expired_live_cannot_allow(self):
        from root_engine.worldmonitor import world_allow, world_expire
        oid = seed_live_pending(self.store)
        deadline = self.store.portfolio()["deadline"]
        self.clock[0] = deadline + 1.0
        world_expire(self.store, oid, actor="operator")
        with self.assertRaisesRegex(RootError, "expired|not pending"):
            world_allow(self.store, oid, actor="operator")
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM observations").fetchone()[0], 0)

    def test_allow_keeps_other_tables_and_show_strips_bytes(self):
        from root_engine.worldmonitor import world_allow, world_show
        oid = seed_live_pending(self.store)
        world_allow(self.store, oid, actor="operator")
        shown = world_show(self.store, oid)
        self.assertNotIn("payload", shown)
        self.assertEqual(shown["state"], "allowed")
        # promotion + component tables untouched
        if self.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='promotions'").fetchone():
            self.assertEqual(self.store.db.execute("SELECT count(*) FROM promotions").fetchone()[0], 0)
        if self.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='components'").fetchone():
            self.assertEqual(self.store.db.execute("SELECT count(*) FROM components").fetchone()[0], 0)

    def test_allow_refuses_when_copy_would_overflow_storage_budget(self):
        # A pending live row already accounted for its bytes, but allow copies those bytes into
        # packages+observations; a portfolio with no room for that copy must fail closed.
        from root_engine.worldmonitor import world_allow
        from root_engine.store import BudgetError, Store
        # Create a tiny-budget store, seed a pending live row at ingest time, then drop the budget
        # so the allow copy would overflow. Use a separate small store to avoid disturbing others.
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tiny = Path(d) / "tiny.sqlite3"
            store = Store(tiny, create=True, objective="tiny", now=lambda: self.clock[0])
            store.db.execute("UPDATE portfolio SET policy=? WHERE id=1", (
                __import__("json").dumps({
                    "max_money_gbp": 0, "max_requests": 3, "max_download_bytes": 2 * 1024 * 1024,
                    "max_storage_bytes": 65536, "max_inference_tokens": 0,
                    "max_elapsed_seconds": 3600, "max_concurrent_jobs": 1,
                }),))
            payload = {"ocid": "ocds-over-1", "id": "over-1",
                       "source_url": "https://www.contractsfinder.service.gov.uk/x",
                       "kind": "tender", "value": 1}
            big = {"ocid": "ocds-over-1", "id": "over-1",
                   "source_url": "https://www.contractsfinder.service.gov.uk/x",
                   "kind": "tender", "value": 1, "blob": "x" * 300000}
            from root_engine import worldmonitor as wm
            wm._ensure_gate_schema(store)
            encoded = __import__("root_engine.store", fromlist=["encode"]).encode(big)
            oid = __import__("root_engine.store", fromlist=["digest"]).digest(["wm", "live", big["ocid"], big["id"], encoded])[:32]
            store.db.execute(
                "INSERT INTO world_pending_observations("
                " id,kind,ocid,release_id,source_url,mode,payload,payload_sha256,state,created,expires,decided,decision_actor,decision_reason)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (oid, wm.KIND, big["ocid"], big["id"], big["source_url"], "live", encoded,
                 __import__("hashlib").sha256(encoded.encode()).hexdigest(), "pending", self.clock[0],
                 store.portfolio()["deadline"], None, None, None))
            with self.assertRaises(BudgetError):
                world_allow(store, oid, actor="operator")
            self.assertEqual(store.db.execute("SELECT count(*) FROM observations").fetchone()[0], 0)
            store.close()

    def test_cli_world_allow_refuses_fixture(self):
        from root_engine.worldmonitor import world_ingest_fixture
        result = world_ingest_fixture(self.store, {"observations": [
            {"ocid": "ocds-cli-1", "id": "r1", "source_url": "fixture://s", "value": 1}]}, actor="op")
        oid = result["pending"][0]
        run = subprocess.run(
            [sys.executable, "-m", "root_engine", "--db", str(self.store.path),
             "world-allow", "--id", oid, "--actor", "operator"],
            capture_output=True, text=True, cwd=PROJECT)
        self.assertEqual(run.returncode, 2, run.stderr)
        self.assertIn("fixture", run.stderr.lower())
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM observations").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()