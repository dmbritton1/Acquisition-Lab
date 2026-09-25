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

## `s4` on dev-000..009 (2026-09-25)

Code at `c989fb1`: an objection nobody could afford to check now changes nothing, and the sweep reads only documents on the diligence map. The smoke-run results are kept in `data/cal-r2/s4-smoke-ef8f418`. There were no timeouts. The Committer refused 0 of 37 reports, and one Investigator used a computed op (a difference, on dev-003).

| | S4 | S1b (same 10 deals) |
|---|---|---|
| Correct calls | 7/10 | 7/10 |
| Regret ÷ ask, paired difference S4 − S1b | −0.0037, 95% CI [−0.024, 0.018] | |
| Flip deals (3), regret difference | −0.018 | |
| Pages, decoy pages | 20.0, 1.2 | |
| Sessions, cost per deal | 9.4, $0.49 | 1, $0.13 |
| `s3_n` | 2 | |

| Deal | Case | S4 | S1b |
|---|---|---|---|
| dev-000 | decoy (truth GO) | NO-GO ✗ | GO ✓ |
| dev-003 | interaction (truth NO-GO) | GO ✗ | GO ✗ |
| dev-004 | unresolvable | ✓ | ✗ |
| dev-006 | clean (truth GO) | NO-GO ✗ | GO ✓ |
| dev-007 | decoy (truth GO) | GO ✓ | NO-GO ✗ |

The other five deals were right for both.

**S4's two wrong NO-GOs have one pattern: the router is myopic.**
- On dev-006, the Lead's first plan put every issue at chance 0.35–0.5 over wide ranges.
- At those chances, no single check can change the call, because ruling out any one issue still leaves NO-GO. Router 6 therefore scores every issue 0 and does no directed reading.
- The sweep then spent the budget by coverage, and debt_like (chance 0.5, up to $46M) was never settled.
- dev-000 shows the same thing. After the first checks, only addback could still flip the call.
- The Lead also barely lowers a chance after reading without settling it: concentration went 0.4 → 0.4 → 0.35 across 3 documents.
  - **Correction (trace re-check):** those 3 documents were the QoE, the legal letter and the board minutes, none of them where concentration usually shows up, and no contract was read. So holding the chance was reasonable there. debt_like was never read in the audited notes (11 pages). On dev-000 the real limit was budget: the QoE took 9 of about 20 usable pages to settle a $0.6M add-back. The clearer case of a sticky chance is the smoke run (concentration held at 0.45 after contract_1 showed nothing).

**Fix D1 (router fallback), code only:** when no single check scores above 0, the router reads in the Lead's order instead of stopping. Replaying dev-006's recorded first plan offline: every score is 0, and the new `pick()` sends debt_like to the audited notes (10 pages). dev-000's first pick is unchanged (addback). The Lead prompt fix is deferred; see `docs/HANDOFF.md`.
