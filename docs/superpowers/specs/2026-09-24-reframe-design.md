# Acquisition Lab: reframe after the Plan 4a checkpoint (design)

*2026-09-24. This revises `2026-09-22-acquisition-lab-design.md` (the main spec). Where they conflict, this document
wins; everything it doesn't mention stays as the main spec says. It was triggered by the main spec's §4 checkpoint
rule: "If the router doesn't help, reframe the claim before building S4 in full."*

## 1. Why the claim changes

**Goal (user decision):** win the competition *and* have a headline number that survives a sceptical judge. The
headline must still be "beats a single Opus on decisions" (user decision); a tie or efficiency claim is not acceptable
as the headline.

**What the Plan 4a checkpoint showed.** The full record is in `docs/results/plan-4a-prompt-log.md`.
- **The router didn't improve decisions.** Four router versions ran over 120 runs, and the last was tested on 30 fresh,
  pre-registered deals. None improved a decision-flip decision over S1b. Verdicts: mixed, mixed, mixed, then reframe.
- **The router reliably changes what gets read.** It reads 8–12% fewer pages and, on fresh deals, wastes 68% fewer pages
  on decoys.
- **S1b is strong.** Its regret per asking price is 0.006–0.009, and it gets about 80% of all deals right. It beats B0
  (0.049) and the margin shortcut (0.011–0.015).
- **Where S1b fails** (about 11 misses in 60 pilot runs):
  - **two-issue interactions**, about 4 misses
  - **wrong beliefs about where evidence lives or how big it is**, which then exhaust the budget, about 3 misses
  - **caution on good deals** (a no-go on a deal worth buying), about 4 misses
- **H1 can't be tested on the current benchmark.** A 25% improvement on 0.006–0.009 is about 0.002, while paired
  per-deal differences are mostly 0 with occasional misses of 0.03–0.13. At 100 test deals, even a genuinely better S4
  would almost never show a significant win.

## 2. The new claim

**Headline:** "On deals where a strong single Opus agent makes costly mistakes, a panel that uses a deterministic LBO
engine to challenge its own beliefs cuts decision regret by at least 25%, at the same diligence budget."

**The contribution replaces the main spec's point (1), "a scheduler that prices each diligence question".** It becomes
**engine-grounded challenge of beliefs**. Code and the engine test "what would have to be true to flip this deal":
- two-issue interactions
- "could this be bigger than I think?"
- "is the evidence somewhere else?"

The Challenger and the Deal Lead must answer those tests.

The router stays as a component. Points (2)–(4) of the main spec's novelty stance are unchanged: the engine as sole
judge, a synthetic data room with hidden ground truth, and a head-to-head at equal cost.

**The Plan 4a result is part of the story, reported honestly:** "Reading in a better order doesn't beat Opus; fixing
its beliefs does" (if H1 holds). Track A's "router 6 doesn't beat valuation-sensitivity routing" becomes a backup slide.

**The main spec's fallback claim is retired,** because S1b + router did not beat S1b. That claim was "the dollar-priced
router is what matters, even for a single agent".

## 3. Hypotheses

These are pre-registered once the benchmark is frozen, before any test deal is generated. They replace the main spec's
list.

- **H1 (headline).** S4's decision regret is at least 25% lower than S1b's on the frozen hard test set, with a paired
  bootstrap 95% CI that excludes zero. S4 must also have lower regret than S3 (best-of-N S1b at matched tokens), so "more
  tokens" can't explain the win.
- **H2.** S4's gain over S1b concentrates on interaction deals and belief-error deals (by case type).
- **H3.** Removing the Challenger increases regret.
- **H4.** S4 spends less budget on decoys than S1b.
- **H5.** Removing the engine sharply increases walk-away error.
- **H6.** The residual sweep reduces regret on deals where a trap is not in the Deal Lead's initial issue list.

The "noticeable difference" rule for H1 is unchanged from the main spec: ≥ 25% lower regret, with a CI excluding zero.

