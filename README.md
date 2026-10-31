# Root

Root is a command-line research tool for public procurement notices. It collects
notices into a local SQLite portfolio, resolves amendments, screens opportunities
against declared constraints, records evidence, and evaluates candidate software
components in isolation before adopting them.

"Bounded" is the central design rule: every collection run, experiment, model
call and promotion works inside declared request, byte, time, storage and
spending limits. A model may propose; it cannot authorize adoption or change
collector behaviour. Adoption is a separate, recorded step, and it can be
rolled back.

The intended pipeline is:

```text
collect → resolve releases → screen → optional local-model advice
        → independent evaluation → adoption or rejection → rollback
```

Everything runs on the Python standard library (3.11 or newer). There is no
package installation and no compilation. A local `llama.cpp` runtime is optional
and is used only for the bounded advisory-model steps.

## Status

**Dormant since 17 September 2026.** The repository has 15 commits, all from
September 2026 and all by a single author. The last commit is `53834df`
(17 September 2026). There is no CI workflow.

The first tranche is implemented and documented. External demand has not been
established: no operator has been contacted, no service is distributed or
scheduled, and the prepared operator experiment has not been run. The repository
contains engineering evidence and synthetic fixtures, not a validated product.

## What demonstrably works

This review did not execute the code, so the following describes what is
implemented and documented in the source tree, not behaviour observed here.

- **A complete CLI lifecycle** is present in `root_engine/`: `init`, `collect`,
  `observations`, `screen`, `status`, `brief`, goal and experiment commands,
  promotion commands, the learning-request lifecycle and the World Monitor gate.
- **Collection** (`collector.py`) targets one verified HTTPS endpoint, follows
  `links.next`, enforces request/byte/time budgets, persists a query checkpoint,
  applies a cooldown on 403/429, and imports pages atomically. Source bodies are
  stored as data, never executed.
- **Release resolution** (`brief.py`) resolves notices sharing an `ocid` to the
  latest applicable release, reports amendments and cancellations, and carries
  forward fields omitted by a later release.
- **Screening** (`screen.py`) separates the transparent opportunity check
  (`reject`, `gather_evidence`, `eligible_for_review`) from a cheap keyword
  prefilter that only decides what is worth model time.
- **Independent evaluation and adoption** (`evaluate_component.py`,
  `retry_component.py`, `goals.py`) run candidate behaviour in a separate Python
  process with no inherited credentials and resource limits. Adoption and
  rollback are recorded; completed-goal replay is intended to make no repeated
  effects.
- **Fixture-based demonstrations** exist under `examples/` and `scripts/`, and
  the repository includes synthetic notices, policies, goal specifications and
  evaluation cases.
- **A standard-library `unittest` suite** is present under `tests/`.

The most reproducible path is the offline fixture demo below: it makes no HTTP
request, loads no model and does not touch live data. The repository's own
records describe live collection and a live component-adoption demonstration;
those records are project claims, not results reproduced in this review.

## Experimental, incomplete or planned

- **External demand is untested.** `EXPERIMENT_TENDER_PREVIEW.md` is a prepared
  experiment, not a run one. No operator has been contacted.
- **Milestone items 4–8 are unbuilt.** The later operating milestones — recurring
  operation, measured intervention time, deployment and retirement — are not
  implemented. The repository explicitly does not demonstrate a validated
  research team or a recurring service.
- **Optional model advice is not settled.** The Gemma four-case benchmark scored
  3/4 on synthetic candidate packets with synthetic parser sources; that result
  does not establish general research ability or real repository integration.
  Another local model is reported to pass its classification controls on saved
  runs, but model compatibility and capability remain runtime-dependent.
- **The learning lifecycle is narrow.** One typed request kind
  (`unsupported_adapter_research_v1`) is supported with
  `authority="evidence_only"`, and live retrieval for it is deliberately refused.
  It cannot create a component or a promotion.
- **The World Monitor gate is fixture-only.** Untrusted observations remain
  `pending` and never become authoritative in fixture mode.
- **Promotion notification is optional and unproven end to end.** It invokes an
  explicitly named external CLI without a shell, records bounded attempts, and
  cannot allow or deny a promotion. Its tests use fake executables; no recipient
  was contacted.
- **The keyword prefilter has a known false rejection**: a retry-capable transport
  wrapper that never uses the word "retry" is abstained on. The published matrices
  are small curated synthetic sets, not real-world error estimates.
- **The preview release resolver is deliberately limited.** It is not a general
  schema-aware OCDS compiled-release implementation; later arrays replace earlier
  arrays.
- **This is not a scheduler or a security sandbox.** It is a local bounded research
  tool, not protection against someone editing the Python source or SQLite file.

## Install, run or inspect

Requirements: Python 3.11 or newer. The project was developed and checked with
Python 3.14 according to its README. No third-party Python packages are needed.
For the optional model-advisory commands you also need an existing `llama.cpp`
runtime and a local GGUF model; no weights ship with the repository.

Clone or unpack the repository, then run from its root. The examples below write
state under `.root/`, which is ignored by Git.

Offline demonstration (synthetic fixture; no network, no model):

