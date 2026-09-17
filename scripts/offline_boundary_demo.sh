#!/bin/sh
# Offline boundary walkthrough: fixtures prove behavior but cannot authorize adoption.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
demo_dir=$(mktemp -d "${TMPDIR:-/tmp}/root-offline-demo.XXXXXX")
db="$demo_dir/portfolio.sqlite3"
trap 'rm -rf "$demo_dir"' EXIT

cd "$root"
python3 -m root_engine --db "$db" init --objective 'Offline evidence-only boundary walkthrough' --policy examples/self-improvement-policy.json
python3 -m root_engine --db "$db" goal-create --file examples/self_improvement_goal.json
python3 -m root_engine --db "$db" goal-run --id respect-source-cooldowns --fixture examples/github.synthetic.json
python3 -m root_engine --db "$db" goal-show --id respect-source-cooldowns
python3 -m root_engine --db "$db" learn-create --file examples/learn_unknown.request.json
python3 -m root_engine --db "$db" learn-run --id unsupported-adapter-demo --fixture examples/learn_unknown.synthetic.json
python3 -m root_engine --db "$db" learn-show --id unsupported-adapter-demo
# World Monitor fixture gate: batch held pending, never authoritative.
WORLD_OUT=$(python3 -m root_engine --db "$db" world-ingest --fixture examples/world_monitor.synthetic.json --actor operator)
WID=$(printf '%s' "$WORLD_OUT" | sed -n 's/.*"\([0-9a-f]\{32\}\)".*/\1/p' | head -n1)
if [ -z "$WID" ]; then
    printf '%s\n' 'world-ingest did not return a pending id' >&2
    exit 1
fi

DB="$db" python3 - <<'PY'
import os
import sqlite3

db = sqlite3.connect(os.environ["DB"])
promotions = db.execute("SELECT count(*) FROM promotions").fetchone()[0]
components = db.execute("SELECT count(*) FROM components").fetchone()[0]
knowledge = db.execute("SELECT count(*) FROM knowledge_records WHERE authority='evidence_only'").fetchone()[0]
world_pending = db.execute("SELECT count(*) FROM world_pending_observations WHERE state='pending'").fetchone()[0]
assert promotions == 0, promotions
assert components == 0, components
assert knowledge == 1, knowledge
assert world_pending == 2, world_pending
print("BOUNDARY VERIFIED: fixture pass created no promotion/component; learning created one evidence-only record; world gate held two batches pending.")
PY

# world-show must never print artifact bytes at the observation row level
# (the top-level "payload" key is stripped; small per-event metadata payloads remain).
python3 -m root_engine --db "$db" world-show --id "$WID" | python3 -c \
  'import json,sys; d=json.load(sys.stdin); assert "payload" not in d, "top-level payload leaked"; print("BOUNDARY VERIFIED: world-show omits artifact bytes.")'

# Fixture execution never produces a promotion ID, so promotion is deterministically unavailable.
if python3 -m root_engine --db "$db" promote-allow --id fixture-has-no-promotion --actor operator; then
    printf '%s\n' 'unexpected fixture promotion success' >&2
    exit 1
else
    printf '%s\n' 'BOUNDARY VERIFIED: fixture promotion attempt refused.'
fi
