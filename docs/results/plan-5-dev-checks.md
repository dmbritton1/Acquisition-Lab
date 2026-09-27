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

## Held-out check: result (2026-09-26)

Runs on `data/heldout-r2` at `0e3b752` (no code or prompt change since the criteria), CLI 2.1.280, Opus 5.5. The
Claude session limit stopped the run three times; finished runs were kept and the run resumed. All 30 deals, both
systems. (The diagnosis and the pessimism control below were first computed on 29 S4 runs, before dev-029 finished;
S4 was right on dev-029.)

| | S4 | S1b |
|---|---|---|
| Correct calls | 23/30 | 27/30 |
| Mean regret ÷ ask | 0.0105 | 0.0078 |
| Paired difference S4 − S1b | +0.0027, 95% CI [−0.0052, +0.0096] | |
| Flip deals (9), paired difference | −0.0094 | |
| Wrong NO-GO on good deals / wrong GO | 7 / 0 | 2 / 1 |
| Cost per deal, sessions | $0.53, 11.5 | |

Floors on this batch (29 deals when computed): always GO 0.0497, always NO 0.0782, B0 0.0294, the margin rule 0.0119
(threshold fitted on these deals).

**Verdict against the criteria fixed beforehand: fails** (S4's regret above S1b's, by 35%). S4 won dev-006 and lost
dev-000, 001, 009, 012, 019 and 022; every loss is a NO-GO on a deal where GO was right.

D3's parked patterns: 78 of 238 objections (33%) had a named document read; the Challenger's round 1 raised nothing
once; the CIM rule converted nothing (S4 never opened the CIM).

### Why: the Lead overrates issues S4 never settles

Replaying each run's final Deal Record from its trace (`docs/results/scripts/plan-5-caution-replay.py`, no Claude
calls) reproduces all 59 recorded calls (`cal-r2` and held-out). At the end, objections are cleared, so the call rests
on committed values and the Lead's beliefs about the issues still open. Of 138 issues still open at the end, the Lead
gave a mean chance of 0.38; 22% were real (chance 0.25–0.40: 15% real; 0.40 and up: 30%).

What-ifs on the final records (regret; wrong NO-GO / wrong GO):

| | `cal-r2` (30) | held-out (29) |
|---|---|---|
| As run | 0.0076; 3 / 1 | 0.0108; 7 / 0 |
| The Lead's beliefs before the Challenger spoke | same | same |
| Open issues priced over the Lead's range only | same | same |
| Open chances halved | 0.0145; 3 / 3 | 0.0065; 3 / 1 |
| Open issues ignored (face value) | 0.0189; 0 / 7 | 0.0047; 0 / 2 |
| Median walk-away against the ask | 0.0115; 3 / 2 | 0.0088; 5 / 0 |

The Challenger does not cause the lean (the Lead's beliefs are the same before and after it spoke) and nor does the
usual-size-range floor. Lowering the Lead's chances trades `cal-r2` for held-out: the lean is a bet on the case mix.

### The `r2` mix: the held-out batch was a GO-heavy draw

500 throwaway `r2` dev deals (`--seed 640000`, no test split, 0 batch problems;
`docs/results/scripts/plan-5-r2-mix.py`): GO is right on 45%; 53% are decision flips, and every flip points to NO-GO
(the face says GO, the truth says NO; none the other way); 30% of issue facts are real. In a random 30 deals, GO is
right on 9–18 (5–95%), median 14: `cal-r2`'s 13 is typical, the held-out batch's 19 of 29 is near the top. The
160-deal test set should hold about 72 GO deals and 84 flips.

On the 59 deals, S4 is far better on flip deals (regret 0.0065 vs S1b 0.0199; 25 deals) and worse on the rest (0.0111
vs 0.0094; 34 deals). Reweighted to `r2`'s 53% flips, S4's regret is 42% below S1b's (bootstrap 90%: −73% to −5%;
chance of at least 25% lower: 0.79).

### What this means

- **The held-out verdict stands as fails.** It was a GO-heavy draw, but S4 does lose on good deals.
- **Don't tune the Lead's chances.** The only data to tune them against is the answer keys' base rates, which parity
  forbids; it would be fitting the benchmark.
- **The claim needs a pessimism control.** Every surprise in `r2` points to NO-GO, so a pessimistic system is rewarded
  by design, and a sceptical judge will ask whether S4 finds problems or just leans NO-GO. Next: compare S4 with a
  pessimism-matched S1b.
- **To explore later (not decided):** `r2` has no hidden upside (a deal that looks like NO-GO but is GO). Adding it
  would make the benchmark fairer to systems that don't lean NO-GO, but it changes the frozen profile and the
  pre-registration.

## The pessimism control (2026-09-26)

Defined and agreed before it was computed: `s1b_matched` is S1b with its least confident GO calls (walk-away closest
above the ask) switched to NO-GO until it says NO-GO as often as S4 on the same deals; only S4's calls and S1b's own
walk-aways choose them, never the answer key (`pilot.s1b_matched`, in the report). It asks whether S4 finds problems
or only leans NO-GO. A secondary analysis added before the test set exists; H1–H6 are unchanged.

| | `cal-r2` (30) | held-out (30) |
|---|---|---|
| S1b | 0.0195 | 0.0078 |
| S1b, as pessimistic as S4 | 0.0182 | 0.0168 |
| S4 | 0.0076 | 0.0105 |
| S4 − pessimistic S1b, 95% CI | −0.0106 [−0.0222, −0.0018] | −0.0064 [−0.0165, +0.0010] |
| Flip deals: S1b / pessimistic S1b / S4 | 0.0243 / 0.0182 / 0.0096 | 0.0094 / 0.0094 / 0 |

