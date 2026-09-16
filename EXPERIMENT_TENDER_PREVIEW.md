# Phase 2 experiment: does the tender preview save an operator effort?

Status: **drafted, not authorised, not run.** No operator has been contacted. Nothing has been
distributed. This document is the thing to approve or reject before any contact happens.

## Product hypothesis

> "We reduce the work needed to identify transport opportunities you can actually pursue."

Deliberately not a claim about model quality, scraper uptime or volume of notices. If the
preview does not reduce an operator's effort to find opportunities they can act on, it has no
value regardless of how well the engine runs.

## What is being compared

Not "preview versus nothing". Operators already have alerts (Contracts Finder email alerts,
SProc.net notifications, trade-association circulars). The comparison is the operator's
**existing alert process** versus the preview, on four measured quantities:

| measure | how it is captured |
|---|---|
| actionable opportunities found | count of notices the operator says they could actually pursue, per source |
| irrelevant notices removed | count the operator says they would have had to read and discard, per source |
| checking time | operator's own estimate of minutes spent per week on this today vs after reading the preview |
| requests another brief | binary: did they ask for the next one without prompting |

Payment interest is recorded separately and is not counted as demand if it is only a
compliment ("this is useful"). A stated willingness to pay a specific amount, or asking what
it costs, is recorded as payment interest; "nice work" is not.

## Draft preview (what an operator would receive)

`evidence/TENDER_PREVIEW.md` - generated from live publisher records at the stated instant.
Each notice states: exact expiry with hours remaining, route, vehicle line, passenger-assistant
obligation, frequency, portal/registration condition, and an explicit list of what the notice
does **not** publish (value, award criteria, insurance/DBS requirements, full addresses).
That unknown list is the honest core of the offer: it tells an operator where they must still
do their own work.

## Feedback questions (draft - 6 questions, no leading praise prompts)

1. Looking at these six notices, how many could you genuinely pursue with your current vehicles?
2. Which of them had you already seen through your normal route? (tests overlap, not novelty)
3. Roughly how long would finding these through your usual process have taken you?
4. What is missing here that you would need before you would bid on one of these?
5. Is anything here wrong or out of date compared with what you see on the portal?
6. Would you want the next one of these sent to you? (and if so, weekly or daily)

Question 4 is the load-bearing one: the continuation threshold counts *operators independently
identifying useful information missing from their existing process*.

## Proposed distribution method (requires explicit authorisation)

Not chosen yet - this is the decision to approve. Options with honest caveats:

1. **One operator, in person or by phone, reading the preview together.** Cheapest, highest
   signal, and the operator can point at what is wrong. Costs Richard's time, not money.
2. **Email to a small number of named operators**, using addresses published on their own
   websites or the buyer's contact route. Must comply with UK direct-marketing rules for
   business-to-business contact and identify the sender and opt-out in the message.
3. **Post in an operator community** (owner-driver or trade group). Lowest effort, lowest
   signal, and risks looking like promotion rather than testing.

Authorisation must name: which channel, how many operators, and whether Richard makes contact
himself or the agent drafts for his review. No contact occurs without that.

## Bounds

- Money: £0. No paid placement, no paid data, no paid mailing service.
- Additional development: capped at 3 hours. The preview generator already exists; the cap
  covers fixes and formatting only.
- Duration: 7 days from authorisation, or until the threshold is met, whichever is first.
- No customer promises, no commitments, no pricing offered.

## Decision rule (pre-declared, before contact)

- **Continue:** two operators independently identify useful information missing from their
  existing process, and at least one requests continued delivery.
- **Revise:** operators engage but flag the same defect (wording, wrong notices, missing field).
  The defect is then the next experiment's subject.
- **Stop:** no operator identifies anything they could act on that they did not already have.
- **Inconclusive:** no responses. An unanswered experiment is not a successful one, and this
  result must be recorded as such rather than reframed.

## Phase 3 is gated on this result

Automation (bounded collection, change detection, freshness checks, an authorised delivery
channel) is **not started and must not start** until this phase passes. Building a scheduled
service for an unvalidated offer would automate a guess.

Already enforced in code, so phase 3 cannot quietly skip them: a `/goal` is refused at creation
unless it names a `bottleneck` and an `acceptance` test; component candidates are revision-pinned
and licence-checked before evaluation; adoption is a separate step from proposal generation
(a proposal passes review, a screen and an independent component test before any portfolio
change, and `goal-rollback` exists to undo one). Model downloads stay paused: no named measured
bottleneck currently exists, and compatibility for Granite remains unresolved (see
RESEARCH_BENCHMARK.md).
