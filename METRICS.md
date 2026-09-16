# Corrected metrics

This file exists because earlier reporting in this project blended three different things and
overstated one of them. Everything below is restated so the three are separate and the
denominators are explicit.

## Three separate measurements, never one number

| what is measured | subject | can it establish usefulness? |
|---|---|---|
| Model performance | the advisory LLM (Gemma) producing a grounded proposal | no |
| Keyword-prefilter performance | the cheap gate that decides what reaches the model | no |
| Independent adoption decision | the component benchmark that actually accepts/rejects | **yes, for the component** |

None of these establish market demand. Demand is external evidence from operators, which does
not exist yet.

## 1. Model performance — Gemma, 4 synthetic packet cases, real CPU inference

**Audit clarification:** these are synthetic packets with placeholder revisions and synthetic
parser sources. The requests-labelled case does not demonstrate execution of Requests source.
The inference runs were real; the candidate evidence was synthetic.

Run: goal `gemma-four-case-eval`, `evidence/gemma_fourcase.export.json`, 12,288 tokens reserved,
1,024-token generation cap, 14 threads, 2048 context. Result: **3 passed / 4 total**. Evaluation:
`fail`.

| case | expectation | outcome | grounded | independently useful | elapsed |
|---|---|---|---|---|---|
| urllib3-retry | propose | pass | yes | yes | 88.4s |
| requests-retry | propose | pass | yes | yes | 90.3s |
| voice-clone-mismatch | refuse | pass | n/a (refused) | n/a | 70.5s |
| wallpaper-mismatch | refuse | **fail** | yes (cited fields matched packet) | **no** (benchmark found no retry capability) | 108.2s |

Single-case control (`gemma-schema-emission-control`): 1/1, 3,072 tokens reserved, 92.2s.

What the failure is: not fabrication and not a citation error. Gemma cited the packet faithfully
and even named the correct rejection condition ("if `list_wallpapers` does not perform network
I/O") while still proposing integration. It over-proposed on a *plausible* mismatch. The engine's
independent component test rejected it, so **no unvalidated adoption occurred**. This is why the
phase-1 exit is "the gates hold", not "the adviser is perfect".

What this does not establish: that Gemma is generally reliable, that the model would behave the
same on other tasks, or anything about market value.

## 2. Keyword-prefilter performance — exact confusion matrix

Corpus: `examples/prefilter_corpus.json` (10 labelled packets). Matrix is **truth × prediction**:

- **truth** = does the component actually implement retry/backoff semantics
- **prediction** = did the prefilter let it proceed to model review

|  | truth: legitimate (5) | truth: mismatch (4) |
|---|---|---|
| **proceed** | tp = 4 (`urllib3-retry`, `requests-retry`, `desktop-app-with-retry-client`, `image-tool-with-retry`) | fp = 0 |
| **abstain** | **fn = 1** (`retry-capable-but-unnamed-in-excerpts`) | tn = 4 (`wallpaper`, `voice-clone`, `sms-gateway`, `csv-parser`) |

- legitimate-refusal rate: **1/5 = 0.20** — the dangerous error: a usable component discarded.
  The case is a transport wrapper that retries with doubling delay but never uses the word
  "retry" in the supplied excerpts. The prefilter cannot see it; that is by design.
- mismatch-proceed rate: **0/4 = 0.00** — costs review time only; the model and benchmark still gate.

**Separate challenge set** (not used in any rate above): 1 case,
`mismatch-mentions-retry-without-implementing`, in which the text discusses retry and explicitly
says it is not implemented. Prefilter decision: *proceeded*. This is the case that creates the
apparent contradiction in earlier reporting.

### Resolving the "missed mismatches 0/4" contradiction

Earlier I reported "missed mismatches 0/4" while also describing a hard negative the prefilter
cannot catch. Both were arithmetically true and jointly misleading, for two reasons:

1. The hard negative was in a **different denominator**. It was not part of the 4 mismatches; it
   sat inside the legitimate group with an `expect` of "eligible", so it could never appear as a
   missed mismatch. I had relabelled a mismatch's *expected prefilter outcome* to match what the
   prefilter does — which is precisely redefining a mismatch to improve a metric.
2. Its `kind` was "mismatch" but its `expect` was "eligible". Keying the confusion matrix on
   `expect` hid the case's true nature.

The main-set calculation is fixed, but separating a hard negative still lowers the reported
main-set error rate. The combined ten-case matrix is therefore also published: **tp=4, fp=1,
fn=1, tn=4**, with legitimate-refusal rate **1/5** and mismatch-proceed rate **1/5**.
These are small curated synthetic sets, not estimates of real-world error rates.

The case is also in its own `challenge` set, the matrix is keyed on `kind` (truth),
and the divergence between expectation and decision is reported in `expectation_divergence` rather
than being designed away. Current value: empty, because in the main set every expectation now
matches the prefilter's actual behaviour — the honest conflicts live in the challenge set and the
false-rejection case instead.

## 3. Independent adoption decisions

In this project the only component ever adopted was `Retry.parse_retry_after` from urllib3
(MIT), behind a restricted adapter, and adoption was decided by the independent benchmark on a
development/holdout split (7/12 → 12/12 cases), with rollback exercised on an isolated copy.
Adoption is a separate step from proposal generation and a model cannot trigger it.

What this establishes: the engine can gate an adoption correctly. It does **not** establish that
the adopted code was needed, valuable, or that any of it produces revenue.

## 4. What passing tests mean here

91 tests pass (`python3 -W error::ResourceWarning -m unittest discover -s tests`). They are
regression evidence for the code path; they are **not** evidence of general safety, model
reliability, or demand. No test in this suite observes an external customer.

## 5. Tender preview — counts and coverage

- Source: `https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search` (OGL v3.0).
- Live query at verification: 32 releases returned in a 2026-09-13 → 2026-09-16T03:30Z window.
- 6 East Sussex County Council releases; **6 matched** the stored copies on deadline and status,
  0 discrepancies, 0 cancellations in that window (see SOURCE_VERIFICATION_PREVIEW.md).
- Stored set: 32 observations → 29 unique ocids → 3 amended ocids (all `tenderAmendment`).
- Preview at generation: 6 in-scope notices, all SME-flagged, 7 explicit unknowns each.

Coverage limits: one buyer, one category family, a two-day publication window, and a single
publisher. The 3 amended releases were all complete (no field dropped), so the carry-forward
path is exercised by fixture rather than by observed partial release.
