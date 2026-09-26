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

## The page-spend audit and D2 (2026-09-25)

An offline replay of the 10 `c989fb1` traces (`uv run python -m acqlab.bench.audit --data data/cal-r2 --system s4
--system s1b`): S4 never opened the audited notes (0 of 10; S1b 18 of 30), which held the hidden fact in 5 of the 10
deals. On dev-003 (28% of S1b's regret on the 30 deals) the answer needed contract_1 and the audited notes, 16 of 25
pages; S4 read contract_1 and S1b read the audited notes, and both said GO.

**D2, the document router** (spec `docs/superpowers/specs/2026-09-25-doc-router-design.md`): offline, on the recorded
first Lead plans, with the router's 4,000 simulated deals, the first pick is the same over 5 seeds on every deal, the
audited notes rank 2–7, and the reading path (replayed assuming nothing is found) reaches the evidence on 6 of the 8
deals that have any: dev-000, 003, 004, 007, 008, 009. It reads the audited notes 2nd on dev-000 and dev-008, 3rd on
dev-003 and 4th on dev-007. It misses dev-002 and dev-005, where the audited notes held only decoys. Expect the
Challenger and the sweep to get little budget (spec Risks). A regret-based document score was tried first and
dropped (spec §8): at the Lead's first plan no single read changes the call.

**Also found (answer keys, read-only):** "not found" is no evidence against an issue (a clean fact states $0.0M), so the
Lead prompt fix deferred earlier is withdrawn. The map's order is off for `r2` (add-backs sit in the audited notes 43%
of the time, the QoE 30%), and the board minutes, off the map, hold 13–30% of each issue's evidence. Both concern the
shared guide, so they are a later fairness question.

## D2 re-run: `s4` on all 30 `cal-r2` dev deals (2026-09-25)

Code at `059a3b4` (document router, 4,000 router worlds, reads survive a search). CLI 2.1.280, Opus 5.5. The `c989fb1`
runs are kept in `data/cal-r2/s4-c989fb1`. No timeouts; 30 of 30 answered.

| | S4 (D2) | S1b (same 30 deals) |
|---|---|---|
| Correct calls | 26/30 | 22/30 |
| Mean regret ÷ ask | 0.0107 | 0.0195 (S4 45% lower) |
| Paired difference S4 − S1b | −0.0088, 95% CI [−0.0228, +0.0055] | |
| Flip deals (17), paired difference | −0.0078 | |
| Pages, decoy pages | 22.6, 2.17 | 2.63 decoy pages |
| Sessions, cost per deal | 10.8, $0.49 | 1, about $0.13 |
| Audited notes read | 18/30 (was 0/10 at `c989fb1`) | 18/30 |
| `s3_n` | 2 | |

By case type, mean regret S4 / S1b: clean 0.0066 / 0.0368 (3 deals), decoy 0.0027 / 0.0078 (8), flip 0.0392 / 0.0273
(3), interaction 0.0203 / 0.0331 (8), unresolvable 0 / 0.0083 (8).

Where the calls differ: S4 wins dev-004, 007, 012, 013, 016, 025 and 029 (S1b regret 0.010–0.110); S4 loses dev-006,
017 and 022; both miss dev-003.

**Reading the result.** S4's regret is 45% below S1b's, above the 25% the headline needs, but the CI on 30 deals includes
zero: the difference rests on a few large deals on each side (S1b's dev-012, 025, 029; S4's dev-022).

**S4's losses:**
- **dev-022 (flip, 0.118): the Challenger was starved** (spec Risks). The $45.8M debt-like flipper is in the QoE, third
  on the map for debt-like items. S4 read the audited notes (first place; nothing there), then spent the rest on cheap
  documents (credit agreement, contract_1). The Challenger named the QoE for debt-like items in both rounds; nothing
  was left to read it.
- **dev-006 (clean) and dev-017 (decoy): caution on good deals.** Issues S4 did not settle keep the Lead's starting
  chances (0.35–0.5 over wide ranges), and those alone hold the call at NO-GO. On dev-017 the board minutes, which held
  two issues' clean facts, were never read.
- **dev-003 (interaction, both systems miss):** S4 read the CIM and committed the seller's claims as $0 for all five
  issues, including concentration, whose $24.5M loss is in contract_1. The CIM ranks high under D2 (second or third on
  the map for most issues); the trust ranking puts it last. 5 commits across the 30 runs quote the CIM.

**Candidate next steps** (not yet decided): give the Challenger a budget of its own (a reserved share for objection
reads), and stop a CIM claim alone from settling an issue.

## D3 offline checks (2026-09-25)

Spec `docs/superpowers/specs/2026-09-25-d3-challenger-cim-design.md`. Replaying the first directed pass of the 30 D2
runs under the strict midpoint (exact until the first commit): the Challenger first speaks with 10–14 pages left on
every deal (under D2: 0–1 on 25 of 30), 13 on dev-003 and dev-022 (where the QoE, holding the $45.8M flipper, costs 9).
The CIM rule converts 5 of the D2 commits, all dev-003's five $0 claims, and none elsewhere.

