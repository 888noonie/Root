# ROOT

Bounded discovery substrate for the [advantage engine](ADVANTAGE_ENGINE.md). Includes milestone
items 1–3 and the first capability-goal demonstration: objective-specific GitHub discovery,
isolated evaluation, conditional adoption and rollback of a curated component. Standard-library
Python 3.11+; no install or dependency download required. Developed and checked with Python 3.14.

## The problem this addresses

Public procurement data is open, but turning it into something an operator can act on is not
free: notices are amended, deadlines move, cancellations happen, and the fields that determine
whether a small operator can actually bid (insurance, DBS/safeguarding, lot structure, value)
are frequently absent from the notice itself. ROOT's working hypothesis is that the scarce
value is not collection volume but **accurate eligibility assessment, timely change detection
and a trusted route to the operator**.

## Current status, stated plainly

- **Built and verified:** bounded collection from one live public source (Contracts Finder OCDS),
  release resolution to the latest applicable release, deterministic relevance scoring, a
  deterministic keyword prefilter, a keyword-free independent component benchmark, conditional
  adoption with rollback, and a source-verified tender preview.
- **Measured:** model performance (3/4 on a pinned four-case advisory benchmark), prefilter
  performance (exact confusion matrix, including one real false rejection), and source agreement
  (6/6 notices matched the publisher at verification). See [METRICS.md](METRICS.md).
- **Not established:** external demand. No operator has been contacted, nothing is distributed,
  nothing is scheduled, and no revenue exists. An experiment is prepared for review and not run:
  [EXPERIMENT_TENDER_PREVIEW.md](EXPERIMENT_TENDER_PREVIEW.md).
- **Unresolved:** project licence (none chosen; see "Licence" below), model compatibility for any
  candidate replacement model, and whether the tender offer is worth continuing.

The four-case Gemma benchmark used **synthetic candidate packets**, zero-filled revision
placeholders and synthetic parser sources. Its 3/4 result measures behavior on those packets;
it does not verify Requests integration, real repository revisions or general research ability.
The separate live urllib3 adoption demonstration has a different evidence basis.
See [PUBLICATION_AUDIT.md](PUBLICATION_AUDIT.md) for the independent publication review.

## Supported runtime

Standard-library Python 3.11 or newer. No third-party Python packages, no compilation, no
package installation. `llama.cpp` (build 10182 in this environment, CPU-only) is required **only**
for the optional local-model advisory steps; collection, screening, fixture component evaluation and brief generation work without it. Research-role goals require an existing model/runtime. No model
weights ship with this repository.

## First demonstration: a self-improvement goal

ROOT's first goal improves source collection by respecting Retry-After instructions longer than its original five-minute cooldown. It measures the baseline, searches GitHub (with one explicitly declared query fallback), inspects metadata/README/license at a pinned commit, evaluates a supported component against independent development and holdout cases, and enables it only on a live-sourced passing result. This first adapter targets `urllib3/urllib3`; selection and integration are curated, rather than arbitrary repository code generation. Stars are discovery metadata, not acceptance criteria.

On the development machine only, the completed demonstration is retained in the excluded `.root/self-improve-live2.sqlite3`. The following inspection commands require that local database and do not work in a fresh clone:

```sh
python3 -m root_engine --db .root/self-improve-live2.sqlite3 goal-show --id respect-source-cooldowns
python3 scripts/verify_saved_goal.py --db .root/self-improve-live2.sqlite3
```

The verifier checks that completed-goal replay makes no repeated effects, then exercises rollback on a temporary SQLite copy; the original adapter stays enabled. The adopted parser changes collector behavior only for its portfolio database. It retains the complete source file and MIT license in SQLite; only the restricted named function is executed, never the full fetched module. It uses standard-library dependencies with no package installation. Function syntax, names, calls and regex are constrained; candidate evaluation runs in a separate Python process with no inherited credentials and memory/CPU limits.

For a separately budgeted new demonstration, the live pass now leaves the candidate **pending** rather than activating it immediately. An explicit operator command is required to promote:

```sh
python3 -m root_engine --db .root/self-improve.sqlite3 init --objective 'Improve affordable, reliable public-source collection' --policy examples/self-improvement-policy.json
python3 -m root_engine --db .root/self-improve.sqlite3 goal-create --file examples/self_improvement_goal.json
python3 -m root_engine --db .root/self-improve.sqlite3 goal-run --id respect-source-cooldowns --live
python3 -m root_engine --db .root/self-improve.sqlite3 goal-show --id respect-source-cooldowns
# pending promotion row; no behavior change yet
python3 -m root_engine --db .root/self-improve.sqlite3 promote-show --id <PROMOTION_ID>
python3 -m root_engine --db .root/self-improve.sqlite3 promote-allow --id <PROMOTION_ID> --actor operator
```

