import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from root_engine.collector import Collector, ENDPOINT, SOURCE
from root_engine.goals import Goals, GitHub, PROJECT, benchmark, run_goal
from root_engine.local_models import RESERVED_TOKENS_PER_CALL
from root_engine.retry_component import active_delay, candidate_delay, extract_parser
from root_engine.store import BudgetError, RootError, Store


class GoalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "goals.sqlite3"
        self.clock = [1000.0]
        policy = json.loads((PROJECT / "examples/self-improvement-policy.json").read_text())
        self.store = Store(self.path, create=True, objective="Improve ROOT's source reliability", policy=policy, now=lambda: self.clock[0])
        self.goals = Goals(self.store)
        self.spec = json.loads((PROJECT / "examples/self_improvement_goal.json").read_text())
        self.fixture = json.loads((PROJECT / "examples/github.synthetic.json").read_text())
        self.goals.create(self.spec)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def opener(self, fixture=None):
        fixture = fixture or self.fixture
        bodies = iter([fixture[key] for key in ("search", "repository", "commit", "readme", "license", "source")])
        def open_response(req, timeout):
            body = next(bodies)
            return io.BytesIO(json.dumps(body).encode() if isinstance(body, dict) else body.encode())
        return open_response

    def test_fixture_run_evaluates_but_cannot_adopt(self):
        result = run_goal(self.goals, self.spec["id"], fixture=self.fixture)
        self.assertEqual(result["state"], "evaluated_fixture")
        self.assertEqual(result["result"]["evaluation"], "pass")
        self.assertEqual(result["result"]["adoption"], "not_adopted")
        self.assertEqual(active_delay(self.store, "900"), 300)
        self.assertEqual(result["requests"], 0)
        self.assertTrue(all(ref["mode"] == "fixture" for ref in result["evidence"]))

    def test_mock_live_pipeline_adopts_only_passing_pinned_component(self):
        result = run_goal(self.goals, self.spec["id"], opener=self.opener())
        self.assertEqual(result["state"], "completed")
        self.assertEqual(result["result"]["adoption"], "enabled_restricted_adapter")
        self.assertEqual(active_delay(self.store, "900"), 900)
        self.assertEqual(result["requests"], 6)
        self.assertEqual(result["requests"], self.store.portfolio()["requests"])
        self.assertEqual(result["downloaded_bytes"], self.store.portfolio()["downloaded_bytes"])
        self.store.close()
        self.store = Store(self.path, now=lambda: self.clock[0])
        self.goals = Goals(self.store)
        self.assertEqual(active_delay(self.store, "900"), 900)
        self.assertEqual(run_goal(self.goals, self.spec["id"])["requests"], 6)

    def test_adopted_component_changes_collector_cooldown_and_rollback_restores_it(self):
        run_goal(self.goals, self.spec["id"], opener=self.opener())
        def forbidden(req, timeout):
            raise urllib.error.HTTPError(req.full_url, 429, "Rate limited", {"Retry-After": "900"}, None)
        with self.assertRaises(RootError):
            Collector(self.store, forbidden).live(ENDPOINT)
        not_before = self.store.db.execute("SELECT not_before FROM source_state WHERE source=?", (SOURCE,)).fetchone()[0]
        self.assertEqual(not_before, self.clock[0] + 900)
        self.goals.rollback(self.spec["id"])
        self.assertEqual(active_delay(self.store, "900"), 300)
        self.assertEqual(self.goals.row(self.spec["id"])["state"], "rolled_back")
        # Rollback does not shorten a cooldown already promised to the source.
        self.assertEqual(self.store.db.execute("SELECT not_before FROM source_state WHERE source=?", (SOURCE,)).fetchone()[0], not_before)

    def test_baseline_and_holdout_measurements_are_recorded(self):
        result = benchmark(self.fixture["source"])
        self.assertEqual(result["development"]["baseline_passes"], 4)
        self.assertEqual(result["holdout"]["baseline_passes"], 3)
        self.assertEqual(result["development"]["candidate_passes"], 6)
        self.assertEqual(result["holdout"]["candidate_passes"], 6)

    def test_unsafe_upstream_function_is_rejected_without_execution(self):
        fixture = copy.deepcopy(self.fixture)
        fixture["source"] = "class Retry:\n def parse_retry_after(self, retry_after):\n  return __import__('os').system('touch should-never-exist')\n"
        result = run_goal(self.goals, self.spec["id"], opener=self.opener(fixture))
        self.assertEqual(result["state"], "stopped")
        self.assertEqual(result["result"]["adoption"], "not_adopted")
        self.assertEqual(active_delay(self.store, "900"), 300)

    def test_full_module_top_level_instructions_are_never_executed(self):
        source = "raise RuntimeError('this module must not run')\n" + self.fixture["source"]
        self.assertEqual(candidate_delay(source, "900", 1000), 900)

    def test_wrong_but_restricted_parser_fails_and_is_not_adopted(self):
        fixture = copy.deepcopy(self.fixture)
        fixture["source"] = "class Retry:\n def parse_retry_after(self, retry_after):\n  return 300\n"
        result = run_goal(self.goals, self.spec["id"], opener=self.opener(fixture))
        self.assertEqual(result["result"]["evaluation"], "fail")
        self.assertEqual(result["result"]["adoption"], "not_adopted")
        self.assertEqual(active_delay(self.store, "900"), 300)

    def test_goal_allowances_cannot_be_overwritten(self):
        with self.assertRaisesRegex(RootError, "already exists"):
            self.goals.create(self.spec)
        bad = dict(self.spec, id="over-budget", max_requests=13)
        with self.assertRaises(RootError):
            self.goals.create(bad)

    def test_goal_request_limit_applies_before_network_call(self):
        limited = dict(self.spec, id="no-network", max_requests=0)
        self.goals.create(limited)
        calls = []
        def should_not_run(req, timeout):
            calls.append(req)
            return io.BytesIO(b"{}")
        result = run_goal(self.goals, limited["id"], opener=should_not_run)
        self.assertEqual(result["state"], "stopped")
        self.assertEqual(calls, [])
        self.assertEqual(result["requests"], 0)

    def test_goal_bytes_limit_counts_failed_partial_download(self):
        limited = dict(self.spec, id="small-body", max_download_bytes=10)
        self.goals.create(limited)
        result = run_goal(self.goals, limited["id"], opener=self.opener())
        self.assertEqual(result["state"], "stopped")
        self.assertEqual(result["downloaded_bytes"], 10)
        self.assertEqual(self.store.portfolio()["downloaded_bytes"], 10)
        self.assertEqual(result["evidence"], [])

    def test_local_inference_reservations_are_independent_of_model_text(self):
        self.goals.reserve_inference(self.spec["id"])
        self.goals.reserve_inference(self.spec["id"])
        with self.assertRaises(BudgetError):
            self.goals.reserve_inference(self.spec["id"])
        second = dict(self.spec, id="second-goal")
        self.goals.create(second)
        with self.assertRaises(BudgetError):
            self.goals.reserve_inference(second["id"])
        self.assertEqual(self.goals.row(self.spec["id"])["inference_reserved"], 2 * RESERVED_TOKENS_PER_CALL)

    def mid_model(self):
        model = Path(self.temp.name) / "mid.gguf"
        with model.open("wb") as handle:
            handle.truncate(600 * 1024 * 1024)
        return model

    def test_mid_model_refuses_small_budget_before_discovery_or_inference(self):
        spec = dict(self.spec, id="mid-over-budget", model_path=str(self.mid_model()))
        self.goals.create(spec)
        with patch("root_engine.goals.classify") as classify:
            result = run_goal(self.goals, spec["id"], local_review=True,
                              opener=lambda *args: self.fail("No discovery permitted before reservation"))
        classify.assert_not_called()
        self.assertEqual(result["state"], "stopped")
        self.assertEqual(result["inference_reserved"], 0)
        self.assertEqual(result["requests"], 0)

    def test_mid_model_selection_and_reservation_use_same_plan(self):
        policy = dict(self.store.portfolio()["policy"], max_inference_tokens=4480)
        store = Store(Path(self.temp.name) / "mid.sqlite3", create=True, objective="Bounded model trial",
                      policy=policy, now=lambda: self.clock[0])
        self.addCleanup(store.close)
        goals = Goals(store)
        model = self.mid_model()
        spec = dict(self.spec, id="mid-review", model_path=str(model), max_inference_tokens=4480)
        created = goals.create(spec)
        self.assertEqual(created["spec"]["model_path"], str(model.resolve()))
        with patch("root_engine.goals.classify", side_effect=[
                {"output": {"fit": True, "reason": "retry"}},
                {"output": {"fit": False, "reason": "wallpaper"}}]) as classify:
            result = run_goal(goals, spec["id"], fixture=self.fixture, local_review=True)
        self.assertEqual(result["inference_reserved"], 4480)
        self.assertEqual(classify.call_count, 2)
        for call in classify.call_args_list:
            self.assertEqual(call.kwargs["model"], model.resolve())
            self.assertEqual(call.kwargs["plan"], created["spec"]["inference_plan"])
        second = dict(spec, id="portfolio-exhausted")
        goals.create(second)
        with patch("root_engine.goals.classify") as classify:
            stopped = run_goal(goals, second["id"], fixture=self.fixture, local_review=True)
        classify.assert_not_called()
        self.assertEqual(stopped["inference_reserved"], 0)
        self.assertEqual(stopped["state"], "stopped")

    def test_changed_model_resources_refuse_execution(self):
        model = self.mid_model()
        spec = dict(self.spec, id="changed-model", model_path=str(model))
        self.goals.create(spec)
        model.write_bytes(b"different size")
        with patch("root_engine.goals.classify") as classify:
            result = run_goal(self.goals, spec["id"], fixture=self.fixture, local_review=True)
        classify.assert_not_called()
        self.assertIn("changed after goal creation", result["result"]["error"])
        self.assertEqual(result["inference_reserved"], 0)

    def test_failed_reviews_keep_full_reservation(self):
        model = Path(self.temp.name) / "small.gguf"
        model.write_bytes(b"placeholder")
        with patch("root_engine.goals.DEFAULT_MODEL", model), patch("root_engine.goals.classify", side_effect=RootError("runtime failed")):
            result = run_goal(self.goals, self.spec["id"], fixture=self.fixture, local_review=True)
        self.assertEqual(result["inference_reserved"], 2304)
        reviews = next(e["payload"] for e in result["events"] if e["stage"] == "advisory_review")
        self.assertTrue(all("uncertain" in item for item in reviews))

    def test_cli_binds_selected_model_when_creating_goal(self):
        # CLI creation uses the real clock, so give this isolated portfolio a real deadline.
        db = Path(self.temp.name) / "cli.sqlite3"
        store = Store(db, create=True, objective="Model selection", policy=self.store.portfolio()["policy"])
        store.close()
        model = self.mid_model()
        result = subprocess.run([sys.executable, "-m", "root_engine", "--db", str(db), "goal-create",
                                 "--file", str(PROJECT / "examples/self_improvement_goal.json"), "--model", str(model)],
                                capture_output=True, text=True, cwd=PROJECT)
        self.assertEqual(result.returncode, 0, result.stderr)
        spec = json.loads(result.stdout)["spec"]
        self.assertEqual(spec["model_path"], str(model.resolve()))
        self.assertEqual(spec["inference_plan"]["context"], 2048)

    def test_license_and_revision_requirements_are_enforced(self):
        for key, value in (("repository", {**self.fixture["repository"], "license": {"spdx_id": "NOASSERTION"}}), ("commit", {"sha": "main"})):
            fixture = dict(self.fixture, **{key: value})
            spec = dict(self.spec, id="license-test-" + key)
            self.goals.create(spec)
            with self.assertRaises(RootError):
                GitHub(self.goals, spec["id"], fixture=fixture).discover(spec["search_query"])

    def test_goal_deadline_prevents_new_work(self):
        self.clock[0] = self.goals.row(self.spec["id"])["deadline"]
        with self.assertRaises(BudgetError):
            run_goal(self.goals, self.spec["id"], fixture=self.fixture)

    def test_nested_functions_and_attribute_writes_are_rejected(self):
        for source in ("class Retry:\n def parse_retry_after(self,retry_after):\n  def max():\n   return 300\n  return max()\n", "class Retry:\n def parse_retry_after(self,retry_after):\n  self.retry_after_max = 0\n  return 0\n"):
            with self.assertRaises(RootError):
                extract_parser(source)

    def test_predeclared_query_fallback_is_bounded_and_recorded(self):
        fixture = dict(self.fixture, search={"items": []}, fallback_search=self.fixture["search"])
        result = run_goal(self.goals, self.spec["id"], fixture=fixture)
        stages = {event["stage"] for event in result["events"]}
        self.assertIn("repository_search_1", stages)
        self.assertIn("repository_search_2", stages)
        self.assertEqual(result["result"]["adoption"], "not_adopted")

    def test_already_satisfied_goal_does_not_repeat_discovery_or_adoption(self):
        run_goal(self.goals, self.spec["id"], opener=self.opener())
        second = dict(self.spec, id="no-duplicate-improvement")
        self.goals.create(second)
        result = run_goal(self.goals, second["id"], opener=lambda *args, **kwargs: self.fail("No new requests expected"))
        self.assertEqual(result["result"]["evaluation"], "already_satisfied")
        self.assertEqual(result["requests"], 0)

    def test_rollback_is_available_after_budgets_expire(self):
        run_goal(self.goals, self.spec["id"], opener=self.opener())
        self.clock[0] = self.store.portfolio()["deadline"] + 1
        self.goals.rollback(self.spec["id"])
        self.assertEqual(active_delay(self.store, "900"), 300)

    def test_goal_record_storage_budget_is_independently_enforced(self):
        limited = dict(self.spec, id="small-storage", max_storage_bytes=16384)
        self.goals.create(limited)
        with self.assertRaisesRegex(BudgetError, "record-storage"):
            self.goals.evidence(limited["id"], "https://api.github.com/test", "x" * 20000, "fixture")
        self.assertEqual(self.goals.view(limited["id"])["evidence"], [])

    def test_goal_creation_records_predeclared_case_digests(self):
        manifest = self.goals.row(self.spec["id"])["spec"]["evaluation_manifest"]
        self.assertEqual(set(manifest), {"development", "holdout"})
        self.assertTrue(all(len(value) == 64 for value in manifest.values()))


if __name__ == "__main__":
    unittest.main()
