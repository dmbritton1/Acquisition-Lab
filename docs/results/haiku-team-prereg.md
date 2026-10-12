# The Haiku team: pre-registration of the final test

**Committed before any held-out deal was run.**

| | |
|---|---|
| Spec | `docs/superpowers/specs/2026-10-10-haiku-team-design.md` (§5 is amended: cost comes from token counts) |
| Plan | `docs/superpowers/plans/2026-10-10-haiku-team.md` |
| Tuning | `docs/results/haiku-team-tuning-log.md` |
| Runner | `acqlab/bench/haiku.py` (`FINAL = "haiku_lean_zero_w0"`) |
| Analysis | `scripts/haiku_team.py`, run once into `docs/results/haiku-team.json` |

## The frozen winner: `haiku_lean_zero_w0`

On each deal it runs these steps, all on `claude-haiku-5-5`:

1. **Reader.** Single Claude's prompt and tools, unchanged (`solver.solve`), at the deal's full page budget.
2. **Three pricers.** Each gets the teaser and the full text of every document the reader opened, has no reading
   budget, and notes every issue type. They use the reconciliation pilot's second-opinion prompt plus one rule (round 1):
   > A document that checks an issue and finds no problem settles it at zero: chance 1, low 0 and high 0 (the seller's
   > own claims in the CIM never settle anything).
3. **Pricing.** The valuation engine prices each pricer's notes, with every open issue's chance set to its base rate
   (`w` = 0; round 2). The base rates come from the 90 practice answer keys (`acqlab/bench/base_rates.json`):

   | Issue type | Base rate |
   |---|---|
   | add-backs | 0.23 |
   | debt-like items | 0.41 |
   | customer concentration | 0.36 |
   | net working capital | 0.19 |
   | capex | 0.24 |

4. **Call.** The majority of the three engine calls, at their median walk-away. A tie is a NO-GO, and with no calls
   the deal is unanswered.

**Practice score:** regret 0.0164, 63.3% correct, 6 false GOs and 27 false NO-GOs over 90 deals, at $0.023 per deal.
On the 60 practice deals that have Opus runs, it scores 0.0137, against single Opus's 0.0136 and the Opus team's
0.0090. **Its weak spot:** relief deals, where it gets 0 of 12 right.

## What runs

- **New systems,** each run once on all 200 held-out deals with `--final --split test`:
  - `haiku_solo` (single Claude on Haiku);
  - `haiku_team` (the frozen team on Haiku);
  - `haiku_lean_zero_w0` (the winner).
- **Deals:** `data/test-r2` (160) and `data/pilot-r2u` (40).
- **Baselines:** the existing `s1b` (single Opus) and `s4` (the Opus team) runs on the same deals.
- **CLI:** Claude Code 2.1.291 (`claude --version`, with `CLAUDE_BIN` unset). Every row records its CLI version.
- **Cost estimate** at list prices: about $0.058 per deal for the three systems together, so about $12 in all.

## Measures and verdicts (spec §5, fixed)

**Comparisons.** Each is a paired difference in mean regret with a 95% paired-bootstrap range, plus deals better,
worse and tied. Each is given on the 160, the 40 and all 200:
1. The winner against `s1b`. **This is the main comparison.**
2. The winner against `s4`.
3. The winner against `haiku_solo`.
4. `haiku_team` against `s4`.

**Verdict for the winner against `s1b`, per deal set:**

| Paired 95% range | Verdict |
|---|---|
| Wholly below zero | **better** |
| Wholly above zero | **worse** |
| Includes zero | **no clear difference: at most X worse**, where X is the range's upper end |

**Also reported:**
- Each verdict comes with the cost ratio: single Opus's cost per deal ÷ the winner's.
  - **Cost basis:** every row is priced from its token counts at list prices (`haiku.list_cost`). CLI 2.1.291 prices
    `claude-haiku-5-5` as an unknown model, at about Opus rates. The user chose this basis on 2026-10-11.
- If the two deal sets disagree, the write-up gives both.
- Per system and per deal type:
  - % correct, false GOs and false NO-GOs;
  - cost per deal, and every Opus ÷ Haiku cost ratio;
  - pages, decoy pages and sessions;
  - unanswered runs, timed-out runs and sessions, refused tool calls and deals over budget.

## When the analysis refuses

It refuses to run, and writes nothing, if:
- a system's deals differ from a set's test split;
- a run has no trace;
- a new row isn't on `claude-haiku-5-5`, or a baseline row isn't on `claude-opus-5-5` (a timed-out row may show no
  model);
- a Haiku row's fingerprint isn't the frozen one;
- the output file already exists.

## The freeze

`tests/bench/test_haiku.py::test_the_frozen_winner_and_its_prompts_are_unchanged` holds every fingerprint below.

| What | SHA-256 |
|---|---|
| `prompt_sha("haiku_solo")` | `61a5b3c4b56351dbde8482c919746f86c3ce7b252dd50635950677f35f2a61a1` |
| `prompt_sha("haiku_team")` | `8cc19f35fa1749bd54212d4593562b3ba995a593a5541a5e8d666e91d03d5372` |
| `prompt_sha("haiku_lean_zero_w0")` | `e46bcea53f89772f2616b3bd43f6d77c8519929e698fd558b0da4aef05763feb` |
| `base_rates.json` | `88a261b3d60411b17081c9b9c9a445ae6c8dcffa94e21d2d0f7d3728c8435616` |
| The reader's rendered prompts on the fixed test room | `768614d8b453c4ba1b9dfea119e2d1c036fbb06d7e4f47ebd01fd6b42058b9d6` |
| A pricer's rendered prompts on the fixed test room | `a0b6e914355b122f9c2ebb41744ae11a8c9728c4dc005b96443a41a9f4fa1ffb` |

- A candidate's `prompt_sha` covers its system prompts, run function, effort level and settings.
- `acqlab/agents` and `acqlab/routers` are still byte-identical to tag `s4-frozen-plan5`.

## Known features, stated now so they are not read as findings later

- **Tuned on the practice deals, so they flatter it.** The 4 tuning rounds, and the base rates, both came from the
  90 practice deals. Its practice regret therefore overstates how well it will do; the held-out test is what counts.
- **Relief deals are its known weak spot.**
  - It got 0 of 12 right in practice.
  - `pilot-r2u` has 16 relief deals, where single Opus got 9 of 16 right.
  - So the 40-deal verdict may well be worse than the 160-deal one.
- **The base rates are pooled** over r2 and r2u practice deals, as spec §3 sets.
- **Haiku's long-prompt price tier** (5× above 100K tokens per request) can't be seen in a run's summed tokens.
  No practice session came near it.

## Correction (2026-10-11, during the final test, before any analysis)

`haiku.PRICES` priced Opus 5.5 cache reads at $0.40 per million tokens. The API reference lists $0.20, so this is
fixed to $0.20. Priced this way, Opus rows now match the CLI's own Opus figures more closely: single Opus comes to
about $0.13 per deal rather than $0.14. Only the cost ratios change: they fall by about 5–10%. No run, prompt or
fingerprint changes.
