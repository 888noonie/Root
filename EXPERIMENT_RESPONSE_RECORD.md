# Response record template (fill per operator, no contact yet)

One block per operator. Leave blank rather than infer. "No response" is a recorded outcome,
not a missing value, and an all-blank experiment is **inconclusive**, not a success.

    operator_id:
    contact_date:
    contact_channel:            # in-person | phone | email | community post
    consent_basis:              # why contacting this operator was acceptable
    preview_version:            # e.g. evidence/TENDER_PREVIEW.md at <generated timestamp>
    existing_alerts_used:       # what they say they already receive

    Q1 could_pursue_count:            # integer or 'unanswered'
    Q2 already_seen_via:              # which notices they had already seen, and via what
    Q3 minutes_usual_process:         # their estimate today
    Q4 missing_information:           # verbatim, and whether it duplicates existing process info
    Q5 errors_or_stale_found:         # anything wrong vs what they see on the portal
    Q6 requests_continuation:         # yes | no | unanswered   (and desired frequency)

    independently_useful_info:        # NEW info they did not have from their own process
    payment_interest:                 # none | asked price | named amount | other - recorded
                                      # separately; a compliment is NOT payment interest
    notes:

## Scoring this at the end of the seven days

    operators_contacted:
    operators_responding:
    operators_identifying_useful_missing_info:   # threshold: >= 2
    operators_requesting_continuation:           # threshold: >= 1
    payment_interest_count:                      # reported separately, never merged

    outcome: continue | revise | stop | inconclusive
    outcome_reason:

Decision rule (pre-declared, unchanged): **continue** if two operators independently identify
useful information missing from their current process AND at least one requests continuation.
**Revise** if they engage but flag the same defect. **Stop** if none identifies anything
actionable they did not already have. **Inconclusive** if there are no responses.
