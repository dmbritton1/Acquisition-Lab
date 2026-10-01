# Plan 6: a post-hoc look at the main run (exploratory)

**Exploratory, not confirmatory.** Everything here was chosen after the verdicts in `plan-6-main-run.md` were known,
on the same 160 test deals. Nothing here changes a verdict. The counterfactuals re-price S4's own final Deal Record
offline (`valuer.replay`, then the engine), which makes no Claude calls. They are in-sample, so they show where the
leverage is, not what a new system would score. Scripts: `scripts/plan-6-posthoc/posthoc{,2,3}.py` (run from the repo
root with `uv run python`).

## 1. The Team never misread a document

On every deal, the value S4 committed for each issue matched the answer key: 0 wrong commits in 800 issue slots.
Unresolvable facts were committed as their documented range, as designed. Replacing S4's committed values with the
truth changes nothing (point regret 0.0146 → 0.0148). **Every one of S4's 35 wrong calls comes from issues still
unsettled when the reading budget ran out.**

## 2. Two opposite ways of being wrong

| | Passed on a good deal | Bought a bad deal | Says NO-GO |
|---|---|---|---|
| S1b (Solo) | 9 | 28 | 40% |
| S3 (best of 2) | 14 | 20 | 48% |
| S4 (Team) | 25 | 10 | 61% |
| Truth | — | — | 52% (face value: 3%) |

Solo's mistakes are mostly buying bad interaction deals (19 of 43): it treats issues it has not read as $0. The Team's
mistakes are mostly passing on good clean, decoy and unresolvable deals (25). Only 12 deals are wrong for both.

## 3. Why the Team passes on good deals

In all 25 of S4's false NO-GOs, the facts S4 had actually committed said GO. The issues still open turned the
call: the engine prices each at the Deal Lead's chance × Uniform(0, max(Lead's high, usual range top)). Those issues
were mostly truly $0.

- **The Deal Lead overrates how often problems exist.** First-plan chance 0.39 on average; 0.28 of issues are real.
  The worst is NWC: 0.34 against 0.11. The cal-r2 and heldout-r2 base rates match the test set (0.15–0.38 by type).
- **Searching without finding doesn't lower the chance.** 357 issues were still open at the end, priced at 0.38
  on average; 0.21 were real. 353 of them had been searched without anything being found.
- **Correcting this barely moves regret (counterfactuals on S4's record):**

| Open-issue pricing | Regret | Correct | − S1b, 95% CI |
|---|---|---|---|
| As run | 0.0088 | 78.1% | −0.0038 [−0.0100, +0.0016] |
| Chances = cal/heldout base rates | 0.0084 | 80.0% | −0.0042 [−0.0103, +0.0014] |
| Chances halved | 0.0101 | 80.0% | −0.0025 [−0.0088, +0.0037] |
| Halved only if searched and not found | 0.0099 | 80.6% | −0.0027 [−0.0091, +0.0036] |
| Open issues dropped (committed facts only) | 0.0146 | 77.5% | +0.0020 [−0.0044, +0.0082] |

Pricing the unknowns *is* the Team's advantage. On its committed facts alone, S4 does worse than Solo. Calibrated
chances trade false NO-GOs for false GOs at about the same regret. The NO-GO lean is mostly the price of a caution that
pays on this test set, where 52% of deals are truly bad but only 3% look bad.

## 4. Decoys: read correctly, lost anyway

S4 committed the correct amount for every decoy it read. It lost 8 decoy deals (Solo lost 2) because these deals have
thin true margins: the true walk-away is 1.5–9% above the ask once the decoy is counted. On those margins, the
leftover open issues tip the call. Decoy documents are 7% of S4's pages, against 5% for Solo. The H4 failure is real,
but decoy reading is not what costs the Team these deals.

## 5. Where the pages go

| Share of pages | Holds a decision-relevant fact | Decoy only | Only $0 facts | No facts at all |
|---|---|---|---|---|
| S1b | 17% | 5% | 49% | 29% |
| S4 | 13% | 7% | 32% | **48%** |
| S0 | 15% | 8% | 43% | 33% |

Per deal, S4 reads 4.0 pages of customer contracts 2–5, which never hold a fact, and 3.5 pages of the QoE. Solo reads
0.8 and 8.8. S4's router favours short documents. S4 still opens a document holding each real fact more often than
Solo (68% against 52%; S0 98%). It reaches more issues but settles fewer per page, so issues stay open, and open issues
cause every error.

**Generator leak:** the concentration evidence is always in `contract_1` (85 of 85 deals). No session can learn this,
since each deal starts fresh, but a future generator should place it at random.

## 6. Where the Team wins

| True margin (|walk-away − ask| / ask) | Deals | S1b wrong | S4 wrong |
|---|---|---|---|
| under 5% | 74 | 24 | 25 |
| 5–10% | 31 | 6 | 9 |
| 10–20% | 38 | 6 | 1 |
| over 20% | 17 | 1 | 0 |

The Team almost never misses a big problem. Near the threshold, it does no better than Solo.

## 7. Noise and power

- **Noise:** S1b agrees with its own second run on 86.2% of calls.
- **Power:** the per-deal S4 − S1b difference has SD 0.037. Detecting the observed −0.0038 with 80% power would take
  about 730 deals; detecting −0.005 would take about 420.
- **Concentration:** half of S4's total gain comes from its 5 biggest wins.

## 8. The components

- **Challenger and sweep:** each changes S4's call on only 3 of the first 40 deals. Dropping the Challenger cuts the
  cost from $0.52 to $0.39 per deal. These 40 deals are also easier than the rest: S4 is 90% correct on them and 78%
  overall.
- **Engine against LLM:**
  - LLM decides disagrees with the engine on 6 deals; the engine was right on 4.
  - −engine disagrees on 22; the engine was right on 15.
- **Solo's notes priced by the engine:** this does worse than plain Solo (0.0171, CI for − S1b [+0.0008, +0.0089]).
  Solo notes only 1.65 issue types per deal, and the engine needs the full issue list the Deal Lead proposes.

## 9. Cost in deal terms

The mean asking price is $147M. Average regret is $1.0M per deal for S4 and $1.9M for S1b, at an extra $0.40 of
compute per deal. The Team's cost is not the obstacle. The obstacle is that 160 deals cannot show the gap reliably.

## What this suggests for a version 2 (new pre-registration, fresh deals)

1. **Reading efficiency (largest lever).** Every error is an issue left open. Stop the router chasing short empty
   documents; weight primary sources (QoE, audited notes) by what they settle, not by cost per page.
2. **Update on absence.** Lower an issue's chance after its likeliest documents are read and nothing is found. On its
   own this is a small change in regret (§3); it pays only alongside (1).
3. **Power.** 400–750 deals, or repeat runs per deal, if H1 is to be re-tested.
4. **Simplify.** The Challenger is a candidate to drop (−25% cost). Test it on more than 40 deals first.
5. **Benchmark.**
   - Place the concentration clause at random.
   - Add hidden-upside cases, so caution isn't rewarded by construction.
   - Redesign H6 so it can trigger.
   - Fix the "$0.0M" template wording.