**Fairness addition.** S1b, S3 and every single-agent system get, in their prompt, the same general diligence
knowledge that S4 gets in code. That knowledge is:
- **The diligence map:** where each issue type is usually settled (see `DILIGENCE_MAP` in `acqlab/agents/knowledge.py` from Plan 4b).
- **The typical size range for each issue type:** see `typical_high`.

The only difference between systems is then architecture, as the main spec requires. This may remove some of S1b's
belief errors; that is accepted.

## 4. The hard benchmark (Plan 4b)

### Difficulty levers

Each lever is grounded in where real diligence loses money. They are pulled in this fixed order, stopping at the first
calibration round that meets every target:

1. **Case mix.** Shift toward deals with several real issues at once: more interaction deals, and more deals where two
   separate problems each look minor. Today's `CASE_MIX` is clean 0.15, flip 0.25, interaction 0.10, none 0.50.
2. **Evidence placement.** Use more split, calculation and contradicted placements; these modes already exist in the
   generator. Some evidence also moves to less obvious documents where real deal problems surface, such as the board
   minutes and the credit agreement.
3. **Budget.** Tighten `BUDGET_SHARE` from 0.25 toward 0.20, only if levers 1 and 2 are not enough.

### Calibration protocol

Calibration runs S1b only, with the §3 fairness knowledge in its prompt. It uses fresh calibration deals, never the test
set.

