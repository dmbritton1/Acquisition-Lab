# Acquisition Lab — Deal Generator & Data Room Design (Plan 2)

Status: Approved 2026-09-23; revised after pre-verifying Plan 2 (see "Revisions").
Parent spec: `2026-09-22-acquisition-lab-design.md` §2 (this document details it; the parent stays the binding authority, and every deviation is listed under "Deviations from the parent spec").
Engine: `acqlab.engine` (Plan 1, on `main`). All money in $M, rates as decimals.

## Goal

Produce synthetic LBO deals whose data rooms hide facts with known ground truth, so every system in the benchmark can be scored on decision regret. Proof of concept first: the whole generator runs without an LLM (template prose); Codex prose is layered on.

## 1. Deal sampling

**Industry first.** Each deal picks an industry from a small LBO-typical table, then draws its operating profile from that industry's figures plus noise. Candidate industries (Damodaran names): Business & Consumer Services, Machinery, Healthcare Products, Building Materials, Packaging & Container, Electrical Equipment, Chemical (Specialty), Food Processing, Information Services, Transportation. Software is excluded for now (Damodaran's capex for software includes capitalised R&D, which does not fit the engine's capex line).

| Engine input | Sampling rule | Source |
|---|---|---|
| EBITDA margin | Industry EBITDA/Sales ± noise | Damodaran, *Operating and Net Margins*, Jan 2026 |
| Capex % revenue | Industry (EBITDA/Sales − pre-tax operating margin) × (Capex / Depreciation) ± noise | Derived from Damodaran margin and capex tables, Jan 2026 |
| D&A % revenue | Industry EBITDA/Sales − pre-tax operating margin | Derived, Damodaran margins |
| NWC % revenue | Industry non-cash working capital / sales ± noise | Damodaran, *Working Capital Requirements*, Jan 2026 |
| Growth | −2% to +8% | Assumption (to source) |
| Tax rate | 25% | 21% US federal statutory + state |
| Enterprise value at asking | $50–500M | GF Data universe ($10–500M TEV) |
| Market multiple | 6–10× reported adjusted EBITDA, mode ~7.2× | GF Data 2025 average 7.2× (pre-COVID 6.7×) |
| Lender max leverage | 3.0–5.0× | GF Data 2025 total debt 3.6× (platform 3.2–3.5×); Lincoln 4.75–6.25× for larger borrowers |
| Interest rate (all-in) | 7.5–9.5% | Lincoln: SOFR 3.70% + 475–550 bp = 8.45–9.20%; GF Data senior 7.5–8.1% |
| Covenant (year 1) | Lender max leverage ÷ (1 − cushion), cushion 25–35% | Sidley Austin, Mar 2026: "25-35% cushion" |
| Covenant step-down | 0.25× per year | Assumption |
| Amortization | 1% per year | Regions Bank (unitranche "often 1% annually"); not yet read in full |
| Cash sweep | 50% | Assumption (market-standard excess-cash-flow sweep) |
| Fees | 2–3% of price | Assumption |
| Sponsor policy | Hurdle 20%, hold 5, min equity 40%, downside −10% / −2pt (parent spec §1) | Parent spec |
| Exit multiple | The deal's market multiple (no multiple expansion) | Assumption |

The Damodaran figures are for US public companies, larger than mid-market targets; this is a stated proxy. Values are pinned in code from Damodaran's HTML tables (read twice on 2026-09-23 and cross-checked); checking them against his .xls files (downloaded with user approval) is a later addition.

**Margin rule (from the Plan 1 review).** A bigger revenue haircut can raise walk-away when capex or NWC is heavy relative to margin. The sampler requires true EBITDA margin ≥ capex % (after `capex_adjustment_pct`) + a buffer, and a property test over sampled deals checks that walk-away never rises with the haircut. The buffer is set by that test (start at 5 points).

**Asking price** = market multiple × reported adjusted EBITDA × (1 + noise). The noise is tuned so ~50% of deals are a true go (see §5).

**Teaser red flags.** The teaser shows reported EBITDA, adjusted EBITDA and the claimed add-backs. A larger adjusted-vs-reported gap raises the probability of a fake add-back. This is a legitimate analyst cue, not a leak.

**History.** Three fiscal years of financials are back-filled from the growth rate (with small noise), so recurrence and trend facts can be derived by calculation.

