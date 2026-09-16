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

DB="$db" python3 - <<'PY'
import os
import sqlite3

db = sqlite3.connect(os.environ["DB"])
promotions = db.execute("SELECT count(*) FROM promotions").fetchone()[0]
components = db.execute("SELECT count(*) FROM components").fetchone()[0]
knowledge = db.execute("SELECT count(*) FROM knowledge_records WHERE authority='evidence_only'").fetchone()[0]
assert promotions == 0, promotions
assert components == 0, components
assert knowledge == 1, knowledge
print("BOUNDARY VERIFIED: fixture pass created no promotion/component; learning created one evidence-only record.")
PY

# Fixture execution never produces a promotion ID, so promotion is deterministically unavailable.
if python3 -m root_engine --db "$db" promote-allow --id fixture-has-no-promotion --actor operator; then
    printf '%s\n' 'unexpected fixture promotion success' >&2
    exit 1
else
    printf '%s\n' 'BOUNDARY VERIFIED: fixture promotion attempt refused.'
fi
