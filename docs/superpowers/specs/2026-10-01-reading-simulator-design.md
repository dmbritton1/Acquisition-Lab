# Acquisition Lab: The Reading Simulator

Status: approved in brainstorming on 2026-10-01.
Parent documents: the Plan 6 results (`docs/results/plan-6-main-run.md`) and the post-hoc look
(`docs/results/plan-6-posthoc.md`).

## Goal

A free, offline test bench for S4's reading and pricing. It compares a handful of strategies against today's team,
and it sizes the next real test. It never calls Claude or Codex. The post-hoc look found three things:

- S4 never misread a document.
- Every wrong call came from issues still open when the budget ran out.
- Every part of S4 that decides what to read, and how to price what is unread, is ordinary code.

So a simulator can run that code for real and replace only the AI turns with rules.

## Decisions (user, 2026-10-01)

- **Approach A:** wrap the real S4 code (`Panel`, `Record`, the router, the engine). Only the AI turns and the
  document scoring are overridden.
- **Deals:**
  - Strategies are compared on free template-prose deals (§3).
  - The winner is confirmed on the 60 practice deals (`cal-r2`, `heldout-r2`), where the real Lead's opening plans
    were logged.
  - The 160 Plan 6 test deals are used only for the faithfulness check (§2), never to judge a strategy.
- **Strategies:** the seven in §1. No Challenger simulation, no new case types, no change to reading.

## Constraints

- **No Claude or Codex calls.** The simulated panel gets a session function that raises if it is ever called.
  Template deals use the generator's template prose (no `--llm`).
- **S4 stays frozen.** `acqlab/agents` and `acqlab/routers` stay byte-identical to tag `s4-frozen-plan5`. The
  simulator subclasses and wraps them from `acqlab/bench/sim.py`.
- **Answer keys** drive only the simulated reader (what a document reveals) and the scoring. They never reach the
  simulated Lead, the router or the engine.
- **Tuning is limited:**
  - A strategy with a setting gets at most 3 preset values, listed in §1.
  - The faithfulness check gets at most one fix (§2).
- **Results are exploratory.** They choose a design and size a test; any claim about it needs a new pre-registered
  real run.

## 1. The strategies

Each strategy is one `Strategy` record (a NamedTuple) with these fields:

| Field | Values |
|---|---|
| `scorer` | `"move"` (today's) or `"regret"` |
| `page_power` | 1 (today), 0.5 or 0 |
| `opening` | `"lead"` (logged or modelled Lead) or `"base_rate"` |
| `absence_cut` | 0 (today), 0.25 or 0.5 |
| `sweep` | True (today) or False |

In every strategy `challenger=False`, because its objections are AI judgment.

| # | Strategy | Change from the baseline |
|---|---|---|
| 0 | Baseline | none: `move`, power 1, `lead`, cut 0, sweep on |
| 1 | Decision-focused picker | `scorer="regret"` |
| 2 | Softer page discount | `page_power` 0.5, then 0 |
| 3 | Calibrated starting guesses | `opening="base_rate"` |
| 4 | Lower a guess after finding nothing | `absence_cut` 0.25, then 0.5 |
| 5 | No sweep | `sweep=False` |
| 6 | Best combination | built from 1–5 as in §3 |

The strategies work as follows.

- **`move`:** today's `Record.rank_docs` (`routers.score_docs`, the expected move in the mean walk-away), divided by
  pages^`page_power`.
- **`regret`:**
  - It uses the same world groups as `score_docs`: in each world, a document settles open issue t where u < its
    settle weight for t.
  - The score is the expected decision regret removed by learning the group, cross-fitted as in
    `routers.score_regret`, then divided by pages^`page_power`.
  - New code in `sim.py`, built from `routers` functions without changing them.
- **`base_rate`:**
  - The opening chance for each issue type is its real rate (amount > 0) in the 60 practice deals' answer keys:
    addback 0.25, debt_like 0.37, concentration 0.38, nwc 0.15, capex 0.28.
  - Sizes and named documents are as under `lead`.
- **`absence_cut`:**
  - Applies after a read that settles nothing for an open issue the document could settle (the issue is among the
    read's router weights).
  - That issue's chance is multiplied by (1 − cut).
  - The cut may hit an issue more than once, after several reads.
  - Settle weights are untouched: the existing renormalization already moves where the evidence is expected.
- **No sweep:** `Config(sweep=False)`. The reserve goes to directed reading, as in the real −sweep ablation.

The 3-value cap counts every value, the baseline's included: `page_power` gets 0.5 and 0 beside today's 1, and
`absence_cut` gets 0.25 and 0.5 beside 0. So there are 8 single-strategy runs, the baseline included.

## 2. The simulated team, and the faithfulness check

### The simulated team

`SimPanel(Panel)` overrides only these methods:

- **`lead()`:**
  - First call: writes a `propose` row with the opening plan (§3) and applies it with `Record.plan`.
  - Later calls (the real loop re-plans after a commit): re-propose the current open beliefs unchanged.
  - It always returns `stop=False`. With the router on, the real loop ignores the stop anyway.
- **`read_doc(d)`:**
  - Writes an `open_document` row charging `pages[d]`.
  - Writes a `report` row whose commits are every fact newly revealed. A fact is revealed when the last document in
    its answer-key evidence has been read: on the 220 real S4 runs, every one of the 173 two-document commits came
    from that document alone. It is committed as `quoted` at (realized, realized).
  - An `unresolvable` fact is committed as `range` over its documented range (`Fact.documented`, already in $M).
  - Issues the read could settle but didn't get a `not_found` commit, as the real Committer writes.
  - Then it applies `absence_cut` and, if anything was committed, re-plans. There is no objection-clearing: without
    the Challenger, no objections exist.
- **`sweep()`:** reads the same documents the real sweep would pick, revealing facts as `read_doc` does.
- **`route()`:** the real candidate filter and budget logic, with the strategy's scorer.

The trace rows match the real format, so `pilot.score` grades a simulated run unchanged.

### Opening plans

- **Practice and test deals:** the real Lead's first accepted `propose` from that deal's real S4 trace. It is made
  before any reading, so it is valid under any reading strategy.
- **Template deals:** a modelled Lead, fitted on the 60 practice deals' logged first plans only:
  - **Chance:** for each issue type, the median logged chance.
  - **High:** the median ratio of the logged high to `typical_high`, times this deal's `typical_high`.
  - **Low:** 0.
  - **Named documents:** the document kinds named in at least half of the logged plans for that type.
  - Every type is proposed, as the logged Lead did on every deal.

### The faithfulness check

It runs before any strategy is compared. The simulated baseline, with each deal's logged opening plan, runs against:

- the real S4 on the 60 practice deals and the 160 test deals;
- the real −Challenger (`s4_nochal`) on test-000–039.

The practice runs are from `b728999` (`heldout-r2`) and the D3 code before the two-pass addendum (`cal-r2`). The
addendum changes only the no-Challenger order, and `b728999` is byte-identical to the tag in `acqlab/agents` and
`acqlab/routers`.

**Measures:**

- Call agreement.
- Mean regret, with a paired bootstrap CI for sim − real.
- Pages read.
- Overlap of the opened-document sets (Jaccard).
- The first divergent document and its cause.

**Pass bars, fixed here:**

1. Calls agree on at least 85% of the deals with a real S4 run (up to 220).
2. |mean regret sim − real| < 0.003, and the CI of the paired difference includes zero.
3. Calls agree on at least 85% of the 40 `s4_nochal` deals.

Bars 1 and 2 are applied separately to the 60 practice deals and the 160 test deals, and all three to the 40
`s4_nochal` deals: stricter than pooling the 220.

**On failure:**

- No strategy comparison runs.
- The report gives the divergences and their causes, and proposes one fix, most likely a rule for the Lead's re-plans.
- After the fix, it gets one re-check. A second failure stops the work for the user's decision.

## 3. Running the comparison, and sizing the real test

**Template deals:**

- `data/sim-r2`: 300 deals, `acqlab.generator.batch` with profile `r2` and template prose, as split `dev`.
- The base seed is chosen so that `testset.clashes` finds no overlap with `testset.used_seeds` over `data/cal-r2`,
  `data/heldout-r2` and `data/test-r2`. The seed is recorded in the report.

**Runs:**

- **Volume:** the 8 single-strategy runs on all 300 template deals, in a process pool over every core.
- **Resuming:** each run is a file at `data/sim-r2/runs/<strategy>/<deal>.json` plus its trace. Existing files are
  skipped, so the runner resumes.
- **Timing:** about 20 s per deal-strategy, so about 1.7 h on 8 cores.
- **Extending:** to 1,000 deals, only if a comparison that decides the combination has a CI straddling zero.

**The combination (#6):**

- Start from the single strategy with the lowest mean regret whose paired CI against the baseline lies below zero.
- Add each other strategy in order of its own mean regret. Keep it only if the paired CI of (with) − (without) lies
  below zero.
- For a strategy with several values, use its best value alone.
- If nothing beats the baseline, #6 is the baseline and the report says so.

**Confirmation:** the baseline and #6 on the 60 practice deals, with the logged opening plans. It passes if #6's
mean regret is no higher than the baseline's. Sixty deals cannot show a small gain, so this checks direction only.

**Sizing:**

- **What it sizes:** a real test of #6 against S1b.
- **Expected gap:** Plan 6's S4 − S1b (−0.0038) plus #6's simulated gain over the baseline on the template deals.
- **Per-deal SD:** Plan 6's 0.0368.
- **Reported:**
  - Deals needed for 80% and 90% power at a two-sided 5% level.
  - The same at half the simulated gain.

**Output:**

- `docs/results/reading-simulator.json` and `docs/results/reading-simulator.md`, the plain-language page.
- The page covers:
  - The faithfulness result.
  - The strategy table: regret, % correct, pages on documents with no facts, share of real facts reached, and the
    paired CI against the baseline.
  - The combination.
  - The confirmation.
  - The deal counts.
  - A recommendation: the design for a real test, or "nothing beats today's team".
- Any real run is a separate plan that needs the user's OK.

## 4. Code and tests

**New files:**

- `acqlab/bench/sim.py`:
  - `Strategy`, `SimPanel`, the `regret` document scorer, the opening-plan model and the reader rule.
  - `NoClaude`: a session function that raises `RuntimeError("the simulator never calls Claude")`.
- `acqlab/bench/simrun.py`, a CLI with three subcommands:
  - `deals`: generates the template deals, with the seed check.
  - `run --data D --strategies ... [--opening logged|model]`: the process pool, resumable.
  - `combine`: the greedy combination (§3). It runs each candidate combination on the template deals as it goes.
  - `report`: the faithfulness check, the comparison, the combination, the confirmation and the sizing. It writes
    `docs/results/reading-simulator.json`; the plain-language page is written by hand from it.
- Tests: `tests/bench/test_sim.py` and `tests/bench/test_simrun.py`.

**Tests** (offline, written first):

- **The reader:**
  - On a hand-made answer key, opening a document reveals exactly the facts whose evidence it completes, and charges
    its pages.
  - A two-document fact is revealed by its last document, not by its first.
  - An `unresolvable` fact commits its documented range.
- **The baseline routes like the real panel:** on a fixed record, `SimPanel.route()` with the baseline strategy picks
  the same document as `Panel.route()`.
- **Each setting changes only its own lever:**
  - `page_power` reorders by pages only.
  - `absence_cut` changes only the chance of issues the read could settle.
  - `base_rate` changes only the opening chances.
  - `sweep=False` writes no sweep reads.
- **The safety catch:** a `SimPanel` run never calls its session. Calling `NoClaude` raises.
- **Repeatable:** the same deal and strategy give identical traces twice.
- **Graded unchanged:** `pilot.score` grades a simulated trace without error, and S4's own scoring fields (`pages`,
  `decoy_pages`, `regret`) agree with the trace.
- **The freeze:** the existing freeze check still passes, so `acqlab/agents` and `acqlab/routers` are unchanged.
- **Seeds:** the chosen base seed clashes with no used seed. A clashing seed is refused.
- **The combination rule:** on synthetic per-deal regrets, the greedy build keeps exactly the strategies whose CIs
  lie below zero.
- **Sizing:** on known inputs (gap and SD), the deal count matches the closed-form result.

## Out of scope

- Simulating the Challenger.
- Hidden-upside or other new case types.
- Fixing the "$0.0M" wording or the `contract_1` placement.
- Any change to reading or to S4's frozen files.
- Any real run.