## 2. Trap library

One trap per engine parameter; litigation is a debt-like item. Every trap makes the deal worse or is zero (favorable surprises are a later addition).

| Trap | Param | Story variants | True value range | Hint (every deal) | Reveal |
|---|---|---|---|---|---|
| Fake add-back | `ebitda_adjustment` (≤ 0) | restructuring; consulting fees; owner compensation | Disallowed 0–25% of reported adj. EBITDA | Add-back schedule in teaser and CIM | QoE disallowance, or the same "one-time" item in 3 years of financials |
| Debt-like item | `debt_like` | earnout; pension deficit; deferred revenue; litigation | 0–15% of EV | CIM sources/uses and "cash-free, debt-free" language | Notes to audited financials; legal letter (litigation) |
| Customer concentration | `revenue_haircut` | contract expiring; customer running an RFP; customer acquired by a competitor | 0–30% of revenue lost | CIM top-10 customer chart | Customer contract (renewal date, termination clause) |
| Working-capital shortfall | `nwc_adjustment` | stretched payables; pulled-forward collections | 0–20% of normal NWC | QoE working-capital section | Monthly NWC vs normal level (derived by calculation) |
| Deferred capex | `capex_adjustment_pct` | aged equipment; deferred maintenance; lease return conditions | +0 to +3% of revenue per year | "Well-maintained asset base" in CIM | Fixed-asset schedule or maintenance log (asset age; capex below depreciation for years) |

Industry weights make traps fit the business (deferred capex in capital-heavy industries, deferred revenue in services, pensions in older manufacturing). Each deal has 2–5 facts, each a different trap type; a debt-like fact picks one variant. The ranges above are assumptions to calibrate later.

**Generator prior.** Each trap type's prior range is its true-value range above. Track A (Plan 3) must use noisy versions of it, never the exact prior (parent spec §4).

## 3. Roles and case types

Each fact gets a role. Roles are **constructed with the engine**, not discovered after sampling: roles are chosen first, then each value is drawn at random from the band where that role holds (so no two deals look alike and every label is guaranteed). Roles are evaluated on the *knowable* value (see Unresolvable).

| Role | Rule (checked by the engine) |
|---|---|
| Flipper | Alone, flips go/no-go versus face value, past its `flip_threshold` by ≥ 20% of its prior range |
| Decoy | Moves walk-away by ≥ 5% of EV, and stays ≥ 20% of its prior range short of its own `flip_threshold` (or never flips within its range) |
| Interaction pair | Each alone stays ≥ 20% of its prior range short of its own `flip_threshold`; together they flip the decision, and it stays flipped if either value is pulled back by 10% of its prior range |
| Unresolvable | The documents support only a range: the key document is referenced but missing, or it gives an estimate range. **Knowable value** = midpoint of the documented range; the **realized value** is drawn within it and recorded separately |
| Clean | True value 0; documents show the topic and resolve it benignly |

The deal's case type is derived from its facts: any flipper → flip case; interaction pair → interaction case; only clean facts → clean case; and so on. Metrics such as "budget spent on decoys" use the per-fact roles directly.

**Scoring against the knowable truth.** True walk-away and go/no-go use knowable values, so a system that correctly reports "$5–20M, cannot narrow it" is not penalised for luck. Realized values are reported separately. The parent spec's "unresolvable handling" metric checks flag-versus-fabricate behaviour directly.

## 4. Planting facts in documents

Every trap topic appears in every deal (presence rule): there are always add-backs, a customer list, equipment notes and a legal letter. What differs is whether the reveal shows a problem. This stops keyword presence (and keyword search) from leaking the answer.

**Placement modes**, easiest to hardest: stated outright; footnote; derivable only by calculation over two or more quotes; contradicted across documents. Modes are drawn from a small weight table per role: decoys lean loud (large numbers in the CIM), flippers lean toward footnotes and calculations.

**Contradictions resolve by trust ranking:** signed contracts and audited financials > QoE report > seller's CIM. The true value is always placed in the more trusted document, so every contradicted fact has one correct value. Unsettleable disagreements are modelled as the Unresolvable role instead.

## 5. Data room, costs, budget, answer keys