**Targets a round must meet:**
- **Hard enough.** S1b is wrong on at least 30% of flip deals. Its regret, and the variance of paired differences
  measured that round, must let a 25% reduction be detected at the planned test size (a power calculation from the
  round's own data).
- **Fair.** S0 (Opus reading everything, no budget) is right on at least 80% of flip deals. This shows the deals are
  hard because of choosing what to read and reasoning about it, not because they can't be solved.
- **Still diligence.** S1b beats B0 and the margin-rule floor.
- **Leak-free.**
  - The batch checks, including the page-length check, report 0 problems on 500 deals.
  - The word-leak report is no worse than before, and is empty if the search tool comes back.
  - The margin shortcut's AUC for flip deals is no higher than generator 3.0.0's 0.72.

**Process:**
- **At most 3 rounds.** Each round uses new deals: 30 for S1b, plus S0 on those deals' flip cases.
- **If 3 rounds fail,** stop and decide with the user. Do not keep tuning.
- **After the passing round:** the generator becomes version 4.0.0 and is frozen, H1–H6 are pre-registered, and the test
  set is generated once.

**Cost:** about $5–10 per round, on the user's subscription.

### Also in Plan 4b
- **The reveal-wording fix,** until `word_leaks.json` is empty, so search can come back. The new placements change that
  wording anyway.
- **The S0 and S3 baselines,** built on the existing `pilot` runner and solver.
- **S1b's prompt gains the §3 fairness knowledge.**

## 5. S4, built against the measured failures (Plan 5)

S4 keeps the main spec's §3 roles. Each is aimed at a failure the pilot measured:

| S1b failure | Where S4 addresses it |
|---|---|
| Two-issue interactions | **Code screens pairs of issues.** For the top open issues, the engine checks whether any two, at plausible sizes, would flip the decision together. The Challenger must answer every pair that could. |
| Size guessed too small | **The Deal Lead's ranges are widened in code** to at least the typical range. The Challenger asks of every "small or not found" conclusion: "could it be bigger, or somewhere else?". Each such objection becomes an engine test that the router prices. |
| Wrong document, then the budget runs out | **The router plus the diligence map.** Prices come from where evidence usually lives, and a big document is funded before the budget runs short. Intent briefs carry the flip threshold. |
| Caution on good deals | **Code makes the call.** Go/no-go comes from the engine at the committed beliefs, not from an LLM (main spec §3: "LLMs read and judge; code holds state, does math"). |
| Evidence split or contradicted | **The Committer's commit types:** quoted, computed from two or more quotes, and contradicted (a range backed by both quotes). |

**Build order.** Each step is checked on calibration or dev deals against S1b, so a role that doesn't earn its place
shows up early:
1. Deal Record, Committer, and the engine making the decision
2. The Investigator with intent briefs
3. The Challenger with the pairwise screen
4. The router and the residual sweep

**Discipline:**
- **Prompt tuning uses dev and calibration deals only,** and the effort is logged equally for S1b (the main spec's parity
  rule).
- **Stretch items stay stretch:** specialists, extra routers, ensembles. Router 2 (LLM judgement) moves from Core to
  Stretch.

**Ablations:** −Challenger, −engine and −residual sweep, as in the main spec, plus **"LLM decides"**: the engine still
prices, but an LLM makes the go/no-go call. This tests whether the code decision matters.

## 6. Sequencing, schedule, cost

The competition is about 8 weeks from 2026-09-24.

| When | Plan | Delivers |
|---|---|---|
| now to ~2026-10-02 | 4b | Generator 4.0.0 levers, the wording fix, S0 and S3, S1b's fairness prompt, calibration rounds, freeze and pre-registration |
| ~10-02 to ~10-23 | 5 | S4 in the §5 build order, with dev checks against S1b |
| ~10-23 to ~11-06 | 6 | The test set generated once; S1b, S3, S4, S0 and the ablations; paired bootstrap for H1–H6 |
| ~11-06 to ~11-20 | 7 | The demo (fork chart, the pairwise "these two together flip it" moment, the evidence trail) and slides |

**Where runs happen:**
- **Development and calibration** use the user's Claude subscription. Batches are resumable, so session limits only slow
  them down.
- **The main run** is decided in Plan 5, from S4's measured tokens per deal:
  - either API credits, about $300–400 by rough estimate for 100 test deals × S1b, S3, S4 and S0, plus ablations on 40
    deals
  - or spread over several days on the subscription

**Parked:** Track A's seed-stream fix, unless Track A is rerun.

## 7. Risks

- **S4 may still tie S1b on the hard set.** The pre-registered result is then reported as it is. The ablations and H2–H6
  still give an honest, finance-relevant story. No headline is claimed that the data doesn't support.
- **Calibration may not reach its targets in 3 rounds.** Stop and decide with the user (§4).
- **The fairness knowledge may make S1b strong enough to close the gap.** This is accepted, since without it a win
  wouldn't be about architecture.
- **Cost and time.** S4 is several times S1b's tokens per deal. Measure early in Plan 5 and size the main run then.

## 8. Revisions from pre-verifying Plan 4b (2026-09-24)

The Plan 4b code was run before the plan was written; see its "Findings". These changes follow from it:

1. **The reveal wording.**
   - A real problem and a clean fact now render the same sentence, word for word; a clean fact states `$0.0M`.
   - An unresolvable fact writes its range where an amount would go (`$6.8–$19.2M`), in any placement.
   - Word leaks on 500 deals fell from 48 to 0.
2. **Placement is role-blind in every profile.**
   - Plan 2's rule ("decoys lean loud, flippers lean buried") is gone. With the wording shared, it was the remaining leak: under `r1`, one word had AUC 0.72.
   - The difficulty lever now changes how buried evidence is *for every role alike* (`r2`).
3. **Search returns document ids, not snippets,** and matches letters only. Otherwise a 1-unit snippet could read an answer that should cost pages.
4. **Lever 2's "less obvious documents" is the board minutes only.** They are now a core document with a neutral line per topic. The credit agreement is not used.
5. **Lever 1 (`r1`):** clean 0.15, flip 0.10, interaction 0.25, none 0.50.
   - Flip + interaction stays at 35%, so the go rate stays inside the 0.38–0.62 check.
   - A first draft with 55% dropped it to 0.33.
6. **The power target uses a model of S4:** it removes all of S1b's regret on a random 25% of deals. It gets replaced by the paired variance once S4 has dev runs.
7. **The test set is generated in Plan 6,** as §6's table says. Plan 4b ends with the freeze and the pre-registration.
