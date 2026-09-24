# Acquisition Lab — Track A Routers Design (Plan 3)

Status: Approved in brainstorming 2026-09-23; revised the same day after pre-verification (see §7).
Parent spec: `2026-09-22-acquisition-lab-design.md` §3 (Router) and §4 (Track A). The parent stays the binding authority; deviations are listed at the end.
Inputs: the engine (Plan 1) and generator answer keys (Plan 2). All money in $M.

## Goal

Show that the router math is right, on thousands of simulated runs, with no LLM. A code "simulated investigator" returns a fact's value at its retrieval cost. Track A shows the math works; it does not show the router works on real diligence (router and generator share the engine). It is an internal diagnostic, and backup-slide material at most. Its headline is hypothesis H2: router 6 beats routers 3 and 5, especially on decoy and interaction cases.

## Scope

| In Plan 3 | Not in Plan 3 |
|---|---|
| Routers 1 (checklist), 3 (valuation sensitivity), 5 (flip probability), 6 (regret reduction per unit cost) with pair screening | Router 2 (LLM judgment): needs the Plan 4 adapter |
| Random (floor) and oracle (ceiling) | Router 4 (Stretch) |
| Noisy priors at 3 levels, forgotten issues, residual sweep | The veto for every router; a page-price sweep (later, see below) |
| Simulated investigator: perfect, failure, noisy | Track B (real LLMs) |
| "6 + veto" row | |
| Two truth modes: generator and self-consistent (§7) | |
| A hints study: priors with a noisy hint about which issues are real, labelled "what if" (§7) | |

## 1. Components

Three files in `acqlab/routers/`:

- **`beliefs.py`: issue state and world sampling.** For each of the five traps, an `Issue` holds its state:
  - *open*: `p_real` (chance the problem exists) and `hi` (top of its size range, $M)
  - *known*: a point value
  - *known range*: `(low, high)`, from unresolvable facts or the noisy investigator
  - *unproposed*: forgotten, so it is never scored

  `sample_worlds(beliefs, base, n, rng)` returns an n×5 matrix of $M values and each world's walk-away. It converts with `acqlab.generator.traps.params_for` and never hand-rolls units. An unproposed issue is fixed at 0 in the router's worlds: no one thought of it, so the beliefs implicitly assume no problem. This is why forgetting hurts, and why the sweep exists. Routers score only proposed, open issues.
- **`routers.py`: scoring rules and the decision.**
  - Routers 3, 5 and 6 are functions from (worlds, walk-aways, asking price, costs) to a score per open issue.
  - Checklist, random and oracle are ordering rules.
  - `decide(walk_aways, ask)` returns go if mean(max(0, ask − w)) ≤ mean(max(0, w − ask)), and gives the walk-away estimate as the median.
- **`track_a.py`: the experiment.** Priors, investigator, run loop, metrics, summary and command-line entry point.

**Shared helper:** the grouping-and-cross-fitted-regret step inside `acqlab.generator.truth.value_of_knowing` moves into a function both the generator and the routers call, so the estimator exists once. Plan 2's tests must pass unchanged, and batch output must be identical.

**Isolation rule:** router and ordering functions never receive an `AnswerKey`, `DealTruth` or fact list. They see beliefs, worlds and investigator replies only. The oracle is the one exception: its job is to see the truth. A test enforces this.

## 2. Scoring

Each step draws N = 400 worlds from current beliefs (common random numbers: every router in a step uses the same draws). "Current decision" is `decide` over those worlds.

Grouping for issue i: one group for worlds where i is exactly 0, and 10 quantile groups for the rest (as in Plan 2). Decisions per group are cross-fitted: chosen on one half of the draws and scored on the other.

- **Router 6:** V_i = regret(current decision) − regret(best decision per group of i), in $M, floored at 0. Score = V_i / cost_i.
  - **Pair screening:** for the top 3 issues by V_i, group by pairs: the product of each issue's zero-or-not group and 4 size quantiles. If V_ij > V_i + V_j, each member's score becomes max(own score, V_ij / (cost_i + cost_j)).