**Documents per deal:** about 12–20. Core types: CIM, QoE, audited financials with notes, credit agreement excerpt, 1–3 customer contracts, fixed-asset/lease schedule, legal letter. Filler (board minutes, HR policy, insurance certificates, IT policy) makes up about one-third. Each document carries a domain tag (accounting/QoE, legal, credit/debt, commercial, filler).

**Tools and costs** (budget units):
- `list_documents()`: free; returns titles, domain tags and page counts.
- `search(query)`: 1 unit; top 5 passages as ~150-character snippets. Plain-Python word-overlap scoring; no new dependency.
- `open_document(id)`: 1 unit per page.

**Budget:** about 30–40% of the data room's total open cost; tuned in the pilot, with three levels for the budget sweep. Every call is logged (tool, arguments, cost, remaining); a call that would exceed the budget is refused.

**Storage:** documents in `data/deals/<id>/room/` (the only path the tools read); answer keys in `data/truth/<id>.json` (unreachable from the tools, enforced by a test). Both git-ignored. The Plan 4 sandbox (empty temp dir, file tools off) is the second layer.

**Answer key, per fact:** trap type, variant, param, role, true / knowable / realized value, prior range, placement mode, hint and reveal documents, retrieval cost, `flip_threshold`, and **decision value** = expected regret with all facts at their priors minus expected regret with this fact known (others still at priors), via `evaluate_under`. **Per deal:** true walk-away, go/no-go, `Result.debt_limit`, case type, seed, generator version.

## 6. Rendering

**Two layers.** Code builds each document's skeleton: every table, every contract clause with dates and amounts, and prose slots with placeholders (e.g. `{{addback_restructuring_fy24}}`). Codex fills prose slots from a short brief that contains no numbers; code substitutes the numbers. Any number in LLM prose that did not come from a placeholder rejects the document for regeneration. Every slot also has a template sentence, so the full pipeline runs with no LLM (tests, CI, offline work).

**Minimal LLM adapter (proof-of-concept shortcut).** One function: prompt in → text + token count out, over `codex exec --json`, with an on-disk cache keyed by prompt hash. Marked in code with a `ponytail:` comment. Plan 4 adds `claude -p`, the sandbox and the API backend. Tests use a fake adapter, so the suite spends no subscription usage.

**Fictional names** from word lists, checked against a short list of real company names.

## 7. Validation (failures regenerate the deal)

| Check | What it verifies |
|---|---|
| Engine | Every role holds with its margins; margin rule; batch go rate ~50% |
| Leak | Teaser, titles and the document list reveal no trap. **Presence check:** across a batch, trap-topic mentions are equally frequent in trap and clean deals |
| Consistency | Every number in every rendered document matches the answer key |
| Recoverability | Codex, given only the reveal document(s), recovers the value within tolerance; given an unrelated document, answers "not found" |

**Recoverability is phased in** (~20–50 Codex calls per deal): proof of concept runs it on every hand-reviewed deal, the showcase deal and a random 20 dev deals; every test deal passes it before the main benchmark.

## 8. Splits, sizes, targets

Held-out material is **variants, not whole trap types**: the test split includes at least one story variant per trap and one template style per document type that dev never sees (each document type has 2 template styles).

| Split | Size | Use |
|---|---|---|
| Dev | 50 | Prompt tuning; the 30-deal pilot |
| Test | 120 | ~100 scored deals plus spare; includes the 40-deal ablation subset |
| Hand-reviewed | ~10 | User realism review; reported separately |
| Showcase | 1 | Demo deal, hand-polished |

Every deal is reproducible from (seed, generator version). Starting mix targets, tuned in the pilot: 2–5 facts per deal; ~60% of deals with a flipper; ~20% with an interaction pair; ~30% with an unresolvable fact; ~15% fully clean; ~50% true go.

## 9. Build order (Plan 2 tasks)

1. Industry table (pinned Damodaran values) and deal sampler
2. Trap library and engine-based role placement
3. Answer keys and per-fact decision value
4. Document skeletons with template prose
5. Data room tools and budget
6. Validators: engine, leak/presence, consistency
7. Codex adapter, prose fill, reply cache
8. Recoverability check (phased in)
9. Batch command producing all splits

Steps 1–6 need no LLM. All steps are test-first with fixed seeds.

## Deviations from the parent spec

