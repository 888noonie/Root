# Experiment budget: seven days, £0, 3 hours additional development

The cap is on **additional development**, and it includes work already done for this experiment.
Recording it now so the remaining allowance is honest.

## Charged so far (phase-1 corrections made specifically for this experiment)

**These minute values are estimates, not stopwatch measurements.** The work ran inside a longer
session, so the split is a judgement about which changes exist solely to make this experiment
valid. Treat the total as `~3h (estimated)` rather than 3h exactly. The estimate is deliberately
not trimmed to leave a convenient remainder: on this reading the allowance is spent.

| item | minutes (est.) | rationale |
|---|---|---|
| deadline summary fix (precise hours, not a coarse window) | 25 | preview was materially wrong about urgency |
| requirement extraction (route, vehicle, PA, registration, flags) | 60 | required for the preview to be actionable at all |
| latest-release resolution + carry-forward + cancellation handling (incl. one corrupted-file recovery) | 55 | stale deadlines or a missed cancellation would mislead an operator |
| publisher-flag reclassification + unknown-field enumeration | 20 | SME flag read as eligibility is a real misrepresentation risk |
| snapshot/expiry rendering semantics | 20 | a preview must not present expired notices as opportunities |
| **total charged** | **~180 min (est.)** | **~3.0 hours estimated** |

**Remaining allowance: ~0 minutes on this estimate.** The development cap is spent. If the
estimate is wrong it is wrong in both directions, so the safe reading is that a new experiment
is required for anything further.

## What this means

No further development work is authorised under this experiment. The preview, questions,
invitation and response template are all prepared. Anything beyond this - a different format,
a scheduled variant, an extra field, a delivery mechanism - is a new bounded experiment with its
own declared cap, not an extension of this one.

If the cap turns out to be wrong, the correct move is to say so and re-ask, not to quietly spend
more.

## Money

£0.00 and no mechanism to spend: no paid placement, no paid data, no mailing service, no hosting.
See COST_LEDGER.md.
