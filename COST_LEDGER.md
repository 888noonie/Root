# Cost and usage ledger

Two separate things, deliberately never merged: what ROOT spends itself, and what the
agent's own inference costs. A provider banner is not evidence of either.

## ROOT programme spend (the engine under test)

| item | amount | evidence |
|---|---|---|
| live OCDS collection (phase 2 window) | £0.00 | public open-data endpoint, OGL v3.0, no auth, read-only |
| local inference (Qwen classify, Gemma research controls) | £0.00 | local llama.cpp on the laptop, no provider involved |
| downloads / model pulls | £0.00 | none performed |
| hosting / scheduled infrastructure | £0.00 | nothing scheduled or deployed |
| operator contact (phase 2 experiment) | £0.00 | not authorised, not started |

Running total: **£0.00**. Zero here is a real measurement, not a placeholder: the operations
performed are local computation or free public read-only endpoints, and no spending mechanism was
ever invoked. Coverage: 3 collection invocations, 2 recorded goal runs (3,072 + 12,288 tokens
reserved) plus diagnostic single calls, and no `.gguf` added to `~/Models`.

## Agent inference costs (this session's tooling)

The running agent model changed mid-session ("model was just switched ... via Ollama Cloud").
That banner establishes neither capability nor cost. What is knowable from this machine:

- Cloud usage and charges are **not measurable from inside this session**. They appear on the
  provider's own billing page. Recording a number here without that source would be invention.
- What *can* be attributed: this session's cloud inference is agent overhead for editing,
  testing and verification - it is not ROOT's operating cost and must not be counted as one.
- To log it honestly, either paste the provider's usage figure here, or record it as
  `unmeasured` until a billing source exists.

| period | provider | usage | charge | source | status |
|---|---|---|---|---|---|
| 2026-09-15/16 | ollama-cloud (agent model) | not measurable here | not measurable here | provider billing page | **unmeasured** |

To replace `unmeasured` with a fact, obtain the provider's own usage figure and cite it. Until
then the honest statement is: *cloud inference cost is unmeasured and excluded from ROOT's £0
running total.*

## Coverage limits of these claims

- £0 covers what was **observed on this machine** for the listed operations. It does not cover
  electricity, hardware depreciation, or Richard's time.
- The 3-hour development cap has its own ledger (EXPERIMENT_BUDGET.md); its minute figures are
  estimates, not stopwatch measurements.
- "No model downloads" covers model files. It does not claim the network was unused: read-only
  public queries were made by design.

Rule for future entries: an inference run that ROOT itself performs gets logged in ROOT's
table. Inference the *agent* consumes while building ROOT gets logged separately, and never
counts as evidence that ROOT can operate profitably.
