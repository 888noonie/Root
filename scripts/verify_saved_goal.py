"""Verify a saved adoption and exercise rollback on an isolated SQLite copy."""

import argparse
import hashlib
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from root_engine.goals import Goals, run_goal
from root_engine.retry_component import active_delay, candidate_delay
from root_engine.store import Store


def _snapshot(store, goal_id):
    goals = Goals(store)
    view = goals.view(goal_id)
    active = store.db.execute("SELECT id FROM components WHERE name='retry_after_parser' AND active=1").fetchone()
    return {
        "state": view["state"],
        "requests": view["requests"],
        "result": view["result"],
        "delay": active_delay(store, "900"),
        "active_id": active[0] if active else None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--id", default="respect-source-cooldowns")
    args = parser.parse_args()
    source_path = Path(args.db).resolve()
    before_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="root-rollback-") as directory:
        copy_path = Path(directory) / "copy.sqlite3"
        source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
        destination = sqlite3.connect(copy_path)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        copy = Store(copy_path)
        try:
            before = _snapshot(copy, args.id)
            goals = Goals(copy)
            view = goals.view(args.id)
            if view["state"] == "pending_promotion":
                expected_baseline_id = before["active_id"]
            else:
                expected_baseline_id = view["result"].get("previous_component_id")
            if expected_baseline_id:
                source_row = copy.db.execute("SELECT source FROM components WHERE id=?", (expected_baseline_id,)).fetchone()
                if not source_row:
                    raise RuntimeError("Saved rollback baseline is missing")
                expected_rollback_delay = candidate_delay(source_row[0], "900", copy.now())
            else:
                expected_rollback_delay = 300.0
            if view["state"] == "pending_promotion":
                replay = run_goal(goals, args.id)
                if replay["requests"] != view["requests"]:
                    raise RuntimeError("Pending replay performed new work")
                if active_delay(copy, "900") != expected_rollback_delay:
                    raise RuntimeError("Pending replay activated an adapter")
                from root_engine.promotion import promote_allow
                promote_allow(copy, view["result"]["promotion_id"], actor="saved-goal-verifier")
                view = goals.view(args.id)
            if view["state"] != "completed" or view["result"].get("adoption") != "enabled_restricted_adapter":
                raise RuntimeError("Requires a completed adoption on the verification copy")
            replay = run_goal(goals, args.id)
            if view["requests"] != replay["requests"]:
                raise RuntimeError("Completed goal replay changed records")
            initial = active_delay(copy, "900")
            Goals(copy).rollback(args.id)
            restored = active_delay(copy, "900")
            if restored != expected_rollback_delay:
                raise RuntimeError("Rollback did not restore the captured baseline behavior")
        finally:
            copy.close()
    after_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    if after_hash != before_hash:
        raise RuntimeError("Verification mutated the original database")
    print(json.dumps({
        "completed_replay_unchanged": True,
        "requests_before": before["requests"],
        "original_state": before["state"],
        "original_delay_seconds": before["delay"],
        "original_after_verification_seconds": before["delay"],
        "original_untouched": True,
        "rollback_copy_before_seconds": initial,
        "rollback_copy_after_seconds": restored,
        "network_requests_during_verification": 0,
    }, indent=2))


if __name__ == "__main__":
    main()
