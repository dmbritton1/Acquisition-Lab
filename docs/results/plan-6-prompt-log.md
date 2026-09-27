# Plan 6 prompt log

## The valuer (2026-09-27)

- **What.** A new prompt for the engine ablations' one valuer turn (`acqlab/bench/valuer.py`, `SYSTEM` and `TASK`):
  the teaser, the deal team's findings (`Record.view()` without its first line, the engine's call) and, for LLM
  decides only, the engine's median walk-away and its 10–90% range. Tools: submit only; reading budget 0.
- **Why.** Spec §3: −engine tests whether an LLM can do the final valuation and call without the engine (H5); LLM
  decides tests whether the code decision matters.
- **Parity.** An S4 ablation's prompt; S1b's prompt is unchanged. It carries no diligence knowledge beyond the issue
  types' definitions, which S1b's tools already state (`server.ADJUSTMENTS`).
- **Checked on:** see Task 8's real rehearsal below.
