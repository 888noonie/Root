"""heartbeat-once CLI: run at most one deterministic due job, no daemon (Task F — RED first)."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from root_engine.goals import PROJECT
from root_engine.store import Store


def _policy(**over):
    base = {
        "max_money_gbp": 0, "max_requests": 3, "max_download_bytes": 2 * 1024 * 1024,
        "max_storage_bytes": 16 * 1024 * 1024, "max_inference_tokens": 0,
        "max_elapsed_seconds": 3600, "max_concurrent_jobs": 1,
    }
    base.update(over)
    return base


class HeartbeatOnceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "heartbeat.sqlite3"
        self.clock = [1000.0]
        self.store = Store(self.path, create=True, objective="heartbeat tests",
                           policy=_policy(), now=lambda: self.clock[0])

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_heartbeat_runs_table_exists_after_first_tick(self):
        from root_engine.heartbeat import tick_once
        out = tick_once(self.store)
        self.assertIn("tick", out)
        self.assertEqual(self.store.db.execute(
            "SELECT count(*) FROM sqlite_master WHERE name='heartbeat_runs'").fetchone()[0], 1)

    def test_double_invocation_does_not_double_collect(self):
        from root_engine.heartbeat import tick_once
        first = tick_once(self.store)
        second = tick_once(self.store)
        # within the same cooldown window the second invocation must not run a second job
        self.assertEqual(first.get("ran"), second.get("ran", "n/a"))
        self.assertGreaterEqual(second.get("already_run_in_window", 0), 1)

    def test_job_window_split(self):
        # advance past the cooldown; a fresh job is due
        from root_engine.heartbeat import COOLDOWN_SECONDS, tick_once
        tick_once(self.store)
        self.clock[0] += COOLDOWN_SECONDS + 1
        out = tick_once(self.store)
        self.assertIn("tick", out)

    def test_expired_portfolio_blocks_work(self):
        from root_engine.store import BudgetError
        from root_engine.heartbeat import tick_once
        deadline = self.store.portfolio()["deadline"]
        self.clock[0] = deadline + 10
        with self.assertRaisesRegex(BudgetError, "deadline"):
            tick_once(self.store)

    def test_uninterrupted_no_daemon_persists_no_running_flag(self):
        # a long-running background process is never started
        from root_engine.heartbeat import tick_once
        tick_once(self.store)
        # no lease/token remains held after a normal tick
        held = self.store.db.execute("SELECT count(*) FROM lease").fetchone()[0]
        self.assertEqual(held, 0)

    def test_cli_heartbeat_once_exists(self):
        result = subprocess.run(
            [sys.executable, "-m", "root_engine", "heartbeat-once", "--help"],
            capture_output=True, text=True, cwd=PROJECT)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_cli_heartbeat_on_empty_db_reports_no_due_work(self):
        db = Path(self.temp.name) / "hb-cli.sqlite3"
        subprocess.run([sys.executable, "-m", "root_engine", "--db", str(db), "init",
                        "--objective", "hb", "--policy", str(PROJECT / "examples/self-improvement-policy.json")],
                       capture_output=True, text=True, cwd=PROJECT, check=True)
        out = subprocess.run([sys.executable, "-m", "root_engine", "--db", str(db), "heartbeat-once"],
                             capture_output=True, text=True, cwd=PROJECT)
        self.assertEqual(out.returncode, 0, out.stderr)
        payload = json.loads(out.stdout)
        self.assertIn("tick", payload)


if __name__ == "__main__":
    unittest.main()