# The Haiku team: final result

**Spec:** `docs/superpowers/specs/2026-10-10-haiku-team-design.md` §5. **Pre-registration:**
`docs/results/haiku-team-prereg.md`. **Tuning:** `docs/results/haiku-team-tuning-log.md`. **Numbers:**
`docs/results/haiku-team.json`, written once by `scripts/haiku_team.py` on 2026-10-12.

Regret is the value lost by a wrong buy/pass call, normalised by the asking price; lower is better. Costs are list
prices from each run's token counts. Every comparison is paired (the same deals for both systems) with a 95%
paired-bootstrap range.

## The answer in one paragraph

The best Haiku team we could build (`haiku_lean_zero_w0`: one Haiku reader, three Haiku second opinions, the engine
on base-rate-calibrated notes, majority vote) shows **no clear difference from single Opus on the 200 held-out deals:
at most 0.0092 worse, at about a fifth of the cost** ($0.024 against $0.131 per deal). On the 40 `r2u` deals on their
own it is **worse** than single Opus, so the two sets disagree; both readings are below. It is **worse than the Opus
team** (`s4`), at a twenty-second of the cost. And the team design **adds nothing over single Haiku** on new deals:
single Haiku scored the same regret (0.0155 against 0.0157) at a third of the team's cost, and a seventeenth of single
Opus's.

## The verdicts

| Deal set | Winner − single Opus (95% range) | Verdict | Single Opus's cost ÷ winner's |
|---|---|---|---|
| `test-r2` (160) | +0.0037 (−0.0034 to +0.0102) | no clear difference: at most 0.0102 worse | 5.6× |
| `pilot-r2u` (40) | +0.0045 (+0.0013 to +0.0083) | **worse** | 5.6× |
| all 200 | +0.0039 (−0.0014 to +0.0092) | no clear difference: at most 0.0092 worse | 5.6× |

The other three pre-registered comparisons, on all 200:

| Comparison | Difference (95% range) | Deals better / worse / tied | Reading |
|---|---|---|---|
| Winner − Opus team (`s4`) | +0.0060 (+0.0015 to +0.0103) | 10 / 32 / 158 | worse, at 1/22 of the cost |
| Winner − single Haiku | +0.0001 (−0.0056 to +0.0056) | 18 / 21 / 161 | no difference: the team adds nothing |
| Haiku team (`haiku_team`) − Opus team | +0.0045 (+0.0008 to +0.0085) | 8 / 22 / 170 | worse, at 1/19 of the cost |

## Every system on all 200 deals

| System | Regret | Correct | False GOs | False NO-GOs | $ per deal | Pages read |
|---|---|---|---|---|---|---|
| Opus team (`s4`) | 0.0097 | 75.0% | 10 | 40 | 0.524 | 22.5 |
| Single Opus (`s1b`) | 0.0118 | 76.5% | 29 | 18 | 0.131 | 18.9 |
| Haiku team (`haiku_team`) | 0.0142 | 68.0% | 10 | 54 | 0.028 | 22.2 |
| Single Haiku (`haiku_solo`) | 0.0155 | 65.5% | 8 | 61 | 0.0075 | 19.6 |
| **The winner** (`haiku_lean_zero_w0`) | 0.0157 | 64.0% | 23 | 49 | 0.024 | 19.6 |

No Haiku run timed out or failed to answer; single Opus missed one answer.

## What it means

- **Haiku is cautious.** Every Haiku system says "pass" too often: 49 to 61 false NO-GOs against single Opus's 18.
  They fall on `clean`, `decoy` and `unresolvable` deals, and on almost every `relief` deal (a disclosed exposure that
  turns out smaller than feared): 14 or 15 of 16, against single Opus's 7.
- **The winner's tuning traded caution for false GOs.** Pricing open issues at the base rate cut false NO-GOs (49
  against single Haiku's 61) but nearly tripled false GOs (23 against 8), almost all on `interaction` deals (20, as many
  as single Opus gets wrong there). On practice that trade looked like a big gain (regret 0.0164 against 0.0309); on new
  deals it came out even.
- **Practice flattered the team, as the limits warned.** Each tuning round was one run per deal on the same 90 deals,
  so the kept changes partly fit that sample. The held-out test is the guard, and it says the gain was not real.
- **For cost, single Haiku is the pick.** At $0.0075 per deal it is the cheapest system by far. It is somewhat worse
  than single Opus overall (regret 0.0155 against 0.0118), but it costs a seventeenth as much.

## Limits

- **Tuning noise:** one run per practice deal, so a kept change may have helped by chance (it did).
- **Mixed practice set:** 60 `r2` and 30 `r2u` deals, with base rates pooled over them.
- **Small `r2u` test set:** 40 deals, so its "worse" verdict rests on 8 lost deals and none won.
- **Prices are list prices from token counts**, not what a subscription or the CLI charges. Prompts over 100K tokens
  would cost Haiku more; no run here came near.
- **The deals are generated,** with template prose on the `r2u` sets.

**Spend:** practice $11.62, final test about $12 (three Haiku systems on 200 deals), at list prices.

**Next:** this result is the starting point for mixing Opus, Sonnet and Haiku
(`docs/superpowers/specs/2026-10-11-mixed-models-design.md`), where a cheap model handles the easy calls and a strong
one is asked only when needed.
