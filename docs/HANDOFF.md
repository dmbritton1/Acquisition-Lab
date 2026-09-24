# Acquisition Lab: Session Handoff

*Last updated 2026-09-23, after Plans 1 and 2 were built, reviewed and squash-merged to `main`. Read this first, then the spec it points to. The spec is the binding authority on design; this file is the source of truth for status and next steps.*

## Start here

**Where things stand:** Plan 1 (the LBO engine) and Plan 2 (the deal generator and budgeted data room) are done and on `main`. 130 tests pass (`uv run pytest -q`). The next piece of work is **Plan 3: Track A routers**, due by about 2026-10-12. The week-4 checkpoint (about 2026-10-19) depends on it.

**Do these in order:**

1. **Regenerate the deals in this checkout.** `data/` is git-ignored, so the 181 deals from the last session are not here. This takes about 30 seconds and needs no LLM:
   ```bash
   uv run python -m acqlab.generator.batch
   ```
   Expect `generated 181 deals into data; 0 batch problems`.
2. **Ask the user about the two outstanding Codex runs.** Both use their ChatGPT Codex quota, so run them only with their explicit OK:
   - **Smoke call** (one tiny call; confirms how token counts are read):
     ```bash
     uv run python -c "from pathlib import Path; from acqlab.llm import complete; print(complete('Reply with the single word: ok', cache_dir=Path('data/llm_cache')))"
     ```
     Expect `('ok', <tokens>)` with tokens above 0. If tokens is 0, look at `codex exec --json` output and fix `_usage_tokens` in `acqlab/llm.py` (with a test).
   - **Proof-of-concept Codex batch** (about 70 calls, roughly half a Codex usage window):
     ```bash
     uv run python -m acqlab.generator.batch --out data/poc --dev 3 --test 0 --hand 0 --showcase 1 --llm
     ```
     Then run the same command plus `--recover 3`. Report batch problems, `prose_fallbacks` and `llm_tokens` (both in `data/poc/truth/*.json`). If Codex hits its usage limit, the command exits with code 2. Run the same command again after the limit resets: it resumes from the cache and pays for nothing twice.
3. **Write Plan 3 (Track A routers).** Start with superpowers:brainstorming for the open details listed under "Plan 3: what the next session needs to know". Then use superpowers:writing-plans, and execute with superpowers:subagent-driven-development.

**Suggested first message for the next session:**

> Read `docs/HANDOFF.md` and the spec, regenerate the deals, then help me design and write Plan 3 (Track A routers).

## Plan 3: what the next session needs to know

**Goal (spec §3–4):** prove the router math on thousands of simulated runs, with no LLM. A code "simulated investigator" returns a fact's value at its retrieval cost, with variants for retrieval failure and noisy values. Track A shows the math is right. It does not show the router works on real diligence, because the router and the generator share the engine. It is an internal diagnostic and backup-slide material only.

**Routers to build** (spec §3), each scoring (issue, action) pairs:
1. Checklist order.
2. LLM judgement. This needs the Plan 4 adapter, so it can come later.
3. Valuation sensitivity.
5. Decision-flip probability.
6. **Expected $ reduction in decision regret per unit cost.** This is the main bet.

Also:
- **Pair screening** for interactions between the top issues.
- **Budget stewardship:** veto any action whose score is below its cost.
- **Residual sweep:** about 10% of the budget goes to undirected reads chosen by coverage.

The spec's Track A comparison is router 6 against routers 3 and 5 (hypothesis H2), especially on decoy and interaction cases.

**Inputs that already exist:**
- **Answer keys** in `data/truth/<id>.json`, the `AnswerKey` model in `acqlab/generator/batch.py`:
  - `truth` (a `DealTruth`): `base.deal` is the engine `Deal` and `base.teaser` is the visible teaser. `facts[*]` holds `trap, variant, role, placement, worst, amount, documented, realized, alone_flips, decision_value`, then `walk_away, go, face_walk_away, face_go, debt_limit, case_type`.
  - `evidence`: which documents reveal each fact.
  - `budget`: the default budget.
  - `retrieval_cost[trap]`: pages to open that fact's evidence documents.
  - Load with `AnswerKey.model_validate_json(path.read_text())`.
- **Engine:**
  - `acqlab.engine.evaluate_under(deal, base_params, beliefs, n, seed)` gives a Monte Carlo of walk-away prices under uniform beliefs `{param: (low, high)}`.
  - `flip_threshold(deal, params, name, lo, hi)` gives the value at which go/no-go flips. It now accepts bounds in either order.
  - `is_go` and `walk_away`.
