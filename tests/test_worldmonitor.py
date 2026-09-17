"""World Monitor pending-ingest gate contracts (move #2 — RED first)."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from root_engine.goals import PROJECT
from root_engine.retry_component import active_delay
from root_engine.store import RootError, Store


class WorldMonitorGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "world.sqlite3"
        self.clock = [1000.0]
        self.store = Store(self.path, create=True, objective="world monitor gate tests", now=lambda: self.clock[0])

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def _batch(self, n=1):
        return {"observations": [
            {"ocid": f"ocds-123-{i}", "id": f"release-{i}", "source_url": "fixture://synthetic.evidence", "kind": "tender", "value": i}
            for i in range(n)
        ]}

    def test_fixture_ingest_is_pending_and_never_authoritative(self):
        from root_engine.worldmonitor import world_ingest_fixture, world_show
        result = world_ingest_fixture(self.store, self._batch(2), actor="operator")
        self.assertEqual(result["mode"], "fixture")
        self.assertEqual(len(result["pending"]), 2)
        # No authoritative observation, no package, no component, no promotion.
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM observations").fetchone()[0], 0)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM packages").fetchone()[0], 0)
        if self.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='components'").fetchone():
            self.assertEqual(self.store.db.execute("SELECT count(*) FROM components").fetchone()[0], 0)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM promotions").fetchone()[0], 0)
        # Fixture gate shows pending and strips artifact bytes.
        shown = world_show(self.store, result["pending"][0])
        self.assertEqual(shown["state"], "pending")
        self.assertEqual(shown["mode"], "fixture")
        self.assertNotIn("payload", shown)

    def test_fixture_gate_permanently_refuses_allow(self):
        from root_engine.worldmonitor import world_allow, world_ingest_fixture
        result = world_ingest_fixture(self.store, self._batch(1), actor="operator")
        # The gate exposes allow/deny for LIVE rows only; a fixture row is still permanently refused.
        self.assertTrue(callable(world_allow))
        self.assertEqual(self.store.db.execute("SELECT state FROM world_pending_observations").fetchone()[0], "pending")
        with self.assertRaises(RootError):
            world_allow(self.store, result["pending"][0], actor="operator")
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM observations").fetchone()[0], 0)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM packages").fetchone()[0], 0)

    def test_fixture_does_not_change_collector_or_promotion(self):
        from root_engine.worldmonitor import world_ingest_fixture
        self.assertEqual(active_delay(self.store, "900"), 300)
        world_ingest_fixture(self.store, self._batch(1), actor="operator")
        self.assertEqual(active_delay(self.store, "900"), 300)

    def test_display_objects_and_raw_nonobjects_rejected(self):
        from root_engine.worldmonitor import world_ingest_fixture
        with self.assertRaisesRegex(RootError, "object"):
            world_ingest_fixture(self.store, {"observations": [123]}, actor="operator")
        with self.assertRaisesRegex(RootError, "source_url"):
            # Valid object shape but a bad source scheme is rejected before any write.
            world_ingest_fixture(self.store, {"observations": [{"ocid": "x", "id": "y", "source_url": "z"}]}, actor="operator")
        with self.assertRaisesRegex(RootError, "ocid"):
            world_ingest_fixture(self.store, {"observations": [{"id": "y", "source_url": "fixture://s"}]}, actor="operator")

    def test_batch_bounds_enforced(self):
        from root_engine.worldmonitor import world_ingest_fixture, MAX_FIXTURE_OBSERVATIONS
        with self.assertRaisesRegex(RootError, "1.."):
            world_ingest_fixture(self.store, {"observations": []}, actor="operator")
        big = self._batch(MAX_FIXTURE_OBSERVATIONS + 1)
        with self.assertRaisesRegex(RootError, "1.."):
            world_ingest_fixture(self.store, big, actor="operator")

    def test_expiry_terminalizes_pending_after_portfolio_deadline(self):
        from root_engine.worldmonitor import world_ingest_fixture, world_expire, world_show
        result = world_ingest_fixture(self.store, self._batch(1), actor="operator")
        oid = result["pending"][0]
        deadline = self.store.portfolio()["deadline"]
        # Before expiry, expire is a no-op (state stays pending).
        self.clock[0] = deadline - 1.0
        self.assertNotEqual(world_expire(self.store, oid, actor="operator")["state"], "expired")
        # At/past the portfolio deadline the pending fixture row can be terminalized.
        self.clock[0] = deadline + 1.0
        exp = world_expire(self.store, oid, actor="operator")
        self.assertEqual(exp["state"], "expired")
        self.assertEqual(world_show(self.store, oid)["state"], "expired")

    def test_reingest_within_remaining_portfolio_makes_fresh_pending(self):
        from root_engine.worldmonitor import world_ingest_fixture, world_expire
        result = world_ingest_fixture(self.store, self._batch(1), actor="operator")
        oid = result["pending"][0]
        deadline = self.store.portfolio()["deadline"]
        self.clock[0] = deadline + 1.0
        world_expire(self.store, oid, actor="operator")
        # Re-ingesting before any new deadline is a fresh pending identity (different created).
        self.clock[0] = 2000.0
        second = world_ingest_fixture(self.store, self._batch(1), actor="operator")
        self.assertEqual(len(second["pending"]), 1)

    def test_cli_world_ingest_show_json_and_no_allow(self):
        db = Path(self.temp.name) / "world-cli.sqlite3"
        op = subprocess.run(
            [sys.executable, "-m", "root_engine", "--db", str(db), "init",
             "--objective", "world cli"], capture_output=True, text=True, cwd=PROJECT)
        self.assertEqual(op.returncode, 0, op.stderr)
        run = subprocess.run(
            [sys.executable, "-m", "root_engine", "--db", str(db),
             "world-ingest", "--fixture", str(PROJECT / "examples/world_monitor.synthetic.json")],
            capture_output=True, text=True, cwd=PROJECT)
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(result["mode"], "fixture")
        self.assertEqual(len(result["pending"]), 2)
        oid = result["pending"][0]
        shown = subprocess.run(
            [sys.executable, "-m", "root_engine", "--db", str(db), "world-show", "--id", oid],
            capture_output=True, text=True, cwd=PROJECT)
        self.assertEqual(shown.returncode, 0, shown.stderr)
        payload = json.loads(shown.stdout)
        self.assertEqual(payload["state"], "pending")
        self.assertNotIn("payload", payload)
        # world-allow now exists for live rows; a fixture row is refused via CLI (exit 2).
        denied = subprocess.run(
            [sys.executable, "-m", "root_engine", "--db", str(db), "world-allow", "--id", oid, "--actor", "operator"],
            capture_output=True, text=True, cwd=PROJECT)
        self.assertEqual(denied.returncode, 2, denied.stderr)
        self.assertIn("fixture", denied.stderr.lower())
        # Authoritative tables are untouched.
        s2 = Store(db)
        self.assertEqual(s2.db.execute("SELECT count(*) FROM observations").fetchone()[0], 0)
        s2.close()


if __name__ == "__main__":
    unittest.main()