`promote-allow` re-evaluates the exact stored artifact bytes, the pinned case manifests, provenance, licence, and trusted-code drift fingerprint before atomically switching the active component pointer. Fixture passes remain non-promotable and cannot be allowed. `promote-show` is read-only and JSON-safe. `promote-deny --id <PROMOTION_ID> --actor <label> --reason <text>` closes the request without activation. All three commands emit canonical JSON; a passing live evaluation alone never changes collector behavior.

`promote-notify --id <PROMOTION_ID> --to <Hermes target> --hermes-bin /absolute/path/to/hermes` is an optional, explicit delivery attempt for an already-pending live promotion. It accepts no hard-coded recipient, invokes `hermes send --to TARGET --json MESSAGE` without a shell, uses a fixed timeout, records a bounded attempt/result event, and cannot allow, deny, or otherwise change promotion authority. A missing CLI, timeout, nonzero exit, negative/malformed receipt, or uncertain delivery leaves the row pending. The executable must be an absolute regular path; no PATH-selected executable is trusted.

`learn-create --file REQUEST.json`, `learn-run --id REQUEST_ID --fixture FIXTURE.json`, and `learn-show --id REQUEST_ID` implement the one typed `unsupported_adapter_research_v1` lifecycle. The record has `authority="evidence_only"`: it cannot create a component, promotion, or collector behavior change. Live retrieval is intentionally refused for this first request kind; no network operation is implied by a learning request.

Use `--fixture examples/github.synthetic.json` instead of `--live` for offline replay. It may pass behavioral evaluation but never creates a promotable artifact. An already-satisfied goal skips discovery and adoption. A stopped/interrupted goal does not silently restart or replenish allowances. A new goal requires a new explicit specification within the portfolio's remaining limits. `goal-run` exits 2 for a stopped goal and 1 for a failed evaluation.

Goal request/body-byte/time/inference limits are independent of the portfolio limits. New specifications also declare zero spending, one concurrent job and a record-storage limit. Record storage counts UTF-8 payloads plus a conservative row overhead; the portfolio separately caps SQLite page allocation. New goals record hashes of development and holdout inputs at creation and refuse execution if they change. Earlier saved demonstration profiles retain their baseline case snapshots instead. Stop and audit records are preserved even after time runs out. `goal-rollback --id ...` remains available after deadlines expire and does not shorten any already-promised source cooldown.

## Optional local models

```sh
python3 -m root_engine models
```

The inventory reads bounded GGUF metadata without loading weights. On the development machine it found Qwen2.5 0.5B (397,808,192 bytes) and a Gemma4 GGUF (5,762,908,128 bytes: 5.76 GB / 5.37 GiB, size label 7.5B). The adapter uses the existing llama.cpp runtime, CPU only; no weights or runtime downloads are needed.

`goal-run --local-review` reviews a relevant description and a synthetic negative control. By default it uses Qwen. To select another existing GGUF, bind it when creating a new goal:

```sh
python3 -m root_engine --db .root/trial.sqlite3 goal-create --file YOUR_GOAL.json --model /absolute/path/to/model.gguf
```

Creation retains the resolved model path, file size and bounded resource plan. Resource changes stop execution. Both controls are reserved atomically before discovery or model execution: the small plan requires 2,304 tokens total (1,024 context + 128 generation per call, 90-second call ceiling); the mid plan requires 4,480 (2,048 + 192 per call, 480-second ceiling). Both remain bounded by the goal deadline and portfolio allowances. The sample policy permits only the small plan; using the mid plan requires a separately declared goal and portfolio allowance. Failed calls retain reservations, and the adapter terminates the subprocess group. Model output cannot authorize adoption or change the evaluator.

Qwen now passes both classification controls on saved live runs. The earlier failures contain grammar-sampler initialization errors; removing `--json-schema` from the tested command fixed those runs while retaining output validation. The saved database named `gemma_full` also identifies Qwen, so it does not validate Gemma through the goal runner. Hermes reported a separate direct Gemma trial; that remains distinct from the audited goal evidence. See [SELF_IMPROVEMENT_RESULT.md](SELF_IMPROVEMENT_RESULT.md). ROOT's component adoption is determined by the independent evaluator.

## Run the offline demonstration

From this directory:

```sh
python3 -m root_engine --db .root/demo.sqlite3 init --objective 'Find evidence-backed opportunities within zero-cash and owner-time constraints'
python3 -m root_engine --db .root/demo.sqlite3 collect --fixture examples/contracts_finder.synthetic.json
python3 -m root_engine --db .root/demo.sqlite3 opportunity-add --file examples/opportunity.json
python3 -m root_engine --db .root/demo.sqlite3 screen
python3 -m root_engine --db .root/demo.sqlite3 observations
python3 -m root_engine --db .root/demo.sqlite3 status
```