```bash
python3 -m root_engine --db .root/demo.sqlite3 init \
  --objective 'Find evidence-backed opportunities within the declared constraints'
python3 -m root_engine --db .root/demo.sqlite3 collect \
  --fixture examples/contracts_finder.synthetic.json
python3 -m root_engine --db .root/demo.sqlite3 opportunity-add \
  --file examples/opportunity.json
python3 -m root_engine --db .root/demo.sqlite3 screen
python3 -m root_engine --db .root/demo.sqlite3 observations
python3 -m root_engine --db .root/demo.sqlite3 status
```

The fixture is synthetic and represents no real notices. Re-importing it should
add zero new observations.

Tender-preview demonstration (also offline):

```bash
python3 -m root_engine --db .root/preview.sqlite3 init \
  --objective 'Offline preview demonstration'
python3 -m root_engine --db .root/preview.sqlite3 brief \
  --fixture examples/tender_preview.synthetic.json \
  --as-of 2026-09-16T10:00:00Z
```

The fixture deliberately includes an amended notice so the preview resolves the
later deadline and lists a value omitted by the amendment instead of silently
dropping it. It also includes two notices that should not appear as
opportunities.

Read-only live collection uses a separate portfolio and an explicit policy. The
sample policy permits one request and a small response budget, with spending
disabled:

```bash
python3 -m root_engine --db .root/live.sqlite3 init \
  --objective 'Check source feasibility, not demand' \
  --policy examples/live-smoke-policy.json
python3 -m root_engine --db .root/live.sqlite3 collect --live \
  --published-from 2026-09-14T00:00:00Z \
  --published-to 2026-09-14T23:59:59Z --limit 1
```

Inspect the design and evidence in `ARCHITECTURE.md`, `ADVANTAGE_ENGINE.md`,
`METRICS.md`, `SOURCE_VERIFICATION.md`, `PUBLICATION_AUDIT.md`,
`SELF_IMPROVEMENT_EXPERIMENT.md`, `SELF_IMPROVEMENT_RESULT.md` and the JSON files
under `evidence/`.

Saved databases referenced by some documentation (for example the live
self-improvement portfolio) are machine-local, ignored by Git and absent from a
fresh clone. Commands that read them will not work here; they are not part of the
reproducible path.

## Tests and build evidence

**Observed in this review**

- A standard-library test suite is present: ten `test_*.py` modules under
  `tests/`.
- The package has no third-party dependency manifest; the code is standard-library
  Python.
- No CI configuration is present.
- No test command, build, live collection or model call was executed for this
  review.

**Claimed by the project**

- The README's "Verify" section says
  `python3 -W error::ResourceWarning -m unittest discover -s tests -q` reports
  `Ran 189 tests ... OK`, with no resource warnings.
- `PUBLICATION_AUDIT.md` (16 September 2026) records a final run of 91 tests,
  while `BUILD_EXPERIMENT.md` records 23 checks for the first tranche. These are
  project records from different snapshots, not a current count.
- `SOURCE_VERIFICATION.md` records a successful one-request live fetch
  (5,842 bytes, one observation imported) after an initially failed sandbox
  attempt, plus a separate live GitHub component-adoption demonstration.
- `METRICS.md` reports the synthetic 3/4 advisory-model result, an exact
  prefilter confusion matrix, and adoption of `urllib3/urllib3`'s
  `Retry.parse_retry_after` behind a restricted adapter.

Those claims were not re-run. The 189-test figure in particular should be
treated as the project's statement, not an observed result. Running the command
above is the only way to confirm it on a given checkout.

## Limitations and dependencies

- **One data source.** Collection targets Contracts Finder's OCDS search
  endpoint. The endpoint, its schema or its availability can change; a 403 or 429
  produces a cooldown rather than a retry storm.
- **Live access is deliberately tiny.** Budgets cap requests, response bytes and
  wall time. Failed requests still consume allowance. Oversized or invalid bodies
  do not leave partial observations.
- **Local models are optional and bounded.** They require an existing
  `llama.cpp` runtime and local GGUF weights. Model output is validated for shape
  and provenance but cannot establish the truth of free-text claims, and cannot
  authorize adoption.
- **Evaluation is a curated boundary, not a general sandbox.** Candidate code
  runs in a separate process with no inherited credentials and memory/CPU limits,
  but this is not a security sandbox for arbitrary repository code.
- **Storage and concurrency are local.** A single collector lease prevents
  concurrent jobs; SQLite journals, temporary files and Python memory sit outside
  the database storage cap.
- **Single author, no CI, no external users.** There is no automated build matrix,
  no published release process and no evidence of demand.
- **The evidence export is a projection.** It retains notice identity, publisher,
  deadline/status and classification, but omits parties, contacts, descriptions
  and other free text. It cannot reproduce historical requirement extraction.

## Licence

**No licence is granted.** There is no `LICENSE` file in the repository, and the
project's own README says the licence choice is unresolved. Reuse and
redistribution terms are undecided; contact the copyright holder before reusing
the code.

Third-party material needs separate attention:

- Some evidence JSON appears to contain exported UK procurement notices whose
  original licence — possibly the Open Government Licence v3.0 — has not been
  independently confirmed. Confirm the applicable data licence and attribution
  before redistributing those files.
- The evaluated `urllib3` component is MIT-licensed. It was adopted behind a
  restricted adapter and retained in a local, excluded database; it is not
  vendored into this repository.
- The parser fixtures are synthetic and represent no real notices.
