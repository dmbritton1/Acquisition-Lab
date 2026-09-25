# Plan 5 dev checks: S4 against S1b

Deals: `data/cal-r2` (frozen profile `r2`, generator 4.0.0). S1b's runs are the ones from calibration round 2. Claude CLI 2.1.280, Opus 5.5.

## Smoke run (2026-09-25): `s4` on dev-000..002

Code at `ef8f418`. No crashes, no timeouts, and every role made its closing call (dev-000: 4 propose, 4 report, 2 challenge; dev-001 and dev-002: 3, 3, 2). The Committer refused 0 of 10 reports. No Investigator used a computed op.

| Deal | Case | S4 call | S1b call | Truth | S4 sessions | S4 tokens | S1b tokens | S4 pages / budget |
|---|---|---|---|---|---|---|---|---|
| dev-000 | decoy | NO-GO (regret 0.060) | GO | GO | 10 | 141k | 57k | 20 / 22 |
| dev-001 | clean | GO | GO | GO | 8 | 112k | 94k | 18 / 21 |
| dev-002 | decoy | GO | GO | GO | 8 | 126k | 77k | 19 / 22 |

Per deal, S4 against S1b: $0.47 against $0.13 (notional), 126k tokens against 76k, about 2 minutes against 34 seconds. `s3_n` = 2 on these 3 deals, which is too few to fix N.

**Why dev-000 went wrong** (an offline replay of the record from the trace, with no Claude calls):
- The directed reading used up the budget before the Challenger's objections could be checked. The objections on concentration (chance 0.4, up to $18.2M) and debt_like (0.35, up to $15.2M) went unchecked. Their widening still stood, per Decision 8, and it alone keeps the call at NO-GO even with the Lead's chances cut to a quarter.
- Without that widening, the Lead's own chances still give NO-GO. It kept concentration at 0.45 after contract_1 showed nothing, and debt_like at 0.35 after legal and credit showed nothing. At half those chances the call is GO.
- The sweep spent its pages on documents outside the diligence map (it_policy, environmental, code_of_conduct).

This is the "S4 too cautious" risk that the plan named, seen in one thin-margin deal: the asking price was $75.8M, and S4's median walk-away was $73.4M.
