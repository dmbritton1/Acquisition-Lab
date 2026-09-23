# Acquisition Lab — Design

Status: Approved 2026-09-23.

## Context and decisions

- **Project:** Acquisition Lab — decision-directed diligence for a leveraged buyout. The system chooses what to investigate in a synthetic data room under a budget, and produces a walk-away price plus go/no-go.
- **Competition:** live demo + pitch (~5–10 min), finance-oriented judges. Solo builder. ~8+ weeks from 2026-09-22.
- **Deal type:** B1 — pure PE leveraged buyout (one target, sponsor, term loan).
- **Decision output:** walk-away price (max price meeting the base-case IRR hurdle, given the debt the sponsor can safely raise — Section 1) AND go/no-go vs. seller asking price. Benchmark scores decision regret; demo shows the go/no-go fork.
- **Models:** solver = Claude Opus 5.5 (`claude-opus-5-5`) for every agent and every single-agent baseline (architecture is the only variable). Document renderer = Codex/GPT family. Development runs on existing subscriptions via CLI (`claude -p`, `codex exec`) behind one adapter (prompt in → text + token count out). Scored runs must be sandboxed (Section 4) and their token overhead comparable across systems; if CLI overhead can't be stripped, scored runs use the API (few hundred $ of credits). The 30-deal pilot's measured token use decides which, before the main run. Benchmark runner is resumable. Check each provider's usage policy before large runs.
- **Multi-agent framework is a fixed requirement.** Architecture is modeled on MAI-DxO (sequential diagnosis panel) run over a blackboard, with a code-based value-of-information scheduler.
- **Benchmark construction:** procedural generator (200+ deals) + ~10 hand-reviewed deals (reported separately) + 1 hand-polished showcase demo deal.
- **Scope tiers:** every component is Core (must ship) or Stretch (only if the pilot shows spare budget and time). See Section 3 and 4 tables.
- **Rough schedule:** engine + generator + Track A wks 1–3; S1 baselines + router checkpoint wk 4; S4 framework wks 4–6; benchmark + ablations wks 6–7; demo UI + slides wks 7–8.
- **Novelty stance:** multi-agent finance/diligence and budgeted sequential information gathering with an LLM panel are not new (see Related work — especially MAI-DxO/SDBench and AUDITFLOW). Claimed contribution: (1) a scheduler that prices each diligence question by its expected effect on the *decision*, computed by a deterministic LBO engine, rather than by LLM judgment or information gain; (2) the engine as sole judge of financial outputs; (3) a synthetic data room with hidden ground truth; (4) head-to-head vs a strong single-agent baseline (one Opus agent) at equal cost — the multi-agent framework runs Opus in every role, so architecture is the only variable, with ablations. Do not claim "first budgeted diligence agent panel." Verify every cited paper and number before it goes on a slide.
- **Presentation:** simple main-slide diagram; full architecture diagram (including Stretch components as the "extended configuration") as backup slide. Pitch line: "a blackboard system whose scheduler prices every diligence question in dollars."

## Section 1 — Deal & financial engine

Engine: pure Python, no LLM, the only source of financial outputs. **Annual periods, single term loan.**

Visible teaser: LTM revenue, reported adjusted EBITDA, growth history, capex % and NWC % of revenue, asking price, lender term sheet (max leverage × EBITDA, rate, amortization, cash sweep, covenants with step-downs), fees, sponsor policy (20% IRR base hurdle, fixed downside case e.g. −10% revenue / −200bp margin, 5-year hold, exit multiple, minimum equity contribution e.g. 40%).

Hidden facts (trap types): EBITDA add-back validity; debt-like items (earnout, pension, deferred revenue); customer concentration; NWC peg; capex underinvestment; litigation/contingencies. Each fact: true value, prior range, revealing documents, retrieval cost.

**Debt sizing (sponsor choice):** debt = min(lender capacity = max leverage × lender-accepted EBITDA; the largest debt that passes the downside covenant test in every year; (1 − min equity %) × price). Covenant and leverage limits therefore constrain debt, never make the deal "undefined."

**Walk-away price:** the maximum price at which base-case IRR ≥ hurdle, with debt sized as above. IRR is monotone decreasing in price, so bisection is well defined. If even the minimum price bound fails the hurdle, walk-away = that lower bound and the decision is no-go.

