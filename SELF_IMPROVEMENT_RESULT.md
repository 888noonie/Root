<!-- NOTE: the test counts in this file are HISTORICAL, recorded when this evidence was written. The current suite count is in README.md / METRICS.md. -->
# ROOT's first GitHub capability goal

Goal: improve affordable, reliable public-source collection by respecting longer Retry-After instructions. Executed 2026-09-16 Europe/London, within the declared build budget.

ROOT searched GitHub, broadened its empty primary search once using the fallback in its immutable goal specification, discovered five candidate repositories, and selected the supported urllib3 parser adapter. It fetched metadata, a commit, README, license and source before evaluation. Seven read-only requests transferred 96,676 bytes, within the 12-attempt/1-MiB goal cap. No downloaded model weights, package installations or spending occurred.

Upstream: [urllib3 Retry parser at pinned revision](https://github.com/urllib3/urllib3/blob/b1d30ab61fe0db8f11092805e8c5ac43e091064a/src/urllib3/util/retry.py). Revision: `b1d30ab61fe0db8f11092805e8c5ac43e091064a`. The original MIT license and full fetched source are retained in the portfolio's `repo_evidence` and `components` tables.

| Predeclared cases | Baseline fixed delay | Restricted candidate |
| --- | --- | --- |
| Development | 4/6 | 6/6 |
| Holdout | 3/6 | 6/6 |
| Total | 7/12 | 12/12 |

ROOT previously conditionally enabled the parser in the historical live profile `.root/self-improve-live2.sqlite3`. That demonstrated immediate adoption on pass. **The current promotion core replaces that behavior:** a live pass now leaves the candidate pending; `promote-allow` must be invoked separately to activate the exact stored artifact. The adapter preserves the five-minute minimum and overrides urllib3's upper cap to avoid shortening a server-requested delay. The full remote module is never executed. Only the curated function subset is accepted.

Saved-goal replay left events and resource usage unchanged. Rollback on an isolated SQLite copy restored 300 seconds; the original portfolio retained 900-second behavior. See `.root/rollback-verification.json` or rerun `python3 scripts/verify_saved_goal.py --db .root/self-improve-live2.sqlite3` without network access. 53 automated checks pass, including component rejection, source provenance, independent budgets, query fallback and rollback after deadlines.

CPU classification has now passed on Qwen2.5 0.5B. The saved diagnostic record shows grammar-sampler initialization failures before successful generation; removing `--json-schema` from this build's `--simple-io` invocation allowed valid output. This corrects the earlier inference that model size explained the failures. Acceptance still requires a parsed object with exactly `{fit: bool, reason: str≤400}`; malformed responses remain uncertain. These observations concern the tested command and runtime, rather than every llama.cpp grammar configuration.

Evidence audited on 2026-09-16:

- `.root/model-evidence/qwen_diag.sqlite3` retains the sampler-failure diagnostics.
- `.root/model-evidence/qwen_diag2.sqlite3` records Qwen's model path, CPU execution (8 threads, context 1,024, generation cap 128), and successful positive/negative classifications in 3.019 s / 0.994 s.
- `.root/model-evidence/gemma_full.sqlite3` also records **Qwen's** model path and smaller execution settings for both reviews (1.377 s / 1.021 s). Its filename is insufficient evidence of Gemma execution. The earlier statement that those goal reviews validated Gemma was incorrect.
- Hermes separately reported a direct Gemma load/classification in 8.3 s, an initial address-space allocation failure, and a successful retry with additional headroom. That reported trial is distinct from the saved goal-level evidence; its measurements have not been independently verified here. Gemma's file is 5,762,908,128 bytes: 5.76 GB / approximately 5.37 GiB, with size label 7.5B.

The original SQLite records are preserved without retrospective edits to reservations or allowances. `.root/model-evidence/attribution-audit.json` contains the extracted advisory records.

The adapter now charges its actual configured ceiling: 1,152 tokens per small-plan call, or 2,240 per mid-plan call (context 2,048 + generation cap 192). A goal atomically reserves both controls before discovery or inference: 2,304 or 4,480 tokens. Both goal and portfolio limits apply; failed calls retain the reservation. The existing 2,304-token example remains unchanged and cannot run the mid plan. New goals can bind an existing model with `goal-create --model PATH`; the path, file size and resource plan are retained, and changed resource requirements stop execution. Caller-supplied plans cannot override the adapter's ceilings.

53 automated checks pass, including larger-plan accounting, rejection before discovery when the budget is insufficient, model selection, portfolio exhaustion, failed-review reservations, and changed model resource requirements. This update ran tests and audited saved results; it did not launch another model trial. Qwen's two-control classification is validated; Gemma goal-level classification and broader research capability remain unproven.

Scope: one curated capability adapter and saved engineering inputs. The candidate search and integration recipe were specified by the implementation, not invented by an autonomous model. This demonstrates bounded execution of an improvement goal and a real upstream component adoption, rather than unrestricted recursive self-modification. It establishes no customer demand, revenue or continuing business autonomy.