- **Unit conversion:** facts are in **$M**, but engine parameters are not all in $M (`revenue_haircut` and `capex_adjustment_pct` are fractions of revenue, and add-backs are negative). Always convert with `acqlab.generator.traps.param_value(trap, amount, truth.base)` or `params_for({trap: amount}, truth.base)`. Both take the generator's `BaseDeal` (`truth.base`), not the engine `Deal` (`truth.base.deal`). Never hand-roll the conversion.
- **Splits:** `data/splits.json` lists `dev`, `test`, `hand` and `showcase` ids.

**Rules the spec fixes:**
- **Priors must be noisy (or LLM-proposed) versions of each trap's range `(0, worst)`, never the generator's own prior.** The generator's prior is "0 with probability 0.70, else uniform on the range" (`truth.PRIOR_CLEAN`).
- Metrics are defined in spec §4. **Decision regret** is the primary one: going on a bad deal costs asking − true walk-away; passing on a good deal costs true walk-away − asking; both are normalised by EV. Score against the answer key's `walk_away` and `go`, which use the **knowable** value for unresolvable facts.

**Open questions to settle in brainstorming:**
- How to add noise to the priors: width, bias, and how often the true value falls outside the range. The spec's "Deal Lead prior calibration" metric comes from this.
- The simulated investigator's failure and noise variants, and what they cost.
- Router 6's exact estimator: the number of outer and inner draws, and how pair screening picks pairs.
- **Decision-value noise.** At the default `--mc 400`, a fact's stored `decision_value` is noisy: a real flipper can score 0 on one set of draws. If Plan 3 compares routers against these stored values, raise `--mc` first (for example to 2000) and regenerate, or average over seeds. At `--mc 2000` a batch takes a few minutes.
- Runtime. A walk-away takes about 1 ms and `evaluate_under` with n=200 takes about 0.2 s. Router 6 over every open issue, per step, per deal, across thousands of runs needs a budget; measure early.

## The project in one paragraph

This is a solo competition entry, due about mid/late November 2026. The deliverable is a live demo plus a 5–10 minute pitch to finance-oriented judges.

A fictional PE sponsor considers buying a company. The seller's asking price is set from a teaser alone. Hidden facts buried in a synthetic data room decide whether the deal is actually good: fake EBITDA add-backs, debt-like items, customer concentration, a working-capital shortfall, deferred capex, litigation.

A multi-agent framework, with Opus in every role, investigates under a diligence budget:
- a Deal Lead
- an Investigator with intent briefs
- a Modeler
- a Challenger using Analysis of Competing Hypotheses
- a code Committer
- a code **Router** that prices every open question by its expected reduction in decision regret per unit cost

A deterministic LBO engine is the only source of financial numbers. The claim to prove is lower decision regret than a single Opus agent at equal cost. The demo shows a "fork chart" of possible walk-away prices narrowing as evidence arrives.

## Decisions already made (don't re-litigate; the spec has the rationale)

| Topic | Decision |
|---|---|
| Deal type | **Pure LBO**: one target, one sponsor, one term loan, annual periods. The PE add-on variant is a later addition. |
| Output | Walk-away price (the max price with base-case IRR ≥ 20%, debt sized by sponsor rules) **and** go/no-go against the asking price |
| Primary metric | **Decision regret** in $, normalised by EV. Also reported on decision-flip cases separately. |
| Models | **Solver = Claude Opus 5.5** (`claude-opus-5-5`) in every agent and baseline. **Document renderer = Codex/GPT.** Dev runs on the user's subscriptions (`claude -p` / `codex exec`) behind one adapter. The 30-deal pilot's token use decides subscription vs API for scored runs. |
| Baselines | S1a (single Opus, tools + budget), **S1b (single Opus + engine as a tool: the fair fight)**, S0 (reads every document; the ceiling), S3 (best-of-N at equal tokens), trivial baselines, B0 (engine on the teaser only) |
| "Noticeable difference" | S4 regret ≥ 25% lower than S1b **and** a paired bootstrap 95% CI excluding zero, on ~100 test deals |
| Benchmark | Procedural generator (181 deals: dev 50 / test 120 / hand-reviewed 10 / showcase 1). Track B (real LLMs) is the headline; Track A (routers with a simulated investigator, **noisy priors**) is an internal diagnostic. |
| Scope tiers | Core vs Stretch tables in spec §3–4 |
| Checkpoint | **End of week 4 (~2026-10-19):** S1b vs S1b + router 6 on the pilot, plus Track A. If the router doesn't help, reframe the claim before building S4 in full. |
| Demo | A recorded S4 trace replay is the primary path. Engine interactions are always live. |
| Stack | Python 3.12, uv, pydantic 2, numpy, pytest + hypothesis. JSON files, no database. Demo is FastAPI + Vite/React (Streamlit fallback). |
| Novelty stance | Closest prior art is **MAI-DxO / SDBench** (arXiv:2506.22405); also AUDITFLOW, arXiv:2605.13110 and arXiv:2603.22651. The claimed contribution is the *combination*; never claim "first". **Verify every citation before it goes on a slide.** |

