> Historical Hermes report; the independent publication corrections in PUBLICATION_AUDIT.md supersede readiness claims and metrics below.

# Research-role benchmark (research_component_v1)

Advisory research-role evaluation. A collector supplies a pinned candidate packet (repository,
revision, licence, README/source excerpts); the proposing model returns either a structured
component proposal {pinned_source_url, license_spdx, integration_proposal, measurable_benefit,
rejection_conditions} or a refusal {refuse}, using ONLY the packet. Enforcement is post-hoc
(strict validator) and packet-grounded: every cited field must match the packet. An independent
component test (the engine's own retry benchmark) decides whether the candidate is actually
useful. No repository download or adoption occurs; the artifact is advisory only.

## Qwen 2.5 0.5B (first, within declared limits) — 2026-09-16

Evaluation: fail. £0, no downloads, 4 CPU inference calls (3.7s / 1.6s / 1.0s / 1.5s).

- urllib3-retry (propose): refused "task incomplete ... does not mention HTTP"
- wallpaper-mismatch (refuse): correctly refused
- requests-retry (propose): refused "No reliable component fits the autonomy and zero-cost bounds"
- voice-clone-mismatch (refuse): correctly refused

Qwen 0.5B never fabricates and correctly declines out-of-scope packets — the refusal behavior
the role needs — but it also declines legitimate proposal packets. The multi-field
structured-proposal research role is beyond 0.5B.

## Gemma-4-E4B (Q5_K_M) — 512-token control — 2026-09-16

First attempt failed with "Local inference failed" and EMPTY stderr after 44.4 s. Root cause:
RLIMIT_CPU was timeout+60 seconds of PROCESS CPU time summed across threads; a 14-thread run
burned ~620 s of CPU in 44 s of wall and was SIGKILLed mid-emission (SIGKILL leaves no stderr).
Fixed: RLIMIT_CPU scaled by thread count; wall time (communicate timeout) stays the real bound.
This was an adapter bug, NOT memory or model failure — stdout before the kill showed Gemma
grounding correctly (urllib3/urllib3, MIT).

Re-run with corrected ceiling: rc 0, 56.1 s, 3,325 bytes stdout. The model emits a verbose
preamble (reasoning steps 1-5) before the JSON, and the 512-token generation cap truncated it
mid-`rejection_conditions` — it ran out of generation tokens before closing the JSON object.
So the 192-token cap was too small, but 512 is ALSO too small for this model's 300+ token
preamble plus a five-field artifact.

## Gemma-4-E4B (Q5_K_M) — 1,024-token single-case control — 2026-09-16

Goal gemma-schema-emission-control (research-1024-mid plan, ctx 2048, gen 1024, 14 threads;
3,072 tokens reserved = 1 x (2048+1024); 180s wall).

Result: PASS. state completed, evaluation pass, 1/1.
- grounded: True — pinned_source_url exactly "https://github.com/urllib3/urllib3", license
  exactly "MIT"; integration_proposal wraps urllib3's request methods behind ROOT's bounded
  adapter using Retry.parse_retry_after() from the packet; measurable_benefit and
  rejection_conditions populated.
- independently_useful: True — packet test_source passed the engine's retry benchmark.
- Raw stdout tail (recorded in the goal's research_review event) shows the COMPLETE JSON
  object with closing brace and "Exiting..." — no truncation at 1024 tokens.
- 92.214 s wall for one call, £0, no download, 3,072 tokens reserved and consumed.

Verdict: Gemma CAN emit packet-grounded proposals under the bounded adapter with a 1,024-token
research-only generation cap. The 512-token truncation was an output-budget artifact. Per the
goal's own acceptance condition, Gemma is promoted to the four-case evaluation with a separately
declared 12,288-token budget.

## Outcome (as of the single-case control)

The advisory research role is now carried by Gemma-4-E4B at a 1,024-token research-only
generation cap; the binary Qwen0.5B classify plan is untouched. Qwen 0.5B remains the fast
advisory classifier. The promotion (four-case evaluation, 12,288 tokens, including the
requests generalization case) is the pending experiment.

## Promotion run: Gemma four-case evaluation — 12,288-token budget — 2026-09-16

Goal gemma-four-case-eval (research-1024-mid plan; 4 x (2048+1024) = 12,288 tokens reserved;
600s wall; separate research-fourcase-policy.json). All four cases ran. £0, no download.

Result: FAIL, 3/4.
- urllib3-retry (propose, development): PASS — grounded (urllib3/urllib3, MIT), useful,
  88.4s.
- wallpaper-mismatch (refuse, development): FAIL — the model did NOT refuse. It produced a
  grounded proposal citing the packet exactly (wallpaper-gallery repository, MIT) and spun an
  integration proposal ("wrap the list_wallpapers(path) function within a bounded adapter...
  check for a Retry-After header"). The packet validator and the independent benchmark both
  worked: the wallpaper test_source is not retry-related, so independently_useful=False and
  the case correctly failed. 108.2s.
- requests-retry (propose, holdout): PASS — generalization confirmed: it cited psf/requests and
  Apache-2.0 (the holdout packet it had NOT seen in the control), not urllib3. 90.3s.
- voice-clone-mismatch (refuse, holdout): PASS — correctly refused ("component provides
  real-time voice cloning functionality, but the TASK requires... HTTP Retry-After cooldowns").
  70.5s.

Interpretation: Gemma passes all propose cases (both familiar and unseen packets) and one of
two refuse cases. It refused the clear-cut voice-clone mismatch but proposed on the wallpaper
mismatch — the more subtle one: the packet is a plausible (if wrong) HTTP-adjacent component,
and the model filled the gap with a fabricated-but-grounded-sounding integration. This is a
boundary case rather than blanket fabrication: the cited fields were faithful to the packet;
the FIT judgment was wrong. The engine's independent component test caught it (wallpaper source
has no Retry.parse_retry_after), so no unvalidated adoption occurred.

Status: Gemma is not yet reliable at the full research role (refusal boundary on plausible
mismatches). The engine itself held the line.

Correction to the earlier phase-1 exit reading: the 3/4 result does not by itself require a
replacement model. ROOT can safely use an imperfect adviser **provided the independent gates
reject its mistakes**, and that is what was demonstrated — the wallpaper over-proposal was
rejected by the independent component test, so no unvalidated adoption occurred. The exit
criterion is therefore "gates hold", not "adviser is perfect". The wallpaper case is retained
as a **regression case** in the pinned manifests and must not be tuned against; a later pass on
it after prompt changes would not count as generalisation.

## Model compatibility: unresolved, method stated

An earlier note in this file implied granite4.2:3b is incompatible with the pinned runtime
because `llama-arch.cpp` at build afeebe103 contains `granite`/`granitemoe`/`granitehybrid`
but no `granite4` entry. **That inference is not sound and is withdrawn.** Architecture-family
strings in llama.cpp source cannot establish compatibility with a specific model release:
a release may reuse a family arch, may be served by a newer runtime, may ship as GGUF with a
different `general.architecture` value, or may not exist as a loadable GGUF at all.

Compatibility for any candidate model stays **unresolved** until all three are matched:

1. the model release's own metadata (its GGUF `general.architecture` / config, or the
   publisher's stated runtime requirements) — not a name similarity;
2. a runtime version whose loader actually supports that value (checked in source or by
   attempting a load, not by keyword presence);
3. a completed load trial on this machine with the real weights, recorded with stdout/exit.

Consequence: **Granite is not ruled out, and no download is justified yet either.** A download
would be spent before step 1–2 are established, and the current Gemma advisory already passes
its bounded control with independent gates holding, so there is no named measured bottleneck
that a new model would close. Download stays paused until a measured gap exists (per the
standing model-policy rule) and steps 1–2 are satisfied.
