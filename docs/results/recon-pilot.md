# Reconciliation pilot: results (exploratory)

The rules were fixed before any run. The spec is `docs/superpowers/specs/2026-10-06-recon-pilot-design.md` and the
plan is `docs/superpowers/plans/2026-10-06-recon-pilot.md`. The numbers are in `recon-pilot.json`, written once by
`scripts/recon_pilot.py`.

**Verdict under the fixed rules: stop.** Design C is the chosen design, but its loss is not below single Claude's, so it
does not earn a larger test. The track moves to hidden-upside deals.

## Setup

- **Deals:** 40 fresh template-prose `r2` deals in `data/pilot-r2`, split `test`, base seed 9,000,000. No seed clashes;
  budgets 18–27 pages.
- **Model and CLI:** all 160 runs used `claude-opus-5-5`, checked in every row, on Claude Code CLI 2.1.291.
- **Dates:** the runs took place on 2026-10-06 and 07.
- **Interruptions:**
  - The runs were stopped three times by session usage limits and twice by network drops. Each time they resumed
    where they stopped.
  - A deal interrupted midway was redone from scratch, so a few steps were paid for twice. That spend is not in the
    rows.
  - Partway through, the user switched the session's Claude account. The model was the same.
- **Recorded cost:**

  | System | Total | Per deal |
  |---|---|---|
  | Single Claude | $5.64 | $0.141 |
  | Team | $21.85 | $0.546 |
  | Design C | $9.95 | $0.249 |
  | Design A | $9.91 | $0.248 |
  | All four | about $47 | |

## Mechanics check: both designs pass

40 of 40 deals ended with a final call in each design, and no deal went over its page budget. No step timed out.

## The four systems

| System | Regret | Correct | False GO / NO-GO | Pages | Real facts reached | Cost / deal | Sessions / deal |
|---|---|---|---|---|---|---|---|
| Single Claude (`s1b`) | **0.0085** | **82.5%** | 4 / 3 | 19.5 | 58% | $0.14 | 1.0 |
| Team (`s4`) | 0.0126 | 65.0% | 4 / 10 | 22.3 | 52% | $0.55 | 11.4 |
| Design C | 0.0102 | 70.0% | 5 / 7 | 12.5 | 21% | $0.25 | 2.15 |
| Design A | 0.0156 | 65.0% | 8 / 6 | 18.1 | 25% | $0.25 | 2.13 |

**Each design against the baselines** (paired; difference in regret, 95% CI, and deals won / lost / tied):

| | Against single Claude | Against the team |
|---|---|---|
| C | +0.0018 [−0.0101, +0.0149]; 3 / 8 / 29 | −0.0023 [−0.0071, +0.0014]; 4 / 2 / 34 |
| A | +0.0071 [−0.0077, +0.0233]; 3 / 10 / 27 | +0.0030 [−0.0062, +0.0147]; 5 / 5 / 30 |

**Regret and share correct by case type:**

| Case type (n) | Single Claude | Team | C | A |
|---|---|---|---|---|
| clean (5) | 0.0000, 100% | 0.0026, 80% | 0.0071, 60% | 0.0071, 60% |
| decoy (11) | 0.0016, 91% | 0.0068, 73% | 0.0042, 82% | 0.0016, 91% |
| flip (2) | 0.0827, 50% | 0.0000, 100% | 0.0000, 100% | 0.0961, 50% |
| interaction (9) | 0.0087, 67% | 0.0281, 56% | 0.0313, 44% | 0.0369, 22% |
| unresolvable (13) | 0.0061, 85% | 0.0125, 54% | 0.0036, 77% | 0.0036, 77% |

## What the designs did

**Design C:**
- The analysts disagreed on 6 of 40 deals (15%).
- The referee overruled the drafter twice and the second opinion four times.
- On disputes the referee read 4.7 new pages on average, and reached a real fact on 2 of the 6.

**Design A:**
- The scouts disagreed on 5 of 40 deals (12.5%).
- The referee overruled Scout 1 four times and Scout 2 once. It read nothing new, because the scouts had used the
  budget.
- The scouts overlapped by 6.1 pages per deal, so pages both read were paid for twice.
- Scout 1 reached 21% of real facts, Scout 2 16%, and both together 25%.

## Why the designs fell short

**The analysts rarely disagree, so the referee rarely acts.**
- **In C:**
  - The drafter has 70% of the budget and the second opinion reads nothing.
  - On 34 of 40 deals no referee runs, so C reads only about 55% of the budget (12.5 pages, against single Claude's
    19.5).
  - It reaches far fewer real facts: 21% against 58%.
  - The reserved 30% mostly goes unused. That is the spec §2 risk the pilot was meant to measure.
- **In A:** the two half-budget scouts overlap by a third of their pages and together reach only 25% of real facts.

**Comparison with the kill test:** a referee does well when it is given more evidence. On the kill test it pooled two
full runs and got 35 of 48 disputed deals right. Splitting one budget leaves it too little to work with.

## Also notable

**On these 40 fresh deals the team did worse than single Claude:** 0.0126 against 0.0085, with 65% correct against
82.5%, and 10 false NO-GOs.
- This is the opposite of Plan 6's 160-deal direction.
- At n = 40 it is within noise, and nothing here was planned to test the team against single Claude.
- It does add to the doubt that the team's edge is real.

## Sizing

- There is no gain over single Claude, so there is nothing to size.
- The pilot gap is +0.0018, with a per-deal SD of 0.041.

## Limits

- **The sample is small:** 40 deals and one run each. Every CI above includes zero.
- **These results reject these two implementations,** at these budget shares and with these prompts. They do not reject
  reconciliation in general.
- **A design that spends its reserve whatever happens** (for example, a referee that always checks) was not tested.
- **The 70/30 split was fixed in advance** and not tuned.
- **Cost:** a timed-out run would count as $0 in the cost averages; there were no timeouts.
