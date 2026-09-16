# Source verification - tender preview (phase 1 exit evidence)

Verified: 2026-09-16T02:12Z (03:12 BST). Read-only GET, `Accept: application/json`, no auth,
no mutations to any external service.

## Claim under test

That the stored observation set in `evidence/tenders_live.sqlite3` reflects the publisher's
current records: no stale deadline, no missed cancellation.

## Method

Re-queried the live OCDS search endpoint for a wider window than the stored collection
(2026-09-13 to 2026-09-16T03:30Z, `stages=tender`), then compared every East Sussex County
Council release against its latest stored observation, field by field on `tenderPeriod.endDate`
and `tender.status`.

Endpoint: `https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search`

## Result

| ocid (tail) | stored endDate | live endDate | live status | match |
|---|---|---|---|---|
| ...1667b775d81c | 2026-09-16T15:00:00 | 2026-09-16T15:00:00 | active | yes |
| ...27bcb5c5f5ee | 2026-09-17T14:00:00 | 2026-09-17T14:00:00 | active | yes |
| ...31a8634ef4fb | 2026-09-16T12:00:00 | 2026-09-16T12:00:00 | active | yes |
| ...815a406f6346 | 2026-09-17T10:00:00 | 2026-09-17T10:00:00 | active | yes |
| ...88bee05c4709 | 2026-09-16T15:00:00 | 2026-09-16T15:00:00 | active | yes |
| ...6785cac40e8a | 2026-09-18T10:00:00 | 2026-09-18T10:00:00 | active | yes |

32 live releases returned, no next-page cursor. 6 ESCC releases live, 6 stored, 6 matched.
Zero discrepancies, zero cancellations present in this window.

## What this does and does not establish

Establishes: as of the verification instant, all six in-scope notices were live at the
publisher and their stored deadlines equalled the publisher's.

Does not establish: eligibility for any particular operator (vehicle, insurance, DBS,
safeguarding requirements are not published in these notices), that the notices will remain
live, or that any operator wants this information. Deadlines move and notices get cancelled -
the preview states expiry precisely for that reason, and resolution to the latest release is
what catches a cancellation.
