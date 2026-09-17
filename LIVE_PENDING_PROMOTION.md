# Live pending promotion lifecycle — reproducible record (Move #1)

**Status: auditable from the repo; no SQLite database is committed and no credential is used.**
This is the documented, bash-verifiable record of the live `goal-run → pending →
`promote-allow` → rollback-copy` lifecycle that the promotion core's design claims.

## Why this record exists

`ADVANTAGE_ENGINE.md` and `SELF_IMPROVEMENT_*` previously centered legacy immediate-adoption
profiles (e.g. `.root/self-improve-live2.sqlite3`). That era ended when the promotion brake made a
passing live evaluation stay **pending** until an explicit operator `promote-allow`. This document
captures the *new* lifecycle so it can be reproduced from a clean checkout, without committing a
portfolio database or any retained license text.

## Database path policy

Use a throwaway path — under `/tmp/` or `.root/` (gitignored). Never commit the SQLite file and
never point these commands at a live/production portfolio without explicit authorization.

## Exact commands (fresh throwaway DB)

```sh
cd /home/richardn/Oct8pia
DB=/tmp/root-live-demo.sqlite3
rm -f "$DB"

python3 -m root_engine --db "$DB" init \
  --objective 'Live pending-allow demonstration' \
  --policy examples/self-improvement-policy.json

python3 -m root_engine --db "$DB" goal-create --file examples/self_improvement_goal.json
python3 -m root_engine --db "$DB" goal-run --id respect-source-cooldowns --live
python3 -m root_engine --db "$DB" promote-show --id <PROMOTION_ID>
python3 -m root_engine --db "$DB" promote-allow --id <PROMOTION_ID> --actor operator
python3 -m root_engine --db "$DB" goal-run --id respect-source-cooldowns --live   # no-op replay
python3 scripts/verify_saved_goal.py --db "$DB"                                   # rolls back a copy
```

> `goal-run --live` performs **real network** discovery against the curated GitHub allowlist
> (search, repo metadata, commits, raw source/license/README). Run it only with authorization.
> `promote-allow` is an OS-local authority boundary (shell + portfolio-DB access); it is not proof
> that Richard personally approved. Do not run it on a live/production portfolio DB.

## Measured outcome (executed 2026-09-17)

| metric | value |
|---|---|
| upstream repository | `urllib3/urllib3` |
| pinned revision | `b1d30ab61fe0db8f11092805e8c5ac43e091064a` |
| network requests | 7 |
| downloaded bytes | 96,677 |
| promotion id | `121f54614165424103c25bace4219700` |
| goal state before allow | `pending_promotion` (result `adoption=pending_operator`, `promotable=true`) |
| promotion state before allow | `pending` (baseline `active_delay(store,"900") == 300`) |
| `promote-allow` result | state `promoted`, `decision_actor=operator`, `component_id` bound |
| collector delay after allow | 300 → **900** |
| replay `goal-run --live` | no-op: state `completed`, requests still 7, same promotion id |
| verifier (`verify_saved_goal.py`) | completed replay unchanged; copy rollback restored 900→**300**; original untouched; 0 network during verification |

State transitions captured: `created → running(live) → pending_promotion → (promote-allow) →
promoted`, goal `completed`. Replaying a completed/pending goal is a no-op and creates no extra
discovery, event, or promotion rows.

## How to confirm the delay change

```python
from root_engine.store import Store
from root_engine.retry_component import active_delay
s = Store("/tmp/root-live-demo.sqlite3")
print(active_delay(s, "900"))  # 300.0 before allow, 900.0 after allow
s.close()
```

## Legacy vs new lifecycle

- Legacy `.root/self-improve-live2.sqlite3`: historical immediate-adoption profile; retained only
  as evidence of the pre-brake era, not the current behavior.
- Current behavior: a passing **live** evaluation writes an exact-byte `pending` promotion row and
  leaves collector behavior unchanged until an explicit `promote-allow` re-validates the stored
  bytes, pinned manifests, provenance, license, trusted-code drift, expiry, and captured baseline.
- Fixture passes remain permanently non-promotable and cannot be allowed.