# Pre-registration addendum: the Plan 6 main run (2026-09-27)

Written before any test deal is generated. It adds only what `plan-4b-preregistration.md` leaves open; H1–H6 are
unchanged. Design: `docs/superpowers/specs/2026-09-27-plan-6-main-run-design.md`. Code: `acqlab/bench/testset.py`,
`valuer.py`, `pilot.py`, `campaign.py`, `analysis.py`.

## Scope (user, 2026-09-27)

- On all 160 test deals: S1b; S3 with N = 2 (the majority of two S1b runs; a 1-1 tie is no-go, as `pilot.s3_rows`
  has done since Plan 4b); S4 at tag `s4-frozen-plan5`; S0.
- Not run: the budget sweep, repeat seeds on a subset and the hand-reviewed deals. The showcase deal moves to Plan 7.

## Definitions

- **H2's belief-error deals are the `flip` case type.** The target group is `interaction` and `flip`; the rest is
  `clean`, `decoy` and `unresolvable`.
- **The ablations:** −Challenger (`s4_nochal`, the frozen panel with the Challenger off; the router's two-pass reading
  is kept) and −residual sweep (`s4_nosweep`), full runs on `test-000` to `test-039`. −engine (`s4_noengine`) and LLM
  decides (`s4_llmdecides`): S4's final Deal Record rebuilt from its trace, then one valuer turn, on all 160 deals.
  −engine's valuer sees no engine output and gives the walk-away and the call; LLM decides' valuer sees the engine's
  median walk-away and its 10–90% range, gives the call and keeps the engine's walk-away.
- **H6:** a real trap is a fact with a nonzero amount; S4's first plan is its first accepted Deal Lead proposal.

## Pass/fail rules

Every comparison is a paired per-deal difference with a paired bootstrap 95% CI (2,000 resamples, seed 0), also
reported by case type. A CI "excludes zero" only if its bound clears zero by more than 1e-12 (float noise).

| | Deals | Holds if |
|---|---|---|
| H1 | 160 | S4's mean regret is at least 25% below S1b's, the CI on S4 − S1b lies below zero, and S4's mean regret is below S3's. |
| H2 | 160 | The mean gain (S1b − S4) on interaction and flip deals minus the mean gain on the rest is above zero, with a CI (resampling within each group) above zero. |
| H3 | 40 | −Challenger's regret exceeds S4's; CI above zero. |
| H4 | 160 | S4's decoy pages are below S1b's; CI below zero. |
| H5 | 160 | −engine's mean walk-away error is at least twice S4's, and the CI on the difference is above zero. |
| H6 | the 40 | On the deals where a real trap is missing from S4's first plan, −sweep's regret exceeds S4's; CI above zero. Fewer than 5 such deals: "too few to test". |

## Also reported (no pass/fail)

The pessimism control beside H1 (S4 − `s1b_matched`: S1b's least confident GO calls switched to NO-GO until it says
NO-GO as often as S4); LLM decides − S4; for every system, correct calls, walk-away error, pages, decoy pages,
sessions and cost; S0 and the no-AI floors. H3 and H6 have 40 deals and little power: a CI that includes zero is
reported as "not shown", not as evidence against.

## The test set

`--seed 3500000 --profile r2 --test 160` (test seeds 3,510,000–3,510,159), checked before generation against every seed
on disk (no match, modulo the 1,000,000 retry offset); its answer keys' fingerprint is committed at once
(`plan-6-test-set.json`). Recoverability: 20 test deals drawn with numpy seed 0 (`testset.recover_sample`), Codex as
the extractor, and any call where Codex used a tool counts as a failure. Any failure stops the main run until it is
understood; failures are reported, not regenerated.

## Conduct

No early stopping and no peeking: the campaign logs progress counts only, and the analysis runs once, after every
phase. If a run cannot complete (for example, a replay that does not give S4's call), the campaign stops and the user
decides; nothing is dropped silently.
Every Claude call uses Claude Code 2.1.280 (the version every S1b and S4 run so far used), a private copy named
by `CLAUDE_BIN`; the campaign refuses to start if `CLAUDE_BIN` is unset or reports another version.