The example correctly returns `gather_evidence`: its channel feasibility and owner-time budget are unresolved and it has no external evidence. The synthetic fixture represents no actual notices. Repeat the fixture import: zero new observations. Initialization refuses to overwrite an existing database.

## Fixture-only quickstart: the tender preview (no network, no weights)

Everything below runs offline from a synthetic fixture. No HTTP request is made and no model is
loaded. The fixture is **not real** - do not act on the notices in it.

```sh
python3 -m root_engine --db .root/preview.sqlite3 init --objective 'Offline preview demonstration'
python3 -m root_engine --db .root/preview.sqlite3 brief --fixture examples/tender_preview.synthetic.json --as-of 2026-09-16T10:00:00Z
python3 -m root_engine --db .root/preview.sqlite3 brief --fixture examples/tender_preview.synthetic.json --as-of 2026-09-16T10:00:00Z --json
```

The fixture contains four observations covering three synthetic notices, deliberately including:

1. an in-scope East Sussex County Council transport notice,
2. a same-`ocid` **amendment** with a revised deadline and a distinct release id, which also
   omits a contract value the first release stated,
3. a right-buyer/wrong-category notice (wallpaper), and
4. a right-category/other-buyer notice.

Expected behaviour, and what makes the demonstration meaningful: the preview resolves notice 1 to
its **amendment** (the later deadline, not the stale one), reports the `tenderAmendment` tag, and
lists the omitted `tender.value` under "Carried forward from an earlier release" rather than
silently dropping it. Notices 3 and 4 do not appear as opportunities. Each rendered opportunity
states its exact expiry with hours remaining, the facts stated in the notice, a separately
labelled publisher flag, and the fields the notice does **not** publish.

## Verify

```sh
python3 -W error::ResourceWarning -m unittest discover -s tests -q
```

Expected: `Ran 150 tests ... OK`, with no resource warnings. The suite is standard-library only.

## Offline authority-boundary walkthrough

```sh
scripts/offline_boundary_demo.sh
```

The script creates a fresh temporary database, runs the Retry-After fixture goal and an evidence-only fixture learning request, queries SQLite to assert zero components/promotions and one knowledge record, then proves a fixture leaves no promotion ID to allow (an attempted nonexistent ID is refused). It makes no network request, sends no Hermes message, and removes its temporary database on exit.

## Architecture

Collection → release resolution → deterministic screening → optional model advice → independent
evaluation → adoption → rollback, with every stage bounded by a declared policy.

- **Collection** (`collector.py`): one verified HTTPS endpoint, pagination via `links.next`,
  declared request/byte/time budgets, a persisted query checkpoint, and a cooldown on 403/429.
  Source bodies are stored, never executed as instructions.
- **Release resolution** (`brief.py: resolve_latest`): releases sharing an `ocid` are distinct
  immutable records; the latest by release date (release id as deterministic tiebreak) is used,
  so a revised deadline supersedes the old one and a cancellation is reported rather than hidden.
  Nested object fields omitted by later releases are **carried forward and listed**; explicit
  null deletions are respected. Arrays supplied later replace earlier arrays. This limited
  preview resolver does not implement schema-aware OCDS identifier-array merging and must
  not be treated as a general compiled-release implementation. The path for this was exercised against live data, where all three amended
  releases were complete; the partial-release path is covered by fixture.
- **Screening** (`screen.py`): two separate things. `screen()` is the transparent opportunity
  eligibility check (missing fields, policy bounds, evidence resolution). `screen_packet()` is a
  cheap **keyword prefilter** that decides only what is worth spending model time on - it is not
  a capability test and its refusals are recorded as keyword-level abstentions.
- **Model advice** (`local_models.py`, `research.py`): an optional bounded local LLM proposes or
  refuses using only a collector-supplied candidate packet. A strict validator checks output shape and the repository URL and licence against the packet;
  it cannot verify the truth of the free-text integration and benefit claims. The model cannot authorize anything.
- **Independent evaluation** (`retry_component.py`, `evaluate_component.py`): a keyword-free
  benchmark runs the candidate's actual parsed behaviour in a separate process with no inherited
  credentials and memory/CPU limits. This, not the model, decides adoption.
- **Adoption and rollback** (`goals.py`): adoption is a separate step, recorded with its evidence;
  `goal-rollback` reverses it, and completed-goal replay makes no repeated effects
  (`scripts/verify_saved_goal.py`).

## Licence and provenance

**This project's own licence is an unresolved decision and has not been chosen here.** No
`LICENSE` file is asserted by this repository; the choice belongs to the repository owner.

Third-party components encountered, all used as *evaluated candidates* rather than vendored:

