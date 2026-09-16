import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from root_engine.goals import GOAL_SCHEMA
from root_engine.retry_component import COMPONENT, active_delay
from root_engine.store import DEFAULT_POLICY, RootError, SCHEMA, Store, encode, migrate_schema_v2
from root_engine.goals import PROJECT


class StoreMigrationTests(unittest.TestCase):
    def test_fresh_portfolio_is_schema_v2(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fresh.sqlite3"
            store = Store(path, create=True, objective="fresh")
            self.assertEqual(store.db.execute("PRAGMA user_version").fetchone()[0], 2)
            self.assertIsNotNone(store.db.execute("SELECT 1 FROM sqlite_master WHERE name='promotions'").fetchone())
            store.close()

    def test_v1_without_goals_migrates_to_v2(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v1.sqlite3"
            path.write_bytes(b"")
            db = sqlite3.connect(path, isolation_level=None)
            db.executescript(SCHEMA)
            db.execute(
                "INSERT INTO portfolio(id, objective, policy, created, deadline) VALUES(1,?,?,?,?)",
                ("legacy", encode(DEFAULT_POLICY), 1.0, 3601.0),
            )
            db.close()
            store = Store(path)
            self.assertEqual(store.db.execute("PRAGMA user_version").fetchone()[0], 2)
            store.close()
            store2 = Store(path)
            self.assertEqual(store2.db.execute("PRAGMA user_version").fetchone()[0], 2)
            store2.close()

    def test_genuine_v1_adopted_component_migrates_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy-adopted.sqlite3"
            path.write_bytes(b"")
            fixture = json.loads((PROJECT / "examples/github.synthetic.json").read_text())
            db = sqlite3.connect(path, isolation_level=None)
            db.executescript(SCHEMA)
            policy = json.loads((PROJECT / "examples/self-improvement-policy.json").read_text())
            db.execute(
                "INSERT INTO portfolio(id, objective, policy, created, deadline) VALUES(1,?,?,?,?)",
                ("legacy", encode(policy), 1000.0, 4600.0),
            )
            db.executescript(GOAL_SCHEMA)
            spec = json.loads((PROJECT / "examples/self_improvement_goal.json").read_text())
            result = {"evaluation": "pass", "adoption": "enabled_restricted_adapter", "component_id": "legacy-comp"}
            db.execute(
                "INSERT INTO goals(id,spec,created,deadline,state,requests,downloaded_bytes,result,mode) VALUES(?,?,?,?,?,?,?,?,?)",
                (spec["id"], encode(spec), 1000.0, 1900.0, "completed", 6, 100, encode(result), "live"),
            )
            db.execute(
                "INSERT INTO components VALUES(?,?,?,?,?,?,1)",
                ("legacy-comp", COMPONENT, spec["id"], "0" * 40, fixture["source"], fixture["license"]),
            )
            db.close()
            store = Store(path, now=lambda: 1000.0)
            self.assertEqual(store.db.execute("PRAGMA user_version").fetchone()[0], 2)
            self.assertEqual(active_delay(store, "900"), 900)
            self.assertEqual(store.db.execute("SELECT state FROM goals WHERE id=?", (spec["id"],)).fetchone()[0], "completed")
            self.assertEqual(store.db.execute("SELECT count(*) FROM promotions").fetchone()[0], 0)
            store.close()

    def test_mid_migration_failure_leaves_v1(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fail.sqlite3"
            path.write_bytes(b"")
            db = sqlite3.connect(path, isolation_level=None)
            db.executescript(SCHEMA)
            db.execute(
                "INSERT INTO portfolio(id, objective, policy, created, deadline) VALUES(1,?,?,?,?)",
                ("legacy", encode(DEFAULT_POLICY), 1.0, 3601.0),
            )
            with self.assertRaisesRegex(RootError, "injected"):
                migrate_schema_v2(db, inject_failure_after=1)
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 1)
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='promotions'").fetchone())
            db.close()

    def test_v2_version_without_required_structure_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "malformed-v2.sqlite3"
            db = sqlite3.connect(path)
            db.execute("CREATE TABLE portfolio(id INTEGER PRIMARY KEY)")
            db.execute("PRAGMA user_version = 2")
            db.close()
            with self.assertRaisesRegex(RootError, "Malformed schema v2"):
                Store(path)

    def test_v2_authority_tables_enforce_foreign_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "foreign-keys.sqlite3"
            store = Store(path, create=True, objective="foreign keys")
            self.addCleanup(store.close)
            foreign_keys = {
                row["table"]
                for table in ("promotions", "promotion_events", "knowledge_records", "learning_events")
                for row in store.db.execute(f"PRAGMA foreign_key_list({table})")
            }
            self.assertTrue({"goals", "promotions", "learning_requests"} <= foreign_keys)
            self.assertEqual(store.db.execute("PRAGMA foreign_key_check").fetchall(), [])


if __name__ == "__main__":
    unittest.main()
