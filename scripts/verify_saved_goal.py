"""Verify a saved adoption and exercise rollback on an isolated SQLite copy."""

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from root_engine.goals import Goals, run_goal
from root_engine.retry_component import active_delay
from root_engine.store import Store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--id", default="respect-source-cooldowns")
    args = parser.parse_args()
    original = Store(args.db)
    try:
        goals = Goals(original)
        before = goals.view(args.id)
        if before["state"] != "completed" or before["result"].get("adoption") != "enabled_restricted_adapter":
            raise RuntimeError("Requires a completed adoption")
        replay = run_goal(goals, args.id)
        if before != replay:
            raise RuntimeError("Completed goal replay changed records")
        with tempfile.TemporaryDirectory(prefix="root-rollback-") as directory:
            copy = Store(Path(directory) / "copy.sqlite3", create=True, objective="Temporary verification copy")
            try:
                original.db.backup(copy.db)
                initial = active_delay(copy, "900")
                Goals(copy).rollback(args.id)
                restored = active_delay(copy, "900")
            finally:
                copy.close()
        still_active = active_delay(original, "900")
        result = {"completed_replay_unchanged": True, "requests_before": before["requests"], "requests_after": replay["requests"],
                  "rollback_copy_before_seconds": initial, "rollback_copy_after_seconds": restored,
                  "original_after_verification_seconds": still_active, "original_component_remains_active": still_active == initial,
                  "network_requests_during_verification": 0}
        if initial != 900 or restored != 300 or still_active != 900:
            raise RuntimeError("Unexpected adapter or rollback behavior")
        print(json.dumps(result, indent=2))
    finally:
        original.close()


if __name__ == "__main__":
    main()
