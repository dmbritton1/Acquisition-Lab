# Mixed models: the two leads, confirmed or not

**Pre-registration:** `docs/results/mix-confirm-prereg.md` (committed 52e0478, before any run). **Numbers:**
`docs/results/mix-confirm.json`, written once by `scripts/mix_confirm.py` on 2026-10-15. **Leads from:**
`docs/results/mix.md`.

Regret is the value lost by a wrong buy/pass call, normalised by the asking price; lower is better. Every comparison
is paired, with a 95% paired-bootstrap range. Costs are list prices from token counts.

## The answer in one paragraph

**Lead 1 (the Haiku reader and one Opus pricer) passes the written rule but did not hold up.** On the 200 held-out
deals it showed no clear difference from the Opus team (at most 0.0091 worse) at a quarter of its cost, which is the
pre-registered "matches the Opus team for less". But it was 0.0038 worse on average, **worse** than the Opus team on
the 160 `r2` deals alone, and a little behind single Opus (0.0135 against 0.0118) at the same cost. Its level match
with the Opus team on the 100 fresh deals was mostly luck. **Lead 2 (the Haiku team alone):** on all 300 deals it
shows no clear difference from single Opus (at most 0.0062 worse) at a fifth of its cost, and is worse than the Opus
team. Its lead over single Opus on the 100 fresh deals was also luck.

## Lead 1: `mix_h_opus1` on the 200 held-out deals

| Deal set | Regret: lead / single Opus / Opus team | Right: lead / single Opus / Opus team | Lead − Opus team (95% range) | Verdict vs Opus team | Verdict vs single Opus |
|---|---|---|---|---|---|
| `test-r2` (160) | 0.0148 / 0.0126 / 0.0088 | 71% / 77% / 78% | +0.0060 (+0.0001 to +0.0123) | **worse** | no clear difference: at most 0.0075 worse |
| `pilot-r2u` (40) | 0.0083 / 0.0084 / 0.0135 | 65% / 75% / 63% | −0.0051 (−0.0133 to +0.0016) | no clear difference: at most 0.0016 worse | no clear difference: at most 0.0026 worse |
| **all 200** | 0.0135 / 0.0118 / 0.0097 | 70% / 77% / 75% | +0.0038 (−0.0008 to +0.0091) | no clear difference: at most 0.0091 worse | no clear difference: at most 0.0061 worse |
| all 300 (with the 100 it came from) | 0.0122 / 0.0130 / 0.0096 | 72% / 76% / 76% | +0.0026 (−0.0013 to +0.0066) | no clear difference: at most 0.0066 worse | no clear difference: at most 0.0029 worse |

Cost per deal: lead $0.128, single Opus $0.131, Opus team $0.524 (all 200). Deals against the Opus team: 20 won, 31
lost, 149 tied. The lead makes both kinds of mistake: 25 false GOs (single Opus 29, Opus team 10) and 36 false
NO-GOs (single Opus 18, Opus team 40).

**Reading:** the pre-registered rule is met, so this is reported as a pass, but a weak one. The range allows the
lead to be up to 0.0091 worse than the Opus team, about as large as the Opus team's whole regret. On the larger set it
is worse. It costs the same as single Opus and does no better than it. There is no reason here to prefer it over
single Opus.

## Lead 2: the Haiku team on its own (no new runs)

| Deals | Regret: team / single Opus / Opus team | Team − single Opus (95% range) | Verdict vs single Opus | Verdict vs Opus team |
|---|---|---|---|---|
| 200 held-out (the test) | 0.0157 / 0.0118 / 0.0097 | +0.0039 (−0.0014 to +0.0092) | no clear difference: at most 0.0092 worse | **worse** |
| 100 fresh (where the lead came from) | 0.0133 / 0.0154 / 0.0092 | −0.0021 (−0.0092 to +0.0053) | no clear difference: at most 0.0053 worse | no clear difference: at most 0.0100 worse |
| all 300 | 0.0149 / 0.0130 / 0.0096 | +0.0019 (−0.0026 to +0.0062) | no clear difference: at most 0.0062 worse | **worse** |

Cost per deal: $0.024, a fifth of single Opus and a twenty-second of the Opus team.

**Reading:** the Haiku team is a fair cheap stand-in for single Opus (on 300 deals, at most 0.0062 worse at a fifth
of the cost) but not for the Opus team. It is not better than single Opus.

## What changes in the mixed-model results

Nothing in `docs/results/mix.md`'s pre-registered verdicts changes. Its two "observations outside the pre-registered
comparisons" are now tested: both looked better on the 100 fresh deals than they are. The best value systems in the
project remain the Haiku team with single Opus on risky or close calls (mix 1: matches single Opus at 30% less) and,
for the lowest cost, the Haiku team or single Haiku alone.

## Limits

- **The held-out deals are not new to the project** (Plan 6 and the Haiku track scored on them), though no choice
  about `mix_h_opus1` was made on them.
- **The baselines ran earlier** (2026-09-28 and 2026-10-08, older Claude Code); the lead ran on 2026-10-14/15 on
  2.1.291.
- **One run per deal.** The run paused for a session limit and a short network outage; finished deals were kept, and
  every deal has one complete run.

**Spend:** $25.53 at list prices (200 runs of `mix_h_opus1`).
