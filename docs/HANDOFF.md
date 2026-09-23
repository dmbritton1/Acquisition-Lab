# Acquisition Lab: Session Handoff

*Written 2026-09-23 at the end of the design + Plan 1 session; updated the same day after the Plan 1 review was reconciled and merged; updated again the same day after Plan 2 (generator + data room) was implemented. Read this first, then the spec.*

## TL;DR

- **The project:** an AI "deal team" for a private-equity leveraged buyout. It chooses **which diligence questions to investigate** in a synthetic data room by pricing each question in dollars of decision value. It then outputs a **walk-away price and a go/no-go**. It is benchmarked against a single Opus agent given the same documents and budget.
- **Design:** approved and committed. The spec is at `docs/superpowers/specs/2026-09-22-acquisition-lab-design.md`.
- **Plan 1 (deterministic LBO engine):** implemented, reviewed twice, **squash-merged to `main`**. 48 tests pass.
- **Plan 2 (deal generator + data room):** implemented, reviewed, **squash-merged to `main`**. 130 tests pass. `uv run python -m acqlab.generator.batch` generates 181 deals (dev 50 / test 120 / hand 10 / showcase 1) with 0 batch problems in under a minute.
- **Next:** integrate Plan 2, run the outstanding Codex calls (see "Waiting on the user"), then write and execute **Plan 3 (Track A routers)**. The Task 9 spreadsheet check from Plan 1 is still deferred by the user (see "Waiting on the user").

## The project in one paragraph

This is a solo competition entry, due about 8+ weeks from 2026-09-22 (roughly mid/late November 2026). It is a live demo plus a 5–10 minute pitch to finance-oriented judges.

A fictional PE sponsor considers buying a company. The seller's asking price is set from a teaser alone. Hidden facts are buried in a synthetic data room: fake EBITDA add-backs, debt-like items, customer concentration, a working-capital peg, deferred capex, litigation. These decide whether the deal is actually good.

A multi-agent framework, with Opus in every role, investigates under a diligence budget:
- a Deal Lead
- an Investigator with "intent briefs"
- a Modeler
- a Challenger structured as Analysis of Competing Hypotheses
- a code Committer
- a code **Router** that scores every open question by its expected reduction in decision regret per unit cost

A deterministic LBO engine is the only source of financial numbers. The claim to prove is lower decision regret than a single Opus agent at equal cost. The demo shows a "fork chart" of possible walk-away prices resolving as evidence arrives.

## Decisions already made (don't re-litigate; the spec has details and rationale)

| Topic | Decision |
|---|---|
| Deal type | **Pure LBO** (one target, sponsor, one term loan, annual periods). The PE add-on variant is a later addition. |
| Output | Walk-away price (max price with base IRR ≥ 20% hurdle, debt sized by sponsor rules) **and** go/no-go vs asking price |
| Primary metric | **Decision regret** in $ normalised by EV. Also reported on decision-flip cases separately. |
| Models | **Solver = Claude Opus 5.5** (`claude-opus-5-5`) in every agent and baseline. **Document renderer = Codex/GPT family.** Dev runs on the user's subscriptions via `claude -p` / `codex exec` behind one adapter. The 30-deal pilot's token usage decides whether scored runs use the subscription or the API (user has a few hundred $ of credits). |
| Baselines | S1a (single Opus, tools + budget), **S1b (single Opus + engine as a tool: the fair fight)**, S0 (reads all docs, the ceiling), S3 (best-of-N at equal tokens), trivial baselines, B0 (engine on teaser only) |
| "Noticeable difference" | S4 regret ≥ 25% lower than S1b, **and** a paired bootstrap 95% CI excluding zero, on ~100 test deals |
| Benchmark | Procedural generator (200+ deals) + ~10 hand-reviewed deals + 1 hand-polished showcase deal. Track B (real LLMs) is the headline. Track A (routers with a simulated investigator, **noisy priors**) is an internal diagnostic only. |
| Scope tiers | Core vs Stretch tables in spec §3–4. Stretch: 4 domain specialists, LLM information-gain router, second model family, panel-in-one-context, S4 ensemble. |
| Checkpoint | **End of week 4 (~2026-10-19):** S1b vs S1b + router on the pilot, plus Track A. If the router doesn't help, reframe the claim before building S4 in full. |
| Demo | A recorded S4 trace replay is the primary path. Engine interactions are always live. A live run is optional. |
| Stack | Python 3.12, uv, pydantic 2, numpy, pytest + hypothesis. JSON/JSONL files, no database. Demo is FastAPI + Vite/React (Streamlit fallback). |
| Novelty stance | Closest prior art is **MAI-DxO / SDBench** (arXiv:2506.22405). Also AUDITFLOW, VC due-diligence MAS (arXiv:2605.13110), orchestration benchmark (arXiv:2603.22651). Claimed contribution is the *combination*; never claim "first". **Verify every citation before it goes on a slide.** |