| component | licence | how it is used |
|---|---|---|
| `urllib3/urllib3` (`Retry.parse_retry_after`) | MIT | adopted behind a restricted adapter; complete source and licence retained in the local SQLite portfolio |
| `psf/requests` | Apache-2.0 | evaluated as a candidate only |
| Contracts Finder OCDS data | OGL v3.0 | public open data, read-only, attributed in the evidence export |

No fetched upstream modules are vendored into this repository; parser examples are synthetic fixtures. The synthetic fixtures are original
and represent no real notices. The live evidence export
(`evidence/tenders_live.export.json`) is an allowlisted projection of identity, buyer, deadline/status and classification fields.
Contacts, parties and free-text descriptions are omitted; it is not a complete release and
cannot reproduce extraction of the historical preview.

## Read-only live collection

Use a separate portfolio with a declared budget. The sample policy permits one HTTP request and at most 2 MiB of response body, no money and no model inference, for 30 minutes after initialization:

```sh
python3 -m root_engine --db .root/live.sqlite3 init --objective 'Check source feasibility, not customer demand' --policy examples/live-smoke-policy.json
python3 -m root_engine --db .root/live.sqlite3 collect --live --published-from 2026-09-14T00:00:00Z --published-to 2026-09-14T23:59:59Z --limit 1
python3 -m root_engine --db .root/live.sqlite3 observations
```

Pagination follows `links.next` on the exact verified HTTPS search endpoint. By default one page is fetched per invocation, at most three with `--max-pages 3` and sufficient portfolio allowance. The query checkpoint and page import commit together; a subsequent invocation with the same bounds and limit resumes, or does nothing after completion. Failed requests still consume request allowance. Invalid or oversized bodies do not leave partial observations. HTTP 403 persists a five-minute cooldown with no automatic retry; 429 also pauses for five minutes. Network redirects are disabled. Source data is retained, never executed as instructions.

The immutable policy's request and body-byte limits apply cumulatively to a portfolio. Money stays disabled; local inference is possible only with a nonzero configured token allowance. The deadline is wall time from initialization, including idle time; status and observation inspection remain available afterward. SQLite writes reserve space conservatively and check database page allocation before committing. The storage cap covers the database, not project files, temporary SQLite journals or Python memory. Local JSON inputs are separately capped at 2 MiB. A response that exactly exhausts the byte allowance is conservatively discarded because confirming EOF would need another read.

A single collector lease prevents concurrent jobs; an interrupted ordinary collection job's lease expires after 60 seconds. Capability goals retain the lease through their declared deadline plus 15 seconds. Ordinary network reads have a ten-second inactivity timeout; the collector checks its 30-second invocation limit between reads and pages. A blocking read can delay that check by its timeout. This is local bounded research, not a scheduler or a security sandbox against someone editing Python/SQLite.

## Opportunity records and screening

Use [examples/opportunity.json](examples/opportunity.json) as the schema example. Edit it and re-import with `opportunity-add --file ...`; the candidate revision changes and previous screen decisions remain recorded. The OCDS collector imports observations only. It does not assert that a notice is a profitable business.

Copy IDs from `observations` into `evidence_refs`. Each claim is explicitly `hypothesis`, `estimate`, `unknown` or `observed`; an observed claim requires an `observation_id` referencing live data. A valid reference establishes provenance only; whether it actually supports the claim is a later research-review responsibility. Live procurement records cannot by themselves establish demand for a service about those records.

Screening emits reasons and one of:

- `reject`: declared costs, owner workload or experiment budgets exceed current bounds.
- `gather_evidence`: missing information, unestablished channel feasibility, or absent external observations.
- `eligible_for_review`: complete enough for research review, with external source provenance. It does not establish willingness to pay or authorize experiments, outreach or deployment.

Distribution must name a channel and steps, declare `agent`, `hybrid` or `human` autonomy, describe owner steps when needed, and declare whether it fits the operating policy. Weekly owner workload must include distribution and support, with a capacity limit. All cost numbers remain the candidate's estimates until measured. The candidate's smallest test must name a real external deliverable and an external evidence method, plus criteria and resource limits; that test is not executed by this tranche.

## Verify

```sh
python3 -m unittest discover -s tests -v
```

Automated tests use synthetic inputs and mock HTTP. The separately logged GitHub capability demonstration used live retrieval. Build budgets and outcomes are in [BUILD_EXPERIMENT.md](BUILD_EXPERIMENT.md) and [SELF_IMPROVEMENT_EXPERIMENT.md](SELF_IMPROVEMENT_EXPERIMENT.md); source provenance is in [SOURCE_VERIFICATION.md](SOURCE_VERIFICATION.md). The complete business traversal in milestone items 4–8 remains unbuilt. No validated research-model team, recurring business, public deployment or profit has been demonstrated.
