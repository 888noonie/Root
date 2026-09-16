> Historical Hermes report; the independent publication corrections in PUBLICATION_AUDIT.md supersede readiness claims and metrics below.

# Handover to Terra

Date: 2026-09-16. Prepared by Hermes for independent verification. **Not pushed.** Terra commits
and pushes to `888noonie/Root` after verifying.

## Statement of state (read this first)

- **External demand: unvalidated.** No operator has been contacted. No reply, meeting, trial user
  or payment intent exists. This is the largest open question and it has not been touched.
- **Nothing distributed or scheduled.** No email, no post, no live offer, no cron job, no daemon.
  The distribution channel and recipients are deliberately unresolved pending authorisation.
- **Cloud inference cost: unmeasured.** The provider-switch banner establishes neither capability
  nor cost. Charges are not visible from inside the session; recorded as `unmeasured` in
  COST_LEDGER.md rather than estimated.
- **ROOT's own direct spend: £0.00**, measured (local compute plus free public read-only endpoints).
- **No model downloads. No cloud experiment.** None performed, none configured.
- **Project licence: unresolved.** No LICENSE file added; not invented on the owner's behalf.

## Changed files (32, including this handover)

Code (4): `root_engine/brief.py`, `root_engine/screen.py`, `root_engine/goals.py`,
`root_engine/local_models.py`, `root_engine/__main__.py` (5 counting `__main__`).
Tests (1): `tests/test_engine.py`.
Fixtures (7): `examples/prefilter_corpus.json`, `examples/tender_preview.synthetic.json`,
`examples/research_component.goal_screens.json`, `examples/research_component.screen_cases.json`,
`examples/research_component_goal_gemma.json`, `examples/research_control_goal_gemma_1024.json`,
`examples/research_fourcase_goal_gemma.json`, `examples/research_screen_goal.json`.
Evidence (5): `evidence/TENDER_PREVIEW.md`, `evidence/TENDER_BRIEF.json`,
`evidence/tenders_live.export.json`, `evidence/gemma_control2.export.json`,
`evidence/gemma_fourcase.export.json`.
Docs (9): `README.md`, `METRICS.md`, `PUBLICATION_MANIFEST.md`, `COST_LEDGER.md`,
`RESEARCH_BENCHMARK.md`, `ADVANTAGE_ENGINE.md`, `SOURCE_VERIFICATION_PREVIEW.md`,
`EXPERIMENT_TENDER_PREVIEW.md`, `EXPERIMENT_BUDGET.md`, `EXPERIMENT_INVITATION_DRAFT.md`,
`EXPERIMENT_RESPONSE_RECORD.md`.

Repair note: `root_engine/screen.py` was corrupted mid-session by a bad in-place edit (a replace
on an empty pattern expanded the file to 26 MB). It was deleted and **rewritten from scratch**;
its full content is reproduced in the new file and both of its functions are covered by tests.
Worth a git diff review rather than a skim.

## Commands run and actual results

```
python3 -W error::ResourceWarning -m unittest discover -s tests -q
  -> Ran 86 tests ... OK            (no ResourceWarnings)

# README offline demonstration (verbatim)
init                       -> OK
collect --fixture contracts_finder.synthetic.json -> inserted 2, mode fixture
opportunity-add            -> procurement-brief-provisional
screen                     -> gather_evidence, 4 missing fields
observations               -> 2
status                     -> OK

# Fixture-only preview demonstration (verbatim)
brief --fixture examples/tender_preview.synthetic.json       -> 45 lines markdown
brief --fixture examples/tender_preview.synthetic.json --json
  -> relevant_count 1, actionable 1
     resolved deadline 2026-09-18T10:00:00+01:00 (the amendment, not the stale 17th)
     release_tags ['tenderAmendment'], carried_forward ['tender.value']
```

Live source re-query (read-only, `Accept: application/json`): 32 releases in a
2026-09-13 → 2026-09-16T03:30Z window; 6 East Sussex County Council releases; **6/6 matched** the
stored copies on deadline and status; 0 discrepancies; 0 cancellations. See
SOURCE_VERIFICATION_PREVIEW.md for the per-notice table.

## Corrected metrics

Full detail in METRICS.md. Summary of what changed:

