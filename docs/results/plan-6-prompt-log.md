# Plan 6 prompt log

## The valuer (2026-09-27)

- **What.** A new prompt for the engine ablations' one valuer turn (`acqlab/bench/valuer.py`, `SYSTEM` and `TASK`):
  the teaser, the deal team's findings (`Record.view()` without its first line, the engine's call) and, for LLM
  decides only, the engine's median walk-away and its 10–90% range. Tools: submit only; reading budget 0.
- **Why.** Spec §3: −engine tests whether an LLM can do the final valuation and call without the engine (H5); LLM
  decides tests whether the code decision matters.
- **Parity.** An S4 ablation's prompt; S1b's prompt is unchanged. It carries no diligence knowledge beyond the issue
  types' definitions, which S1b's tools already state (`server.ADJUSTMENTS`).
- **Checked on:** 2026-09-27, `cal-r2` dev-000 and dev-001, from their existing S4 runs (Claude Code 2.1.280,
  Opus 5.5, on a scratch copy of the data). All four turns submitted.

  | Deal | S4 | −engine | LLM decides |
  |---|---|---|---|
  | dev-000 | GO, $79.4M | GO, $79.5M | GO, $79.4M (the engine's) |
  | dev-001 | GO, $292.7M | NO-GO, $283.0M | GO, $292.7M (the engine's) |

  Cost: −engine $0.10 and $0.08, LLM decides $0.03 and $0.02 (notional), $0.22 in all; −engine costs about twice
  the plan's estimate of $0.05 per turn.