Key mechanism: lenders size on lender-accepted EBITDA, so a small fake add-back cuts debt capacity by the leverage multiple and shrinks covenant headroom — small valuation moves can flip the decision.

API: `evaluate(state)` → IRR, MOIC, debt sized, leverage path, covenant headroom, equity bridge; `walk_away(state)` → max price; `evaluate_under(beliefs)` → distribution of walk-away prices; `flip_threshold(state, param)` → value of one parameter at which go/no-go flips, holding others at current beliefs.

Testing: hand-built spreadsheet LBO for 3 deals must match engine to the dollar; property tests (worse EBITDA never raises walk-away; more debt-like items always lower it; walk-away is monotone in the hurdle).

Prepared judge answers: annual covenant testing is a known simplification (quarterly is a later addition); exit multiple dominates walk-away and is fixed by sponsor policy — backup slide shows exit-multiple sensitivity.

## Section 2 — Generator & data room

Generation:
1. Sample company/financing from cited mid-market LBO ranges.
2. Sample 2–5 hidden facts controlled by case type: decision-flipping, decoy, interaction, unresolvable, clean.
3. **Asking price comes from the visible teaser only:** market multiple × reported adjusted EBITDA + noise. Hidden facts decide whether the deal is actually good. Noise and trap mix are tuned so ~50% of generated deals are true go.
4. Compute ground truth with the engine: true walk-away, true go/no-go, per-fact decision value.

Rendering: numbers/tables rendered by code, never by the LLM; LLM writes prose only. Per-fact placement plan (explicit, footnote, contradicted across docs, derivable by calculation). Doc types: CIM, QoE report, audited financials + notes, credit agreement excerpt, customer contracts, lease schedule, legal letter, plus filler. **Renderer is the Codex/GPT family; the solver (Claude) never renders.**

Validation per deal (failures regenerated):
- Leak check: teaser and document titles don't reveal hidden facts.
- Recoverability check: an extractor from the non-solver family recovers each fact from its target document(s) and not from unrelated ones. (Passing means "an LLM can extract it" — stated as such.)
- Consistency check: numbers parsed from documents reconcile with ground truth.

Data room tools (shared by all systems, budgeted): `list_documents()` free; `search(query)` small cost; `open_document(id)` cost scales with length. Each document carries a domain tag (accounting/QoE, legal, credit/debt, commercial, filler).

Splits: dev (prompt tuning); test (held-out trap types and doc styles); hand-reviewed (~10, reported separately); showcase demo deal.

## Section 3 — Agents

Principle: LLMs read and judge; code holds state, does math, enforces rules. Every agent must be justified by an ablation. Topology is **centralized** (one coordinator, no peer-to-peer agents): independent agents amplify errors more than centrally coordinated ones, and multi-agent setups degrade sequential reasoning (arXiv:2512.08296). Parallelism only where work is genuinely independent; the final valuation is sequential and stays in code.

Architecture: a **blackboard** (Deal Record) + a **code scheduler** (Router) + LLM knowledge sources, roles mapped from the MAI-DxO physician panel.

- **Deal Record (code, the blackboard):** per issue — engine parameter, status (prior/estimated/confirmed/contradicted/unresolvable), value/range, evidence. Written only via Committer. Also holds:
  - **Issue tree** (task ledger): issues, sub-questions, what has been searched/opened for each.
  - **Progress ledger:** per round — did any range narrow? is an action repeating? stall counter; N stalled rounds → Deal Lead must re-plan (targets step repetition, the top failure mode in MAST, arXiv:2503.13657).
- **Router (code, the scheduler; swappable):** Monte Carlo over open-issue ranges via engine; scores each (issue, action) by expected reduction in decision regret per unit cost; screens top-issue pairs for interactions; vetoes actions whose score < cost (budget stewardship). Variants: (1) checklist order, (2) LLM judgment (MAI-DxO Test-Chooser style), (3) valuation sensitivity, (4) LLM-estimated information gain [Stretch], (5) decision-flip probability, (6) expected $ reduction in decision regret per unit cost (main bet).
  - **Residual sweep:** ~10% of diligence budget reserved for undirected reads chosen by coverage (documents/domains not yet touched). The router can only price issues the Deal Lead proposed; an unproposed trap has zero score.