User preferences:
- Ambitious scope is welcome ("don't get timid"), but always keep a guaranteed-to-work demo path.
- Wants a complex architecture diagram for credibility: a simple main slide plus a full backup slide.
- Finance judges, so lead with the financial decision.
- Likes plain explanations ("explain like I'm 12") when asked.
- Wants reviews held to a high standard.

## What's built

### Repo map

```
acquisition-lab/
  docs/
    HANDOFF.md                                             ← this file
    superpowers/specs/2026-09-22-acquisition-lab-design.md  ← THE spec (binding authority)
    superpowers/specs/2026-09-23-plan-2-generator-design.md ← Plan 2 design; read its "Revisions" section
    superpowers/plans/2026-09-23-plan-1-lbo-engine.md       ← Plan 1 (done except the Task 9 spreadsheet check)
    superpowers/plans/2026-09-23-plan-2-generator.md        ← Plan 2 (done)
  acqlab/engine/      model.py, lbo.py, walkaway.py, beliefs.py         (Plan 1)
  acqlab/generator/   industries.py, sample.py, traps.py, roles.py, truth.py, documents.py,
                      render.py, validate.py, prose.py, recover.py, batch.py   (Plan 2)
  acqlab/dataroom/tools.py                                              (Plan 2)
  acqlab/llm.py                                                         (Plan 2)
  tests/engine/, tests/generator/, tests/test_llm.py, tests/conftest.py
  data/               git-ignored: deals/<id>/room/, truth/<id>.json, splits.json, llm_cache/
```

### The engine (`acqlab.engine`, Plan 1)

All money is in **$M**; rates are decimals. There are no LLM calls, and this is the only code allowed to produce financial numbers.

**Public API:**
- `evaluate(deal, params, price=None)` returns a `Result`: uses, debt, equity, exit equity, IRR, MOIC, base and downside year paths, covenant headroom, `debt_caps`, `debt_limit` (which cap set the debt), and `bridge` (`EquityBridge`).
- `walk_away(deal, params)`: the max price with IRR ≥ hurdle, by bisection. `PRICE_FLOOR = 0.01` if nothing clears.
- `is_go(deal, params)`: exact, meaning IRR at the asking price ≥ hurdle.
- `flip_threshold(deal, params, name, lo, hi)`: the parameter value where go/no-go flips. Bounds may come in either order.
- `evaluate_under(deal, base, beliefs, n=200, seed=0)`: a Monte Carlo of walk-away prices. Keys are sampled in sorted order, so a seed gives the same result every time.

**Parameters** (`Params`, the only knobs):

| Parameter | Bounds |
|---|---|
| `ebitda_adjustment` | any sign |
| `debt_like` | ≥ 0 |
| `revenue_haircut` | [0, 1) |
| `nwc_adjustment` | ≥ 0 |
| `capex_adjustment_pct` | any sign |

Unknown fields, NaN/inf and out-of-range values all raise `ValidationError`.

**Definitions:**
- Debt = min(lender cap, covenant-safe debt in the −10% revenue / −2pt margin downside, (1 − min equity) × uses).
- Uses = price × (1 + fees) + debt-like items + NWC adjustment.
- IRR = MOIC^(1/5) − 1.
- Revolver draws pay interest; surplus cash earns none.

**Verified:**
- A hand-checked simple fixture, and a full fixture matched against independent reference scripts.
- Property tests over random deals, stress-run at 3,000 deals per property.
- **Never edit golden numbers to make a test pass.**
- Known exception: a bigger revenue haircut can raise walk-away in thin, cash-hungry deals. The generator's margin rule keeps deals out of that regime.

**Documented simplifications** (have judge answers ready):
- annual covenant testing
- one term loan
- no loss carryforward
- fees charged on price
- the year-1 working-capital release in the downside
- the exit multiple is fixed by policy and dominates the walk-away (prepare an exit-multiple sensitivity backup slide)

