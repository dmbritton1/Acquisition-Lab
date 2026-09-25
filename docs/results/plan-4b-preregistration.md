# Pre-registration: H1–H6 on the frozen hard benchmark (Plan 4b, 2026-09-25)

Written after calibration and before any test deal is generated. The calibration record is
`docs/results/plan-4b-calibration.md`, and the design is `docs/superpowers/specs/2026-09-24-reframe-design.md`.

## The frozen benchmark

- **Profile:** `r2`, frozen by calibration round 2. It is the `batch --profile` default from this commit on.
- **Generator version:** 4.0.0.
- **Test size:** 160 deals, which is max(100, round 2's "test deals needed" of 160). The user accepted this in place of
  a third calibration round.
- **When the test set is made:** once, in Plan 6 (spec §6).

## Hypotheses (verbatim from the spec, §3)

- **H1 (headline).** S4's decision regret is at least 25% lower than S1b's on the frozen hard test set, with a paired
  bootstrap 95% CI that excludes zero. S4 must also have lower regret than S3 (best-of-N S1b at matched tokens), so "more
  tokens" can't explain the win.
- **H2.** S4's gain over S1b concentrates on interaction deals and belief-error deals (by case type).
- **H3.** Removing the Challenger increases regret.
- **H4.** S4 spends less budget on decoys than S1b.
- **H5.** Removing the engine sharply increases walk-away error.
- **H6.** The residual sweep reduces regret on deals where a trap is not in the Deal Lead's initial issue list.

## The analysis

- **Comparisons are paired.** Every difference between systems is taken per deal on the same test deals. Each one is
  reported as a mean with a paired bootstrap 95% CI.
- **The H1 rule.** H1 holds if S4's regret is at least 25% lower than S1b's, the CI on the difference excludes zero, and
  S4's regret is also lower than S3's.
- **Results by case type.** Every comparison is also reported for each case type: clean, flip, decoy, interaction and
  unresolvable.
- **S3's N.** N is round(S4 tokens per deal ÷ S1b tokens per deal), measured on dev deals in Plan 5, before the test
  set exists.
