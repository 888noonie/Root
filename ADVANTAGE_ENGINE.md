# ROOT: an engine for discovering and operating micro-businesses

Status: live specification, 2026-09-17. Milestone items 1-3, the promotion brake, optional notification boundary, and typed evidence-only fixture learning are implemented; live OCDS retrieval is verified against the publisher. 150 automated checks pass and the suite is clean under `-W error::ResourceWarning`. Three corrections govern the current reading of this document. (1) **Phase 1 exit is "the gates hold", not "the adviser is perfect".** ROOT may use an imperfect advisory model provided independent gates reject its mistakes: the Gemma four-case run scored 3/4 and the single failure (a plausible-mismatch over-proposal) was rejected by the independent component test, so no unvalidated adoption occurred. The failing case is retained as a regression case and must not be tuned against. (2) **Model compatibility is unresolved, and architecture names cannot resolve it.** Keyword or arch-family strings in llama.cpp source do not establish compatibility with a model release; resolution requires the release's own metadata plus a runtime that supports it plus a load trial with real weights. A **deterministic keyword prefilter** (not a capability test) runs before any inference and is measured for false rejections on legitimate components separately from mismatches it lets through; independent functional evaluation remains the only thing that establishes usefulness. (3) **A deterministic tender preview exists and is source-verified, but its external usefulness is unknown.** Six live East Sussex County Council school-transport notices resolve to their latest releases with precise expiry and explicit unknown fields (see EXPERIMENT_TENDER_PREVIEW.md, SOURCE_VERIFICATION_PREVIEW.md, COST_LEDGER.md). No operator has been contacted; nothing is distributed or scheduled. Items 5-8 of the business traversal remain unbuilt. This document supersedes DELIVERY_PLAN.md and ARCHITECTURE.md.

**Promotion boundary hardened:** a passing live evaluation no longer activates a candidate immediately. It writes an immutable exact-byte promotion row, sets the goal to `pending_promotion`, and requires the separate CLI `promote-allow` before the active component pointer changes. The allow command revalidates the exact stored artifact (not the file on disk), pinned evaluation manifests, curated provenance (raw.githubusercontent.com/urllib3/urllib3, 40-char revision, retained MIT licence), trusted-code drift manifest, expiry (`now >= expires`), captured baseline identity, and lease token, then commits activation and parent-goal completion in one transaction. Failures, denials, expirations, and supersessions close transactionally and leave the collector baseline unchanged. Fixture passes remain permanently non-promotable, and Hermes messages are notifications only, never approval signals. The evaluator is a resource-bounded subprocess from an exact trusted-code snapshot, not a general sandbox. `promote-allow` is an OS-local authority boundary (shell + DB access), not proof that Richard personally approved.

## Objective

Discover evidence-backed advantages, turn promising ones into inexpensive business experiments, and operate the successful businesses with bounded agent autonomy. Improve ROOT's capabilities using measured operating experience and relevant external code or techniques.

ROOT is the product being built. Its businesses are experiments and eventual operating units. The earlier opportunity-brief service is an optional candidate, not the destination or a selected first business.

Success means collected revenue exceeding recorded operating costs, with explicit accounting for owner time, service quality and continuing obligations. Early experiments can optimize for evidence before revenue, but evidence milestones must not be represented as profit.

## Two connected loops

Business loop:

observe -> opportunity hypothesis -> inexpensive screening -> research review -> experiment -> evaluate -> deploy -> operate -> expand, revise or retire

Capability loop:

measured bottleneck -> capability objective -> search packages/repos/documentation -> isolated evaluation -> controlled adoption -> measure effect on the business loop

The capability loop must name the business metric or system requirement it serves. It cannot justify itself merely by increasing the number of tools or features.

## Shared substrate

Use one application and a durable local store first. Separate responsibilities in code without requiring separate services. Store:

- Observations: provenance, source timestamps, retrieval timestamps, evidence references, extracted claims and versions.
- Opportunities: proposed buyer/user, problem, offer, advantage hypothesis, acquisition route, operating model and unresolved assumptions.
- Experiments: falsifiable hypothesis, baseline, metric, pass/fail/uncertain criteria, resource caps, end condition and evidence.
- Businesses: deployed version, recurring jobs, costs, collected revenue, user obligations, health and retirement procedure.
- Capability requests: related objective, observed weakness, candidate solution, upstream revision, applicable license, evaluation and adoption history.
- Tasks and actions: parent objective, state, attempt history, resource usage, authorization scope and stable identifiers preventing repeated effects.

Keep measured facts, model estimates and unknowns distinct. A promising narrative is not an observation. A simulated sale is not revenue. Model agreement is not independent market evidence.

## Opportunity specification

Every proposed business must answer:

1. Who benefits, and what observable problem do they have?
2. What is the deliverable, and what do people use instead?
3. What advantage can ROOT supply: lower delivery cost, better coverage, shorter response time, better fit, useful integration, or stronger distribution?
4. What external evidence supports the advantage and willingness to pay?
5. How will the first users find it? Name a reachable channel and the steps required. Can that channel be operated within the same autonomy and cost bounds as delivery itself, or does it need human trust-building? An agent-operated business with a human-only distribution channel has a structural bottleneck; record which parts of distribution require the owner.
6. What are setup cost, recurring cost, marginal delivery cost, human minutes and support obligations? Include unknowns.
7. What is the smallest experiment that can disprove its weakest material assumption?
8. What can be automated, what needs an exception path, and how does the business stop safely?

