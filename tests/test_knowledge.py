"""Behavioral contracts for evidence-only learning (plan task 1 — tests before implementation)."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from root_engine.goals import PROJECT
from root_engine.retry_component import active_delay
from root_engine.store import Store


@unittest.skip("Deferred to plan task 7 (learning loop); tasks 1–5 cover promotion core only.")
class KnowledgeContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "knowledge.sqlite3"
        self.clock = [1000.0]
        policy = json.loads((PROJECT / "examples/self-improvement-policy.json").read_text())
        self.store = Store(
            self.path,
            create=True,
            objective="Knowledge contract tests",
            policy=policy,
            now=lambda: self.clock[0],
        )

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_learn_create_cli_exists(self):
        result = subprocess.run(
            [sys.executable, "-m", "root_engine", "learn-create", "--help"],
            capture_output=True,
            text=True,
            cwd=PROJECT,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_learn_run_cli_exists(self):
        result = subprocess.run(
            [sys.executable, "-m", "root_engine", "learn-run", "--help"],
            capture_output=True,
            text=True,
            cwd=PROJECT,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_learning_records_are_evidence_only_authority(self):
        from root_engine.knowledge import AUTHORITY_EVIDENCE_ONLY

        self.assertEqual(AUTHORITY_EVIDENCE_ONLY, "evidence_only")

    def test_successful_fixture_learn_creates_no_component_or_promotion(self):
        from root_engine.knowledge import Learning, run_learning_request

        fixture = {
            "readme": "# stub\n",
            "license": "MIT\n",
            "source": "class Retry:\n def parse_retry_after(self, retry_after):\n  return 900\n",
        }
        spec = {
            "id": "unsupported-adapter-contract",
            "kind": "unsupported_adapter_research_v1",
            "trigger": "unknown_adapter_v9",
            "parent_objective": "test",
            "need": "document unsupported adapter",
            "practice_fixture": "inline",
            "acceptance": "retain provenance",
            "max_requests": 0,
            "max_download_bytes": 0,
            "max_storage_bytes": 65536,
            "max_elapsed_seconds": 3600,
            "max_inference_tokens": 0,
            "max_money_gbp": 0,
            "max_concurrent_jobs": 1,
        }
        learning = Learning(self.store)
        learning.create(spec)
        run_learning_request(learning, spec["id"], fixture=fixture)
        self.assertEqual(active_delay(self.store, "900"), 300)
        if self.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='components'").fetchone():
            self.assertEqual(self.store.db.execute("SELECT count(*) FROM components").fetchone()[0], 0)
        if self.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='promotions'").fetchone():
            self.assertEqual(self.store.db.execute("SELECT count(*) FROM promotions").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
