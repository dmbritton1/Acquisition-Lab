# Reconciliation pilot: designs C and A at the same page budget (design)

**Status:** design, approved section by section on 2026-10-06. Exploratory: a pilot, not a confirmatory test.

**Goal:** a team that is actually better than single Claude at the same page budget. The track is "independent
analyses that reconcile". Its kill test passed (`docs/results/referee-kill-test.md`): on the 48 deals where the team
and single Claude disagreed, a referee who saw both analysts' work got 35 of 48 calls right, against the team's 25.
That referee pooled about 1.5 times the reading budget. This pilot asks whether reconciling still helps when the
pages are capped at one budget.

**What the pilot is for:**
- Check that designs C and A work end to end, and catch any large failure.
- Choose one of the two by a rule fixed here, before any run.
- It cannot prove a winner. 40 deals is far too few (Plan 6 needed about 740).

## 1. What is compared

- **Deals:** 40 fresh template-prose `r2` deals, as split `test`, made by the same generator and profile as the
  Plan 6 test set.
  - Base seed 9,000,000. The seeds are clash-checked against every used seed (`testset.clashes`) over `data/cal-r2`,
    `data/heldout-r2`, `data/test-r2` and `data/sim-r2`.
  - Data goes to `data/pilot-r2`, which git ignores.
  - Each deal keeps its generated page budget (about 22).
- **Four systems on every deal, paired:**

  | Name | System |
  |---|---|
  | `s1b` | Single Claude at the full budget: the main comparison. |
  | `s4` | The frozen team (tag `s4-frozen-plan5`) at the full budget: the result to beat. |
  | `recon_c` | Design C (§2). |
  | `recon_a` | Design A (§3). |

  All four use model `claude-opus-5-5` with Claude Code CLI 2.1.291 or newer. All of them run fresh on these deals,
  so no old run is reused.
- **Measured for every system (as Plan 6):**
  - regret and share of calls correct;
  - false GOs and false NO-GOs;
  - pages, decoy pages and real facts reached;
  - cost and AI sessions per deal;
  - results by case type.
- **Measured for C and A only:**
  - the dispute rate;
  - how often the referee overrules each analyst;
  - pages the referee read, and whether those reads reached a real fact;
  - in A, pages both scouts read, and real facts found by each scout and by the two together.
- **Cost estimate:** about $45 in all: `s4` about $21, `s1b` about $5, C and A about $10 each.
- **Every Claude call waits for the user's OK,** given after the code is built and tested and the deals are made.

## 2. Design C: draft, dispute, check

The deal budget is B. The tool server enforces every session's budget, so the total pages never exceed B.

1. **Draft.** Single Claude, unchanged (the S1b prompt and tools), with budget 0.7·B. It reads, notes and calls.
2. **Second opinion.** One session that cannot read.
   - **It gets:** the teaser and the full text of every document the drafter opened. It never gets the drafter's
     notes, evaluations or call.
   - **Its tools:** `note_issue` and `submit` only.
   - **Its task:** for each of the five issue types, record its chance that the issue is real and its size range in
     $M, using the documents it was given.
   - **Its call** is the engine's call on those notes (§4, "Notes to an engine call"), not the call it submits. The
     submitted call is logged for diagnostics only.
   - **Why a different method:** this keeps the split between judgment and engine pricing that created the kill
     test's disputes.
3. **Check, only on a dispute.**
   - **A dispute** is when the two calls differ, or either step produced no call.
   - **The referee** is one session that sees the teaser, the full text of every document opened so far, and both
     analysts' work, labelled Analyst 1 and Analyst 2 in an order fixed per deal from its id (as in the kill test).
   - **Its tools:** `list_documents`, `open_document`, `search`, `evaluate` and `submit`.
   - **Its budget:** B minus the drafter's pages, which is at least 0.3·B. Documents already opened are in its prompt,
     so opening one again is never needed.
   - **Its submitted call is final.**
4. **Without a dispute,** the shared call stands, with the drafter's walk-away.

**Sessions:** 2 per deal, 3 on disputes.

## 3. Design A: two scouts, one referee

1. **Two scouts, each with budget 0.5·B,** run independently. Neither sees the other's reads, notes or call.
   - **Scout 1:** single Claude, unchanged (the S1b prompt and tools). Its call is its submitted call.
   - **Scout 2:** single Claude with router advice (the existing `s1b_router` prompt and tools). Its call is the
     engine's call on its final notes (§4), and its submitted call is logged only.
2. **A dispute** is defined as in C.
3. **The referee** works as in C. Its budget is B minus both scouts' pages. A document both scouts opened counts
   twice against B; that overlap is a real cost of A, and the pilot reports it.
4. **Without a dispute,** the shared call stands, with Scout 1's walk-away.

**Sessions:** 2 per deal, 3 on disputes.

