"""Bounded live world ingest into pending (Task D — RED first).

Uses the existing collector fetch machinery (single shared Contracts Finder allowlist,
budgets, timeouts) to fetch one OCDS package and route its releases into the world
pending gate with mode=live — never into observations until an explicit world-allow.
CI uses fixture replay of the recorded package; no live request is made.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from root_engine.collector import ENDPOINT, search_url, validate_package
from root_engine.goals import PROJECT
from root_engine.store import RootError, Store
from root_engine.worldmonitor import world_show


class _ReplayOpener:
    """Opener that returns a locally recorded OCDS search package, no network."""

    def __init__(self, package):
        import io
        self.body = json.dumps(package).encode("utf-8")

    def __call__(self, req, timeout=None):
        import io
        return io.BytesIO(self.body)


def _package():
    return json.loads((PROJECT / "examples/contracts_finder.synthetic.json").read_text())


def _replay_package():
    pkg = _package()
    pkg["uri"] = search_url("2026-09-14T00:00:00Z", "2026-09-15T00:00:00Z", 20)
    return pkg


class WorldLiveIngestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "world-live.sqlite3"
        self.clock = [1000.0]
        self.store = Store(self.path, create=True, objective="world live ingest tests", now=lambda: self.clock[0])

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_live_replay_ingest_goes_pending_not_observations(self):
        from root_engine.worldmonitor import world_ingest_live
        result = world_ingest_live(
            self.store, "2026-09-14T00:00:00Z", "2026-09-15T00:00:00Z",
            actor="operator", opener=_ReplayOpener(_replay_package()))
        self.assertEqual(result["mode"], "live")
        self.assertGreaterEqual(len(result["pending"]), 1)
        # authoritative observations/packages untouched
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM observations").fetchone()[0], 0)
        self.assertNotIn("package_id", result)
        # pending rows are mode=live
        modes = {r[0] for r in self.store.db.execute("SELECT mode FROM world_pending_observations")}
        self.assertEqual(modes, {"live"})

    def test_live_replay_rows_can_be_allowed(self):
        from root_engine.worldmonitor import world_allow, world_ingest_live
        result = world_ingest_live(
            self.store, "2026-09-14T00:00:00Z", "2026-09-15T00:00:00Z",
            actor="operator", opener=_ReplayOpener(_replay_package()))
        oid = result["pending"][0]
        allowed = world_allow(self.store, oid, actor="operator")
        self.assertEqual(allowed["state"], "allowed")
        # one authoritative observation inserted only for the allowed row
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM observations").fetchone()[0], 1)
        # world-show still strips bytes after allow
        self.assertNotIn("payload", world_show(self.store, oid))

    def test_rejects_non_allowlisted_url(self):
        from root_engine.worldmonitor import world_ingest_live
        with self.assertRaisesRegex(RootError, "allowlist|endpoint|host"):
            world_ingest_live(
                self.store, "2026-09-14T00:00:00Z", "2026-09-15T00:00:00Z",
                actor="operator", opener=_ReplayOpener(_replay_package()),
                source_url="https://evil.example.com/not/allowlisted")

    def test_malformed_package_refused_no_pending(self):
        from root_engine.worldmonitor import world_ingest_live
        bad = _package()
        bad["releases"] = "nope"
        with self.assertRaisesRegex(RootError, "OCDS|releases"):
            world_ingest_live(
                self.store, "2026-09-14T00:00:00Z", "2026-09-15T00:00:00Z",
                actor="operator", opener=_ReplayOpener(bad))
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM world_pending_observations").fetchone()[0], 0)

    def test_pending_bytes_match_recorded_package_exact(self):
        from root_engine.worldmonitor import world_ingest_live
        result = world_ingest_live(
            self.store, "2026-09-14T00:00:00Z", "2026-09-15T00:00:00Z",
            actor="operator", opener=_ReplayOpener(_replay_package()))
        oid = result["pending"][0]
        row = self.store.db.execute("SELECT payload,payload_sha256 FROM world_pending_observations WHERE id=?", (oid,)).fetchone()
        import hashlib
        self.assertEqual(hashlib.sha256(row["payload"].encode()).hexdigest(), row["payload_sha256"])


if __name__ == "__main__":
    unittest.main()