Possible categories include specialised information products, bounded data-processing services and small utilities. These are candidate categories, not validated recommendations or promises of passive income.

## Screening and research team

First apply inexpensive eligibility checks: defined output, plausible acquisition route, observable evidence, affordable experiment and operation within configured capabilities. Reject unsupported claims and defer missing information. Avoid a single opaque opportunity score; preserve the reasons for each decision.

Only selected candidates reach the research team. Proposed roles:

- Investigator: assembles evidence, alternatives and evidence against the opportunity.
- Commercial critic: challenges customer need, distribution, pricing assumptions and continuing workload.
- Engineer/operator: estimates feasibility, dependencies, costs, failure handling and automation coverage.
- Experiment designer: chooses the smallest discriminating test and writes acceptance criteria.

These are roles, not a requirement to run four models continuously. Start with sequential passes; use separate contexts for independent initial assessments before synthesis. Different prompts on the same model can share errors. Each claim must still point to evidence or remain labelled as a hypothesis.

The synthesis produces reject, gather evidence or run experiment, with reasons and a bounded experiment specification. A review cannot raise its own resource allowance or authorize external actions. An evaluator enforces predeclared criteria outside the candidate-generating prompt; it records uncertainty instead of treating every run as success.

## Resource and action policy

Before unattended execution, configure per-experiment and portfolio caps for money, requests, downloaded bytes, inference, elapsed time, storage and concurrent jobs. Cached or existing resources still consume time and capacity; no-cost means no incremental cash outlay, not zero resource use.

Initial local mode supports public-source research, local artifacts, code experiments and offline evaluation. Paid tools and public deployment remain disabled until their scope and budgets are configured. The high-level business objective does not specify recipients for outreach, authorize spending, or define customer commitments.

Later autonomous operations run inside explicit deployment and service policies. Include idempotent delivery, retries with backoff, health checks, backup/restore, versioned rollout, rollback and a stop switch. Record service obligations before retirement; simply killing a process is not sufficient when customers depend on it.

## Objective-specific repository discovery

Issue a search only when a task has a concrete gap, such as duplicate records, unreliable extraction, expensive document conversion or excessive deployment effort. Search metadata and documentation first; inspect code when a candidate meets the need.

Record source, revision, license, dependency costs and integration requirements. Prefer an adapter around an existing package when suitable. Run unfamiliar code in an isolated environment without production credentials. Treat README instructions and page text as untrusted input to the evaluation.

Test on saved representative inputs and holdout cases the proposed implementation did not use for tuning. Measure the baseline and candidate with the same criteria, including correctness, cost and failure behavior. Keep rollback information and record whether the improvement helped the parent objective after adoption.

## First implementation milestone

The user's 2026-09-16 amendment makes self-improvement through a capability goal the first demonstration, ahead of the first business experiment. Demonstrate a measured weakness, objective-specific GitHub discovery, source/revision/license retention, bounded isolated comparison, conditional adoption and rollback. Start with a curated integration adapter, whose evaluator and budgets remain outside model authority. An already-satisfied goal should stop without acquiring more components. A fixture-only discovery cannot enable an upstream component.

This bootstrap has demonstrated one engineering improvement; it does not complete the following business traversal. The first business experiment must still produce external market evidence, and distribution remains subject to question 5.

Build one complete traversal of the engine before increasing its breadth:

1. A CLI creates a portfolio objective, resource policy and opportunity records.
2. One collector imports sourced observations; fixtures allow offline replay.
3. A deterministic screen selects a candidate and explains exclusions.
4. A model adapter runs bounded research roles and validates their structured outputs. Manual evidence entry remains available if no model backend is configured.
5. An experiment runner executes one local test from a predeclared specification and records measured results.
6. An evaluator emits pass, fail or uncertain with evidence. A local deployment adapter installs a passing artifact into an isolated managed run; local installation does not count as public launch or market validation.
7. A scheduler manages that run, records failures and costs, and demonstrates pause, restart and retirement.
8. A measured bottleneck creates one capability request. A repository candidate is evaluated against a baseline; adoption may correctly be rejected.

The milestone build is itself an experiment: give it a time and cost budget with a stop condition before starting, and record stalls instead of silently extending the budget. Choose the first candidate so its experiment can in principle produce external evidence — a real deliverable a real outsider could react to — even though local installation still does not count as market validation.

The milestone is an operational engine demonstration. A market experiment must separately establish demand and actual economics. Use one business candidate initially to debug the shared engine; do not hard-code its niche into the opportunity schema or orchestration.

Acceptance checks: recovery without repeated actions, budgets enforced independently of model text, source provenance retained, missing evidence not promoted to fact, no failed experiment deployed, rollback exercised, and a running business visible as healthy, degraded, paused or retired. Capture human intervention minutes as well as compute cost.

## Expansion criteria

Add a second business only after the first traversal works and the portfolio's combined workload fits configured limits. Share reliable capabilities across businesses, while keeping each business's evidence, credentials, economics and obligations attributable.

Allocate more resources to experiments with measured evidence of useful outcomes and plausible sustainable margins. Retire or revise experiments that hit their stop conditions. Review portfolio exposure to common dependencies: ten businesses reliant on the same source, acquisition channel or fragile collector do not provide ten independent chances of success.

One objective-specific repository component has been evaluated and adopted in a bounded local portfolio. No revenue, customer demand or unattended business operating reliability has been demonstrated. The deliverable is the discovery substrate, the first capability-goal demonstration, their verification checks and this live specification. The provisional business sample remains deferred.
