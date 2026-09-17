# World Monitor ingest adapter gate (move #2)

**Status: fixture-protocol only. No live World Monitor crawler is built here.**

This is the **gate + spec** for wiring a future World Monitor observation source through the
same pending / explicit-operator-allow authority boundary that component promotion already uses.
It deliberately does **not** add a live network host, does **not** touch the hardened
`root_engine/promotion.py` core, and does **not** mutate historical v2 portfolios on open.

## Why a gate, not straight ingestion

Today `collect` writes observations straight into `observations` and `screen`/`brief` act on
them. That is fine for a known, source-verified publisher. A World Monitor feed is a future,
less-trusted source: raw ingests should be **held pending** so they can never silently become
authoritative observations. This mirrors the promotion brake: evidence can be retained and
inspected, but it changes nothing until an explicit operator action makes it authoritative.

## Files

- `root_engine/worldmonitor.py` — self-contained fixture gate (stdlib only).
- `tests/test_worldmonitor.py` — 7 contract/adversarial tests.
- `examples/world_monitor.synthetic.json` — synthetic offline batch (not real market data).
- CLI: `world-ingest --fixture FILE [--actor LABEL]`, `world-show --id OBS_ID`.

## Authority contract (mirrors the promotion brake)

| facet | component promotion | world-monitor gate |
|---|---|---|
| live pass | `pending_promotion`, needs `promote-allow` | (future live ingest, gated) |
| fixture pass | `promotable=false`, no allow path | `mode=fixture`, no allow path |
| explicit allow | `promote-allow` re-checks exact bytes | `world-allow` would exist only for genuine live |
| terminal | denied / expired / failed / superseded | expired via `world_expire` fixture path |
| collector effect | none until allow | none ever in fixture mode |

A fixture World Monitor batch:
- is retained as **exact payload bytes** with a SHA-256 in a dedicated `world_pending_observations`
  table (created only when the adapter runs, on any store);
- is **permanently non-authoritative**: it never appears in `observations`, `packages`,
  `components`, or `promotions`; `collect`, `screen`, and `brief` ignore it entirely;
- **has no allow path**: `worldmonitor.py` exposes only `world_ingest_fixture`, `world_show`,
  and `world_expire` — there is no function that moves fixture bytes into authoritative storage
  and no `world-allow` CLI branch;
- is bounded by the portfolio storage/deadline and a 256 KiB / 50-row batch cap.

## Why the gate is not a security sandbox

The fixture path parses a bounded JSON object and writes rows. It does **not** execute candidate
code, open arbitrary hosts, or hold network credentials. A future live adapter must copy the
promotion model: exact-byte retention, resource-bounded retrieval from an explicitly pinned
host set, and an explicit operator allow after independent re-check. That is ***not*** a sandbox.

## CLI

```sh
python3 -m root_engine --db /tmp/world.sqlite3 init --objective 'World Monitor gate demo'
python3 -m root_engine --db /tmp/world.sqlite3 world-ingest --fixture examples/world_monitor.synthetic.json --actor operator
python3 -m root_engine --db /tmp/world.sqlite3 world-show --id <OBSERVATION_ID>
```

`world-show` prints state, mode, provenance, and expiry and **strips the artifact payload**
(never prints source bytes). There is no `world-allow` for fixture data.

## Out of scope (deliberate)

A real World Monitor network adapter (live host, auth, scheduler) is a future, separately
authorized build. This gate only proves the pending / non-authority boundary is reusable for the
observation/ingest path.