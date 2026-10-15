# Mixing Opus, Sonnet and Haiku: final result

**Spec:** `docs/superpowers/specs/2026-10-11-mixed-models-design.md`. **Pre-registration:** `docs/results/mix-prereg.md`.
**Practice:** `docs/results/mix-tuning-log.md`. **Numbers:** `docs/results/mix.json`, written once by
`scripts/mix_final.py` on 2026-10-14.

Regret is the value lost by a wrong buy/pass call, normalised by the asking price; lower is better. Costs are list
prices from each step's token counts. Every comparison is paired (the same 100 fresh deals for every system) with a 95%
paired-bootstrap range.

## The answer in one paragraph

On 100 deals no system had seen, two mixes did what they were picked for, within what 100 deals can show. **The Haiku
team with single Opus called in on risky or close calls** showed no clear difference from single Opus (at most 0.0016
worse, the tightest result in the test) at **30% less cost**. **A Haiku reader with one Opus second opinion, handing
close calls to low-effort Opus,** showed no clear difference from the Opus team (at most 0.0097 worse) at **28% of its
cost**, and was better than the Opus team on the 20 `r2u` deals. Single Haiku was worse than the Opus team. Every mix
did worse on fresh deals than on practice, as expected.

## The four frozen mixes against the two Opus baselines (all 100 deals)

| Mix | Regret | Right | $ per deal | vs single Opus | vs Opus team |
|---|---|---|---|---|---|
| 1. Haiku team → single Opus on a flagged risk or within 5% | 0.0135 | 73% | 0.094 | no clear difference: at most 0.0016 worse | no clear difference: at most 0.0110 worse |
| 2. Haiku reader + Opus pricer → low-effort Opus within 2% | 0.0117 | 82% | 0.148 | no clear difference: at most 0.0045 worse | no clear difference: at most 0.0097 worse |
| 3. Single Haiku | 0.0222 | 65% | 0.0075 | no clear difference: at most 0.0184 worse | **worse** |
| 4. Single Haiku → Sonnet within 2% | 0.0163 | 70% | 0.016 | no clear difference: at most 0.0110 worse | no clear difference: at most 0.0171 worse |
| Single Opus (`s1b`) | 0.0154 | 74% | 0.134 | | |
| Opus team (`s4`) | 0.0092 | 77% | 0.537 | | |

**The named readings (all 100):**
- **"Beats single Opus for less"** (cheaper than `s1b` and not "worse"): mixes 1, 3 and 4. Mix 2 costs a little more
  than single Opus ($0.148 against $0.134), so it does not qualify.
- **"Matches the Opus team for less"** (cheaper than `s4` and not "worse"): mixes 1, 2 and 4.

"Not worse" is weak evidence for mixes 3 and 4: their ranges allow them to be up to 0.011–0.018 worse than single
Opus. Mix 1's range against single Opus is narrow, and mix 2's against the Opus team is moderate.

## By deal set

| Mix | `mix-test-r2` (80) vs single Opus / Opus team | `mix-test-r2u` (20) vs single Opus / Opus team |
|---|---|---|
| 1 | no clear difference (≤0.0012) / no clear difference (≤0.0147) | no clear difference (≤0.0060) / no clear difference (≤0.0000) |
| 2 | no clear difference (≤0.0060) / no clear difference (≤0.0137) | no clear difference (≤0.0000) / **better** (7 deals won, 0 lost) |
| 3 | no clear difference (≤0.0201) / **worse** | **worse** / no clear difference (≤0.0151) |
| 4 | no clear difference (≤0.0117) / no clear difference (≤0.0214) | no clear difference (≤0.0121) / no clear difference (≤0.0000) |

The two sets agree on mixes 1 and 4. They differ for mix 2 (better than the Opus team only on `r2u`) and mix 3 (worse
than a different baseline in each set).

## Practice against fresh deals

| System | Practice regret | Fresh regret |
|---|---|---|
| Mix 1 | 0.0096 | 0.0135 |
| Mix 2 | 0.0077 | 0.0117 |
| Mix 4 | 0.0237 | 0.0163 |
| Single Haiku | 0.0309 | 0.0222 |
| Single Opus | 0.0132 | 0.0154 |
| Opus team | 0.0112 | 0.0092 |

The two cascades picked as the best of 176 lost about 0.004 each, as the pre-registration warned. Single Opus also did
a little worse on these deals than on practice, which helped the mixes' comparisons against it.

## Observations outside the pre-registered comparisons

These come from the mixes' parts, run on the same deals; they were not frozen as mixes, so treat them as leads.
Both were tested afterwards (`docs/results/mix-confirm.md`): each looked better here than it is.
- **The Haiku reader + one Opus pricer, on its own,** scored 0.0096 at $0.128: level with the Opus team (0.0092) at a
  quarter of its cost. Handing its close calls to low-effort Opus (mix 2) made it worse on the 80 `r2` deals, because
  low-effort Opus makes many false GOs (20 of 100).
- **The Haiku team on its own** scored 0.0133 at $0.024, as well as mix 1 at a quarter of mix 1's cost, and lower than
  single Opus's regret on these deals (not a tested comparison). On the Haiku track's 200 held-out deals it was slightly worse than single Opus, so this
  set may simply favour it.
- **Sonnet alone** scored 0.0163 at $0.052, close to single Opus at 40% of its cost.

## Limits

- **100 fresh deals** give paired ranges of about ±0.004–0.012, so most comparisons read "no clear difference".
- **Picked on practice:** the four mixes were chosen from 182 candidates on the same 90 practice deals.
- **One generator warning on `mix-test-r2`** (add-back item/claimed differs by role); kept because its seed was fixed in
  advance, and every system saw the same deals.
- **List prices from token counts,** not what a subscription or the CLI charges. A cascade is charged for its strong
  system only on escalated deals, though here every system ran on every deal.
- **One run per deal per system.**

**Spend:** practice $56.70, final test $98.00, at list prices.
