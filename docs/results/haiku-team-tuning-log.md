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
- **Run:** 2026-10-11, $2.10. A network drop (ENOTFOUND) stopped it after 12 deals. It was resumed with a
  retry loop, and the finished deals were skipped.

| System (90 practice deals) | Regret | Correct | False GO | False NO-GO | $/deal |
|---|---|---|---|---|---|
| `haiku_lean` (parent) | 0.0238 | 55.6% | 6 | 34 | 0.024 |
| **`haiku_lean_zero`** | **0.0207** (0.02068) | 61.1% | 5 | 30 | 0.023 |
| `haiku_team` (round-0 best) | 0.0207 (0.02074) | 60.0% | 4 | 32 | 0.028 |

- **Kept.** `scripts/haiku_practice.py --keep haiku_lean_zero --over haiku_lean` returns True:
  - regret falls from 0.0238 to 0.0207;
  - relief false NO-GOs stay at 12 of 12;
  - confirmed false GOs stay at 0.
- **By set:**
  - cal-r2 improves from 0.0213 to 0.0158.
  - practice-r2u improves from 0.0233 to 0.0204.
  - heldout-r2 barely moves, from 0.0268 to 0.0258.
- **The new best by a hair:** `haiku_lean_zero` now edges past `haiku_team`.
- **Still the main problem:** relief deals, where it gets 0 of 12 right.
- **Running total:** $7.40 of $15 (smoke test, round 0 and round 1).

## Round 2: open issues at the base rate (`haiku_lean_zero_w0`)

- **Diagnosis of `haiku_lean_zero`'s 30 false NO-GOs:** the open notes were still too high.
  - 96 notes were left open where a document the pricers had showed zero.
  - 171 notes were open on issues no one read; they are zero in truth.
- **The relief deals:** the reader never opened the settling document on 7 of the 12.
- **A free replay of round 1's notes:**

  | Variant | Regret | Correct | False GO | False NO-GO |
  |---|---|---|---|---|
  | `w` = 0.5 (as run) | 0.0207 | 61.1% | 5 | 30 |
  | `w` = 0 | 0.0165 | 64.4% | 6 | 26 |
  | Open notes dropped | 0.0176 | | 22 | 2 |

  Dropping the open notes was rejected for its 22 false GOs.
- **The change:** `w` goes from 0.5 to 0, so every open chance is the base rate. Prompts and everything else are
  unchanged.
- **How it is judged:** run for real on the 90 deals, not judged from the replay, because the spec says rerun.
- **Run:** 2026-10-11, $2.09.

| System (90 practice deals) | Regret | Correct | False GO | False NO-GO |
|---|---|---|---|---|
| `haiku_lean_zero` (parent) | 0.0207 | 61.1% | 5 | 30 |
| **`haiku_lean_zero_w0`** | **0.0164** | 63.3% | 6 | 27 |

- **Kept.** The keep rule returns True. Relief false NO-GOs stay at 12 and confirmed false GOs stay at 0.
- **The replay predicted it:** 0.0165 against 0.0164 as run.
- **By set:**

  | Set | Haiku | Single Opus | Opus team |
  |---|---|---|---|
  | cal-r2 | 0.0130 | 0.0195 | 0.0076 |
  | heldout-r2 | 0.0144 | 0.0078 | 0.0105 |
  | **The 60 r2 deals** | **0.0137** | **0.0136** | |
  | practice-r2u | 0.0220 | (no runs) | (no runs) |

- **Running total:** $9.49 of $15.

## Round 3: the reader settles a disclosed exposure first (`haiku_lean_flag`)

- **Diagnosis of the 12 relief deals:** `haiku_lean_zero_w0` got all 12 wrong (false NO-GO).
  - **8 of 12:** the reader never opened the settling document (`board_minutes` or `audited`, often 2 pages), so
    the pricers priced the flagged item near the teaser's "up to $X".
  - **3 of 12:** the pricers settled the flagged item exactly at its true size, yet the other open issues, at base
    rates, still tipped the call.
  - **1 of 12:** concentration was settled at the true size by only one pricer.
- **The change:** one bullet added to the reader's system prompt (`haiku.FLAG_RULE`): "When the teaser discloses an
  exposure ("up to $X"), that figure is the seller's worst case, not the actual amount: make settling its actual
  size your first reading priority. Search for it and read the documents that mention it, short ones first."
  - It names no document types.
  - Everything else is as in `haiku_lean_zero_w0`.
- **Status:** running.
