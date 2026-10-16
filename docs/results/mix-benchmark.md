# Mixed models: the full benchmark on 300 deals

**Pre-registration:** `docs/results/mix-benchmark-prereg.md` (committed 6803376, before any run). **Numbers:**
`docs/results/mix-benchmark.json`, written once by `scripts/mix_benchmark.py` on 2026-10-15. **Earlier results:**
`docs/results/mix.md` (the four mixes' pre-registered test, 100 fresh deals) and `docs/results/mix-confirm.md` (the
two leads, 200 held-out deals).

Every system and frozen mix on the same 300 deals: the 200 held-out deals (`test-r2`, `pilot-r2u`) and the 100 fresh
deals (`mix-test-r2`, `mix-test-r2u`). Regret is the value lost by a wrong buy/pass call, normalised by the asking
price; lower is better. Costs are list prices from token counts. Minutes are Claude's reported session time per deal,
summed over a run's sessions. Verdicts are paired 95% bootstrap ranges: "better", "worse", or "no clear difference:
at most X worse".

## The answer in one paragraph

On 300 deals **the Opus team is the most accurate system** and nothing cheaper is clearly as good: every system is
either "worse" than it or allowed by its range to be up to 0.0066–0.0073 worse. **Three systems come closest to single
Opus:** the Haiku team with single Opus on risky or close calls (mix 1: at most 0.0021 worse, **31% cheaper**), the
Haiku reader + one Opus pricer (at most 0.0029 worse, about the same cost), and that pair with low-effort Opus on
close calls (mix 2: at most 0.0036 worse, 11% dearer). **The cheap systems**
(single Haiku, the Haiku team, mix 4, single Sonnet, low-effort Opus) all show no clear difference from single Opus
but with wider ranges (at most 0.005–0.010 worse), and all are worse than the Opus team. **Single Opus is the fast
choice** (0.6 minutes a deal); the team systems take 1.2–2.5 minutes.

## All 300 deals

| System | Regret | Right | False GO | False NO-GO | $ per deal | Minutes (median / slowest 10%) | vs single Opus | vs Opus team |
|---|---|---|---|---|---|---|---|---|
| Opus team (`s4`) | 0.0096 | 76% | 15 | 58 | 0.528 | 2.5 / 2.9 | | |
| Haiku reader + one Opus pricer (`mix_h_opus1`) | 0.0122 | 72% | 31 | 53 | 0.128 | 1.2 / 1.4 | no clear difference: at most 0.0029 worse | no clear difference: at most 0.0066 worse |
| **Mix 1:** Haiku team → single Opus on a flag or within 5% | 0.0126 | 74% | 41 | 36 | 0.091 | 2.5 / 3.3 | no clear difference: at most 0.0021 worse | no clear difference: at most 0.0072 worse |
| **Mix 2:** Haiku reader + Opus pricer → low-effort Opus within 2% | 0.0127 | 76% | 37 | 36 | 0.147 | 1.2 / 1.6 | no clear difference: at most 0.0036 worse | no clear difference: at most 0.0073 worse |
| Single Opus (`s1b`) | 0.0130 | 76% | 44 | 29 | 0.132 | 0.6 / 0.8 | | |
| Single Opus, low effort | 0.0148 | 72% | 58 | 25 | 0.098 | 0.4 / 0.6 | no clear difference: at most 0.0049 worse | **worse** |
| Haiku team | 0.0149 | 66% | 31 | 70 | 0.024 | 2.2 / 2.8 | no clear difference: at most 0.0062 worse | **worse** |
| **Mix 4:** single Haiku → Sonnet within 2% | 0.0149 | 68% | 12 | 85 | 0.016 | 0.7 / 1.0 | no clear difference: at most 0.0062 worse | **worse** |
| Single Sonnet | 0.0160 | 71% | 45 | 42 | 0.051 | 0.3 / 0.3 | no clear difference: at most 0.0071 worse | **worse** |
| **Mix 3:** single Haiku | 0.0177 | 65% | 10 | 94 | 0.0075 | 0.7 / 0.9 | no clear difference: at most 0.0098 worse | **worse** |

Mix 1 hands 49% of deals to single Opus; mix 2 hands 19% to low-effort Opus; mix 4 hands 16% to Sonnet.

## The two halves

| System | Regret, 200 held-out | Regret, 100 fresh |
|---|---|---|
| Opus team | 0.0097 | 0.0092 |
| Single Opus | 0.0118 | 0.0154 |
| Mix 1 | 0.0121 | 0.0135 |
| Single Opus, low effort | 0.0131 | 0.0183 |
| Mix 2 | 0.0133 | 0.0117 |
| Haiku reader + one Opus pricer | 0.0135 | 0.0096 |
| Mix 4 | 0.0142 | 0.0163 |
| Single Haiku | 0.0155 | 0.0222 |
| Haiku team | 0.0157 | 0.0133 |
| Single Sonnet | 0.0158 | 0.0163 |

The halves disagree on the order. Single Opus did unusually badly on the fresh 100, which flattered every system
compared with it there; the Haiku reader + one Opus pricer did unusually well there. On the 200 held-out deals only
mix 1 comes within 0.001 of single Opus. Mix 1 and the Opus team are the only systems near the top in both halves.

## What it means

- **For accuracy, the Opus team.** It has the lowest regret on 300 deals and on each half, at four times single
  Opus's cost and time.
- **For value, mix 1.** About single Opus's quality (at most 0.0021 worse on 300 deals, the tightest match in the
  table) at 69% of its cost; but it is the slowest system, since it runs the Haiku team first.
- **For speed, single Opus.** Under a minute a deal, and the baseline the cheaper systems are measured against.
- **For the lowest cost, the Haiku team or mix 4** (2–4 cents a deal). Both lean NO-GO: they pass on many deals they
  should take (70 and 85 false NO-GOs against single Opus's 29).
- **Low-effort Opus and Sonnet are not bargains:** both say GO too readily (58 and 45 false GOs) and cost more
  than the Haiku team and are no better on regret.

## Limits

- **The pre-registered verdicts stand where they were made** (`mix.md` for the four mixes, `mix-confirm.md` for the
  leads). This table includes the deals each pick and lead came from, so it is a description, not a new test.
- **300 deals still give ranges of about ±0.004–0.007,** so most comparisons read "no clear difference".
- **Run dates differ** (2026-09-28 to 2026-10-15) and Claude Code versions with them; times depend on server load
  and exclude waits for usage limits.
- **One run per deal per system.**

**Spend:** $29.98 at list prices (`mix_sonnet_solo` and `mix_opus_low` on the 200 held-out deals).
