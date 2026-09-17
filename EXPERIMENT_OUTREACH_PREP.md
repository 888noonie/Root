# Operator outreach experiment prep (move #3)

**Status: preparation only. No operator has been contacted, nothing is scheduled, and no
recipient list exists.** This document defines the authorization boundary so that outreach is
never conflated with promotion notification.

## The core separation

There are three distinct authority boundaries in ROOT, and they must never be merged:

| action | tool | authority |
|---|---|---|
| activating an adopted component | `promote-allow` | OS-local shell + portfolio-DB access |
| notifying about an already-pending promotion | `promote-notify` | an explicitly supplied target + a real Hermes send |
| **contacting an operator / business about an opportunity** | **not yet built — requires a NEW authorization** | explicit outreach authorization only |

`promote-notify` is **not** outreach. It tells an existing channel about an internal,
already-pending promotion decision. It says nothing to a business, sells nothing, and opens no
commercial channel. **Reaching out to an operator is a separate, higher-stakes act** because it
spends the business's reputation and touches an external human; it demands its own explicit,
scoped approval.

## Rules for outreach (when a future experiment requests it)

1. **No hard-coded recipient.** An outreach experiment requires a separately declared recipient
   list or channel policy, exactly like `promote-notify` requires `--to`.
2. **No reuse of `promote-notify`'s authority.** `--actor operator` or the notifier path grants
   no permission to contact a business. A new, distinct authorization is required.
3. **Content is reviewed, not model-authored.** Outreach copy is drafted by a human operator and
   reviewed; the model may propose text but cannot send it. This mirrors the rule that model
   output cannot authorize adoption.
4. **Idempotent and revocable.** An outreach experiment must be a single, explicit, logged action
   with a stop switch; nothing scheduled, no automatic retry, no background sending.
5. **Zero-cost boundary holds within this tranche.** Any future outreach that would spend money
   or contact an external recipient requires its own authorization matching the portfolio's
   zero-spending and bounded-resource policy. Nothing in this tranche does that.
6. **Recipient data stays private.** Named individuals' work emails / mobile numbers (as seen in
   procurement payloads) are third-party personal data: never publish raw payloads or their
   SQLite, and redact any export. Outreach contact details, when created, are treated the same.

## What "prepared" means here

- The boundary above is written down and agrees with `ADVANTAGE_ENGINE.md` ("No operator has
  been contacted; nothing is distributed or scheduled").
- No outreach code, recipient list, or sender target exists in this repository.
- `promote-notify` remains test-only (fake executables); no real Hermes send was made.

Any future experiment that wants to contact an operator must first present: the exact recipient
policy, the reviewed copy, the single-action send mechanism, the stop switch, and reuse of this
boundary. It will be implemented only with explicit user authorization.