- **Deal Lead (LLM):** proposes issues in its own words, maps them to generic engine parameters (EBITDA adjustment, debt-like item, revenue haircut, NWC, capex) with prior ranges; updates the issue list after each commit; re-plans on stall; proposes stop. Does no arithmetic. NOT given the trap library.
- **Investigator (LLM; Core = one generalist):** receives an **intent brief** from code: the issue, current range, the engine's flip threshold (e.g. "decision flips if accepted EBITDA < $14.1M; determine whether the $1.8M restructuring add-back recurs"), and a sub-budget. Returns quoted findings, or not found / unresolvable. Multiple issues may be investigated in parallel.
  - [Stretch] **4 domain specialists** (accounting/QoE, legal, credit/debt-like, commercial) owning their domain's documents (partitioned blackboard), cross-domain reads at normal cost.
- **Modeler (LLM → structured):** findings → typed parameter updates (sign, units, period, recurring vs one-off), schema-validated.
- **Challenger (LLM; Analysis of Competing Hypotheses):** independent review of the Deal Record without the Deal Lead's conclusion. For each material committed value: competing explanations, which evidence discriminates, the disconfirming check. Every objection must be an engine test or an evidence problem; objections enter the issue tree and are priced by the Router.
- **Committer (code):** decomposes each proposal into atomic claims and accepts only if checks pass. Three commit types:
  - **Quoted:** value stated verbatim in a cited document.
  - **Computed:** value = code-evaluated formula over ≥2 verbatim quotes (for "derivable by calculation" facts).
  - **Contradicted:** documents disagree → commit a range backed by both quotes.
- **Engine (code):** sole judge of financial outputs.
- **Stopping:** (best remaining router score < investigation cost, or budget exhausted) AND residual sweep complete AND no unresolved Challenger objections.

| Core | Stretch |
|---|---|
| Deal Record + issue tree + progress ledger | 4 domain specialists + partitioned blackboard |
| Committer (quoted / computed / contradicted) | Router variant 4 (LLM information gain) |
| Routers 1, 2, 3, 5, 6 + residual sweep | Panel role-played in one context vs separate agents |
| Deal Lead, generalist Investigator with intent briefs, Modeler, Challenger | S4 ensemble |

## Section 4 — Evaluation

**Track B (headline):** real LLM systems on real data rooms. This is the result on the slides.

**Track A (internal diagnostic):** routers only, no LLM. Simulated investigator in code returns the fact at its cost (variants: retrieval failure probability, noisy value). **Prior ranges must be noisy or LLM-proposed, never the generator's true priors.** Track A shows the router math is correct and isolates it from reading ability; it does not show the router works on real diligence (the router and the generator share the engine). Runs on thousands of deals, ready by ~week 3. Backup slides at most.

### Systems (all on Opus 5.5)
| System | Definition | Tier |
|---|---|---|
| Trivial baselines | walk-away = asking price; always go; always no-go | Core |
| B0 | engine on teaser only, no diligence | Core |
| S0 | single Opus, all documents, no budget (reading ceiling) | Core |
| S1a | single-agent baseline (one Opus agent), data-room tools + budget, does its own math | Core |
| **S1b** | single-agent baseline (one Opus agent), data-room tools + budget + **engine as a tool** — the fair fight | Core |
| S1b + router | S1b choosing questions via Router 6 (checkpoint and fallback claim) | Core |
| S2 | fixed checklist workflow | Stretch |
| S3 | best-of-N S1b, N set to match S4 total tokens | Core |
| **S4** | multi-agent framework, Opus in every role (Section 3) | Core |
| Ablations | −Challenger; −engine (LLMs compute valuation); −residual sweep | Core |
| Ablations | −Deal Record (shared chat log); −intent briefs; −specialists; panel-in-one-context; each router variant end-to-end | Stretch |
| Second model family | S1b and S4 on Codex/GPT | Stretch |

**Fairness rules:** same model, deals, tools, diligence budget and sandbox for every system. **Prompt-tuning parity:** S1a/S1b get the same dev-set tuning effort as S4 (log hours/iterations).

**Sandboxing:** every scored solver call runs from an empty temp directory with built-in file/shell tools disabled; data-room access only through the budgeted tools. Ground truth never lives under a solver-reachable path.

