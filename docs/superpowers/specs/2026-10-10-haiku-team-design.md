# The best Haiku team against single Opus (design)

**Status:** design, approved section by section on 2026-10-10.

**Goal:** build the best buy/pass system we can from Claude Haiku 5.5, tuned on practice deals only. Then test it once,
on held-out deals, against single Opus (`s1b`) and the Opus team (`s4`). Report how good it is and what it costs.

**Why:**
- Haiku 5.5 costs $0.10 / $0.50 per million input / output tokens (prompts up to 100K tokens), against Opus 5.5's
  $4 / $20. A Haiku team that runs several sessions per deal should still cost a few cents, against single Opus's
  $0.13 and the Opus team's $0.52. The cost win is near certain; the open question is quality.
- The Plan 6 post-hoc findings (`docs/results/plan-6-posthoc.md`) suggest where a weaker model could still do well:
  - the team never misread a document; its wrong calls came from issues still open when the budget ran out;
  - the Deal Lead overrated how often problems exist (chance 0.39 against a real rate of 0.28; NWC 0.34 against
    0.11), and searching without finding didn't lower the chance.

  So a design where code, not the model, does the pricing, and open issues are priced at realistic rates, may let
  Haiku match Opus where it matters.

**There is no pass mark.** The user asked for the best Haiku team, reported honestly. §5 fixes the wording of the
verdict in advance.

## 1. What is compared in the final test

| System | What it is | Runs needed |
|---|---|---|
| `s1b` | single Opus | none: the existing runs |
| `s4` | the Opus team, frozen at tag `s4-frozen-plan5` | none: the existing runs |
| `haiku_solo` | single Claude's prompt and tools, on Haiku | new; the control |
| `haiku_team` | the frozen team's code and prompts, on Haiku | new |
| the winner | the best candidate after tuning (§3), frozen | new, unless it is `haiku_solo` or `haiku_team` |

- **Deals:** the 160 deals in `data/test-r2` and the 40 in `data/pilot-r2u`. They are reported separately and
  together (200). Both sets already have `s1b` and `s4` runs.
- **Same page budget for every system:** the deal's `default_budget`. A Haiku system may spend extra sessions, votes
  and thinking, but never extra pages.
- **Model:** every new session uses `claude-haiku-5-5`; every row records its models, and the analysis checks them.
- **CLI:** Claude Code 2.1.291 or newer, the version recorded in the pre-registration.

## 2. Integrity rules

- **The test deals are never touched during tuning.** The runner refuses `data/test-r2` and `data/pilot-r2u` unless
  the run is the final one (§4), and the final run accepts only `haiku_solo`, `haiku_team` and the frozen winner.
- **No answer key at decision time.** No step reads `truth/`. The only use of answer keys is the base rates (§3),
  computed once from the practice deals' keys and committed as a file.
- **The frozen team's files stay untouched.** `acqlab/agents` and `acqlab/routers` stay byte-identical to tag
  `s4-frozen-plan5`. The model is switched at run time, not by editing them.
- **Every paid step needs the user's OK** (§6).

## 3. Tuning on practice deals

**Practice deals (90):**
- `data/cal-r2` (30) and `data/heldout-r2` (30): existing dev deals, with `s1b` and `s4` runs for reference.
- `data/practice-r2u` (30, new): mixed-news deals made with the `r2u` profile, as `data/pilot-r2u` was. Their seeds
  are checked against every seed already used under `data/` (`testset.clashes`), so none repeats a test deal. No Opus
  runs are made on them.

**Base rates:** for each issue type, the share of practice deals where the problem is really present, read from the
90 practice answer keys. They are stored in `acqlab/bench/base_rates.json`, pooled over the 90 deals: at decision
time a system doesn't know which kind of deal it has.

