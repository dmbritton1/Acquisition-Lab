# Midpoint and named-source check: rules fixed before any run (exploratory)

Written and committed before any run of these strategies. It follows from the framework review
(`framework-review-2026-10-04.md`, items 1 and 2). The simulator, deals and scoring are unchanged from
`reading-simulator.md`. No Claude or Codex call is made.

## The two changes (`acqlab/bench/sim.py`)

- **`no_mid`:** the first directed pass is no longer limited to documents that fit in half the budget (`MID_SHARE`).
  The router reads in one pass over the full budget, as today's second pass does. Page scoring is unchanged.
- **`named_x2`:** for each issue, every unread document the Lead named for it has its settle weight doubled. That
  issue's weights over unread documents are then renormalized to sum to 1. On-map and off-map named documents are
  treated alike. The factor 2 is fixed here and will not be tuned.
- **`no_mid+named_x2`:** both changes.

## Test 1, the midpoint (primary)

- **Arms:** `baseline` against `no_mid`.
- **Deals:** the 300 template deals in `data/sim-r2`, with the modelled Lead and the existing baseline runs.
- **Win:** the paired 95% bootstrap CI of the regret difference (`no_mid` − `baseline`) lies entirely below zero.
- **If it wins:** run both arms on 300 fresh template deals (`data/sim2-r2`, base seed 8,000,000, clash-checked
  against every used seed). It is confirmed if the mean difference there is below zero; the CI is reported too.
- **If it does not win:** there is no confirmation run.

## Test 2, the four arms (secondary, exploratory)

- **Arms:** `baseline`, `no_mid`, `named_x2` and `no_mid+named_x2`.
- **Deals:** the 220 deals with a real S4 trace (60 practice deals in `cal-r2` and `heldout-r2`, 160 in `test-r2`),
  each with its real Lead's logged opening plan.
- **Why these deals:** the modelled Lead names the same document kinds on every deal, so `named_x2` carries no
  deal-specific information on template deals.
- **Caveat:** these deals already informed the review, so the results are exploratory and nothing here is
  confirmatory.
- **Reported:** each arm against the baseline, and the interaction (combo − `no_mid` − `named_x2` + baseline), each
  with a paired CI.

## Reported for every arm

- Mean regret.
- Paired CI against the baseline.
- Share of calls correct.
- False GOs and false NO-GOs.
- Deals won, lost and tied against the baseline.
- Pages read, real facts reached, and the share of pages on documents with no facts.
- Test 2 also reports how many documents the Lead names per issue, because a Lead that names nearly everything makes
  the boost meaningless.

## Known limits

- **The simulator has no Challenger.** In the real team the second half of the budget is what the Challenger's
  objections compete for. Removing the midpoint lets the router spend it first, which the simulator cannot see.
- **A simulator win is a lead, not an improvement to the real team.** It needs real runs, which are a separate plan
  and need the user's OK.
- **A loss closes only these specific implementations,** not scheduling or evidence requests in general.