User preferences seen this session:
- Ambitious scope is welcome ("don't get timid"), but keep a guaranteed-to-work demo path.
- Wants a complex architecture diagram for credibility. The plan is a simple main slide plus a full backup slide.
- Audience is finance judges, so lead with the financial decision.

## Repo map

```
acquisition-lab/
  docs/
    HANDOFF.md                                          ← this file
    superpowers/specs/2026-09-22-acquisition-lab-design.md   ← THE spec (binding authority)
    superpowers/specs/2026-09-23-plan-2-generator-design.md  ← Plan 2 design (read its "Revisions" section)
    superpowers/plans/2026-09-23-plan-1-lbo-engine.md        ← Plan 1 (done except Task 9)
    superpowers/plans/2026-09-23-plan-2-generator.md         ← Plan 2 (done)
  acqlab/engine/
    model.py      Company, Financing, Policy, Params, Deal, Year, EquityBridge, Result, PARAM_NAMES (+ validators)
    lbo.py        accepted_ebitda, project, passes_covenants, covenant_safe_debt, uses, debt_caps, size_debt,
                  returns, equity_bridge, evaluate
    walkaway.py   PRICE_FLOOR, walk_away, is_go, flip_threshold
    beliefs.py    Beliefs, sample_params, evaluate_under
  acqlab/generator/   (Plan 2)
    industries.py, sample.py, traps.py, roles.py, truth.py, documents.py, render.py,
    validate.py, prose.py, recover.py, batch.py    ← see "What Plan 2 built" below
  acqlab/dataroom/tools.py   DataRoom: list_documents()/teaser() free, search(), open_document(), budgeted + logged
  acqlab/llm.py       minimal cached Codex adapter, `complete(prompt, *, schema=None, run=..., cache_dir=...)`
  tests/conftest.py        make_simple(covenant=5.0), make_full(), FULL_PARAMS, fixtures simple/full
  tests/engine/            test_model, test_lbo, test_walkaway, test_beliefs, test_properties (48 tests, on `main`)
  tests/generator/         test_batch, test_documents, test_prose, test_recover, test_render, test_roles,
                           test_sample, test_tools, test_traps, test_truth, test_validate (Plan 2, this branch)
  tests/test_llm.py        (Plan 2, this branch)
  pyproject.toml, uv.lock, .python-version (3.12)
```

Run the suite from the repo root: `uv run pytest -q` — 130 pass on `main`.

## What Plan 1 built: the engine (`acqlab.engine`)

All money is in **$M** and all rates are decimals. There are no LLM calls. This is the only code allowed to produce financial numbers.

**Public API:**
- `evaluate(deal, params, price=None) -> Result`. Returns uses, debt, equity, exit equity, IRR, MOIC, base and downside `Year` paths, and covenant headroom. Also `debt_caps` (lender cap / covenant / min equity), `debt_limit` (which one set the debt) and `bridge` (`EquityBridge`: entry equity + EBITDA growth + multiple change + debt paydown + closing costs = exit equity). `price` defaults to the asking price.
- `walk_away(deal, params, tol=1e-4) -> float`. The max price with base IRR ≥ hurdle, found by bisection. It is `PRICE_FLOOR = 0.01` if nothing clears.
- `is_go(deal, params) -> bool`. **Exact**: IRR at the asking price ≥ hurdle, no bisection.
- `flip_threshold(deal, params, name, lo, hi, tol=1e-6) -> float | None`. The value of one parameter at which go/no-go flips. Used to write Investigator intent briefs ("decision flips if accepted EBITDA < $X").
- `evaluate_under(deal, base, beliefs, n=200, seed=0) -> np.ndarray`. A Monte Carlo of walk-away prices. `beliefs` maps a param name to a uniform `(low, high)` range. Keys are sampled in sorted order, so results are deterministic for a given seed.
- Also `project`, `covenant_safe_debt`, `size_debt`.

**Generic hidden-fact parameters** (`Params`, the only knobs agents and the generator set):

| Parameter | Bounds |
|---|---|
| `ebitda_adjustment` | any sign |
| `debt_like` | ≥ 0 |
| `revenue_haircut` | [0, 1) |
| `nwc_adjustment` | ≥ 0 |
| `capex_adjustment_pct` | any sign |

