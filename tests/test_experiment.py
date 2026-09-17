"""Local tender-experiment runner (Task G — RED first). No outreach, no send.

Stores a hypothesis, a declared baseline (e.g. operator minutes saved, marked unknown),
and a pass/fail/uncertain outcome with evidence refs. It can never create components or
promotions and never contacts anyone.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from root_engine.goals import PROJECT
from root_engine.store import RootError, Store


class ExperimentRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "experiment.sqlite3"
        self.clock = [1000.0]
        self.store = Store(self.path, create=True, objective="experiment tests", now=lambda: self.clock[0])

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def _spec(self, eid="tender-preview-usefulness"):
        return {
            "id": eid,
            "kind": "tender_preview_usefulness_v1",
            "hypothesis": "The preview reduces operator effort to find actionable transport opportunities.",
            "baseline_metric": {"name": "operator_minutes_per_week", "value": None,
                                "note": "declared unknown pending an operator interview"},
            "evidence_refs": [],
            "pass_criterion": "operator reports a measurable effort reduction without prompting for more",
            "fail_criterion": "operator reports no effort reduction or rejects the preview",
            "max_elapsed_seconds": 3600,
            "zero_money_gbp": True,
        }

    def test_create_and_show(self):
        from root_engine.experiment import Experiments
        spec = self._spec()
        Experiments(self.store).create(spec)
        shown = Experiments(self.store).show(spec["id"])
        self.assertEqual(shown["state"], "created")
        self.assertEqual(shown["kind"], "tender_preview_usefulness_v1")
        # baseline metric is declared unknown, not zero-filled
        self.assertIsNone(shown["baseline_metric"]["value"])

    def test_run_records_pass_with_evidence(self):
        from root_engine.experiment import Experiments
        spec = self._spec()
        Experiments(self.store).create(spec)
        out = Experiments(self.store).run(
            spec["id"],
            outcome="pass",
            evidence_refs=["evt-1", "evt-2"],
            note="operator interview transcribed and agreed to continue",
        )
        self.assertEqual(out["state"], "completed")
        self.assertEqual(out["token_issue"], "pass")
        self.assertEqual(out["evidence_refs"], ["evt-1", "evt-2"])

    def test_run_records_uncertain_without_demand(self):
        from root_engine.experiment import Experiments
        spec = self._spec()
        Experiments(self.store).create(spec)
        out = Experiments(self.store).run(spec["id"], outcome="uncertain", note="compliment only; not payment interest")
        self.assertEqual(out["state"], "completed")
        self.assertEqual(out["token_issue"], "uncertain")

    def test_duplicate_run_rejected(self):
        from root_engine.experiment import Experiments
        spec = self._spec()
        Experiments(self.store).create(spec)
        Experiments(self.store).run(spec["id"], outcome="pass", note="done")
        with self.assertRaisesRegex(RootError, "already"):
            Experiments(self.store).run(spec["id"], outcome="pass", note="again")

    def test_creates_no_component_or_promotion(self):
        from root_engine.experiment import Experiments
        spec = self._spec()
        Experiments(self.store).create(spec)
        Experiments(self.store).run(spec["id"], outcome="uncertain", note="no demand")
        if self.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='components'").fetchone():
            self.assertEqual(self.store.db.execute("SELECT count(*) FROM components").fetchone()[0], 0)
        if self.store.db.execute("SELECT 1 FROM sqlite_master WHERE name='promotions'").fetchone():
            self.assertEqual(self.store.db.execute("SELECT count(*) FROM promotions").fetchone()[0], 0)

    def test_invalid_outcome_rejected(self):
        from root_engine.experiment import Experiments
        spec = self._spec()
        Experiments(self.store).create(spec)
        with self.assertRaisesRegex(RootError, "pass|fail|uncertain"):
            Experiments(self.store).run(spec["id"], outcome="definitely-sold")

    def test_cli_experiment_commands_exist(self):
        for sub in ("experiment-create", "experiment-run", "experiment-show"):
            result = subprocess.run([sys.executable, "-m", "root_engine", sub, "--help"],
                                    capture_output=True, text=True, cwd=PROJECT)
            self.assertEqual(result.returncode, 0, f"{sub}: {result.stderr}")

    def test_cli_experiment_lifecycle(self):
        db = Path(self.temp.name) / "exp-cli.sqlite3"
        subprocess.run([sys.executable, "-m", "root_engine", "--db", str(db), "init",
                        "--objective", "exp cli"], capture_output=True, text=True, cwd=PROJECT, check=True)
        created = subprocess.run(
            [sys.executable, "-m", "root_engine", "--db", str(db), "experiment-create",
             "--file", str(PROJECT / "examples/tender_usage_experiment.spec.json")],
            capture_output=True, text=True, cwd=PROJECT)
        self.assertEqual(created.returncode, 0, created.stderr)
        self.assertEqual(json.loads(created.stdout)["state"], "created")
        ran = subprocess.run(
            [sys.executable, "-m", "root_engine", "--db", str(db), "experiment-run",
             "--id", "tender-preview-usefulness", "--outcome", "uncertain", "--note", "compliment only"],
            capture_output=True, text=True, cwd=PROJECT)
        self.assertEqual(ran.returncode, 0, ran.stderr)
        self.assertEqual(json.loads(ran.stdout)["token_issue"], "uncertain")
        shown = subprocess.run(
            [sys.executable, "-m", "root_engine", "--db", str(db), "experiment-show",
             "--id", "tender-preview-usefulness"],
            capture_output=True, text=True, cwd=PROJECT)
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertEqual(json.loads(shown.stdout)["state"], "completed")

    def test_cli_experiment_fail_exit_1(self):
        db = Path(self.temp.name) / "exp-fail.sqlite3"
        subprocess.run([sys.executable, "-m", "root_engine", "--db", str(db), "init",
                        "--objective", "exp fail"], capture_output=True, text=True, cwd=PROJECT, check=True)
        subprocess.run([sys.executable, "-m", "root_engine", "--db", str(db), "experiment-create",
                        "--file", str(PROJECT / "examples/tender_usage_experiment.spec.json")],
                       capture_output=True, text=True, cwd=PROJECT, check=True)
        ran = subprocess.run(
            [sys.executable, "-m", "root_engine", "--db", str(db), "experiment-run",
             "--id", "tender-preview-usefulness", "--outcome", "fail", "--note", "no reduction"],
            capture_output=True, text=True, cwd=PROJECT)
        self.assertEqual(ran.returncode, 1)
        self.assertEqual(json.loads(ran.stdout)["token_issue"], "fail")


if __name__ == "__main__":
    unittest.main()