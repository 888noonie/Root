#!/bin/sh
# Offline observation-closure walkthrough: pending -> world-allow -> authoritative,
# with fixture rows permanently non-authoritative. No real network request is made.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
python3 scripts/world_observation_closure_demo.py