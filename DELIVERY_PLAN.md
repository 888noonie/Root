# ROOT: delivery before expansion

Superseded by [ADVANTAGE_ENGINE.md](ADVANTAGE_ENGINE.md). The opportunity qualification service below is an optional experiment, not ROOT's overall product scope. Preserve its evidence and delivery checks where applicable.

Decision proposal, 2026-09-15. This plan supersedes the build order in ARCHITECTURE.md. ROOT is the working name; the workspace remains Oct8pia. No deployment, outreach or spending has occurred.

## Objective and central correction

Create a repeatable service that a reachable customer pays for and that Richard can pause or hand over during recovery. Income is an objective, not a promised result. The first milestone is a useful deliverable and evidence of willingness to pay. Self-improvement is deferred until delivering that service exposes a recurring engineering problem.

The previous architecture made a mistake: it put model benchmarking and repository discovery ahead of customer validation. That allows engineering activity to continue without proving the business. The revised sequence is customer problem, sample deliverable, paid pilot, repeatable production, bounded autonomy, then measured capability improvement.

## Initial offer hypothesis

ROOT produces a short opportunity qualification brief for one small-business niche. It identifies relevant new or changed public procurement notices and explains what merits the owner's attention. The customer's decision is whether to investigate an opportunity, not whether to trust an opaque score.

Public procurement is a provisional starting point because official structured data is available. It is not a claim of an underserved market. Choose the niche by access to owners and demonstrated pain. If Richard has stronger access to another sector with a recurring information chore, that access can change the offer before implementation.

The government already offers free contract search and saved-search email updates. Selling the same alerts would have weak differentiation. The proposed paid work is qualification against a real business's services, geography, capacity and documented requirements, plus a concise account of material changes.

Proposed pilot offer: a fixed two-week trial for £100, covering one business profile, a weekday check and up to three relevant opportunities per brief when any exist. This is a pricing experiment, not a market valuation. Confirm scope and fee with an actual buyer before accepting work. Never manufacture opportunities to fill a quota. No promise of contract wins or comprehensive market coverage.

## Deliverable contract

Each opportunity card contains:

- Buyer, notice title, official link, source notice identifier and last checked time.
- Publication or update date, current stage and deadline with its stated timezone where supplied.
- Stated value and geography, explicitly unknown when absent.
- Fit reasons linked to the agreed business profile.
- Mandatory requirements found in the inspected material, with quotations or precise references; whether attachments were inspected.
- Reasons to skip, unanswered questions and the next practical step.

Use “worth checking”, “likely unsuitable” or “insufficient information” with reasons. Do not declare complete eligibility from a short notice. Distinguish a completed check with no matches from a failed or incomplete check. Corrections must be traceable to the earlier brief.

## Work packets and decision gates

These are work packets, not calendar promises. Richard's availability determines the pace.

### 1. Prove a useful sample before building the pipeline

Obtain one business profile: services, service area, typical job size, hard exclusions and known credentials. Inspect current official notices and prepare one real sample brief. Record actual review effort. If there are no relevant opportunities, widen the observation window transparently or reconsider source/niche; do not present old notices as current opportunities.

Prepare a short list of plausible prospects and a demonstration message. Richard can send it, or explicitly authorize sending. Ask prospects what they currently use, what they miss, and which part of the sample saves work. A compliment is weaker evidence than a request for another brief; payment is stronger evidence still.

Gate: at least one owner confirms a specific useful decision or a recurring chore the brief improves. If the profile cannot produce a useful sample, change the offer before building infrastructure.

### 2. Make a concrete paid offer

Use the sample in up to ten qualified conversations if capacity permits. These are actual conversations with relevant decision makers; unanswered messages do not count as rejection of the product.

Gate: secure one paid pilot or a concrete agreement to buy it at the stated scope and price. If ten relevant conversations yield no such commitment, pause expansion and inspect why: poor buyer access, weak need, inadequate sample, wrong scope or wrong price. Change one assumption at a time. Ten is an operational stop rule, not a statistically conclusive market test.