**Round 0 candidates:**
1. **`haiku_solo`:** single Claude (`solver.solve`), unchanged, on Haiku.
2. **`haiku_team`:** the frozen team (`panel.solve`), unchanged, on Haiku.
3. **`haiku_lean`:** a short pipeline where Haiku reads and notes, and the engine decides:
   - **Reader:** one single-Claude run on Haiku at the full budget. It takes notes as usual.
   - **Pricers:** three sessions of the reconciliation pilot's second-opinion step (`recon.second`). Each gets the
     teaser and the full text of every document the reader opened, has budget 0, and notes every issue type with
     `note_issue`.
   - **Calibrated pricing:** each pricer's notes become a Deal Record as `recon.notes_record` builds one, except that
     each open issue's chance (below 1) is pulled toward its base rate: `chance' = w·chance + (1 − w)·rate`, starting
     at `w = 0.5`. Settled issues (chance 1) are unchanged.
   - **Call:** the engine prices each pricer's record. The final call is the majority of the three engine calls; its
     walk-away is the median of the three. Pricers that gave no call are left out; with none, the deal is unanswered.

**Each tuning round:**
1. Read the current best candidate's practice misses and find the commonest cause.
2. Make **one** change, as a new registry entry (so every version stays in git). Allowed changes:
   - prompts and roles;
   - the number of pricers or votes;
   - how open issues are priced (including `w`);
   - how the budget is split between steps;
   - the effort level (`--effort`).

   Not allowed: more pages than the budget, the answer key at decision time, or any test deal.
3. Run the new version on all 90 practice deals.
4. **Keep it** only if mean practice regret falls and neither relief false NO-GOs nor confirmed false GOs rise (both
   counted on `practice-r2u`, the only practice set with those deal types). Otherwise revert to the previous best.
5. Log the round in `docs/results/haiku-team-tuning-log.md`: the change, why, the scorecard before and after, the cost,
   and kept or reverted.

**Cap:** 8 rounds or $15, whichever comes first, under one OK from the user for the whole practice phase. Round 0
counts as the first round.

**The winner** is the candidate with the lowest mean practice regret after the last round.

## 4. Freeze and final test

**Freeze**, before any test deal runs:
- record the winner's name in `haiku.FINAL`;
- pin its prompts with a fingerprint test, as the debate pilot did (the template hashes and each step's rendered
  prompt on a fixed test room);
- commit `docs/results/haiku-team-prereg.md`: §1, §5 restated, the winner and its settings, the fingerprints, the CLI
  version, the practice scorecard and the tuning cost.

**Final test:** after the user's OK, one run of each new system on all 200 deals. Estimated cost: about $5–10.

## 5. Analysis (fixed now, run once)

`scripts/haiku_team.py` writes `docs/results/haiku-team.json` once and refuses to overwrite it.

**Comparisons**, each as a paired difference in mean regret with a 95% paired-bootstrap range (`analysis.compare`),
and deals better / worse / tied, on the 160, the 40 and all 200:
1. **The winner against `s1b`. This is the main comparison.**
2. The winner against `s4`.
3. The winner against `haiku_solo`: what the team design adds on Haiku.
4. `haiku_team` against `s4`: what the same team loses by moving to Haiku.

**The verdict wording**, for each deal set:

| Paired 95% range for winner − `s1b` | Wording |
|---|---|
| wholly below zero | "**better** than single Opus" |
| wholly above zero | "**worse** than single Opus" |
| includes zero | "**no clear difference**: at most X worse", where X is the range's upper end |

Each verdict is stated with the cost ratio (single Opus's cost per deal ÷ the winner's). If the sets disagree, the
write-up says so and gives both.

**Also reported, per system:**
- % correct, false GOs and false NO-GOs, by the generator's deal type (`clean`, `flip`, `decoy`, `interaction`,
  `unresolvable`, `relief`, `confirmed`);
- cost per deal, and each Opus system's cost ÷ each Haiku system's;
- pages, decoy pages and sessions per deal;
- unanswered runs, timeouts, refused tool calls and deals over budget.

**Refusals:** the analysis refuses to run if any system's deals differ from the data set's, if any new row's models
aren't `["claude-haiku-5-5"]` (or any baseline's aren't `["claude-opus-5-5"]`; a timed-out row may have none), or if
any winner row's prompt fingerprints differ from the frozen ones.

**Write-up:** `docs/results/haiku-team.md`, in plain language, linking the tuning log. Plus a `docs/HANDOFF.md`
update.

## 6. Build and tests

| File | What it does |
|---|---|
| `acqlab/bench/haiku.py` (new) | **Model switch:** a context manager that replaces `solver.command` for the duration of a run, so every session gets `--model claude-haiku-5-5` (and `--effort` when a candidate sets one); the original is restored afterwards. **Registry:** `haiku_solo`, `haiku_team` and `haiku_lean` to start, each a run function like `debate.RUN`'s. **Lean pipeline:** reuses `solver.solve`, `recon.second`, `recon.step`, `recon.combine`, `referee.opened` and the engine. **Calibrated pricing:** `calibrated_record(room, trace, rates, w)`. **Runner:** `run(data, systems, split, deals=None, final=False)` skips finished deals, raises `LLMUnavailable` to stop, and refuses the test sets as §2 says. `main` with `--data`, `--systems`, `--split`, `--deals`, `--final`, `--confirm-claude`. |
| `acqlab/bench/base_rates.json` (new) | The base rates (§3), with the 90 deal ids they came from. |
| `scripts/haiku_practice.py` (new) | Prints a practice scorecard: regret, % correct and wrong calls by deal set and type, cost, and health. It writes nothing, so it can run as often as needed. |
| `scripts/haiku_team.py` (new) | The §5 analysis. |
| `docs/results/haiku-team-tuning-log.md` (new) | One entry per round. |
| `data/practice-r2u` (new, not committed) | The 30 practice deals. |

**Tests**, with the fake Claude as in `tests/bench/test_debate.py`:
- the model switch reaches the command line (`--model claude-haiku-5-5`, and `--effort` when set), and the Opus
  command is restored afterwards, even after an error;
- each round-0 candidate runs end to end on a fake room and stays within its budget;
- `calibrated_record` pulls an open issue's chance as the formula says and leaves settled issues alone;
- the lean pipeline's majority vote and median walk-away, including a missing pricer call and no calls at all;
- the base rates contain no deal from `test-r2` or `pilot-r2u`;
- the runner refuses a test set without `--final`, and refuses a non-frozen system with it;
- the analysis: each verdict branch, the cost ratio, and each refusal;
- `acqlab/agents` and `acqlab/routers` are unchanged, and the earlier prompt fingerprint tests still pass.

## 7. Order of work and cost

1. **Build and test** (free).
2. **Generate the 30 practice deals and compute the base rates** (free).
3. **Smoke test, then up to 8 practice rounds.** One OK from the user covers the whole practice phase, capped at $15.
   The smoke test runs the three round-0 candidates on 2 practice deals (pennies). It checks that Haiku answers,
   budgets hold and every row records Haiku.
4. **Freeze** the winner (§4).
5. **The user's OK, then the final test** on 200 deals (about $5–10).
6. **Run the analysis once**, then the write-up and the HANDOFF update.

## 8. Out of scope

- Mixed teams (Haiku readers with an Opus decider); Sonnet.
- Any change to the frozen team, to single Claude's prompt or to the tools.
- More than one run per deal in the final test.

## Limits (stated in the write-up)

- **Tuning noise:** each practice round is one run per deal, so a kept change may have helped by chance. The held-out
  test is the guard against that.
- **The practice set mixes two kinds of deal** (60 `r2` and 30 `r2u`) to match the two test sets; base rates are
  pooled over them.
- **Haiku's cost depends on prompt size:** prompts over 100K tokens cost five times as much. Each row records its real
  cost.
- **The deals:** generated, with template prose on the `r2u` sets.