## 4. Shared rules

- **Notes to an engine call:** a fresh Deal Record for the deal, with the last note per issue type.
  - A note with chance 1 is applied as a committed range [low, high], as the team records a confirmed fact.
  - Every other note becomes an open issue, priced as the team prices one: chance × Uniform(0, max(high,
    typical_high)).
  - An issue type with no note counts as no problem.
  - The call is `Record.decide()`: GO or NO-GO, and the median walk-away.
- **The referee prompt** extends the kill test's (`acqlab/bench/referee.py`): the same instructions, plus the remaining
  budget and the reading tools.
- **One combined trace per deal:**
  - Every session's rows, in order, each tagged with its step.
  - Then one final `submit` row with the design's call.
  - `pilot.score` scores it like any run. Pages are the sum of every step's paid reads; cost, tokens and sessions are
    summed over the steps.
- **A failed step:**
  - A timeout or a missing submit is a missing call, and a missing call is a dispute.
  - If the referee itself fails, the deal is scored as an unanswered run (the face decision, `answered=False`).
- **The answer key is read only by scoring,** after the final call.
- **The frozen team's files stay byte-identical** to tag `s4-frozen-plan5`.

## 5. Decision rules (fixed before any run)

1. **Mechanics check, per design:**
   - at least 38 of 40 deals end with a final call;
   - no deal's total pages exceed B (asserted in the analysis).
   - A design that fails is buggy. Fix it, log the fix, rerun that design on all 40 deals, then analyse.
2. **Pick:**
   - The design with the lower mean regret is chosen.
   - If the two are within 0.0005, the one with the lower mean cost per deal is chosen.
3. **Go or stop:**
   - The chosen design earns a properly sized test only if its mean regret on these 40 deals is below both `s1b`'s
     and `s4`'s. These are point estimates; no CI is required at n = 40.
   - Otherwise the track stops, the result is written up, and the next track is hidden-upside deals.
4. **Reported whatever the outcome:**
   - each design against `s1b` and against `s4`: the paired difference, its 95% bootstrap CI, and deals won, lost and
     tied;
   - the §1 measures.
5. **Sizing:**
   - The deals needed for 80% and 90% power against `s1b` (two-sided, 5%), using the pilot's per-deal SD of the
     paired difference.
   - It is computed at the pilot's gap and at half of it.
   - The larger test gets its own spec and the user's OK.
6. **No tuning:**
   - Prompts, budget shares and rules are frozen before the first Claude run.
   - A bug fix is logged in the results page and its design is rerun on all 40 deals.

## 6. Build and tests

- **New module:** `acqlab/bench/recon.py`.
  - The C and A orchestration, the notes-to-engine-call helper, the dispute rule and the combined trace.
  - The second-opinion prompt.
  - A runner that refuses without `--confirm-claude`, skips finished deals and stops on `LLMUnavailable`.
- **Extended:** `acqlab/bench/referee.py`, with a reading variant: the remaining budget plus the reading tools.
- **New script:** `scripts/recon_pilot.py`.
  - It applies §5 and writes `docs/results/recon-pilot.json` and `recon-pilot.md`.
- **Reused unchanged:**
  - `solver.solve` with a budget;
  - `run_session`, the tool server and `Record`;
  - `pilot.score` and the S1b and S4 runs through the pilot runner;
  - `analysis.compare` and `bootstrap_ci`;
  - `batch` deal generation, `testset.clashes` and `simrun.deals_needed`.
- **Tests, with the fake `claude` and no quota:**
  - **Budgets:** the drafter gets 0.7·B and the scouts 0.5·B each; the referee gets B minus the pages already spent,
    and the total never exceeds B.
  - **Independence:** the second opinion's prompt holds no drafter notes, evaluations or call, and Scout 2 never sees
    Scout 1's work.
  - **Notes to an engine call:**
    - a chance-1 note is committed;
    - an open note is priced at max(high, typical_high);
    - a missing type counts as no problem;
    - the call equals `Record.decide()`.
  - **Disputes:** an agreement runs no referee session; a disagreement, or a missing call from any step, runs one.
  - **The combined trace:** `pilot.score` gives the right pages and final call, and cost and sessions sum over the
    steps.
  - **No answer key:** none is read before scoring.
  - **Frozen files:** S4's are unchanged.
  - **The runner:** it refuses to start without `--confirm-claude`.
- **Order of work:**
  1. Build and test.
  2. Generate the 40 deals.
  3. Ask the user's OK.
  4. Run `s1b`, `s4`, `recon_c` and `recon_a`.
  5. Analyse.

## Out of scope

- Design B (one library, two analysts). It is parked unless A shows that independent reading is what helps.
- Hidden-upside deals and the Challenger replay: later tracks.
- Any change to the frozen team.
- A larger test, which needs its own spec.
