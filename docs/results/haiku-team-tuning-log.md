# Haiku team: tuning log

**Spec:** `docs/superpowers/specs/2026-10-10-haiku-team-design.md` §3. **Scorecard:**
`.venv/bin/python scripts/haiku_practice.py`.

Practice deals only (`data/cal-r2`, `data/heldout-r2`, `data/practice-r2u`; 90 in all). The held-out sets
(`data/test-r2`, `data/pilot-r2u`) are never run before the freeze.

**Base rates** (`acqlab/bench/base_rates.json`, from the 90 practice answer keys): addback 0.23, debt_like 0.41,
concentration 0.36, nwc 0.19, capex 0.24.

**Rules:** one change per round, as a new registry entry in `acqlab/bench/haiku.py`; kept only if
`scripts/haiku_practice.py --keep <new> --over <best>` says True. Cap: 8 rounds or $15, round 0 included.

Each round records: the change and why (the commonest cause of the best candidate's misses), the scorecard before and
after, the cost, and kept or reverted.

## Smoke test (2026-10-11)

The user OK'd the practice phase (smoke test plus up to 8 rounds, $15 cap) on 2026-10-11.

- **Setup:** the three round-0 candidates on `data/cal-r2` dev-000 and dev-001.
- **Mechanics:** all 6 runs answered, none timed out, none went over budget. Every row shows
  `["claude-haiku-5-5"]` and CLI 2.1.291. The lean pipeline's 4 sessions and the team's 8–9 sessions all ran.
- **Cost surprise:** the CLI prints `unrecognized_model` for `claude-haiku-5-5` (cost basis "unknown") and prices it
  at about Opus rates: $4.12 for the 6 runs. From token counts at Haiku's list price the 6 runs cost $0.11.
  - Single Haiku: $0.009 per deal. The Haiku team: $0.023. The lean pipeline: $0.022.
  - Single Opus: $0.141 per deal, and the Opus team $0.535, on the same token-priced basis over cal-r2 and
    heldout-r2. That is within about 5% of the CLI's own Opus figures.
  - Haiku writes about 4× the output tokens Opus does on the same deal.
  - **The user's ruling:** cost is measured from token counts at list prices, for every system. The $15 cap is on
    that basis. The spec §5 is amended.
- **Prompts:** unchanged, so round 0 reuses these 6 rows.
- **Fix before round 0:** the scorecard crashed on the old cal-r2 s1b rows, which lack session counts (fixed,
  82407c8).

## Round 0

Running: the three candidates on all 90 practice deals.