### 3. Build only the pilot's production path

Implement one Python application with these boundaries:

1. Fetch official structured notices in bounded date windows, with pagination, timeouts, retry/backoff and saved source responses.
2. Normalize releases while retaining source identifiers and versions. Preserve amendments and cancellation stages; avoid treating every release as a new opportunity.
3. Store source evidence, run status, business profile and processing state in SQLite.
4. Apply deterministic filters for explicit profile criteria. Keep unknown data visible.
5. Optionally use one model call to draft a compact explanation from retrieved evidence. Require factual fields to retain source references; leave uncertain cases for review.
6. Render a local HTML and Markdown brief, with a persistent delivery identifier. Add the agreed delivery channel after its destination and sending are authorized.
7. Record useful/rejected/corrected feedback and actual production effort.

Acceptance checks cover notice amendments, expired deadlines, duplicates, missing values, interrupted pagination, restart recovery and source failures. A repeated run must not repeat delivery or silently lose updates. The same saved inputs must support replay after an extraction change.

A model is optional for the first useful version. Choose its deployment only after measuring the task and available hardware. A small local model can later replace a more expensive step if it meets the same evaluation criteria. No model download is required to validate demand.

### 4. Make operation survive absence

Add a single scheduled job, health record, durable retries, backups and one pause switch. Show when collection last succeeded. Recovery from a missed run uses a saved cursor or time window; laptop sleep and shutdown must be represented as gaps until catch-up succeeds.

Before recurring service commitments, decide whether scheduled operation can rely on the laptop. Hosting is a later concrete deployment decision with a known cost. Exercise restore and restart with a saved dataset, and document how a trusted person can pause the service. Do not rely on Richard being available to repair it after surgery.

If a brief cannot be produced reliably, mark delivery delayed rather than recycling stale content as fresh. Payment, customer changes and contractual commitments remain outside any unconfigured autonomous loop.

Gate: the pilot's review/support burden fits Richard's chosen time allowance and the service can pause cleanly. Proposed initial target: no more than 15 minutes of average human review per business per delivery day, with zero unsupported critical deadline or eligibility claims in the reviewed pilot output. These are targets to measure, not current results.

### 5. Expand from observed demand

Ask the pilot buyer to renew at a clearly stated recurring price. Record cash collected, direct operating cost, human minutes, corrections, useful opportunities and renewal. At £100/month, ten customers would yield £1,000 monthly revenue before costs and tax; at 15 minutes each across 20 delivery days they would also require 50 hours of review monthly. Reduce measured service burden before extrapolating scale.

A setup fee can compensate for genuinely useful bespoke configuration, but quote it transparently and include the support obligation. If the customer values a bespoke workflow more than recurring briefs, test a fixed-scope installation and handover as an alternative offer.

Only introduce repository scouting when a recurring failure or cost has a baseline and acceptance test. Give each experiment a time budget. Promote a change only after it improves the existing service without degrading source accuracy. Never let the agent replace customer usefulness with repository activity as its success metric.

## Work deferred

Globe UI, multi-service infrastructure, a general autonomous browser, continuous repository assimilation, speculative trading and a universal opportunity score are outside the first pilot. Add a component when a demonstrated delivery requirement justifies its operational cost.

## Immediate next artifact

One real opportunity qualification brief for one reachable business. The business profile is the remaining input; official source documentation is already identified. Until that input exists, the initial niche remains a hypothesis.

## Sources checked

- [Contracts Finder](https://www.gov.uk/contracts-finder): existing government search and saved-search email updates establish a free baseline the proposed service must improve upon.
- [Find a Tender data documentation](https://www.find-tender.service.gov.uk/Developer/Documentation): public notices are available in the Open Contracting Data Standard JSON format.
- [Contracts Finder API documentation](https://www.contractsfinder.service.gov.uk/apidocumentation): published-notice search and record/release retrieval are documented.

These sources establish data availability and the free baseline. They do not establish customer demand, competitive advantage or the proposed price.