## D3 re-run: `s4` on all 30 `cal-r2` dev deals (2026-09-26)

Code at `5e7640f` (the Challenger at the midpoint, CIM claims). CLI 2.1.280, Opus 5.5. The D2 runs are kept in
`data/cal-r2/s4-d2-059a3b4`. No timeouts; 30 of 30 answered.

| | S4 (D3) | S4 (D2) | S1b |
|---|---|---|---|
| Correct calls | 26/30 | 26/30 | 22/30 |
| Mean regret ÷ ask | 0.0076 | 0.0107 | 0.0195 (D3 61% lower) |
| Paired difference vs S1b | −0.0119, 95% CI [−0.0243, −0.0016] | −0.0088, [−0.0228, +0.0055] | |
| Paired difference D3 − D2 | −0.0032, 95% CI [−0.0118, +0.0015] | | |
| Flip deals (17), paired difference vs S1b | −0.0147 | −0.0078 | |
| Pages, decoy pages | 22.8, 2.1 | 22.6, 2.17 | 20.3, 2.63 |
| Sessions, cost per deal | 10.8, $0.50 | 10.8, $0.49 | 1, about $0.13 |
| Audited notes read | 18/30 | 18/30 | |

By case type, mean regret S4 (D3) / S1b: clean 0.0066 / 0.0368, decoy 0.0055 / 0.0078, flip 0 / 0.0273, interaction
0.0203 / 0.0331, unresolvable 0 / 0.0083.

Calls against D2: the same on 28 deals. D3 wins dev-022 (flip, D2 regret 0.118) and loses dev-010 (decoy, 0.023).
S4's losses: dev-006, dev-010, dev-017 (caution on good deals) and dev-003 (with S1b).

**The Challenger's budget.** Its first round came with 10–14 pages left on every deal (D2: 0–1 on 25 of 30); round 2
with 0–2. It never raised nothing in round 1. 85 of its 265 objections (32%) had a named document read afterwards.

**What decided the changed deals (traces):**
- **dev-022 won, but not by reading the QoE.** At the midpoint the Challenger objected on debt-like items (chance 0.4,
  naming the audited notes and the QoE). The router then preferred cheaper documents per page (credit agreement 0.79
  vs QoE 0.63–0.67), and after them the QoE (9 pages) no longer fit. The $45.8M flipper was never read; the call went
  NO-GO because the objection kept debt-like items open at a raised chance. Right call, for a cautious reason.
- **dev-010 lost: the same caution on a good deal.** D3 read the audited notes in the second half and correctly found
  the $19.6M NWC fact, but the QoE and board minutes it would have read under D2 went unread, so add-backs and
  concentration stayed open; the Challenger's round 2 (chances 0.45–0.5, no budget left) held the call at NO-GO.
- **dev-003 still missed, differently.** S4 never read the CIM; at the midpoint the Challenger named contract_1 (the
  $24.5M concentration loss), but the router took the audited notes (13 pages, which found the $2.8M add-back) and
  nothing was left for contract_1 or the asset schedule.

**The CIM rule did not fire.** No D3 run opened the CIM (0/30), so it converted nothing; its live effect is untested.

**Reading the result.** The CI against S1b now excludes zero on 30 deals, and regret is 61% below S1b's. But D3 against
D2 is within noise (two deals changed, one each way), and both changed calls turn on the Challenger's late objections
raising chances that no budget remains to settle: caution that helps on flip deals and hurts on good ones. The
midpoint gives the Challenger pages, but the router seldom spends them on the documents it names (32%).

## Held-out check: set-up and criteria, written before any run (2026-09-26)

D1–D3 were each tuned on the same 30 `cal-r2` deals. This check asks whether S4's lead over S1b holds on deals S4 has
never seen.

- **Deals:** `data/heldout-r2`, 30 fresh dev deals, `--seed 630000 --profile r2` (seeds 630000–630029; no earlier batch
  used them; Plan 6's test set must avoid them), generator 4.0.0, 0 batch problems. Case mix: unresolvable 12,
  decoy 8, interaction 5, clean 5, flip 0; 9 decision flips (`cal-r2` had 17), so fewer chances for either system
  to err, and less power than the 30-deal dev result.
- **Systems:** S1b and S4 at `b728999` (D3 plus the addendum; the addendum does not change `s4`), CLI 2.1.280,
  Opus 5.5. No code or prompt changes between now and the report.
- **Criteria, fixed now:** the check **holds** if S4's mean regret is at least 25% below S1b's (the headline's size);
  it is **weak** if S4 is below S1b by less than 25%; it **fails** if S4's regret is at or above S1b's. The paired
  difference and its 95% CI are reported whatever they show; with 9 flips the CI is expected to include zero, so the
  check judges direction and size, not significance.
- **Also reported:** correct calls, regret by case type, and whether D3's parked patterns recur (objections with a
  named document read, late objections deciding a call, CIM conversions).