- Recoverability runs on a sample during the proof of concept; every test deal still passes before scoring (§7).
- The test split holds out story variants and document template styles rather than whole trap types (§8).
- Litigation is a debt-like variant rather than a separate trap type (§2).
- No favorable surprises in the first version (§2).
- Market data note: real deals of this size carry ~55–60% equity (GF Data, Lincoln). Because asking prices sit below market averages (see Revisions, item 3), the policy's 40% minimum equity in fact binds in about half of generated deals. No change proposed.

## Revisions from pre-verification (2026-09-23)

Found while running the Plan 2 code before writing the plan (details in the plan's "Findings" section):

1. Every deal records all five traps as facts; the presence rule makes an absent trap identical to a clean one. Typically one to three facts are not clean.
2. Case mix: clean 15%, flip 25%, interaction 10%, other 50%. All traps are adverse, so ~60% flippers cannot coexist with ~50% true go. Measured: true go 44–48%; deals with an unresolvable fact ~37%.
3. Asking price = market EV × (1 + N(−15%, 10%)): a 20% hurdle with no multiple expansion almost never clears at the GF Data multiple.
4. Decision value uses a base-rate prior (0 with probability 0.70, else uniform on the range); a uniform prior makes every decision value zero.
5. D&A % uses the pre-tax *unadjusted* operating margin; Transportation dropped, Software excluded.
6. Recoverability costs 10 Codex calls per deal, not 20–50.
7. A budget unit ("page") is 120 words.
8. The answer key stores reveal documents (as evidence) but not hint documents or per-fact flip thresholds: hints are fixed per trap and thresholds are recomputable with the engine.
9. Prose is requested one call per document (JSON enforced by `--output-schema`), not per paragraph; a broken paragraph is retried alone. Per document, not per deal, so the CIM's writer never sees what the QoE reveals. About 4–7 calls per deal.
10. Codex usage limits: a failed call is never cached and stops the batch cleanly (exit code 2); rerunning the same command resumes from the cache without paying twice.

From the final review of the Plan 2 branch:

11. The CIM makes all five assertive seller claims in every deal; for a trap fact not placed "contradicted" the claim is simply false and the higher-tier reveal document settles it.
12. Default (non-reveal) sentences are neutral and identical for trap and clean facts: none says a problem is absent. Every contract states the same annual-renewal term.
13. A clean add-back's CIM line item is drawn from a role-independent severity distribution shaped like trap items; `check_batch` compares item/claimed quartiles for clean and non-clean facts.
14. Decision value is cross-fitted (each bin's decision chosen on one half of the draws, scored on the other), with severity-0 draws in their own bin and empty bins skipped.
15. Recoverability failures are reported, not regenerated (a deviation from §7 until test deals are scored).
16. Known mild cue: placement weights make "the QoE defers to the notes" slightly predictive of a buried problem.
17. Design point for the pilot: `search()` snippets can return a fact's amount cheaply, without paying to open the document.

## Later additions

- Harden the LLM adapter (Plan 4).
- A dice-rolled realism batch: random values labelled after the fact, reported separately as a robustness check.
- Favorable surprises (e.g. understated EBITDA).
- Source the trap size ranges and the assumption rows in §1.
- Aggressive-seller archetypes (correlated traps).
- Messy documents (mixed units, fiscal year-ends, rounding).
- Full recoverability coverage (before the main benchmark; required, not optional).

## Sources (checked 2026-09-23)

- GF Data Q4 2025 reports, via ACG: https://www.acg.org/news-trends/news/gf-data-releases-q4-2025-ma-and-leverage-reports
- "The New Normal for Middle-Market M&A", ACG Insights, 2026-08-12: https://middlemarketgrowth.org/gf-data-new-normal-middle-market-m-a/
- Lincoln International, Private Market Perspectives Q1 2026 (pp. 8, 16, 21, 31): https://www.lincolninternational.com/wp-content/uploads/Lincoln-VOG-Private-Market-Perspectives_Q1-2026_Final.pdf
- Sidley Austin, "Financial Covenants in Private Credit Transactions", 2026-03-24: https://www.sidley.com/en/insights/newsupdates/2026/03/financial-covenants-in-private-credit-transactions
- Damodaran data sets (NYU Stern), updated 2026-01-09: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datacurrent.html
- Regions Bank, "What is Unitranche Financing?": https://www.regions.com/insights/commercial/article/what-is-unitranche-financing
