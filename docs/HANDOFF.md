# Acquisition Lab: Session Handoff

*Last updated 2026-09-24, after Plan 3 (Track A routers) was built and run. Read this first, then the spec it points to. The spec is the binding authority on design; this file is the source of truth for status and next steps.*

## Start here

**Where things stand:** Plans 1 (LBO engine), 2 (deal generator and data room) and 3 (Track A routers) are built. 159 tests pass (`uv run pytest -q`). Plan 3 lives on branch `plan-3-track-a`; its final Opus review is done and its findings fixed, so it is ready to merge. The week-4 checkpoint (about 2026-10-19) is next, and **Track A's H2 verdict below is an input to it**.

**Do these in order:**

1. **Regenerate the deals in this checkout** (`data/` is git-ignored; about 30 s, no LLM):
   ```bash
   uv run python -m acqlab.generator.batch
   ```
   Expect `generated 181 deals into data; 0 batch problems`. The Track A batch (`data/track_a`, 2,000 deals, about 5 min) and its results are only needed to re-check Plan 3.
2. **Finish the Codex recoverability check** (with the user's OK; it uses their ChatGPT Codex quota). The smoke call and the prose run are done; see "Codex status" below. Rerun:
   ```bash
   uv run python -m acqlab.generator.batch --out data/poc --dev 3 --test 0 --hand 0 --showcase 1 --llm --recover 3
   ```
   It pays only for the 19 calls that didn't run plus 4 reworded concentration questions (all prose replies are cached). Exit code 2 means the usage limit hit again: rerun after it resets.
3. **Decide the week-4 checkpoint framing with the user**, using the Track A results below (spec §4: "if the router doesn't help, reframe the claim before building S4 in full").
4. **Plan 4** (brainstorm, then write): LLM adapter hardening (`claude -p`, API backend), the solver sandbox, baselines S1a/S1b/S0/trivial/B0, router 2, the 30-deal pilot, and the S1b vs S1b + router 6 checkpoint.

**Suggested first message for the next session:**

> Read `docs/HANDOFF.md` and the spec, regenerate the deals, then help me decide the week-4 checkpoint framing from the Track A results and brainstorm Plan 4.

## Codex status (Plan 2 proof of concept)

- **Smoke call (2026-09-23):** returned `('ok', 19648)`. Token parsing works, but nearly all of those tokens are the Codex CLI's own built-in instructions: every call carries about 20k tokens of overhead. Plan 4 needs this number (spec §4: token overhead must be comparable across systems, or scored runs use the API).
- **Prose run (2026-09-23):** 4 deals, 0 batch problems, 0 prose fallbacks, 31 calls, about 200k tokens per deal (184k–225k). Codex mostly splits the template sentences, so it adds little realism; loosening the prose prompt is a cheap later improvement.
- **Recoverability (`--recover 3`), half done:** Codex hit the usage limit after 21 of 40 calls; 20 of the 21 passed. The one failure was a question problem (it asked about "the largest customer", which the contract never says) and is fixed. Finish it with step 2 above.

## Plan 3 results: Track A (2026-09-24)

Spec: `docs/superpowers/specs/2026-09-23-plan-3-track-a-design.md` (§7 has the pre-verification revisions). Plan: `docs/superpowers/plans/2026-09-23-plan-3-track-a.md`. Code: `acqlab/routers/` (`beliefs.py`, `routers.py`, `track_a.py`).

**What was run:** 2,000 separate Track A deals (`--seed 200000`, never the benchmark splits), 189,000 runs, no skipped deals, 2 h 23 min on this laptop:
- **headline:** 7 routers × perfect investigator × medium priors × budgets 25/50/100% of default × truth {generator, self}, on 2,000 deals.
- **full:** × investigators {perfect, failure, noisy} × prior levels {low, medium, high}, on the first 500 answer keys sorted by filename (dev-000 … dev-1362). Its perfect/medium cells reuse the headline rows for those 500 deals.
- **hints:** clue 0.7 and 0.9 (a "what if" study that uses the answer key), on the same 500.

**Every cell, with CIs: `docs/results/2026-09-24-track-a.md`** (all four slices; means for routers 3, 5, 6, checklist, random and oracle; 6−3, 6−5, 6−random and 6−checklist with 95% CIs and win/loss flags; generated from the summaries by `uv run python docs/results/track_a_table.py`). Raw data (git-ignored): `data/track_a/{headline,full,hints}.txt`, `summary_<grid>.json`, `read_rates.txt`, `results.jsonl`. Rerun a grid with `uv run python -m acqlab.routers.track_a --deals data/track_a --grid <grid> --workers 8`; it resumes, so on the existing rows it only re-summarises (a few seconds).

**Headline, mean regret ÷ asking price (lower is better), generator truth, 2,000 deals:**

| Budget | random | checklist | 5 flip | 3 sensitivity | 6 regret/page | 6 + veto | oracle |
|---|---|---|---|---|---|---|---|
| 25% | 0.0234 | 0.0224 | 0.0224 | 0.0222 | 0.0223 | 0.0221 | 0.0137 |
| 50% | 0.0179 | 0.0147 | 0.0147 | 0.0141 | 0.0136 | 0.0144 | 0.0026 |
| 100% | 0.0064 | 0.0038 | 0.0042 | 0.0033 | 0.0034 | 0.0048 | 0.0001 |

**Fair game (true values drawn from the routers' own priors), 2,000 deals:** at 50%: random 0.0115, checklist 0.0090, 5 0.0083, 3 0.0067, 6 0.0068, oracle 0.0013. Router 6 beats random and checklist at every budget (at 50%: −0.0047 [−0.0065, −0.0032] and −0.0022 [−0.0034, −0.0012]). **The router math is confirmed: when beliefs are right, computed routing beats random and checklist reading.**

**H2 verdict (pre-registered rule: lower mean and paired bootstrap 95% CI excluding zero, per cell). Counts are over all four slices:**
- **Router 6 vs router 3: not supported.** Headline: no win in any cell on either truth (generator 50%: −0.0005 [−0.0013, +0.0003]; decoy −0.0003 [−0.0019, +0.0010]; interaction −0.0005 [−0.0023, +0.0011]). One cell goes the other way: in the fair game at 25%, router 3 is significantly better, +0.00014 [+0.00001, +0.00029], but only 11 of 2,000 deals differ, so it is fragile. Full grid: 13 wins of 108 cells (4 of 27 on the all slice), 12 of them at the 50% budget, and 3 losses: failure investigator, medium priors, 100% budget, on all (+0.0020 [+0.0007, +0.0036]), flip and decoy. Hints: no wins, no losses. **The full-grid wins do not replicate** because they come from one 500-deal subset: on those 500 deals, the headline 50% cell gives 6 − 3 = −0.0022 [−0.0041, −0.0006]; on the other 1,500 it gives +0.00006 [−0.0008, +0.0009]. The full grid reuses those same deals and priors in every cell, so one fluctuation repeats across correlated cells.
- **Router 6 vs router 5: partly supported.** Headline generator truth: wins at 100% on all, flip and decoy (all: −0.0008 [−0.0015, −0.0002]); not at 25% or 50%, not on interaction deals. Fair game: wins at 50% and 100% (all and flip), not at 25%. Full grid: 17 wins of 108 (6 of 27 on the all slice). Hints: 1 win of 24. No losses anywhere.
- **Router 6 vs checklist:** no win on generator truth at any budget (25%: −0.00003 [−0.0007, +0.0006]; 50%: −0.0011 [−0.0023, +0.00003]; 100%: −0.0004 [−0.0011, +0.0002]). Fair game: wins at every budget on the all slice (5 of 6 cells). Full grid: 6 wins and 3 losses of 108. Hints: at clue 0.9 and 50%, a win (−0.0016 [−0.0029, −0.0003]); losses on flip deals at 25% for both clues.
- **Router 6 vs random:** wins at every budget on generator truth (all slice; at 25% only just: −0.0010 [−0.0021, −0.00003]), 8 of 12 headline cells; all 6 fair-game cells. Full grid: 31 wins and 2 losses of 108; the losses are interaction deals at 50% (perfect and noisy investigators, medium priors: for perfect, +0.0067 [+0.0008, +0.0136]). Hints: 3 wins and 1 loss (interaction deals, clue 0.9, 50%: +0.0067 [+0.0013, +0.0139]). The matching 2,000-deal headline interaction cell is −0.0004 [−0.0060, +0.0051], so these losses sit on the same 500 deals.
- **Why 6 ties 3 (measured, not the flat costs):** at step 0 (50% budget, medium priors, first 300 deals), the two routers' first picks agree in only 62% of deals, and scoring router 6 with flat costs changes its pick in only 9%, so dividing by page cost is not what makes them alike. A fresh set of 400 worlds changes router 6's first pick in 15% of deals (13–18% over five fresh sets) and router 3's in 12% (10–13%): both scores are noisy at N_WORLDS = 400. In the headline results at 50%, the two read in a different order in 44.5% of deals but end with a different regret in only 4.8%: most differing reads don't change the final decision.
- **Why every router is close to random on generator truth at 25%:** that budget buys about one fact (router 6 reads 1.14 facts, 1.24 pages), and the priors carry no deal-specific clue about which issue is real; the clue lives in the documents (Track B).

**Other results:**
- **Hints study ("what if"):** with strong hints (0.9) at 50%, routers 3/5/6 reach 0.0061/0.0064/0.0066 against checklist 0.0082 and random 0.0117, so routing pays once the reader supplies clues. Router 6 still ties 3 and 5. At clue 0.7 router 6's only all-slice win is against random at 50%. The hint update overstates hints (see limitations).
- **"6 + veto"** (stop routing below 0.25% of asking price per page) is worse than router 6 at 50% and 100% (0.0144 vs 0.0136; 0.0048 vs 0.0034). It does not stop spending: after routing stops, the sweep spends the rest of the budget cheapest-first (spec §4, "the sweep still runs"). At 50% the veto row spends 3.01 pages against 3.21 for router 6 and reads more facts (2.21 vs 2.16). So the row measures "router 6, then cheapest-first", not budget stewardship. For the later veto work, turn the sweep off for vetoed budget, or report pages saved.
- **Prior calibration** (share of real problems inside the prior range, full grid): low 0.88, medium 0.83, high 0.74. **Sweep:** finds a forgotten problem in 4.4% (headline) to 4.5% (full, hints) of non-oracle runs.
- **Read rates** (generator truth, medium priors, 50% budget; 984 decision-flip deals): router 6 reads a decision-relevant fact in 595, router 3 in 618, checklist 581, random 494. The oracle reads one in only 283, because the prior decision is often already right and it prefers the cheapest set of reads on ties.

**Implication for the checkpoint:** on generator truth (headline), router 6 beats random reading, but not checklist and not router 3; it beats router 5 only at the 100% budget. It beats checklist consistently only in the fair game, where beliefs are right (and with strong hints at 50%). It does not beat router 3 robustly anywhere. So Track A supports "an engine-computed router beats random reading, and beats a checklist when beliefs are right", not "router 6 beats valuation sensitivity". If H2 matters to the pitch, the levers are more worlds per score (raise N_WORLDS, or average scores over seeds) alongside more varied costs (bigger data rooms). The cheapest test, not yet run: the fair-game 50% cell on 500 deals with N_WORLDS = 2000. Otherwise reframe around routers 3/6 jointly versus LLM judgement (router 2) and S1b.

**Known limitations of Track A:**
- **Retrieval cost reveals the role:** for addback, debt_like, nwc and capex, a cost of 3 pages or more always means a non-clean fact (219 of 2,000 deals), because only non-clean facts get the "contradicted" placement. No Track A router exploits it (router 6 divides by cost, so it leans away). Fix or control for it before giving any other router costs (for example router 2 in Plan 4).
- **Seed-stream collision (parked):** numpy seeds `[s, lvl]` and `[s, lvl, 0]` give the same stream, so the priors and the step-0 worlds share a stream; at "low" they also equal the generator's `default_rng(seed)`, at "medium" the renderer's `[seed, 1]`. Measured no leak. Fix with distinct nonzero seed tags before any re-run (it changes every result).
- **The hint update is not Bayes:** it multiplies p by the likelihood ratio instead of the odds, so a "real" hint at clue 0.9 on p = 0.30 gives 0.95 (the clip) instead of 0.79. This affects only how the hints study reads (spec §7).
- **"First 500 deals"** means the first 500 answer keys sorted by filename (dev-000 … dev-1362), not dev-000 to dev-499. Harmless.

**Deviations recorded in the spec:** router 2 moved to Plan 4; the veto is a single "6 + veto" row; budgets are 25/50/100% of default; a fair-game truth mode and a hints study were added (user decisions, spec §7).

## Findings from the handoff review still relevant (2026-09-23, 800-deal batch)

- **The default budget barely binds, and costs are flat.** The non-filler room is about 11 pages; the default budget (about 7) covers every evidence document in 86% of deals. The pilot must re-check room size for Track B.
- **Decision-flip cases are `go != face_go`, not `case_type == "flip"`.** 51% of deals flip versus face value, and 30% of those have `case_type == "unresolvable"`. Use `go != face_go` for every "decision-flip cases" metric; use per-fact roles for decoy and interaction metrics.
- **Regret normaliser:** "EV" in spec §4 means **asking price**, everywhere.
- **Leak audit: clean.** Neither the teaser, `list_documents` (titles, domains, page counts), nor any non-evidence text predicts a fact's role; the only cues are the realistic ones (the add-back gap, and a thin face-value margin predicting flips).
- **Answer keys and units:** load with `AnswerKey.model_validate_json(path.read_text())` (`acqlab/generator/batch.py`). Facts are in $M; always convert with `acqlab.generator.traps.params_for(amounts, truth.base)` (it takes the generator's `BaseDeal`, not the engine `Deal`).
- **Decision-value noise:** a fact's stored `decision_value` (at `--mc 400`) is noisy; raise `--mc` or average over seeds before comparing against it.

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
    superpowers/specs/2026-09-23-plan-3-track-a-design.md   ← Plan 3 design; read §7
    superpowers/plans/2026-09-23-plan-3-track-a.md          ← Plan 3 (done; results above)
  acqlab/engine/      model.py, lbo.py, walkaway.py, beliefs.py         (Plan 1)
  acqlab/generator/   industries.py, sample.py, traps.py, roles.py, truth.py, documents.py,
                      render.py, validate.py, prose.py, recover.py, batch.py   (Plan 2)
  acqlab/dataroom/tools.py                                              (Plan 2)
  acqlab/llm.py                                                         (Plan 2)
  acqlab/routers/     beliefs.py, routers.py, track_a.py                (Plan 3)
  tests/engine/, tests/generator/, tests/routers/, tests/test_llm.py, tests/conftest.py
  data/               git-ignored: deals/<id>/room/, truth/<id>.json, splits.json, llm_cache/, poc/, track_a/
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
- `recover.py`: a positive and a negative probe per fact. Each question says "answer 0 only if the documents show…", so an unrelated document gets null, not 0. The handoff review fixed this: "answer 0 if none" contradicted the "null if not found" rule.

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
- **Decision values are noisy at `--mc 400`** (see the findings list above).
- **Weak, realistic cues remain:**
  - Flippers' add-back line items run larger than clean ones when compared by role (the overall distributions match).
  - Placement weights make "the QoE defers to the notes" mildly predictive.
  - `search()` snippets can surface a fact's amount cheaply; watch this in the pilot.
- **Wording nits:**
  - The CIM's "renewed on a long-term basis" reads against every contract's "renews annually".
  - The number-word guard rejects "third-party"; drop "third" if Codex fallbacks pile up.
  - One capex claim is ungrammatical for plural labels.
  - Company-name suffixes ignore the industry (the showcase deal is "Marlow Mill Manufacturing", an information services business). Fix this before polishing the showcase deal. Note that it changes every prose prompt, so the cached prose would be paid for again.
- **Recoverability failures are reported, not regenerated.** Every test deal must pass recoverability before the main benchmark.
- **Plan 1's Task 9 spreadsheet check is still deferred by the user.** The spec lists it as required.
- **Negative `debt_like` / `nwc_adjustment` values are rejected, not modelled.** A favourable surprise can only enter through `ebitda_adjustment`.

## Later plans (after Plan 3)

- **Plan 4 (week 4, ~2026-10-19):** (router 2, LLM judgement, joins Track A here)
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
main               4a113ba spec → 6b34612 Plan 1 (squash) → eb6a3ee Plan 2 (squash) → handoff review, Codex PoC, Plan 3 spec and plan (7e965f0); 130 tests
plan-3-track-a     Plan 3 (Tasks 1–5) plus final-review fixes on top of main; 159 tests; ready to merge
plan-1-lbo-engine  full Plan 1 history
plan-2-generator   full Plan 2 history
claude/plan-1-implementation-review-727227  finished review branch (kept)
```

The Plan 2 worktree (`.claude/worktrees/plan-1-implementation-review-727227`) is managed by the Claude app and can be removed from there. No git remote is configured.