**Reading.** Pessimism alone does not reproduce S4's result: made just as pessimistic, S1b barely improves on
`cal-r2` (0.0195 → 0.0182) and gets much worse on the held-out batch (0.0078 → 0.0168), and S4 beats it on both,
with the CI excluding zero on `cal-r2`. S4's NO-GO calls land on better deals than S1b's least confident GO calls,
so its advantage is in which deals it rejects, not only how many. Caveat: S1b's walk-away is the only ranking the
control can use; a better-calibrated pessimist might do better.

## S4 frozen, `s3_n`, and the main-run budget (2026-09-26)

**S4 is frozen** (user decision, 2026-09-26). S4's code (`acqlab/agents`, `acqlab/routers`) has not changed since
`b728999` (D3 and its addendum); tag `s4-frozen-plan5`. The main run uses exactly this code. Task 6 Step 3 (prompt
tuning, confirmed on `cal-r1`) is skipped: after three design changes on `cal-r2` and a held-out check, further tuning
on seen deals would fit S4 to them. Plan 5's only prompt change is D2's document brief, an architecture change
logged in `plan-5-prompt-log.md`; no prompt was tuned against results.

**`s3_n` = 2**, per the pre-registration (round(S4 tokens ÷ S1b tokens), measured on dev deals before the test set):
138k ÷ 72k on `cal-r2` (30 deals) and 148k ÷ 67k on the held-out batch (29), both rounding to 2.

**Measured per run** (notional subscription cost, median time): S1b $0.13, 0.6 min; S4 $0.51, 2.4 min; S0 $0.17,
0.5 min (flip deals).

**Main-run budget** (reframe design §6; 160 test deals, ablations on 40):

| Runs | Per deal | Deals | Cost | Time |
|---|---|---|---|---|
| S1b (also S3's first run) | $0.13 | 160 | $21 | 1.6 h |
| S3's second S1b run (N = 2) | $0.13 | 160 | $21 | 1.6 h |
| S4 | $0.51 | 160 | $82 | 6.4 h |
| S0 | $0.17 | 160 | $27 | 1.3 h |
| Ablations: −Challenger, −engine, −sweep, LLM decides (about S4's cost each) | $0.50 × 4 | 40 | $80 | 6.4 h |
| **Total** | | | **about $230** | **about 17 h of runs** |

On the subscription: a usage window held about $17 of runs on 2026-09-26 (27 S1b and 26 S4 runs before the session
limit), so the main run needs about 14 windows, roughly 4–5 days if each is restarted promptly (the pilot stops cleanly
at a limit and resumes where it left off); a weekly limit, if one applies, would stretch it. On API credits it is
about $230 plus any cache differences. The user decides.

## Build-step checks (2026-09-26)

Reframe design §5: each step on the first 10 `cal-r2` deals, at the frozen code (`s4-frozen-plan5`), CLI 2.1.280,
Opus 5.5 ($9.47 in all). `s4_1`: one Investigator reads for every issue, the engine decides. `s4_2`: + the Deal Lead,
issues investigated in its order. `s4_3`: + the Challenger. `s4`: + the document router (D2, D3). S1b and `s4` are
their existing runs on the same 10 deals.

| | S1b | `s4_1` | `s4_2` | `s4_3` | `s4` |
|---|---|---|---|---|---|
| Correct (of 10) | 7 | 7 | 8 | 9 | 8 |
| Mean regret ÷ ask | 0.0280 | 0.0263 | 0.0080 | 0.0134 | 0.0183 |
| Flip deals (3), difference from S1b | | +0.0151 | −0.0725 | −0.0725 | |
| Pages, decoy pages | 20.3, 2.63 (30 deals) | 21.3, 2.10 | 16.9, 1.20 | 18.6, 1.20 | 22.8, 2.10 (30) |
| Sessions, cost per deal | 1, $0.13 | 1, $0.10 | 5.2, $0.27 | 15.2, $0.80 | 10.8, $0.50 (30) |

Per deal (✓/✗ and regret) where the steps differ: dev-000 (GO) `s4_2` ✗ 0.060; dev-001 (GO) `s4_3` ✗ 0.134;
dev-003 (NO) S1b, `s4_1` and `s4` ✗ 0.163, `s4_2` and `s4_3` ✓; dev-004 (NO) S1b and `s4_1` ✗ 0.055; dev-006 (GO)
`s4_2` and `s4` ✗ 0.020; dev-007 (GO) S1b ✗ 0.062; dev-008 (NO) `s4_1` ✗ 0.045.

**Reading** (10 deals: one deal moves a mean by up to 0.016, so only large steps are visible):
- **The engine deciding alone (`s4_1`) does not help:** it matches S1b (0.0263 vs 0.0280).
- **The Deal Lead with issue-by-issue investigation (`s4_2`) is where the gain appears:** 0.0080, and −0.0725 on
  the flip deals. It is also the only step besides `s4_3` to catch dev-003's $24.5M concentration loss.
- **The Challenger (`s4_3`) and the router (`s4`) do not show a regret gain over `s4_2` on these 10 deals.** `s4_3`
  gets the most calls right (9) but one costly miss on a good deal (dev-001, 0.134) and costs $0.80 over 15 sessions;
  the router brings the cost down to $0.50 and misses dev-003. Their own tests are the pre-registered ablations on 40
  test deals (H3 for the Challenger), not these 10 deals; S4 stays frozen (choosing a step from 10 seen deals would be
  fitting too).