### The generator and data room (Plan 2)

**Sampling:**
- `industries.py`: 9 industries from Damodaran's January 2026 tables.
- `sample.py`: the teaser, financing and 3 years of history from cited ranges: GF Data (7.2x, 3.6x leverage), Lincoln (SOFR + 4.75–5.50%), Sidley (25–35% covenant cushion).
- Asking prices sit about 15% below the market average, because a 20% hurdle with no multiple expansion rarely clears at market prices.

**Traps and roles:**
- `traps.py`: 5 traps, one per engine parameter. Litigation is a debt-like variant. Some story variants are held out of dev and appear only in test.
- `roles.py`: flipper, decoy, interaction pair, unresolvable and clean, constructed with the engine.

**Answer keys** (`truth.py`):
- Every deal records all five traps as facts.
- Case mix: clean 15%, flip 25%, interaction 10%, other 50%. About 47% of deals are a true go.
- Unresolvable facts are scored at the midpoint of their documented range.
- Decision values are cross-fitted, with zero-severity draws in their own bin.

**Documents** (`documents.py`, `render.py`):
- Code writes every number.
- **Presence rule:** every trap topic appears in every deal.
- Trust ranking: contracts and audited accounts > QoE > CIM.
- The CIM always makes the seller's claims, and default sentences are neutral, so neither reveals a fact's role.

**Checks** (`validate.py`):
- engine roles, leaks, consistency
- batch go rate
- topic presence
- the add-back line-item distribution, clean vs trap

**Codex layer:**
- `prose.py`: Codex writes prose one call per document. It may write no digits or number words, and a broken paragraph is retried on its own.
- `recover.py`: a positive and a negative probe per fact.

**The command** (`batch.py`):
```bash
uv run python -m acqlab.generator.batch [--out data] [--dev 50] [--test 120] [--hand 10] [--showcase 1] [--seed 0] [--mc 400] [--llm] [--recover N]
```
Exit codes: 0 clean, 1 batch problems, 2 Codex stopped (rerun to resume), 3 generation failed.

**Data room** (`dataroom/tools.py`): `DataRoom(room, budget)`.
- `teaser()` and `list_documents()` are free.
- `search(query)` costs 1 unit and returns the top 5 hits as 150-character snippets.
- `open_document(id)` costs 1 unit per 120-word page.
- The default budget is 35% of the room.
- Every call is logged, over-budget calls are refused, and only indexed ids can be opened.

