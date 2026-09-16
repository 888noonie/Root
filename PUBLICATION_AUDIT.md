# Independent publication audit

Terra reviewed the first publication on 16 September 2026. This report supersedes
publication-readiness claims and file counts in the earlier Hermes handover. There
was no Git history to compare: the review read the current source, fixtures and evidence.

## Corrections made

- Nested amendment fields are inherited with visible provenance. Explicit null deletions
  cannot resurrect earlier values. Release ordering uses parsed timestamps, including offsets.
  Cancellation is checked after resolution; an omitted cancelled status cannot reactivate a notice.
- The resolver is explicitly limited: later arrays replace earlier arrays. It is **not** a
  general schema-aware OCDS compiled-release implementation. Identifier-array updates require
  further work before claiming that support. Reference:
  [OCDS merging rules](https://standard.open-contracting.org/latest/en/schema/merging/).
- “Not required” passenger-assistant statements are handled before positive “required” matches.
  Empty labels cannot consume the next line. Vehicle ranges cannot become exact seat counts.
  Portal distribution no longer invents a stated registration requirement.
- Exactly reached deadlines are expired. Unknown deadlines are separated from the actionable
  rendered list. Rendering records its own timestamp; score explanations are labelled as
  generation-time assessments. Existing expired records also recompute elapsed time.
- Prefilter truth labels are mandatory. A combined matrix includes the hard negative:
  tp=4, fp=1, fn=1, tn=4; mismatch-proceed rate 1/5. The main/challenge breakdown remains available.
- The real Gemma inference benchmark used **synthetic packets and synthetic test source**.
  Requests-labelled output is not proof of Requests integration. The original 3/4 result and
  raw exports remain unchanged. URL/licence checks do not validate free-text capability claims.
- Research prompts now actually include the packet revision. This is a prompt change, not a
  rerun or promotion of the old benchmark. Custom evaluation-file defaults are normalized
  before their manifest is pinned.
- Raw contact records remain excluded. The earlier redacted export still retained telephone
  numbers in free-text descriptions. Publication now uses an allowlisted metadata projection,
  excluding parties, contacts and descriptions. It cannot reproduce historical requirement
  extraction; the full local database remains available to its owner only.
- README distinguishes machine-local evidence inspection from fresh-clone commands.
  Git ignores cover SQLite sidecars, model weights, desktop metadata and environment files.

## Scope and limits

The source review covered CLI, collector, store, goals, local inference, proposal validation,
restricted parser, subprocess evaluation, screening and preview generation. Regression tests
exercise budget enforcement, source restrictions, fixture/live separation, replay and rollback.
The subprocess and AST restrictions are a curated execution boundary, not a general security
sandbox for arbitrary repository code. Resource ceilings do not establish desktop memory safety
on every machine; model compatibility and capability remain runtime-dependent. Model
resource pinning checks path/byte size/plan, not a cryptographic content hash.

Original benchmark fixtures and raw model evidence were not rewritten to improve outcomes.
No models were downloaded or inferred during this review. No outreach or scheduled service
was started. Historical live notices were not re-fetched; this audit verifies the retained
snapshot and code, not their current availability.

Recorded direct API/download spending remains £0. Electricity, hardware and agent/cloud
inference are not measured by that ledger. The operator experiment's estimated development
allowance remains exhausted. Richard separately authorized this publication audit and necessary
fixes; this work does not extend the customer experiment or authorize distribution.

Project licence and external distribution remain undecided. Customer demand, uniqueness,
autonomous business management and income are unproved.

## Verification

Results are recorded after running the final source in a fresh offline demonstration directory
and against a staged publication snapshot. No credentials, SQLite databases, runtime directories
or model weights are included in the initial commit. See PUBLICATION_MANIFEST.md for the final
tracked-file policy.

Final verification: **91 tests passed** with ResourceWarnings treated as errors. Fresh temporary
portfolios passed fixture collection/deduplication, opportunity screening/status, a historical
amendment preview, and fixture component evaluation with no adoption. The tender demo now
accepts an explicit fixture-only `--as-of` instant, making the demonstration reproducible after
its synthetic deadlines expire. Publication JSON parses and the staged-source checks passed.