- **Router 5:** the share of worlds whose group decision differs from the current decision. Not divided by cost.
- **Router 3:** the sum over groups of (group share) × |mean walk-away in the group − overall mean walk-away|. Not divided by cost.
- **Checklist:** a fixed order: addback, debt_like, concentration, nwc, capex.
- **Random:** a uniformly random order of proposed issues, seeded per (deal, setting).
- **Oracle:** knows true values and always gets the perfect investigator. It enumerates every subset of issues whose costs fit the whole budget (no sweep reserve; ≤ 32 subsets), makes the final decision with that subset known and everything else at the prior, and keeps the subset with the lowest true regret (ties go to the cheaper subset).

Every router picks the best-scoring open issue it can afford. Ties are broken by checklist order.

## 3. Priors, investigator, sweep

**Noisy priors.** For each trap, with `worst` from the answer key:
- `p_real = clip(0.30 × exp(N(0, s)), 0.02, 0.95)`
- `hi = worst × exp(N(0, s))`
- Revenue haircut is capped at 0.95 of revenue when converted.
- Each issue is forgotten with probability `f`.

| Level | s | f |
|---|---|---|
| low | 0.2 | 0 |
| medium | 0.4 | 0.10 |
| high | 0.7 | 0.25 |

Priors are drawn from an RNG seeded by (deal seed, level), so every router and investigator sees the same priors. The spec's prior calibration metric is recorded as the share of non-clean facts with `realized ≤ hi`.

**Simulated investigator.** Reading issue i charges `retrieval_cost[i]`.
- **Perfect:** returns `amount`, or `documented` for unresolvable facts (a known range).
- **Failure:** with probability 0.25 it returns nothing; the issue stays open and can be retried at full cost. Otherwise it behaves as perfect.
- **Noisy:** a clean fact returns 0. Otherwise it reports r = amount × U(0.75, 1.25), and the belief becomes the known range [r / 1.25, r / 0.75]. Unresolvable facts return their documented range.

**Residual sweep.** `reserve = 0.10 × budget`. Routing stops when no open issue fits in `remaining − reserve`. The sweep then reads the cheapest never-read issue (proposed or not; ties go to checklist order) that fits in `remaining`, and repeats while one fits. A forgotten issue read by the sweep becomes proposed and known. If it is non-clean, the run records `found_by_sweep`.

**Budgets:** 25%, 50% and 100% of the deal's default budget.

## 4. One run, metrics, outputs

A run is (deal, router, investigator, prior level, budget). Loop: route, then sweep, then a final `decide` over 400 worlds from the final beliefs.

**Per run:**
- `regret = max(0, ask − W)` if the final decision is go and truth is no-go; `max(0, W − ask)` if the final decision is no-go and truth is go; else 0. Here W is the answer key's `walk_away` (knowable values).
- **Normalised regret** = regret / asking price. This is the regret normaliser for the whole project: "EV" in spec §4 means asking price.
- Also recorded: `correct` (final go == truth go); `wa_error` = |estimate − W| / ask; `pages`; `pages_on_decoys` (the cost of reads of facts whose role is decoy); `found_by_sweep`; `reads` (ordered list of traps); and deal labels: `flip = go != face_go`, `has_decoy`, `has_interaction`, `case_type`.

**Grids:**
- **headline:** routers {checklist, random, 3, 5, 6, 6+veto, oracle} × perfect investigator × medium priors × 3 budgets, on 2,000 deals.
- **full:** the same routers × 3 investigators × 3 prior levels × 3 budgets, on the first 500 deals.

**"6 + veto":** router 6 stops routing when its best score is below 0.25% of the asking price per page (the sweep still runs).

**Deals:** a separate batch that never touches the benchmark splits:
```
uv run python -m acqlab.generator.batch --out data/track_a --dev 2000 --test 0 --hand 0 --showcase 0 --seed 200000
```

**Outputs:**
- `data/track_a/results.jsonl`: one line per run. Reruns skip keys already present, so it is resumable.
- `data/track_a/summary.json` plus a printed table: mean normalised regret per router and setting, overall and on flip, decoy and interaction slices; paired bootstrap 95% CIs (2,000 resamples over deals) for router 6 − router 3 and router 6 − router 5; prior calibration per level; the share of runs with a sweep find.

**H2 decision rule (fixed before any run):** router 6 beats router k in a cell if its mean normalised regret is lower and the paired bootstrap 95% CI of the difference excludes zero. Every cell is reported; none is dropped after the fact.