**Codex adapter** (`llm.py`): `complete(prompt, *, schema=None, run=..., cache_dir=...)`.
- Codex is the CLI bundled with the ChatGPT app, at `/Applications/ChatGPT.app/Contents/Resources/codex`. It is not on PATH; set `CODEX_BIN` to override.
- Each call runs with `--ephemeral` (so calls stay out of the user's Codex history), a read-only sandbox, and an empty temp working directory.
- A failed call raises `LLMUnavailable` and is never cached. Cache writes are atomic.
- Plan 4 adds `claude -p`, the solver sandbox and an API backend behind the same signature.

**Known limitations (parked, with reasons):**
- **Codex can read files.** Its `--sandbox read-only` blocks writes, not reads, so the recoverability extractor could in principle read other files. That's acceptable for the proof of concept, but it must be closed (Plan 4 sandbox) before recoverability gates scored test deals.
- **Decision values are noisy at `--mc 400`** (see the Plan 3 section above).
- **Weak, realistic cues remain:**
  - Flippers' add-back line items run larger than clean ones when compared by role (the overall distributions match).
  - Placement weights make "the QoE defers to the notes" mildly predictive.
  - `search()` snippets can surface a fact's amount cheaply; watch this in the pilot.
- **Wording nits:**
  - The CIM's "renewed on a long-term basis" reads against every contract's "renews annually".
  - The number-word guard rejects "third-party"; drop "third" if Codex fallbacks pile up.
  - One capex claim is ungrammatical for plural labels.
- **Recoverability failures are reported, not regenerated.** Every test deal must pass recoverability before the main benchmark.
- **Plan 1's Task 9 spreadsheet check is still deferred by the user.** The spec lists it as required.
- **Negative `debt_like` / `nwc_adjustment` values are rejected, not modelled.** A favourable surprise can only enter through `ebitda_adjustment`.

## Later plans (after Plan 3)

- **Plan 4 (week 4, ~2026-10-19):**
  - Harden the LLM adapter (`claude -p --output-format json`, API backend).
  - **Sandbox:** every scored call runs from an empty temp dir with file and shell tools disabled, and data-room access only through the budgeted tools. This also closes the Codex read gap above.
  - Baselines: S1a, S1b, S0, the trivial baselines, B0.
  - The 30-deal pilot, which measures variance and **real tokens per run**.
  - The **checkpoint:** S1b vs S1b + router 6.
- **Plan 5 (weeks 4–6):** the S4 framework.
  - Deal Record: blackboard, issue tree, progress ledger.
  - Committer with quoted / computed / contradicted commits.
  - Deal Lead, never shown the trap library.
  - Investigator with intent briefs from `flip_threshold`.
  - Modeler, Challenger, a residual sweep, and the stopping rule.
- **Plan 6 (weeks 6–7):**
  - A resumable benchmark runner and the spec §4 metrics.
  - Paired bootstrap confidence intervals.
  - Core ablations: −Challenger, −engine, −residual sweep.
  - **Pre-register hypotheses H1–H6 before touching the test set, and log prompt-tuning effort equally across systems.**
- **Plan 7 (weeks 7–8):**
  - Demo UI (FastAPI + React): fork chart, router board, evidence viewer, agent timeline.
  - Recorded-trace replay as the primary path.
  - Slides and judge answers.
- **Anytime before slides:** read arXiv:2605.13110 and arXiv:2603.22651 in full and verify every citation.

**Later additions** (from the Plan 2 design):
- a dice-rolled realism batch
- favorable surprises
- sourced trap size ranges
- aggressive-seller archetypes
- messy documents (mixed units, fiscal year ends)
- pinning the Damodaran values against his .xls files

## How this project is worked (conventions and lessons)

**Workflow:**
1. superpowers:brainstorming for anything new.
2. superpowers:writing-plans: one plan per subsystem, in `docs/superpowers/plans/`.
3. superpowers:subagent-driven-development, with a ledger in the git-ignored `.superpowers/sdd/<plan>/`. The workspace is deleted when the plan finishes; git history is the record.
4. superpowers:finishing-a-development-branch. So far: squash-merge to `main` with the Opus trailer, keeping the feature branch for its full history.

**Plan style:** complete code in every step, TDD, and exact expected test counts. **Pre-verify every plan by running its code in a scratch copy, then rebuild the plan from its own text on a fresh `main` and run the suite.** For Plan 2, that caught:
- an engine bug (`flip_threshold` with reversed bounds)
- a biased case mix
- an all-zero decision-value prior
- digits in prose templates

**Lessons from Plan 2:**
- **Per-task reviews can't see cross-document leaks.** The Opus final review found two answer leaks that pre-verification and nine task reviews missed:
  - a clean add-back's CIM line item was always 40% of the total
  - the seller's claim appeared mostly for clean facts

  It found them by **measuring role-dependence statistically** over a generated batch. For any plan that generates or scores data, include that measurement as a step, and run the final review on Opus.
- **Controller fidelity check:** after each transcription task, diff the committed files against the verified scratch copy. It's cheap, and it confirms the implementer copied exactly.
- **Plan-mandated review findings were worth fixing.** Reviewers flagged duplicated evidence code, missing negative tests for validators, a Codex timeout that escaped as a crash, and a non-numeric JSON crash. All four were real.

**Commits and subagents:**
- **Commits** end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Tell subagents this explicitly, because Haiku subagents default to their own name.
- **Model choice:** Haiku for transcription tasks when the plan has complete code; Sonnet for task reviews; Opus for final reviews and judgment-heavy fix waves. Always set the model explicitly.
- **Tell every subagent:**
  - never modify settings or permissions files
  - if a git operation is blocked, stop and report
  - never make a real LLM/Codex call unless the user approved it

**Other rules:**
- **Ponytail mode** is active: minimal code, stdlib first, no speculative abstractions.
- **Never put ground-truth files anywhere a solver sandbox could read them.**
- **Real Codex calls use the user's ChatGPT subscription quota.** Ask before running any, and size runs to fit a usage window. Batches are resumable (exit code 2, then rerun).

## Git state

```
main               4a113ba spec → 6b34612 Plan 1 (squash) → eb6a3ee Plan 2 (squash); 130 tests
plan-1-lbo-engine  full Plan 1 history
plan-2-generator   full Plan 2 history
claude/plan-1-implementation-review-727227  finished review branch (kept)
```

The Plan 2 worktree (`.claude/worktrees/plan-1-implementation-review-727227`) is managed by the Claude app and can be removed from there. No git remote is configured.
