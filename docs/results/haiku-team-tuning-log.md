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

## Round 0 (2026-10-11): the three starting candidates

All 270 runs answered, with no timeouts, no deals over budget, and every row on `claude-haiku-5-5`. Cost: $5.30 at list
prices (smoke rows included): single Haiku $0.67, the team $2.49, lean $2.14.

| System (90 practice deals) | Regret | Correct | False GO | False NO-GO | $/deal |
|---|---|---|---|---|---|
| `haiku_solo` | 0.0309 | 57.8% | 2 | 36 | 0.007 |
| **`haiku_team`** (best) | **0.0207** | 60.0% | 4 | 32 | 0.028 |
| `haiku_lean` | 0.0238 | 55.6% | 6 | 34 | 0.024 |
| For reference on the 60 r2 deals: single Opus `s1b` | 0.0136 | 81.7% | 7 | 4 | 0.141 |
| ... the Opus team `s4` | 0.0090 | 81.7% | 1 | 10 | 0.535 |

- **All three Haiku systems pass far too often.** False NO-GOs are 32–36 of 90, against Opus's 4–10 of 60. Relief
  deals are 0–2 right of 12; confirmed deals are 6 of 6 right for all three.
- **The cause (diagnosed on `haiku_lean`'s pricers):**
  - In 385 notes, the pricer had the document showing the issue was zero, yet left it open, at an average chance of 0.27.
    It settled such an issue at zero only 131 times.
  - Open issues on documents nobody read average a chance of 0.45, where 32% are real.
  - The engine priced these phantom risks into NO-GOs.
- **The team's Deal Lead** opens with chances of 0.36–0.53 by type, against real rates of 0.19–0.41.
- **A free replay of `haiku_lean`'s round-0 notes** at other pull strengths (`w`) gave this:

  | `w` | Regret |
  |---|---|
  | 1.0 (no pull) | 0.0244 |
  | 0.5 (as run) | 0.0238 |
  | 0.25 | 0.0215 |
  | 0 (pure base rates) | 0.0210 |

  This is in-sample, and smaller than the cause above.
- **Ruling: tune the lean line, not the team.** The team's prompts are the frozen S4 files, and its pricing is inside
  the frozen engine code. The lean pipeline's pricing is ours to change, and it trails the team by only 0.003.
  - A lean change is kept only if it beats `haiku_lean`, its parent, under the keep rule.
  - The winner at the freeze is the lowest practice regret of all candidates, including `haiku_team`.

## Round 1: the zero rule (`haiku_lean_zero`)

- **The change:** one sentence added to the pricers' prompt (`haiku.ZERO_RULE`): "A document that checks an issue
  and finds no problem settles it at zero: chance 1, low 0 and high 0 (the seller's own claims in the CIM never
  settle anything)."
- **Unchanged:** everything else, including `w` = 0.5, the 3 pricers and the reader.
- **Status:** running on the 90 practice deals.
