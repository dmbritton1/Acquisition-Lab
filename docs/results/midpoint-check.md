# Midpoint and named-source check: results (exploratory)

The rules were fixed in advance in `midpoint-check-prereg.md` (commit b987a30). The numbers are in
`midpoint-check.json` (`scripts/midpoint_check.py`). This used the simulator only; no Claude or Codex call was made.
Regret is the decision loss as a share of the asking price.

## Test 1, the midpoint (primary): no win

300 template deals, modelled Lead.

| Arm | Regret | Correct | False GO / NO-GO | Real facts reached | Pages on documents with no facts | − baseline, 95% CI | Deals won / lost / tied |
|---|---|---|---|---|---|---|---|
| Baseline | 0.0066 | 83.7% | 17 / 32 | 55% | 47% | — | — |
| `no_mid` | 0.0066 | 84.3% | 16 / 31 | 60% | 43% | +0.0001 [−0.0014, +0.0016] | 8 / 6 / 286 |

The CI does not lie below zero, so this is not a win. By the rules, there is no confirmation run.

Dropping the half-budget limit reaches more real facts (60% against 55%) for the same pages. It changes the outcome on
only 14 deals, and loss does not move. The framework review's long-document finding ("22 of the 35 wrong calls") was a
real chance to read more evidence, but that evidence rarely decides the deal.

## Test 2, the four arms (secondary): no arm beats the baseline

The 220 deals with a real Lead's logged opening plan. These deals informed the review, so the results are
exploratory.

| Arm | Regret | Correct | False GO / NO-GO | Real facts reached | − baseline, 95% CI | Deals won / lost / tied |
|---|---|---|---|---|---|---|
| Baseline | 0.0099 | 78.2% | 13 / 35 | 60% | — | — |
| `no_mid` | 0.0111 | 79.1% | 16 / 30 | 61% | +0.0012 [−0.0015, +0.0042] | 10 / 8 / 202 |
| `named_x2` | 0.0106 | 77.3% | 13 / 37 | 59% | +0.0007 [+0.0000, +0.0018] | 0 / 2 / 218 |
| Both | 0.0102 | 80.5% | 13 / 30 | 62% | +0.0003 [−0.0024, +0.0031] | 12 / 7 / 201 |

- **Named sources barely matter.** Doubling the weight of the Lead's named documents changed the outcome on 2 deals,
  both for the worse. The Lead names 3.6 documents per issue, about 19% of a deal's documents, and none of the 1,100
  opening issues names nothing. The names add little that the standard reading list does not already say.
- **The interaction is positive but not useful.** Its estimate, (both − `no_mid`) − (`named_x2` − baseline), is
  −0.0015 [−0.0033, −0.0002], with the CI below zero. That is because each change alone is slightly worse and together
  they are less bad. The combination is still no better than the baseline (+0.0003, CI across zero). This is one of
  several statistics on deals that were already examined, so it is not a finding.
- **The same pattern as Test 1:** more facts reached and more calls correct (the combination is 80.5% against 78.2%,
  with five fewer false NO-GOs), but no lower loss.

## What this means

- **Close these two implementations.**
  - Removing the midpoint and boosting named documents do not improve today's team in the simulator, alone or
    together.
  - They join the seven changes in `reading-simulator.md`.
  - This closes these rules, not scheduling or evidence requests in general.
- **Reading more is not the bottleneck at this budget.**
  - Every change that found more real facts left loss flat.
  - The team's remaining losses come from how it prices what it has not read, which these changes don't touch.
- **The simulator cannot test a better Challenger handoff.** It has no Challenger, and the Lead's names are not a
  stand-in for the Challenger's later, evidence-informed requests. Testing that needs real runs, which are a separate
  plan and need the user's OK.