### Cost definitions
- **Diligence budget** (retrieval-cost units) constrains what a system may read. Same for all budgeted systems; S0 is unbudgeted by definition.
- **Tokens** are compute cost, including coordination, challenges and retries; measured, not constrained.
- **"Equal cost"** = same diligence budget, with tokens matched as closely as possible (S3's N). Every chart states its x-axis; both regret-vs-tokens and regret-vs-diligence-spend are reported.

### Metrics
- **Decision regret (primary):** go on bad deal → overpay (asking − true walk-away); no-go on good deal → value forgone (true walk-away − asking); normalized by EV. Reported overall AND on decision-flip cases separately.
- Walk-away error (% of EV); go/no-go accuracy; range coverage; unresolvable handling (flagged vs fabricated); evidence precision (share of atomic claims supported); budget spent on decoys; issues first found by residual sweep; **Deal Lead prior calibration** (true value inside proposed prior range; the most likely reason S4 loses); total tokens.

### "Noticeable difference" (fixed before touching the test set)
S4 beats S1b if decision regret is **≥ 25% lower** AND the paired bootstrap 95% CI on the difference excludes zero, on ~100 test deals. The pilot checks whether 100 deals can detect that effect; adjust deal count before the main run, not after.

### Pre-registered hypotheses
- H1: S4 has lower regret than S1b at equal cost (and than S1a, S3).
- H2: Router 6 beats routers 3 and 5, especially on decoy/interaction cases.
- H3: removing the Challenger increases evidence errors and regret.
- H4: S4 spends less budget on decoys.
- H5: removing the engine sharply increases walk-away error.
- H6: residual sweep reduces regret on cases where a trap isn't in the Deal Lead's initial issue list.

### Scale
Pilot: 30 dev deals — measures variance and **actual tokens per run**, which decides subscription vs API for scored runs. Main: ~100 test deals, core systems at medium budget, 3 seeds on a subset. Budget sweep (3 budgets) and core ablations on a 40-deal subset. Track A on thousands. Paired design, paired bootstrap CIs, broken down by case type; hand-reviewed set reported separately.

Reference points: trivial baselines and B0 (floor — if S4 can't clearly beat B0, nothing else matters), oracle router (routing ceiling), S0 (reading ceiling).

### Checkpoint, end of week 4
Compare S1b vs S1b + router on the pilot, plus Track A (router 6 vs 3 and 5). If the router doesn't help, reframe the claim before building S4 in full. If S4 later fails to beat S1b but S1b + router does, the claim becomes "the dollar-priced router is what matters, even for a single agent."

### Headline charts
Regret vs tokens; regret vs diligence spend; regret by case type (flip cases highlighted); budget on decoys; ablation bars (−engine as the finance-judge slide).

## Section 5 — Demo, UI & stack

### On-stage loop (~3 min of the pitch)
1. **Teaser:** fictional company (no real names), asking price. **Fork chart:** distribution of walk-away prices given current beliefs, asking price as a vertical line; share of go vs no-go.
2. **Router board:** open issues ranked by decision value. Key moment: a big-valuation-impact assumption ranked low because it never flips the decision; a small add-back ranked #1.
3. **Investigation:** document opens, quote highlighted, Committer check passes, distribution narrows/shifts, a new issue rises.
4. **Challenger:** interaction test (e.g. customer concentration + covenant step-down) → engine shows downside effect.
5. **Verdict:** go/no-go at the asking price, walk-away with range, open issues, evidence map.
6. **Results slide:** single-agent baseline (one Opus agent) vs Acquisition Lab (Opus in every role; same documents, budget); regret vs tokens; budget on decoys.

### Reliability
- Engine interactions are always live and instant (change asking price, hurdle, downside case, or which document is revealed).
- **Primary path: replay of a recorded S4 trace of the showcase deal**, labeled "recorded run" — no network or latency risk (CLI steps take minutes).
- Optional live run of S4 on a freshly generated deal if time and network allow.

### UI views
Fork chart; router board; evidence viewer with highlighted quotes; agent timeline; full architecture diagram (backup).

### Tech stack
- Python 3.12 + uv; pydantic for all schemas; numpy for Monte Carlo; pytest + hypothesis.
- LLM adapter: subprocess to `claude -p --output-format json` / `codex exec --json`, run in a sandbox temp dir; optional API backend.
- Storage: JSON/JSONL files; one folder per deal, one trace per run keyed by (deal, system, budget, seed); resumable runner. No database.
- Demo: FastAPI backend serving engine + traces; Vite + React frontend. Streamlit fallback if time runs short.

### Repo layout
```
acqlab/
  engine/      lbo.py, walkaway.py, beliefs.py
  generator/   sample.py, traps.py, render.py, validate.py
  dataroom/    tools.py (budgeted list/search/open)
  agents/      record.py, committer.py, deal_lead.py, investigator.py, modeler.py, challenger.py
  routers/     checklist, llm, valuation, flip, decision_value
  systems/     baselines, s0, s1a, s1b, s3, s4 + ablation configs
  llm.py       adapter + sandbox
  bench/       runner.py (resumable), metrics.py, report.py
demo/          api/ (FastAPI), web/ (React)
data/          deals/ (ground truth kept outside solver sandbox), runs/
tests/
```

## Related work (to cite; positioning — verify each before slides)

- **MAI-DxO / SDBench** (Microsoft, arXiv:2506.22405) — closest analogue. Sequential diagnosis with per-test costs; gatekeeper reveals information only on request; single LLM role-plays a 5-doctor panel (Hypothesis, Test-Chooser, Challenger, Stewardship, Checklist); instant-answer → budgeted → unconstrained → ensemble variants; accuracy-cost frontier. Our difference: question value computed by a deterministic engine against the decision, not LLM judgment; financial outputs never from the LLM.
- **AUDITFLOW** (arXiv:2606.03031) — LLM auditors + symbolic XBRL environment; removing deterministic checks reportedly drops accuracy sharply. Prior art for engine-as-judge.
- **Magentic-One** (arXiv:2411.04468) — task ledger / progress ledger, stall detection and re-planning.
- **Blackboard systems:** LbMAS (arXiv:2507.01701); Salemi et al. (arXiv:2510.01285), partitioned data and volunteering agents.
- **Information-seeking LLMs:** BED-LLM (arXiv:2508.21184), Uncertainty of Thoughts (arXiv:2402.03271) — information-gain question selection; our router targets decision value (Howard 1966 value of information).
- **CICERO** (Meta, Science 2022) — planner picks intents; language model conditioned on them.
- **TAR stopping rules** (Cormack & Grossman) — estimating undiscovered relevant material.
- **Analysis of Competing Hypotheses** (Heuer); AgentCDM applies it to LLM agents.
- **SAFE** (arXiv:2403.18802) — atomic-claim decomposition and verification.
- **PentestGPT** (USENIX Security '24) — task tree held outside the LLM.
- **Cautions:** MAST failure taxonomy (arXiv:2503.13657); Towards a Science of Scaling Agent Systems (arXiv:2512.08296); Should we be going MAD? (arXiv:2311.17371); Anthropic multi-agent research system (token usage explains most performance variance).
- **Finance MAS (weak prior art):** VC due-diligence orchestration (arXiv:2605.13110); financial document processing orchestration benchmark (arXiv:2603.22651); FinRobot, FinCon, TradingAgents.

## Adversarial review (2026-09-22) — resolved 2026-09-23

| # | Finding | Resolution |
|---|---|---|
| 1 | Asking price leaked ground truth | Asking price from teaser only; ~50% true-go; trivial baselines added (§2, §4) |
| 2 | Walk-away undefined under covenant gates | Sponsor debt sizing with min equity; IRR-only bisection (§1) |
| 3 | Router graded by the model that generated answers | Track A scoped as math check with noisy priors; prior-calibration metric (§4) |
| 4 | CLI sandboxing and token accounting | Empty-dir sandbox, tools disabled; pilot decides subscription vs API (§4, Context) |
| 5 | Verbatim-quote rule vs derived/contradicted facts | Computed and contradicted commit types (§3) |
| 6 | Two cost currencies | Cost definitions (§4) |
| 7 | Week-4 checkpoint vs schedule | Checkpoint on S1b vs S1b + router (§4, schedule) |
| 8 | Small, noisy regret | Fixed by #1; flip-case regret reported separately (§4) |
| 9 | Renderer family | Codex/GPT renders, Claude solves (§2) |
| 10 | Recoverability check is LLM-dependent | Stated; non-solver family extracts (§2) |
| 11 | Annual covenants | Prepared answer (§1) |
| 12 | Exit multiple dominates | Backup sensitivity slide (§1) |
| 13 | Demo latency | Replay is primary path (§5) |

## Possible later additions / changes

- Second-lien debt tranche.
- Quarterly periods (more realistic covenant testing).
- Simulated management Q&A tool (can be evasive, high cost).
- PE add-on variant (B2): platform company acquiring a competitor, integration story.
- All Stretch items in Sections 3–4.
