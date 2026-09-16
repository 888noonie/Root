# Milestone build experiment: tranche 1

Started: 2026-09-15 22:28 UTC. Deadline: 2026-09-15 23:13 UTC (45 minutes).

Scope: milestone items 1–3 in ADVANTAGE_ENGINE.md: CLI, durable SQLite portfolio/policy/opportunities, one OCDS collector with offline fixtures, deterministic screening with recorded reasons.

Hypothesis: a standard-library implementation can preserve provenance, prevent repeated imports, enforce resource limits outside model output, and distinguish eligible research candidates from incomplete or unsupported proposals.

Budgets: £0 incremental spend; zero dependency downloads; no model calls; at most one optional live collector smoke request, at most 2 MiB response data. Local development and verification only. No outreach, business deployment or recurring jobs are part of this tranche.

Stop condition: stop at the deadline or any budget breach, record incomplete checks and stalls here, and do not expand to milestone items 4–8. Failure or uncertainty is an acceptable outcome.

Acceptance: CLI demonstration completes; saved fixtures replay without duplicate observations; failed imports do not leave partial observations; request/byte/storage/deadline limits are enforced; 403 cooldown survives restart; unsafe pagination is rejected; missing evidence and synthetic evidence cannot qualify a candidate; distribution autonomy and capacity are screened; results remain attributable to input revisions.

This build is an engineering experiment. Its output is not evidence of customer demand, autonomous operation or profit. The first business candidate remains provisional and its proposed experiment must produce a deliverable an outsider could react to.

Result recorded: 2026-09-15 22:54 UTC, within the 45-minute deadline.

Local engineering outcome: pass. Implemented the stated tranche with Python standard library only, no dependency downloads, no inference and £0 incremental spend. `python3 -m unittest discover -s tests -v` passed 23 checks, including CLI traversal, restart/idempotency, atomic failure recovery, resource gates, persistent cooldown, pagination constraints and evidence/distribution screening.

Saved demonstration: `.root/demo.sqlite3` contains one provisional opportunity, two synthetic observations and one recorded `gather_evidence` decision. A second import inserted zero observations. No synthetic datum was promoted to external evidence; no business candidate was deployed or validated.

Stall: the optional live smoke failed at sandbox DNS resolution, consuming its one-attempt allowance. The required outside-sandbox rerun was then blocked by the engine's unchanged request budget before any HTTP request. `.root/live.sqlite3` records requests=1, downloaded_bytes=0, no packages or observations. Live transport verification is uncertain; see SOURCE_VERIFICATION.md. Waiting for the sandbox escalation consumed part of the build's wall-time budget; one approval interaction occurred, and active owner minutes were not measured.

Stall resolution (same day, parent session): the live smoke was rerun outside the sandbox on a fresh one-request portfolio and succeeded — one request, 5,842 bytes, one live observation imported, pagination checkpoint persisted. Live collector transport is verified; see SOURCE_VERIFICATION.md. The original budget was not retroactively increased; the fresh portfolio carried its own declared budget.

Stop: tranche 1 delivery recorded; no expansion to items 4–8. The remaining market and operating acceptance checks (experiment evaluation, rollout/rollback, recurring health, retirement and measured owner intervention time) belong to the later tranche and have not been demonstrated.