1. **Model vs prefilter vs adoption are now separated** and never combined into one number.
   Gemma: 3/4 (single-control 1/1). The miss is a *fit-judgment* error on a plausible mismatch
   (faithful citations, over-proposal); the independent benchmark rejected it, so nothing
   unvalidated was adopted.
2. **The "missed mismatches 0/4" contradiction is resolved.** The hard negative was in a
   *different denominator*: it sat inside the legitimate group with `expect="eligible"`, so it
   could never register as a missed mismatch. I had relabelled a mismatch's expected prefilter
   outcome to match prefilter behaviour — the exact redefinition the close-out forbids. Now fixed:
   the matrix is keyed on truth (`kind`), the case sits in its own `challenge` set
   (1 case, proceeded), and `expectation_divergence` is reported rather than designed away.
3. **Exact confusion matrix (truth × prediction):** tp=4, fp=0, **fn=1**, tn=4, over 5 legitimate
   and 4 mismatch packets. Legitimate-refusal rate **1/5 = 0.20** — a real, reported error: a
   transport wrapper that retries with doubling delay but never says "retry" in its excerpts.
   Mismatch-proceed rate 0/4. The challenge set is excluded from every rate.
4. **Tests prove regressions, not safety or demand.** 86 pass; none observes a customer.

## Experiment budget: used / remaining

- Additional development: **~3.0 h of 3.0 h used** (estimates, not stopwatch; itemised in
  EXPERIMENT_BUDGET.md). **Remaining: ~0.** Anything further needs a new bounded experiment.
- Money: **£0.00 of £0.00**. No spending mechanism exists.
- Prepared and unused: preview, six feedback questions, invitation draft, response-record
  template, pre-declared decision rule. **Not sent.**

## Publication inclusions / exclusions

Full table in PUBLICATION_MANIFEST.md. Headlines:

- **Include 59 files** (code, tests, fixtures, docs, 5 portable evidence exports).
- **Exclude `evidence/tenders_live.sqlite3`** — it contains third-party personal data from the
  raw publisher payload: **named individuals' work emails and mobile numbers**. The rendered
  preview and the redacted export contain none of it (verified: 0 email matches after redaction).
- **Exclude the two Gemma `.sqlite3` files** (binary, machine-local paths) — portable JSON exports
  replace them.
- **Exclude `.root/`** entirely (runtime scratch, regenerable by the documented commands).
- Fixtures: four Gemma/Qwen goal fixtures now carry a documented placeholder path instead of this
  machine's absolute path; `local_models.py` reads `ROOT_MODELS_DIR` / `ROOT_LLAMA_CLI` with `~/...`
  defaults. The two evidence exports keep their verbatim run-time paths deliberately, annotated,
  because editing an evidence record would misrepresent the run.
- **No `.gguf` is inside the project directory**, so no weights can be committed.

## Unresolved decisions (for the owner, not for me)

1. **Project licence** — none chosen. Recommend the owner pick explicitly before or after the
   first commit; nothing here presupposes one.
2. **Distribution channel and recipients** for the operator experiment (in-person/phone vs B2B
   email vs community post), and whether Richard makes contact or the agent drafts for review.
3. **Granite / replacement-model question** — compatibility remains *unresolved*, not ruled out:
   architecture-family names cannot establish compatibility with a model release. Method stated in
   RESEARCH_BENCHMARK.md. No download until a measured bottleneck plus release-metadata and
   runtime-loader support.
4. Whether to keep `ARCHITECTURE.md` and `DELIVERY_PLAN.md` in the tree as history (currently
   included, marked superseded).

## Suggested first-commit message

```
Initial publication: ROOT bounded advantage engine

Bounded discovery substrate: public-source collection with declared budgets,
release resolution to the latest applicable OCDS release (with carry-forward),
deterministic relevance scoring and a keyword prefilter that is measured as a
prefilter rather than a capability test, optional bounded local-model advice,
and a keyword-free independent component benchmark that alone decides adoption.

Evidence included as portable, redacted exports. Personal contact data from the
publisher payload and the machine-local SQLite files are deliberately excluded.

Status: external demand unvalidated, nothing distributed or scheduled, no
revenue, £0 direct spend, cloud inference cost unmeasured, no licence chosen.
86 tests pass offline with no network access and no model weights.
```
