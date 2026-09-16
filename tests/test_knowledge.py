"""Behavioral contracts for evidence-only learning (plan task 7 — RED first)."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from root_engine.goals import PROJECT
from root_engine.retry_component import active_delay
from root_engine.store import Store


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

    def test_learn_show_cli_and_record(self):
        from root_engine.knowledge import Learning
        spec = {
            "id": "show", "kind": "unsupported_adapter_research_v1", "trigger": "t",
            "parent_objective": "po", "need": "n", "practice_fixture": "inline",
            "acceptance": "a", "max_requests": 0, "max_download_bytes": 0,
            "max_storage_bytes": 65536, "max_elapsed_seconds": 3600,
            "max_inference_tokens": 0, "max_money_gbp": 0, "max_concurrent_jobs": 1,
        }
        Learning(self.store).create(spec)
        result = subprocess.run(
            [sys.executable, "-m", "root_engine", "--db", str(self.path), "learn-show", "--id", "show"],
            capture_output=True, text=True, cwd=PROJECT,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["state"], "created")

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

    def test_replay_blocked_after_completed(self):
        from root_engine.knowledge import Learning, run_learning_request
        from root_engine.store import RootError
        spec = {
            "id": "replay", "kind": "unsupported_adapter_research_v1", "trigger": "t",
            "parent_objective": "po", "need": "n", "practice_fixture": "inline",
            "acceptance": "a", "max_requests": 0, "max_download_bytes": 0,
            "max_storage_bytes": 65536, "max_elapsed_seconds": 3600,
            "max_inference_tokens": 0, "max_money_gbp": 0, "max_concurrent_jobs": 1,
        }
        learning = Learning(self.store)
        learning.create(spec)
        run_learning_request(learning, spec["id"], fixture={"readme": "# stub\n", "license": "MIT\n", "source": "class Retry:\n def parse_retry_after(self, retry_after):\n  return 900\n"})
        with self.assertRaisesRegex(RootError, "only 'created'"):
            run_learning_request(learning, spec["id"], fixture={})

    def test_live_mode_refused(self):
        from root_engine.knowledge import Learning, run_learning_request
        from root_engine.store import RootError
        spec = {
            "id": "live-refuse", "kind": "unsupported_adapter_research_v1", "trigger": "t",
            "parent_objective": "po", "need": "n", "practice_fixture": "inline",
            "acceptance": "a", "max_requests": 0, "max_download_bytes": 0,
            "max_storage_bytes": 65536, "max_elapsed_seconds": 3600,
            "max_inference_tokens": 0, "max_money_gbp": 0, "max_concurrent_jobs": 1,
        }
        learning = Learning(self.store)
        learning.create(spec)
        with self.assertRaisesRegex(RootError, "Live learning retrieval not implemented"):
            run_learning_request(learning, spec["id"], fixture=None)
        self.assertEqual(learning.row(spec["id"])["state"], "failed")

    def test_budget_violation_blocks_creation(self):
        from root_engine.knowledge import Learning
        from root_engine.store import RootError
        spec = {
            "id": "budget", "kind": "unsupported_adapter_research_v1", "trigger": "t",
            "parent_objective": "po", "need": "n", "practice_fixture": "inline",
            "acceptance": "a", "max_requests": 0, "max_download_bytes": 0,
            "max_storage_bytes": 65536, "max_elapsed_seconds": 3600,
            "max_inference_tokens": 0, "max_money_gbp": 1, "max_concurrent_jobs": 1,
        }
        learning = Learning(self.store)
        with self.assertRaisesRegex(RootError, "zero spending"):
            learning.create(spec)

    def test_learning_result_is_evidence_only(self):
        from root_engine.knowledge import Learning, run_learning_request, AUTHORITY_EVIDENCE_ONLY
        spec = {
            "id": "evidence-only", "kind": "unsupported_adapter_research_v1", "trigger": "t",
            "parent_objective": "po", "need": "n", "practice_fixture": "inline",
            "acceptance": "a", "max_requests": 0, "max_download_bytes": 0,
            "max_storage_bytes": 65536, "max_elapsed_seconds": 3600,
            "max_inference_tokens": 0, "max_money_gbp": 0, "max_concurrent_jobs": 1,
        }
        learning = Learning(self.store)
        learning.create(spec)
        run_learning_request(learning, spec["id"], fixture={"readme": "# stub\n", "license": "MIT\n", "source": "class Retry:\n def parse_retry_after(self, retry_after):\n  return 900\n"})
        result = learning.row(spec["id"])["result"]
        self.assertEqual(result["authority"], AUTHORITY_EVIDENCE_ONLY)
        records = [dict(r) for r in self.store.db.execute("SELECT * FROM knowledge_records WHERE request_id=?", (spec["id"],))]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["authority"], AUTHORITY_EVIDENCE_ONLY)

    def test_learning_does_not_import_promotion_module(self):
        import ast
        path = PROJECT / "root_engine" / "knowledge.py"
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                self.assertNotIn("promotion", node.module)


if __name__ == "__main__":
    unittest.main()