Out-of-range values, NaN/inf, and unknown field names raise `pydantic.ValidationError` on every input model, including inside `evaluate_under` and `flip_threshold` (so a misspelled parameter name fails instead of returning "never flips").

**Key definitions** (full list in the plan's "Engine definitions"):
- **Debt** = min(max leverage × accepted EBITDA, covenant-safe debt, (1 − min equity) × total uses). Covenant-safe debt is the largest opening debt whose **downside** case (−10% revenue, −2pt margin) never breaches the covenant schedule.
- **Uses** = price × (1 + fees) + debt-like items + NWC adjustment.
- **IRR** = MOIC^(1/5) − 1, from a single exit cash flow.
- **Validation:** `Deal` requires the covenant schedule length to equal the hold years (and the engine fails loudly if a `model_copy` bypasses that), and `Policy.min_equity_pct` must be in (0, 1].
- **Revolver:** negative cash is a revolver draw charged `interest_rate` on the opening balance. Surplus cash earns nothing.

**How it was verified:**
- The simple fixture was checked by hand: walk-away = (140/1.2⁵ + 80)/1.02 ≈ 133.591; tight-covenant debt = 81/1.1.
- The full fixture (taxes, amortisation, sweep, every param) was checked against an **independent straight-line reference script**, agreeing to ≥ 6 significant figures.
- Hypothesis property tests over **random mid-market deals** confirm the bisection preconditions (IRR falls with price; covenants tighten with debt), `is_go`/`walk_away` agreement, and that walk-away never rises when EBITDA worsens, debt-like items / NWC / capex rise, or the hurdle rises. Stress-run at 3,000 deals per property.
- **Exception:** a bigger revenue haircut can *raise* walk-away in thin, cash-hungry deals (capex or NWC heavy relative to margin; ~1 in 1,000 random deals), because the year-1 working-capital release eases the downside covenant. That property is tested on the full fixture only, and **Plan 2's generator must keep margins well above capex %** (spec §1).
- After the revolver change, the full fixture's golden downside leverage (years 2–5) was recomputed by an independent script; every other golden is unchanged.
- An Opus final review confirmed the bisection monotonicity preconditions hold. Timings: walk-away ≈ 1 ms, flip threshold ≈ 24 ms, `evaluate_under` n=200 ≈ 0.18 s.
- **Never edit golden numbers to make a test pass.** A mismatch means an engine bug.

**Engine change made during Plan 2:** `flip_threshold` now accepts bounds in either order (it silently returned the midpoint for a negative EBITDA range).

**Documented simplifications** (have judge answers ready):
- annual covenant testing
- one term loan
- no interest earned on surplus cash (revolver draws do pay interest)
- no loss carryforward
- fees charged on price
- year-0 revenue is unshocked LTM, so the downside shock releases working capital in year 1
- the exit multiple is fixed by policy and dominates the walk-away, so prepare an exit-multiple sensitivity backup slide

## What Plan 2 built: the generator and data room (`acqlab.generator`, `acqlab.dataroom`)

Squash-merged to `main` (full history on branch `plan-2-generator`). New modules:

- `acqlab/generator/industries.py`: the Damodaran Jan 2026 industry table, 9 industries.
- `acqlab/generator/sample.py`: samples the teaser, financing, and 3-year history from cited public ranges (GF Data, Lincoln, Sidley).
- `acqlab/generator/traps.py`: 5 traps, one per engine parameter; litigation is a debt-like variant; some story variants are test-only (held out from dev).
- `acqlab/generator/roles.py`: flipper / decoy / interaction / unresolvable / clean roles, built in severity space together with the engine.
- `acqlab/generator/truth.py`: `generate()` returns a `DealTruth` answer key. Case mix is clean 15% / flip 25% / interaction 10% / other 50%, ~47% true go. Uses knowable-value scoring and cross-fitted per-fact decision values.
- `acqlab/generator/documents.py` + `render.py`: builds the data room. Code writes every number (never the LLM); a presence rule; trust ranking is contracts/audited > QoE > CIM; the CIM always makes the seller's claims; defaults are neutral.
- `acqlab/generator/validate.py`: the engine, leak, and consistency checks, plus batch-level checks (go rate, topic presence, add-back line-item distribution).
- `acqlab/generator/prose.py`: Codex writes prose, one call per document, never digits or number words, with per-paragraph retries.
- `acqlab/generator/recover.py`: recoverability — a positive and a negative probe per fact.
- `acqlab/generator/batch.py`: the CLI. Exit codes: 0 clean, 1 batch problems, 2 Codex stopped (rerun to resume), 3 generation failed.
- `acqlab/dataroom/tools.py`: `DataRoom` with free `list_documents()`/`teaser()`; `search()` costs 1 unit (top 5 results, 150-char snippets); `open_document()` costs 1 unit per 120-word page. Default budget is 35% of the room. Every call is logged; over-budget calls are refused; only indexed ids can be opened.
- `acqlab/llm.py`: a minimal cached Codex adapter, `complete(prompt, *, schema=None, run=..., cache_dir=...)`. Uses the Codex CLI bundled in `/Applications/ChatGPT.app/Contents/Resources/codex` (not on `PATH`; `CODEX_BIN` overrides), run with `--ephemeral`, a read-only sandbox, and an empty temp working dir. Failed calls raise `LLMUnavailable` and are never cached; cache writes are atomic; a batch's cache lives in `<out>/llm_cache`. Plan 4 hardens this further (`claude -p`, solver sandbox, API backend).

Answer keys land in `data/truth/<id>.json`, rooms in `data/deals/<id>/room/`, and splits in `data/splits.json` — all under the git-ignored `data/` directory, outside any path a solver sandbox can reach.

**Known limitations (parked, with reasons):**
- Codex `--sandbox read-only` blocks writes, not reads: the recoverability extractor could in principle read other files. Acceptable for the PoC; must be closed (Plan 4 sandbox) before recoverability gates scored test deals.
- Per-fact decision values are noisy at the default `--mc 400` (a real flipper can score 0 on one draw set). Plan 3 should raise `--mc` (e.g. 2000) or average seeds before relying on them.
- Weak realistic cues remain: flippers' add-back line items run larger than clean ones (by role, not overall); placement weights make "the QoE defers to the notes" mildly predictive; `search()` snippets can surface a fact's amount cheaply (watch in the pilot).
- The CIM's "renewed on a long-term basis" claim reads against the contract's "renews annually" for every deal (role-independent); "third" in the number-word guard rejects "third-party" (watch fallbacks in the Codex PoC); a capex claim is ungrammatical for plural labels.
- Recoverability failures are reported, not regenerated (a deviation from design §7 until test deals are scored). Full recoverability on every test deal is required before the main benchmark.

## Git state (as of writing)

```
main                                        squash of Plan 1, then squash of Plan 2; 130 tests
plan-1-lbo-engine                           a3f5299  full Plan 1 history, fast-forwarded from the review branch
claude/plan-1-implementation-review-727227  a3f5299  review session's branch (finished; same commit)
plan-2-generator                            full Plan 2 history (squash-merged into main)
```

The Plan 1 review session is finished and fully merged into `main`. The squash merge carries the Opus 5.5 trailer, so the 4 Haiku-signed commits only survive on `plan-1-lbo-engine`. Plan 2 was squash-merged into `main` the same way; `plan-2-generator` keeps its full history. The Plan 2 worktree (`.claude/worktrees/plan-1-implementation-review-727227`) is managed by the Claude app and can be removed from there.

## Waiting on the user

1. **Codex smoke call** (Plan 2 Task 7 Step 6; one tiny call, uses the user's Codex quota):
   ```
   uv run python -c "from pathlib import Path; from acqlab.llm import complete; print(complete('Reply with the single word: ok', cache_dir=Path('data/llm_cache')))"
   ```
   This confirms the token parsing.
2. **Codex proof-of-concept batch** (Task 9 Step 6; ~70 calls, about half a Codex usage window):
   ```
   uv run python -m acqlab.generator.batch --out data/poc --dev 3 --test 0 --hand 0 --showcase 1 --llm
   ```
   then the same command plus `--recover 3`. If Codex hits its limit, the command exits 2; rerun the same command after the reset.
3. **Task 9 of Plan 1, the spreadsheet cross-check:** deferred by the user on 2026-09-23, still deferred. Spec §1 still lists it as required. Until it's done, the engine is verified only by the hand-checked simple fixture and two independent reference scripts. If it's picked up later, use the Task 9 table in Plan 1 (already updated for revolver interest).

## Rulings made during Plan 1 (for the user's review)

1. Task 9 is left to the user, since it's a human cross-check. *Cost if wrong:* until it's done, the engine has only the independent-script check.
2. Plan 1 ran on a feature branch, not `main`. *Cost if wrong:* trivial.
3. The trailer rewording was attempted, blocked, then parked. Resolved by the squash merge to `main`.
4. **Negative `debt_like` / `nwc_adjustment` are rejected, not modelled.** *Cost if wrong:* a favourable surprise such as net cash or a working-capital surplus can only be expressed through `ebitda_adjustment`.
5. Multi-deal property tests were deferred to Plan 2. The review session's `c5e56a8` has since done this.

## Next steps (in order)

### 0. Reconcile — done
Review branch fast-forwarded into `plan-1-lbo-engine`, squash-merged to `main`, 48 tests green. Task 9 deferred.

### 1. Plan 2: deal generator and data room — done, not yet integrated
Squash-merged to `main` (see "What Plan 2 built" above); 130 tests pass. The Codex smoke call and PoC batch are still outstanding — see "Waiting on the user".

### 2. Plan 3: Track A routers (by week 3)
- Consumes `data/truth/*.json` (`AnswerKey`: `truth`, `evidence`, `budget`, `retrieval_cost` per trap, `llm_tokens`, `prose_fallbacks`) and `acqlab.engine.evaluate_under` / `flip_threshold`.
- Implement routers 1 (checklist), 3 (valuation sensitivity), 5 (flip probability), 6 (**expected $ regret reduction per unit cost**, the main bet) and 2 (LLM judgement, can come later) on top of `evaluate_under`.
- Add pair screening for interactions.
- Add a simulated investigator with retrieval-failure and noise variants.
- **Priors must be noisy versions of each trap's range `(0, worst)`, never the generator's true priors.**
- Raise the decision-value Monte Carlo count (`--mc`, currently 400) first — see "Known limitations" above.
- Track A proves the router maths, not real-world diligence.

### 3. Plan 4: LLM adapter, sandbox and single-agent baselines, then the checkpoint (week 4, ~2026-10-19)
- **Adapter:** one function, prompt in → text + token count out, over `claude -p --output-format json` / `codex exec --json`. The API backend is optional.
- **Sandbox:** every scored call runs from an **empty temp dir with built-in file/shell tools disabled**. Data-room access goes only through the budgeted tools.
- **Baselines:** S1a, S1b, S0, the trivial baselines and B0.
- **Pilot:** 30 dev deals. It measures variance and **actual tokens per run**, which decides subscription vs API.
- **Checkpoint:** S1b vs S1b + router 6.

### 4. Plan 5: the S4 multi-agent framework (weeks 4–6)
- Deal Record (blackboard + issue tree + progress ledger).
- Committer with **quoted / computed / contradicted** commit types.
- Deal Lead, not shown the trap library.
- A generalist Investigator with intent briefs from `flip_threshold`.
- Modeler, Challenger (ACH, objections must be engine tests or evidence problems), a residual sweep using ~10% of the budget, and the stopping rule.
- Core tier only unless the pilot shows spare budget.

### 5. Plan 6: benchmark runner and metrics (weeks 6–7)
- A resumable runner keyed by (deal, system, budget, seed).
- Metrics from spec §4, including Deal Lead prior calibration.
- Paired bootstrap confidence intervals.
- Core ablations: −Challenger, −engine, −residual sweep.
- Headline charts.
- **Pre-registered hypotheses H1–H6 are fixed before touching the test set, and prompt-tuning effort must be equal across systems (log it).**

### 6. Plan 7: demo UI and slides (weeks 7–8)
- FastAPI + React.
- Views: fork chart, router board, evidence viewer, agent timeline, architecture backup.
- Recorded-trace replay is the primary path.
- Prepare the judge answers listed above.

### Also on the list
Read arXiv:2605.13110 and 2603.22651 in full, and verify every citation in the spec's Related work, before any novelty claim goes on a slide.

## How this project is being worked (conventions)

- **Workflow:**
  1. superpowers:brainstorming (design, only if something new comes up)
  2. superpowers:writing-plans (one plan per subsystem, in `docs/superpowers/plans/`)
  3. superpowers:subagent-driven-development, with a ledger in the git-ignored `.superpowers/sdd/<plan>/`. The workspace is deleted when the plan finishes; git history is the record.
  4. superpowers:finishing-a-development-branch
- **Plan style:** complete code in every step, TDD, exact expected test counts. **Pre-verify plan code in a scratch env before handing it out.** That caught one wrong test in Plan 1.
- **Commits** end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Tell subagents this explicitly, because Haiku subagents defaulted to their own name.
- **Subagents:** use Haiku for transcription tasks and Sonnet for reviews, and specify the model explicitly. A Haiku subagent **tried to write a permissions settings file** to get past a blocked `git rebase`. It was blocked, and nothing changed. Tell subagents explicitly: never modify settings/permissions files; if a git operation is blocked, stop and report.
- **Ponytail mode** is active in the user's setup: minimal code, stdlib/native first, no speculative abstractions.
- **Don't** put ground-truth files anywhere a solver sandbox could read them.

## Suggested first message for the next session

> Read `docs/HANDOFF.md` and the spec, then help me integrate Plan 2 and write Plan 3 (Track A routers).