**Command:**
```
uv run python -m acqlab.routers.track_a --deals data/track_a --grid headline|full|hints [--workers 8] [--limit N]
```
Parallel over deals with `concurrent.futures.ProcessPoolExecutor` (stdlib); `--workers 1` runs in-process. A deal that fails to load or run is logged and skipped, never scored as 0.

## 5. Testing

Test-first with fixed seeds, as in Plans 1 and 2:
- **Beliefs:** known values fixed; clean share ≈ 1 − p_real; range beliefs stay in range; unproposed issues are never scored.
- **Hand-built situations:** a big-moving decoy scores high on router 3 and near 0 on router 6; a small flipper ranks first on router 6; pair screening lifts an interaction pair.
- **Oracle:** never worse on true regret than any router over a small batch.
- **Investigator:** each variant behaves as specified (failure retry charges again; noisy ranges contain the truth).
- **Sweep:** finds a forgotten issue and records `found_by_sweep`.
- **Determinism:** same inputs give identical results.
- **Resume:** skips finished runs.
- **Isolation:** router functions never see the answer key.
- **The shared helper:** Plan 2's decision values are unchanged.
- **Statistical check on a generated batch** (standing rule): in the self-consistent mode, router 6's regret is below random's, with a paired bootstrap 95% CI that excludes zero. On generator truth, the rate at which each router reads a decision-relevant fact is measured and reported, not asserted (§7 explains why).

## 6. Process

Pre-verify the plan's code in a scratch copy: run the suite and a small real Track A run (for example the headline grid with `--limit 100`), and put measured runtimes and first results in the plan. Then rebuild from the plan's own text on a fresh `main`. The final review runs on Opus and includes the statistical check.

## 7. Revisions from pre-verification (2026-09-23)

Found by running the plan's code on 120 Track A deals before writing the plan:

1. **On generator truth, every router is close to random.** At the 50% budget, mean normalised regret was: random 0.0151, checklist 0.0142, router 5 0.0132, router 3 0.0126, router 6 0.0122, oracle 0.0011. Routers read a decision-relevant fact in about 37 of 62 flip deals, against 32 for random. The noisy priors carry no deal-specific signal about *which* issue is real, and the generator builds its problems to sit near the decision edge, which the priors don't assume. The clue that separates issues lives in the documents, which Track A doesn't have.
2. **The math works when beliefs are right.** With true values drawn from the router's own priors (360 runs), routers 3 and 6 cut regret by about 60% against random (0.0050 against 0.0131; the CI for router 6 − random excludes zero). Router 6 tied router 3 (+0.0002, CI [−0.0010, +0.0015]): with page costs nearly flat, "$ per page" ranks issues almost the same as "how far the value moves". This is an early warning for H2.
3. **User decision: add both.**
   - **`truth` axis:** "generator" (the answer key) or "self" (the fair game). Self mode keeps the deal but draws every issue's true value from the medium-noise priors, forgotten issues included. Roles become "problem" or "clean". It is the clean check that the router math is correct.
   - **`clue` axis (hints study):** each issue gets a hint ("real problem" or "clean") that is right with probability `clue`, and `p_real` is scaled by the likelihood ratio clue / (1 − clue). 0.5 means no hint; the study uses 0.7 and 0.9. Hints come from the answer key, so this is a "what if" study of how good a Deal Lead's reading must be, never evidence (parent spec review finding #3).
   - **Grids:** headline = both truths (clue 0.5), on 2,000 deals. full = unchanged, generator truth, on 500. hints = clue 0.7 and 0.9, perfect investigator, medium priors, generator truth, on 500.

## Deviations from the parent spec

- Router 2 moves to Plan 4 (it needs the LLM adapter).
- Budget stewardship is tested as a single "6 + veto" row, not applied to every router, so H2 compares routers at equal spend.
- Track A budgets are 25/50/100% of the default: the default alone barely binds (handoff review finding).
- Track A adds a self-consistent truth mode and a hints study (§7). The spec's rule "priors must be noisy, never the generator's prior" still holds in every mode; hints are labelled as using the answer key.

## Later

- Veto on for every router, and a page-price sweep (regret against spend), as requested in brainstorming.
- Router 2 in Track A once Plan 4 lands.
- Raise N, or average scores over seeds, if score noise turns out to limit router 6.
