"""Promotion brake contracts and adversarial guarantees."""

import ast
import hashlib
import io
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from root_engine.constitution import TRUSTED_RELATIVE_PATHS, trusted_manifest
from root_engine.goals import GOAL_SCHEMA, Goals, PROJECT, run_goal
from root_engine.promotion import (
    PromotionClosed,
    _reevaluate_artifact,
    create_pending_retry_after,
    promote_allow,
    deny,
    show,
)
from root_engine.retry_component import COMPONENT, active_delay
from root_engine.store import RootError, SCHEMA, Store, digest, encode


class PromotionContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "promotion.sqlite3"
        self.clock = [1000.0]
        policy = json.loads((PROJECT / "examples/self-improvement-policy.json").read_text())
        self.store = Store(
            self.path,
            create=True,
            objective="Promotion contract tests",
            policy=policy,
            now=lambda: self.clock[0],
        )
        self.goals = Goals(self.store)
        self.spec = json.loads((PROJECT / "examples/self_improvement_goal.json").read_text())
        self.fixture = json.loads((PROJECT / "examples/github.synthetic.json").read_text())
        self.goals.create(self.spec)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def opener(self, fixture=None):
        fixture = fixture or self.fixture
        bodies = iter(
            [fixture[key] for key in ("search", "repository", "commit", "readme", "license", "source")]
        )

        def open_response(req, timeout):
            body = next(bodies)
            return io.BytesIO(json.dumps(body).encode() if isinstance(body, dict) else body.encode())

        return open_response

    def _rows(self):
        return [dict(row) for row in self.store.db.execute("SELECT * FROM promotions")]

    def _pending(self):
        return run_goal(self.goals, self.spec["id"], opener=self.opener())

    def test_fixture_pass_is_explicitly_non_promotable(self):
        result = run_goal(self.goals, self.spec["id"], fixture=self.fixture)
        self.assertEqual(result["state"], "evaluated_fixture")
        self.assertEqual(result["result"]["evaluation"], "pass")
        self.assertEqual(result["result"].get("promotable"), False)

    def test_fixture_pass_creates_no_promotion_row(self):
        run_goal(self.goals, self.spec["id"], fixture=self.fixture)
        self.assertEqual(self._rows(), [])

    def test_fixture_forged_promotion_cannot_be_allowed(self):
        run_goal(self.goals, self.spec["id"], fixture=self.fixture)
        artifact = self.fixture["source"].encode()
        self.store.db.execute(
            """INSERT INTO promotions(
                id, goal_id, target, artifact_kind, artifact, artifact_sha256, source_url, upstream_revision, license,
                mode, evaluation_manifest, evaluation_receipt, trusted_manifest, baseline_component_id,
                state, created, expires
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "forged-fixture",
                self.spec["id"],
                "retry_after_parser",
                "restricted_retry_after_source",
                artifact,
                hashlib.sha256(artifact).hexdigest(),
                "https://raw.githubusercontent.com/urllib3/urllib3/000/src/urllib3/util/retry.py",
                "0" * 40,
                self.fixture["license"],
                "fixture",
                encode(self.goals.row(self.spec["id"])["spec"]["evaluation_manifest"]),
                encode({"evaluation": "pass"}),
                encode(trusted_manifest()),
                None,
                "pending",
                self.clock[0],
                self.clock[0] + 800,
            ),
        )
        with self.assertRaisesRegex(RootError, "Fixture"):
            promote_allow(self.store, "forged-fixture", actor="test")
        self.assertEqual(active_delay(self.store, "900"), 300)
        self.assertIsNone(self.store.db.execute("SELECT id FROM components WHERE active=1").fetchone())

    def test_unknown_promotion_rejected(self):
        with self.assertRaisesRegex(RootError, "Unknown promotion"):
            promote_allow(self.store, "missing", actor="test")

    def test_database_rejects_invalid_promotion_state_and_digests(self):
        pending = self._pending()
        pid = pending["result"]["promotion_id"]
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.db.execute("UPDATE promotions SET state='bogus' WHERE id=?", (pid,))
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.db.execute("UPDATE promotions SET artifact_sha256='bad' WHERE id=?", (pid,))

    def test_mock_live_pass_leaves_collector_on_baseline_until_allow(self):
        result = self._pending()
        self.assertEqual(result["result"]["adoption"], "pending_operator")
        self.assertEqual(active_delay(self.store, "900"), 300)
        self.assertEqual(self._rows()[0]["state"], "pending")
        promote_allow(self.store, result["result"]["promotion_id"], actor="test-operator")
        self.assertEqual(active_delay(self.store, "900"), 900)
        receipt = self.store.db.execute(
            "SELECT payload FROM promotion_events WHERE promotion_id=? AND stage='evaluation_passed'",
            (result["result"]["promotion_id"],),
        ).fetchone()
        self.assertEqual(json.loads(receipt["payload"])["stderr_tail"], "")

    def test_custom_pinned_case_files_are_used_for_goal_and_promotion_recheck(self):
        spec = dict(
            self.spec,
            id="custom-pinned-cases",
            evaluation_files={
                "development": "retry_after.holdout.json",
                "holdout": "retry_after.development.json",
            },
        )
        self.goals.create(spec)
        pending = run_goal(self.goals, spec["id"], opener=self.opener())
        self.assertEqual(pending["state"], "pending_promotion")
        promote_allow(self.store, pending["result"]["promotion_id"], actor="operator")
        self.assertEqual(active_delay(self.store, "900"), 900)

    def test_pending_survives_restart_and_replay_is_idempotent(self):
        first = self._pending()
        requests = first["requests"]
        self.store.close()
        self.store = Store(self.path, now=lambda: self.clock[0])
        self.goals = Goals(self.store)
        self.assertEqual(active_delay(self.store, "900"), 300)
        replay = run_goal(self.goals, self.spec["id"], opener=lambda *a, **k: self.fail("replay must not discover"))
        self.assertEqual(replay["requests"], requests)
        self.assertEqual(replay["state"], "pending_promotion")
        self.assertEqual(len(self._rows()), 1)

    def test_show_projection_excludes_artifact_and_license(self):
        pending = self._pending()
        view = show(self.store, pending["result"]["promotion_id"])
        self.assertNotIn("artifact", view)
        self.assertNotIn("license", view)
        self.assertNotIn("trusted_manifest", view)
        json.dumps(view)
        self.assertEqual(view["state"], "pending")
        self.assertEqual(view["artifact_bytes"], len(self.fixture["source"].encode()))

    def test_evaluator_entrypoint_does_not_import_promotion_module(self):
        path = PROJECT / "root_engine" / "evaluate_component.py"
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotIn("promotion", alias.name)
            if isinstance(node, ast.ImportFrom) and node.module:
                self.assertNotIn("promotion", node.module)

    def test_promotion_recheck_parses_and_executes_only_in_trusted_snapshot_subprocess(self):
        manifest = self.goals.row(self.spec["id"])["spec"]["evaluation_manifest"]
        with patch("root_engine.promotion.extract_parser", side_effect=AssertionError("parent parse"), create=True), \
             patch("root_engine.promotion.benchmark", side_effect=AssertionError("live benchmark"), create=True):
            measured = _reevaluate_artifact(
                self.fixture["source"],
                manifest,
                trusted=trusted_manifest(),
            )
        self.assertEqual(measured["development"]["candidate_passes"], measured["development"]["total"])

    def test_notify_fake_hermes_success(self):
        pending = self._pending()
        pid = pending["result"]["promotion_id"]
        fake = Path(self.temp.name) / "fake-hermes"
        fake.write_text('#!/bin/sh\necho \'{"success":true,"delivery_id":"test-1"}\'')
        fake.chmod(0o755)
        result = subprocess.run(
            [sys.executable, "-m", "root_engine", "--db", str(self.store.path),
             "promote-notify", "--id", pid, "--to", "telegram:test", "--hermes-bin", str(fake)],
            capture_output=True, text=True, cwd=PROJECT,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "sent")

    def test_notify_missing_hermes_fails_cleanly(self):
        pending = self._pending()
        pid = pending["result"]["promotion_id"]
        result = subprocess.run(
            [sys.executable, "-m", "root_engine", "--db", str(self.store.path),
             "promote-notify", "--id", pid, "--to", "telegram:test", "--hermes-bin", "/nonexistent/hermes"],
            capture_output=True, text=True, cwd=PROJECT,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("executable regular file", result.stderr.lower())

    def test_notify_hermes_nonzero_exit_still_pending(self):
        pending = self._pending()
        pid = pending["result"]["promotion_id"]
        fake = Path(self.temp.name) / "fake-hermes"
        fake.write_text('#!/bin/sh\nexit 1')
        fake.chmod(0o755)
        result = subprocess.run(
            [sys.executable, "-m", "root_engine", "--db", str(self.store.path),
             "promote-notify", "--id", pid, "--to", "telegram:test", "--hermes-bin", str(fake)],
            capture_output=True, text=True, cwd=PROJECT,
        )
        self.assertNotEqual(result.returncode, 0)
        from root_engine.promotion import show
        after = Store(self.store.path, now=lambda: self.clock[0])
        self.assertEqual(show(after, pid)["state"], "pending")
        after.close()

    def test_notify_malformed_json_is_uncertain_and_still_pending(self):
        pending = self._pending()
        pid = pending["result"]["promotion_id"]
        fake = Path(self.temp.name) / "fake-hermes"
        fake.write_text('#!/bin/sh\necho not-json')
        fake.chmod(0o755)
        result = subprocess.run(
            [sys.executable, "-m", "root_engine", "--db", str(self.store.path),
             "promote-notify", "--id", pid, "--to", "telegram:test", "--hermes-bin", str(fake)],
            capture_output=True, text=True, cwd=PROJECT,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("uncertain", result.stderr.lower())
        after = Store(self.store.path, now=lambda: self.clock[0])
        self.assertEqual(after.db.execute("SELECT state FROM promotions WHERE id=?", (pid,)).fetchone()[0], "pending")
        event = json.loads(after.db.execute("SELECT payload FROM promotion_events WHERE promotion_id=? AND stage='notify_result' ORDER BY id DESC", (pid,)).fetchone()[0])
        self.assertEqual(event["status"], "uncertain")
        after.close()

    def test_notify_explicit_relative_path_is_rejected(self):
        pending = self._pending()
        pid = pending["result"]["promotion_id"]
        result = subprocess.run(
            [sys.executable, "-m", "root_engine", "--db", str(self.store.path),
             "promote-notify", "--id", pid, "--to", "telegram:test", "--hermes-bin", "./fake"],
            capture_output=True, text=True, cwd=PROJECT,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("absolute path", result.stderr.lower())

    def test_notify_negative_json_is_uncertain_and_still_pending(self):
        pending = self._pending()
        pid = pending["result"]["promotion_id"]
        fake = Path(self.temp.name) / "fake-hermes"
        fake.write_text('#!/bin/sh\necho \'{"success":false,"error":"refused"}\'')
        fake.chmod(0o755)
        result = subprocess.run(
            [sys.executable, "-m", "root_engine", "--db", str(self.store.path),
             "promote-notify", "--id", pid, "--to", "telegram:test", "--hermes-bin", str(fake)],
            capture_output=True, text=True, cwd=PROJECT,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("uncertain", result.stderr.lower())
        after = Store(self.store.path, now=lambda: self.clock[0])
        self.assertEqual(after.db.execute("SELECT state FROM promotions WHERE id=?", (pid,)).fetchone()[0], "pending")
        after.close()

    def test_notify_timeout(self):
        pending = self._pending()
        pid = pending["result"]["promotion_id"]
        fake = Path(self.temp.name) / "fake-hermes-slow"
        fake.write_text('#!/usr/bin/env python3\nimport time\ntime.sleep(30)\n')
        fake.chmod(0o755)
        result = subprocess.run(
            [sys.executable, "-m", "root_engine", "--db", str(self.store.path),
             "promote-notify", "--id", pid, "--to", "telegram:test", "--hermes-bin", str(fake), "--timeout", "0.5"],
            capture_output=True, text=True, cwd=PROJECT,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("timed out", result.stderr.lower())

    def test_cli_show_allow_deny_json_and_exits(self):
        db = Path(self.temp.name) / "cli.sqlite3"
        policy = self.store.portfolio()["policy"]
        store = Store(db, create=True, objective="cli", policy=policy)
        goals = Goals(store)
        spec = dict(self.spec, id="cli-goal")
        goals.create(spec)
        pending = run_goal(goals, spec["id"], opener=self.opener())
        promotion_id = pending["result"]["promotion_id"]
        store.close()

        def run_cli(*args):
            return subprocess.run(
                [sys.executable, "-m", "root_engine", "--db", str(db), *args],
                capture_output=True,
                text=True,
                cwd=PROJECT,
            )

        shown = run_cli("promote-show", "--id", promotion_id)
        self.assertEqual(shown.returncode, 0, shown.stderr)
        payload = json.loads(shown.stdout)
        self.assertEqual(payload["state"], "pending")
        self.assertNotIn("artifact", payload)
        self.assertNotIn("license", payload)
        allowed = run_cli("promote-allow", "--id", promotion_id, "--actor", "cli-operator")
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        self.assertEqual(json.loads(allowed.stdout)["state"], "promoted")
        again = run_cli("promote-allow", "--id", promotion_id, "--actor", "cli-operator")
        self.assertEqual(again.returncode, 0, again.stderr)
        denied_db = Path(self.temp.name) / "cli-deny.sqlite3"
        store = Store(denied_db, create=True, objective="cli-deny", policy=policy)
        goals = Goals(store)
        spec = dict(self.spec, id="cli-deny-goal")
        goals.create(spec)
        pending = run_goal(goals, spec["id"], opener=self.opener())
        pid = pending["result"]["promotion_id"]
        store.close()
        denied = subprocess.run(
            [sys.executable, "-m", "root_engine", "--db", str(denied_db), "promote-deny",
             "--id", pid, "--actor", "cli-operator", "--reason", "not today"],
            capture_output=True, text=True, cwd=PROJECT,
        )
        self.assertEqual(denied.returncode, 1, denied.stdout + denied.stderr)
        self.assertEqual(json.loads(denied.stdout)["state"], "denied")
        again_deny = subprocess.run(
            [sys.executable, "-m", "root_engine", "--db", str(denied_db), "promote-deny",
             "--id", pid, "--actor", "cli-operator", "--reason", "not today"],
            capture_output=True, text=True, cwd=PROJECT,
        )
        self.assertEqual(again_deny.returncode, 0, again_deny.stderr)

    def test_expiry_one_tick_before_equality_and_after(self):
        pending = self._pending()
        pid = pending["result"]["promotion_id"]
        expires = self.store.db.execute("SELECT expires FROM promotions WHERE id=?", (pid,)).fetchone()[0]
        self.clock[0] = expires - 1
        promote_allow(self.store, pid, actor="tick")
        self.assertEqual(active_delay(self.store, "900"), 900)

        path = Path(self.temp.name) / "expiry.sqlite3"
        self.clock[0] = 1000.0
        policy = json.loads((PROJECT / "examples/self-improvement-policy.json").read_text())
        store = Store(path, create=True, objective="expiry", policy=policy, now=lambda: self.clock[0])
        self.addCleanup(store.close)
        goals = Goals(store)
        spec = dict(self.spec, id="expiry-eq")
        goals.create(spec)
        pending = run_goal(goals, spec["id"], opener=self.opener())
        pid = pending["result"]["promotion_id"]
        expires = store.db.execute("SELECT expires FROM promotions WHERE id=?", (pid,)).fetchone()[0]
        self.clock[0] = expires
        with self.assertRaises(PromotionClosed):
            promote_allow(store, pid, actor="eq")
        self.assertEqual(store.db.execute("SELECT state FROM promotions WHERE id=?", (pid,)).fetchone()[0], "expired")
        self.assertEqual(goals.row(spec["id"])["result"]["adoption"], "not_adopted")
        self.assertEqual(active_delay(store, "900"), 300)

        spec = dict(self.spec, id="expiry-after")
        self.clock[0] = 1000.0
        goals.create(spec)
        pending = run_goal(goals, spec["id"], opener=self.opener())
        pid = pending["result"]["promotion_id"]
        expires = store.db.execute("SELECT expires FROM promotions WHERE id=?", (pid,)).fetchone()[0]
        self.clock[0] = expires + 1
        view = show(store, pid)
        self.assertEqual(view["state"], "expired")

    def test_expiry_during_evaluation_cannot_activate(self):
        pending = self._pending()
        pid = pending["result"]["promotion_id"]
        expires = self.store.db.execute("SELECT expires FROM promotions WHERE id=?", (pid,)).fetchone()[0]
        self.clock[0] = expires - 1
        import root_engine.promotion as promotion

        original = promotion._reevaluate_artifact

        def advancing(artifact_text, manifest, **kwargs):
            self.clock[0] = expires + 1
            return original(artifact_text, manifest, **kwargs)

        with patch.object(promotion, "_reevaluate_artifact", advancing):
            with self.assertRaisesRegex(PromotionClosed, "expired"):
                promote_allow(self.store, pid, actor="slow")
        self.assertEqual(active_delay(self.store, "900"), 300)
        self.assertEqual(self._rows()[0]["state"], "expired")
        self.assertEqual(self.goals.row(self.spec["id"])["result"]["promotion_decision"], "expired")

    def test_deny_and_idempotent_deny(self):
        pending = self._pending()
        pid = pending["result"]["promotion_id"]
        first = deny(self.store, pid, actor="op", reason="no")
        self.assertEqual(first["state"], "denied")
        self.assertEqual(active_delay(self.store, "900"), 300)
        second = deny(self.store, pid, actor="op", reason="no")
        self.assertEqual(second["state"], "denied")
        with self.assertRaises(PromotionClosed):
            promote_allow(self.store, pid, actor="op")

    def test_double_allow_is_idempotent(self):
        pending = self._pending()
        pid = pending["result"]["promotion_id"]
        first = promote_allow(self.store, pid, actor="op")
        second = promote_allow(self.store, pid, actor="op")
        self.assertEqual(first["state"], second["state"])
        self.assertEqual(active_delay(self.store, "900"), 900)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM components WHERE active=1").fetchone()[0], 1)

    def test_competing_pending_for_same_baseline_rejected(self):
        self._pending()
        spec = dict(self.spec, id="second-goal")
        self.goals.create(spec)
        result = run_goal(self.goals, spec["id"], opener=self.opener())
        self.assertEqual(result["state"], "stopped")
        self.assertEqual(len(self._rows()), 1)

    def test_artifact_tamper_fails_closed(self):
        pending = self._pending()
        pid = pending["result"]["promotion_id"]
        self.store.db.execute("UPDATE promotions SET artifact=? WHERE id=?", (b"not-the-bytes", pid))
        with self.assertRaises(RootError):
            promote_allow(self.store, pid, actor="op")
        self.assertEqual(active_delay(self.store, "900"), 300)

    def test_unexpected_evaluator_error_terminalizes_attempt_with_bounded_receipt(self):
        pending = self._pending()
        pid = pending["result"]["promotion_id"]
        with patch("root_engine.promotion._reevaluate_artifact", side_effect=ValueError("boom")):
            with self.assertRaisesRegex(RootError, "unexpected"):
                promote_allow(self.store, pid, actor="operator")
        row = self.store.db.execute("SELECT state FROM promotions WHERE id=?", (pid,)).fetchone()
        self.assertEqual(row["state"], "failed")
        event = self.store.db.execute(
            "SELECT payload FROM promotion_events WHERE promotion_id=? AND stage='evaluation_failed'",
            (pid,),
        ).fetchone()
        receipt = json.loads(event["payload"])
        self.assertTrue(receipt["attempt_token"])
        self.assertEqual(receipt["error_tail"], "boom")

    def test_tampered_provenance_and_license_cannot_promote(self):
        changes = (
            ("source_url", "https://evil.invalid/retry.py"),
            ("upstream_revision", "f" * 40),
            ("license", "not the retained MIT license"),
        )
        policy = json.loads((PROJECT / "examples/self-improvement-policy.json").read_text())
        for column, value in changes:
            with self.subTest(column=column):
                path = Path(self.temp.name) / f"tampered-{column}.sqlite3"
                store = Store(path, create=True, objective="tamper test", policy=policy, now=lambda: self.clock[0])
                self.addCleanup(store.close)
                goals = Goals(store)
                spec = dict(self.spec, id=f"tampered-{column}")
                goals.create(spec)
                pending = run_goal(goals, spec["id"], opener=self.opener())
                pid = pending["result"]["promotion_id"]
                store.db.execute(f"UPDATE promotions SET {column}=? WHERE id=?", (value, pid))
                with self.assertRaises(RootError):
                    promote_allow(store, pid, actor="op")
                self.assertEqual(active_delay(store, "900"), 300)

    def test_reassigned_parent_goal_cannot_receive_promotion_decision(self):
        pending = self._pending()
        pid = pending["result"]["promotion_id"]
        other = dict(self.spec, id="unrelated-goal")
        self.goals.create(other)
        self.store.db.execute("UPDATE promotions SET goal_id=? WHERE id=?", (other["id"], pid))
        with self.assertRaises(RootError):
            promote_allow(self.store, pid, actor="operator")
        self.assertEqual(self.goals.row(other["id"])["state"], "created")
        self.assertEqual(self.goals.row(self.spec["id"])["result"]["promotion_decision"], "failed")

    def test_existing_component_id_with_different_bytes_is_rejected(self):
        pending = self._pending()
        pid = pending["result"]["promotion_id"]
        row = self.store.db.execute("SELECT * FROM promotions WHERE id=?", (pid,)).fetchone()
        component_id = digest([COMPONENT, row["upstream_revision"], row["artifact"].decode()])
        self.store.db.execute(
            "INSERT INTO components(id,name,goal_id,revision,source,license,active) VALUES(?,?,?,?,?,?,0)",
            (component_id, COMPONENT, row["goal_id"], row["upstream_revision"], "forged source", "forged license"),
        )
        with self.assertRaisesRegex(RootError, "evaluated artifact"):
            promote_allow(self.store, pid, actor="operator")
        self.assertEqual(self.store.db.execute("SELECT state FROM promotions WHERE id=?", (pid,)).fetchone()[0], "failed")
        self.assertIsNone(self.store.db.execute("SELECT id FROM components WHERE active=1").fetchone())

    def test_conflicting_denial_is_not_idempotent(self):
        pending = self._pending()
        pid = pending["result"]["promotion_id"]
        deny(self.store, pid, actor="alice", reason="reason-a")
        with self.assertRaisesRegex(PromotionClosed, "different decision"):
            deny(self.store, pid, actor="bob", reason="reason-b")

    def test_promotion_row_cannot_change_during_evaluation(self):
        pending = self._pending()
        pid = pending["result"]["promotion_id"]
        replacement = b"class Retry:\n def parse_retry_after(self, retry_after):\n  return 301\n"
        import root_engine.promotion as promotion

        original = promotion._reevaluate_artifact

        def replace_after_evaluation(artifact_text, manifest, **kwargs):
            measured = original(artifact_text, manifest, **kwargs)
            self.store.db.execute(
                "UPDATE promotions SET artifact=?, artifact_sha256=? WHERE id=?",
                (replacement, hashlib.sha256(replacement).hexdigest(), pid),
            )
            return measured

        with patch.object(promotion, "_reevaluate_artifact", replace_after_evaluation):
            with self.assertRaises(RootError):
                promote_allow(self.store, pid, actor="op")
        self.assertEqual(active_delay(self.store, "900"), 300)
        self.assertIsNone(self.store.db.execute("SELECT id FROM components WHERE active=1").fetchone())

    def test_activation_cannot_exceed_goal_storage_allowance(self):
        path = Path(self.temp.name) / "activation-budget.sqlite3"
        policy = json.loads((PROJECT / "examples/self-improvement-policy.json").read_text())
        store = Store(path, create=True, objective="activation budget", policy=policy, now=lambda: self.clock[0])
        self.addCleanup(store.close)
        goals = Goals(store)
        spec = dict(self.spec, id="activation-budget", max_storage_bytes=24000)
        goals.create(spec)
        pending = run_goal(goals, spec["id"], opener=self.opener())
        self.assertEqual(pending["state"], "pending_promotion")

        with self.assertRaises(RootError):
            promote_allow(store, pending["result"]["promotion_id"], actor="op")

        self.assertEqual(active_delay(store, "900"), 300)
        self.assertLessEqual(goals.payload_bytes(spec["id"]), spec["max_storage_bytes"])
        self.assertIsNone(store.db.execute("SELECT id FROM components WHERE active=1").fetchone())
        self.assertEqual(store.db.execute("SELECT state FROM promotions").fetchone()["state"], "pending")

    def test_manifest_and_trusted_drift_fail_closed(self):
        pending = self._pending()
        pid = pending["result"]["promotion_id"]
        self.store.db.execute("UPDATE promotions SET evaluation_manifest=? WHERE id=?", (encode({"development": "0"*64, "holdout": "1"*64}), pid))
        with self.assertRaises(Exception):
            promote_allow(self.store, pid, actor="op")
        spec = dict(self.spec, id="trust-drift")
        self.goals.create(spec)
        pending = run_goal(self.goals, spec["id"], opener=self.opener())
        pid = pending["result"]["promotion_id"]
        self.store.db.execute("UPDATE promotions SET trusted_manifest=? WHERE id=?", (encode({"nope": "x"}), pid))
        with self.assertRaisesRegex(RootError, "Trusted code"):
            promote_allow(self.store, pid, actor="op")

    def test_baseline_must_still_improve_captured_component(self):
        first = self._pending()
        promote_allow(self.store, first["result"]["promotion_id"], actor="op")
        active = self.store.db.execute("SELECT id FROM components WHERE active=1").fetchone()
        spec = dict(self.spec, id="no-improve")
        self.goals.create(spec)
        second = run_goal(self.goals, spec["id"], opener=self.opener())
        self.assertEqual(second["result"]["evaluation"], "already_satisfied")
        self.assertEqual(len(self._rows()), 1)
        self.assertEqual(self.store.db.execute("SELECT id FROM components WHERE active=1").fetchone()[0], active["id"])

    def test_stale_evaluation_lease_can_be_reclaimed(self):
        pending = self._pending()
        pid = pending["result"]["promotion_id"]
        self.store.db.execute(
            "UPDATE promotions SET state='evaluating', attempt_token=?, attempt_expires=? WHERE id=?",
            ("live-token", self.clock[0] + 100, pid),
        )
        with self.assertRaisesRegex(RootError, "in progress"):
            promote_allow(self.store, pid, actor="op")
        self.store.db.execute("UPDATE promotions SET attempt_expires=? WHERE id=?", (self.clock[0] - 1, pid))
        promote_allow(self.store, pid, actor="op")
        self.assertEqual(active_delay(self.store, "900"), 900)
        abandoned = self.store.db.execute(
            "SELECT payload FROM promotion_events WHERE promotion_id=? AND stage='evaluation_abandoned'",
            (pid,),
        ).fetchone()
        self.assertEqual(json.loads(abandoned["payload"])["attempt_token"], "live-token")

    def test_atomic_pending_creation_rolls_back_split_writes(self):
        discovery = {
            "source": self.fixture["source"],
            "license": self.fixture["license"],
            "source_url": "https://raw.githubusercontent.com/urllib3/urllib3/" + "0" * 40 + "/src/urllib3/util/retry.py",
            "revision": "0" * 40,
            "mode": "live",
        }
        measured = {"development": {"candidate_passes": 6, "baseline_passes": 4, "total": 6},
                    "holdout": {"candidate_passes": 6, "baseline_passes": 3, "total": 6}}
        result = {"evaluation": "pass", "adoption": "pending_operator", "promotable": True}
        for point in ("promotion", "event", "goal"):
            with self.assertRaisesRegex(RootError, "injected"):
                create_pending_retry_after(
                    self.goals, self.spec["id"], discovery, measured, None,
                    expires=self.clock[0] + 800, result=result, fail_after=point,
                )
            self.assertEqual(self._rows(), [])
            self.assertEqual(self.goals.row(self.spec["id"])["state"], "created")

    def test_over_budget_pending_creates_nothing(self):
        spec = dict(self.spec, id="tiny-storage", max_storage_bytes=16384)
        self.goals.create(spec)
        discovery = {
            "source": self.fixture["source"],
            "license": self.fixture["license"] + "L" * 20000,
            "source_url": "https://raw.githubusercontent.com/urllib3/urllib3/" + "0" * 40 + "/src/urllib3/util/retry.py",
            "revision": "0" * 40,
            "mode": "live",
        }
        measured = {"development": {"candidate_passes": 6, "baseline_passes": 4, "total": 6},
                    "holdout": {"candidate_passes": 6, "baseline_passes": 3, "total": 6}}
        from root_engine.store import BudgetError
        with self.assertRaises(BudgetError):
            create_pending_retry_after(
                self.goals, spec["id"], discovery, measured, None,
                expires=self.clock[0] + 800,
                result={"evaluation": "pass", "adoption": "pending_operator"},
            )
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM promotions WHERE goal_id=?", (spec["id"],)).fetchone()[0], 0)
        self.assertEqual(self.goals.row(spec["id"])["state"], "created")

    def test_promotion_events_are_ordered_and_durable(self):
        pending = self._pending()
        pid = pending["result"]["promotion_id"]
        promote_allow(self.store, pid, actor="op")
        stages = [row[0] for row in self.store.db.execute(
            "SELECT stage FROM promotion_events WHERE promotion_id=? ORDER BY id", (pid,)
        )]
        self.assertEqual(stages, ["created", "evaluating", "evaluation_passed", "promoted"])
        self.store.close()
        self.store = Store(self.path, now=lambda: self.clock[0])
        stages = [row[0] for row in self.store.db.execute(
            "SELECT stage FROM promotion_events WHERE promotion_id=? ORDER BY id", (pid,)
        )]
        self.assertEqual(stages, ["created", "evaluating", "evaluation_passed", "promoted"])

    def test_rollback_after_expiry_and_refuses_later_activation(self):
        pending = self._pending()
        pid = pending["result"]["promotion_id"]
        promote_allow(self.store, pid, actor="op")
        self.clock[0] = self.store.portfolio()["deadline"] + 1
        self.goals.rollback(self.spec["id"])
        self.assertEqual(active_delay(self.store, "900"), 300)
        with self.assertRaises(RootError):
            self.goals.rollback(self.spec["id"])

    def test_research_goal_creates_no_promotion(self):
        policy = json.loads((PROJECT / "examples/research-benchmark-policy.json").read_text())
        store = Store(Path(self.temp.name) / "research.sqlite3", create=True, objective="research", policy=policy,
                      now=lambda: self.clock[0])
        self.addCleanup(store.close)
        goals = Goals(store)
        spec = json.loads((PROJECT / "examples/research_component_goal.json").read_text())
        model = Path(self.temp.name) / "r.gguf"
        model.write_bytes(b"placeholder")
        spec["model_path"] = str(model)
        goals.create(spec)
        self.assertEqual(store.db.execute("SELECT count(*) FROM promotions").fetchone()[0], 0)

    def test_verifier_does_not_mutate_original(self):
        policy = json.loads((PROJECT / "examples/self-improvement-policy.json").read_text())
        path = Path(self.temp.name) / "verify.sqlite3"
        store = Store(path, create=True, objective="verify", policy=policy)
        goals = Goals(store)
        spec = dict(self.spec, id="verify-goal")
        goals.create(spec)
        pending = run_goal(goals, spec["id"], opener=self.opener())
        before_state = goals.row(spec["id"])["state"]
        before_delay = active_delay(store, "900")
        before_requests = pending["requests"]
        store.close()
        result = subprocess.run(
            [sys.executable, str(PROJECT / "scripts/verify_saved_goal.py"), "--db", str(path), "--id", spec["id"]],
            capture_output=True, text=True, cwd=PROJECT,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["original_untouched"])
        store = Store(path)
        self.addCleanup(store.close)
        self.assertEqual(Goals(store).row(spec["id"])["state"], before_state)
        self.assertEqual(active_delay(store, "900"), before_delay)
        self.assertEqual(Goals(store).row(spec["id"])["requests"], before_requests)

    def test_verifier_copies_legacy_database_before_migration_and_restores_dynamic_baseline(self):
        path = Path(self.temp.name) / "legacy-verify.sqlite3"
        db = sqlite3.connect(path)
        db.executescript(SCHEMA)
        db.executescript(GOAL_SCHEMA)
        policy = json.loads((PROJECT / "examples/self-improvement-policy.json").read_text())
        db.execute(
            "INSERT INTO portfolio(id,objective,policy,created,deadline) VALUES(1,?,?,?,?)",
            ("legacy verify", encode(policy), 1.0, 9999999999.0),
        )
        spec = dict(self.spec, id="legacy-verify-goal")
        result = {
            "evaluation": "pass",
            "adoption": "enabled_restricted_adapter",
            "component_id": "candidate",
            "previous_component_id": "baseline",
        }
        db.execute(
            "INSERT INTO goals(id,spec,created,deadline,state,requests,downloaded_bytes,result,mode) VALUES(?,?,?,?,?,?,?,?,?)",
            (spec["id"], encode(spec), 1.0, 9999999999.0, "completed", 0, 0, encode(result), "live"),
        )
        db.execute(
            "INSERT INTO components(id,name,goal_id,revision,source,license,active) VALUES(?,?,?,?,?,?,?)",
            ("baseline", COMPONENT, spec["id"], "0" * 40, "class Retry:\n    def parse_retry_after(self, retry_after):\n        return 600\n", "MIT", 0),
        )
        db.execute(
            "INSERT INTO components(id,name,goal_id,revision,source,license,active) VALUES(?,?,?,?,?,?,?)",
            ("candidate", COMPONENT, spec["id"], "0" * 40, self.fixture["source"], self.fixture["license"], 1),
        )
        db.commit()
        db.close()
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        completed = subprocess.run(
            [sys.executable, str(PROJECT / "scripts/verify_saved_goal.py"), "--db", str(path), "--id", spec["id"]],
            capture_output=True, text=True, cwd=PROJECT,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["rollback_copy_before_seconds"], 900)
        self.assertEqual(payload["rollback_copy_after_seconds"], 600)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
        check = sqlite3.connect(path)
        self.addCleanup(check.close)
        self.assertEqual(check.execute("PRAGMA user_version").fetchone()[0], 1)


class ConstitutionPathTests(unittest.TestCase):
    def test_symlink_trusted_paths_rejected(self):
        from root_engine.constitution import PROJECT as ROOT
        from root_engine.store import RootError as StoreError
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory) / "proj"
            for relative in TRUSTED_RELATIVE_PATHS:
                dest = tree / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, dest)
            target = tree / "root_engine/store.py"
            target.unlink()
            target.symlink_to(ROOT / "root_engine/store.py")
            with self.assertRaisesRegex(StoreError, "symlink"):
                trusted_manifest(tree)
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory) / "proj"
            for relative in TRUSTED_RELATIVE_PATHS:
                dest = tree / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, dest)
            real = tree / "root_engine_real"
            shutil.move(str(tree / "root_engine"), str(real))
            (tree / "root_engine").symlink_to(real)
            with self.assertRaisesRegex(StoreError, "symlink"):
                trusted_manifest(tree)


if __name__ == "__main__":
    unittest.main()
