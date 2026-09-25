# Plan 4b: The Hard Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the calibrated hard benchmark from the reframe design (§4): search-safe reveal wording, search back for agents, the same diligence knowledge for every system, difficulty profiles (more interaction deals, buried evidence including the board minutes, a tighter budget), the S0 and S3 baselines, and a calibration check. Then run the calibration rounds with the user's OK.

**Architecture:**
- **Generator.**
  - A real problem and a clean fact render the *same* sentences; only the numbers differ.
  - Placement is role-blind, so where a sentence sits says nothing either. That is what lets search come back.
  - `PROFILES` in `truth.py` holds the pre-registered difficulty levers, chosen with `batch --profile`.
- **Agents.** A new `acqlab/agents/knowledge.py` holds the diligence map and typical sizes. The router uses it in code, and every system's prompt states it.
- **Bench.**
  - `pilot.py` gains S0 (the whole room as budget), repeat runs, and S3 (the majority of S1b runs).
  - The new `calibrate.py` checks a round against the targets.

**Tech Stack:** Python 3.12, uv, pydantic 2, numpy 2, pytest. Claude Code CLI 2.1.280+ for the calibration runs (controller only).

**Spec:** `docs/superpowers/specs/2026-09-24-reframe-design.md` (§3 fairness, §4 the hard benchmark). It revises `docs/superpowers/specs/2026-09-22-acquisition-lab-design.md`; where they conflict, the reframe wins.

## Global Constraints

**Dependencies and scope**
- Python `>=3.12`, no new dependencies. Money is in **$M**.
- This plan doesn't change `acqlab/engine` or `acqlab/routers` (source code).

**Tests**
- No test calls Claude or Codex; tests use `tests/agents/fake_claude.py`.
- Never edit a golden test number to make a test pass. The one Track A test change (Task 1) gives a scenario enough budget; it changes no expected number.

**Real runs and subagents**
- Real Claude runs happen only after the user's OK, and only with `--confirm-claude`.
- Subagents must never make a real Claude or Codex call.
- Subagents must never modify settings or permissions files, and must stop and report if a git operation is blocked.

**Commits**
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

**Leak rules (spec §4 "Leak-free")**
- Batch checks, now including word leaks, report **0 problems on 500 deals**.
- The margin shortcut's AUC for flip deals is **≤ 0.72**.
- Every system gets the same general diligence knowledge (`knowledge.GUIDE`; spec §3).

**Calibration targets (spec §4, verbatim values)**
- S1b is wrong on ≥ 30% of flip deals.
- The test size needed for a 25% cut is ≤ 100 deals.
- S0 is right on ≥ 80% of flip deals.
- S1b beats both B0 and the margin rule.
- At most 3 rounds, with levers in the order case mix → placement → budget.
- If 3 rounds fail, stop and decide with the user.

## Review Focus

These five input classes or failure modes aren't exercised by the spec's own tests. Each line names the test that pins it.

1. **An unresolvable fact placed anywhere** (explicit, footnote, contradicted, minutes) must still state its range, and the consistency check must find it. `test_an_unresolvable_fact_states_its_range_where_an_amount_would_go` (Task 1) and the minutes test (Task 3).
2. **Clean facts in "contradicted" or "minutes" placements**, which only real problems had before, must render and validate. `test_a_real_problem_and_a_clean_fact_render_the_same_sentences` (Tasks 1 and 3).
3. **A search for numbers**, such as "0" to find $0.0M, must return nothing. `test_search_costs_one_unit_and_returns_short_snippets` (Task 2).
4. **A calibration round where every deal is a flip deal, or none is**, must not crash the margin AUC. `test_margin_auc_is_one_when_thin_margins_are_exactly_the_flip_deals` (Task 5).
5. **A summary with S1b runs only**, as in calibration, must give floors and no checkpoint. `test_a_summary_with_only_s1b_has_floors_but_no_checkpoint` (Task 4).

## Findings from pre-verifying this plan (read before starting)

All the code below was run before this plan was written. It passes 220 tests, and the batch checks were measured on 500-deal batches.

1. **Word leaks on 500 deals fell from 48 to 0.**
   - Every reveal sentence is shared, word for word, between a real problem and a clean fact. A clean fact shows `$0.0M`.
   - An unresolvable fact writes its range where an amount would go, as `$6.8–$19.2M`: one unit sign, so it has as many words as one amount.
   - Contract notices always state exactly one dollar figure. Without that, contract_1's count of `m` gave traps away.
2. **Role-dependent placement had to go.** Plan 2 placed evidence differently by role: decoys loud, flippers buried. With the wording shared, placement alone was still a leak: under `r1` at seed 700000, the NWC word "covered" had AUC 0.72.
   - Placement is now role-blind in every profile. Unresolvable facts use the same places as every other role, except "calculation".
   - The old "range" placement is gone.
   - Measured result: 0 word leaks and 0 batch problems for `base`, `r1` and `r2` at seeds 0, 700000 and 900000 (9 batches of 500 deals).
3. **Search returns document ids, not snippets.** A 150-character snippet of a reveal sentence would read the answer for 1 unit instead of the document's pages. Search tokens are letters only, the same view `validate.doc_words` audits.
4. **Profile `r1`.** Its first draft (interaction 0.30, flip 0.25) pushed the go rate to 0.33, below the 0.38–0.62 check.
   - The final `r1` keeps flip + interaction at 35%, as `base` does, but with 2.5× the interaction deals.
   - Its clean add-back items are drawn uniform on (0.2, 1.0) of the worst case, so they match trap sizes under that mix.
5. **Margin shortcut AUC** (400 deals each): base 0.66, r1 0.59, r2 0.59. All are under 0.72.
6. **A 500-deal audit takes about 2.5 minutes** through the batch CLI.
7. **Track A's sweep test assumed its deal's problem was cheap to read.** With the new placements it isn't. The test now gives the scenario a budget that covers every fact; no expected number changed.

## File map

| File | Task | Responsibility |
|---|---|---|
| `acqlab/generator/render.py` | 1, 3 | Shared reveal wording, ranges, and the board minutes |
| `acqlab/generator/truth.py` | 1, 3 | Role-blind placement, `PROFILES`, `DealTruth.profile`, `GENERATOR_VERSION = "4.0.0"` |
| `acqlab/generator/validate.py` | 1, 3 | Range consistency, minutes in `CORE_TITLES` and `PAGE_DOCS` |
| `acqlab/generator/padding.py` | 3 | Board minutes pad like filler |
| `acqlab/generator/batch.py` | 2, 3 | Word leaks as problems, `problems.json`, `--profile` |
| `acqlab/agents/knowledge.py` | 2 | `DILIGENCE_MAP`, `typical_high`, `GUIDE` |
| `acqlab/agents/server.py` | 2 | Search tool; knowledge moved out |
| `acqlab/agents/prompts.py` | 2 | Search sentence and `GUIDE` in every prompt |
| `acqlab/dataroom/tools.py` | 2 | Letters-only search tokens |
| `acqlab/bench/pilot.py` | 4 | S0, repeat runs, S3 |
| `acqlab/bench/calibrate.py` | 5 | The calibration targets |

---

### Task 1: Search-safe reveal wording and role-blind placement

**Files:**
- Modify: `acqlab/generator/render.py`, `acqlab/generator/truth.py`, `acqlab/generator/validate.py`
- Modify: `tests/generator/test_render.py`, `tests/generator/test_validate.py`, `tests/generator/test_padding.py`, `tests/routers/test_track_a.py`

**Interfaces:**
- Produces:
  - `render.span(low: float, high: float) -> str`, giving `"$6.8–$19.2M"`.
  - `truth._role_blind(weights: dict[str, float]) -> dict[str, dict[str, float]]`.
  - `truth.PLACEMENT`, now role-blind.
  - `GENERATOR_VERSION = "4.0.0"`.
  - The `"range"` placement no longer exists. An unresolvable fact's `placement` is explicit, footnote or contradicted, and its `documented` range is written where an amount would be.
  - `render.SUPPORT` is deleted.
- Consumes: nothing new.

- [ ] **Step 1: Write the failing tests**

In `tests/generator/test_render.py`, replace:

```python
from acqlab.generator.render import LABELS, answer, render, teaser_text
```

with:

```python
from acqlab.generator.render import LABELS, answer, render, span, teaser_text
```

Append to `tests/generator/test_render.py`:

```python


def _templates(t) -> dict[str, str]:
    return {f"{d.id}/{b.id}": b.template for d in render(t)[0] for b in d.blocks if isinstance(b, Slot)}


def test_a_real_problem_and_a_clean_fact_render_the_same_sentences():
    """Plan 4b: only the numbers differ, so no word (and no search) tells a trap deal from a clean one."""
    t = DEALS[0]
    for i, fact in enumerate(t.facts):
        for placement in ("explicit", "footnote", "calculation", "contradicted"):
            def deal(role, amount):
                facts = list(t.facts)
                facts[i] = fact.model_copy(update={"role": role, "amount": amount, "realized": amount,
                                                   "documented": None, "placement": placement})
                return t.model_copy(update={"facts": facts})
            assert _templates(deal("flipper", round(0.6 * fact.worst, 1))) == _templates(deal("clean", 0.0)), \
                (fact.trap, placement)


def test_an_unresolvable_fact_states_its_range_where_an_amount_would_go():
    for t in DEALS:
        docs, evidence = render(t)
        text = {d.id: d.render() for d in docs}
        for f, ev in zip(t.facts, evidence):
            assert f.placement != "range"
            if f.documented:
                assert ev.formula == "range" and any(span(*f.documented) in text[d] for d in ev.docs), t.id
```

In `tests/generator/test_validate.py`, replace:

```python
def test_word_leaks_finds_a_planted_word_and_the_known_template_leak(big_batch):
    deals, _, _, words = big_batch
    found = {(r["trap"], r["doc"], r["word"]) for r in word_leaks(deals, words)}
    assert ("concentration", "contract_1", "confirmed") in found  # Plan 2's reveal wording; fixed in Plan 4b
```

with:

```python
def test_word_leaks_finds_a_planted_word_and_the_reveal_wording_has_none(big_batch):
    deals, _, _, words = big_batch
    assert word_leaks(deals, words) == []  # Plan 4b: a real problem and a clean fact share every reveal word
```

In `tests/generator/test_padding.py`, replace:

```python
from acqlab.generator.render import LABELS, SUPPORT, TERM, render, teaser_text
```

with:

```python
from acqlab.generator.render import LABELS, TERM, render, teaser_text
```

In `tests/generator/test_padding.py`, replace:

```python
BANNED = (tuple(TOPIC_WORDS.values()) + LEAK_WORDS + tuple(LABELS.values()) + tuple(SUPPORT.values())
```

with:

```python
BANNED = (tuple(TOPIC_WORDS.values()) + LEAK_WORDS + tuple(LABELS.values())
```

In `tests/routers/test_track_a.py`, replace:

```python
    key = next(k for k in keys if any(f.role != "clean" for f in k.truth.facts))
    problem = next(f.trap for f in key.truth.facts if f.role != "clean")
```

with:

```python
    key = next(k for k in keys if any(f.role != "clean" for f in k.truth.facts))
    # enough budget to read every fact, so the premise (the sweep can reach the problem) holds whatever its placement
    key = key.model_copy(update={"budget": sum(key.retrieval_cost.values())})
    problem = next(f.trap for f in key.truth.facts if f.role != "clean")
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest -q tests/generator/test_render.py tests/generator/test_validate.py`
Expected: FAIL. `span` can't be imported, and the word-leak test finds leaks.

- [ ] **Step 3: Make placement role-blind** (`acqlab/generator/truth.py`)

In `acqlab/generator/truth.py`, replace:

```python
GENERATOR_VERSION = "3.0.0"
```

with:

```python
GENERATOR_VERSION = "4.0.0"
```

In `acqlab/generator/truth.py`, replace:

```python
PLACEMENT = {  # mode weights by role: decoys lean loud, flippers lean buried (design §4)
    "flipper": {"explicit": 1, "footnote": 2, "calculation": 2, "contradicted": 1},
    "interaction": {"explicit": 1, "footnote": 2, "calculation": 2, "contradicted": 1},
    "decoy": {"explicit": 3, "footnote": 1, "calculation": 1, "contradicted": 1},
    "clean": {"explicit": 2, "footnote": 1, "calculation": 1},
    "unresolvable": {"range": 1},
}
```

with:

```python


def _role_blind(weights: dict[str, float]) -> dict[str, dict[str, float]]:
    """Placement weights (mode -> weight) for every role alike, so where a sentence sits says nothing about whether it
    is a real problem (Plan 4b: search is back, and it would see a role-dependent placement). An unresolvable fact
    states its range in the same places, except a calculation."""
    return {r: weights for r in ("flipper", "interaction", "decoy", "clean")} | {
        "unresolvable": {k: w for k, w in weights.items() if k != "calculation"}}


PLACEMENT = _role_blind({"explicit": 2, "footnote": 2, "calculation": 2, "contradicted": 1})
```

- [ ] **Step 4: Share every reveal sentence** (`acqlab/generator/render.py`)

In `acqlab/generator/render.py`, replace (the range sentences that used it are gone):

```python
SUPPORT = {"earnout": "earnout calculation", "pension": "actuarial valuation",
           "deferred_revenue": "deferred revenue roll-forward"}
BOILERPLATE = (
```

with:

```python
BOILERPLATE = (
```

In `acqlab/generator/render.py`, replace:

```python
def _clean_item_severity(rng: np.random.Generator) -> float:
```

with:

```python
def span(low: float, high: float) -> str:
    """A $M range with one unit sign ("$6.8–$19.2M"), so it holds as many words as a single amount."""
    return f"${low:,.1f}–{money(high)}"


def _span(f: Fact) -> str:
    """An unresolvable fact's documented range, written where a resolved fact writes its amount (no extra words)."""
    return span(*f.documented)


def _clean_item_severity(rng: np.random.Generator) -> float:
```

In `acqlab/generator/render.py`, replace:

```python
    if f.placement in ("explicit", "contradicted"):
        qoe = ("We do not accept {{label}} of {{item}} as an add-back: the cost recurred in each of the last three "
               "years and is expected to continue." if trap else
               "We accept {{label}} of {{item}} as an add-back: the cost arose once and has not recurred.")
        if f.placement == "contradicted":
            qoe = "Contrary to the CIM, {{label}} recur every year; we do not accept the {{item}} add-back."
    elif f.placement == "footnote":
        note = ("Note 9 — {{label_cap}}. The Company incurred {{label}} of {{item}} in {{fy_last}}; similar costs were "
                "incurred in each prior year and management expects them to continue." if trap else
                "Note 9 — {{label_cap}}. The Company incurred {{label}} of {{item}} in {{fy_last}}; no similar costs "
                "were incurred in prior years and none are expected.")
```

with:

```python
    # A real problem and a clean fact share each sentence word for word; only the numbers differ (Plan 4b).
    if f.placement in ("explicit", "contradicted"):  # contradicted: the CIM's one-time claim is the other side
        qoe = ("We reviewed the add-back for {{label}} of {{item}}. Of this, {{recurring}} recurred in each of the "
               "last three years and is expected to continue, so we exclude it from adjusted EBITDA.")
    elif f.placement == "footnote":
        note = ("Note 9 — {{label_cap}}. The Company incurred {{label}} of {{item}} in {{fy_last}}. Of this, "
                "{{recurring}} was also incurred in each prior year and is expected to continue.")
```

In `acqlab/generator/render.py`, replace:

```python
    elif f.placement == "range":
        qoe = ("We could not determine whether {{label}} will recur. Between {{low}} and {{high}} of the {{item}} "
               "add-back may prove recurring; supporting invoices were not provided.")
    vals = dict(label=lab, label_cap=_cap(lab), item=money(item), fy_last=FY_LAST)
    if f.documented:
        vals |= dict(low=money(f.documented[0]), high=money(f.documented[1]))
```

with:

```python
    vals = dict(label=lab, label_cap=_cap(lab), item=money(item), fy_last=FY_LAST,
                recurring=_span(f) if f.documented else money(item if trap else 0.0))
```

In `acqlab/generator/render.py`, replace:

```python
           "calculation": ["audited"], "range": ["qoe"]}[f.placement]
```

with:

```python
           "calculation": ["audited"]}[f.placement]
```

In `acqlab/generator/render.py`, replace:

```python
    vals = dict(label=lab, label_cap=_cap(lab), amount=money(f.amount), support=SUPPORT.get(f.variant, ""))
```

with:

```python
    vals = dict(label=lab, label_cap=_cap(lab), amount=money(f.amount))
```

In `acqlab/generator/render.py`, replace:

```python
            legal = ("We represent the Company in a {{label}}. We expect it to settle for {{amount}}, payable by the "
                     "Company." if trap else "The {{label}} against the Company was dismissed; there is no liability.")
        elif f.placement == "calculation":
            gross = round(f.amount + (float(np.round(f.worst * 0.3, 1)) if trap else 0.0), 1) if trap else 0.0
            insured = round(gross - f.amount, 1) if trap else 0.0
            legal = ("A {{label}} claims damages of {{gross}}. Insurance available to cover the claim is {{settled}}; "
                     "the Company bears the rest." if trap else
                     "The {{label}} against the Company was dismissed; there is no liability.")
```

with:

```python
            legal = ("We represent the Company in a {{label}}. We expect it to settle for {{amount}}, payable by the "
                     "Company.")
        elif f.placement == "calculation":
            gross = round(f.amount + float(np.round(f.worst * 0.3, 1)), 1)  # clean: insurance covers the whole claim
            insured = round(gross - f.amount, 1)
            legal = ("A {{label}} claims damages of {{gross}}. Insurance available to cover the claim is {{settled}}; "
                     "the Company bears the rest.")
```

In `acqlab/generator/render.py`, replace:

```python
        elif f.placement == "range":
            legal = ("We cannot predict the outcome of the {{label}}; a settlement between {{low}} and {{high}} "
                     "is possible.")
    else:
        docs = {"explicit": ["qoe"], "footnote": ["audited"], "calculation": ["audited"],
                "contradicted": ["cim", "audited"], "range": ["audited"]}[f.placement]
        if f.placement == "explicit":
            qoe = ("Debt-like items: we identify a {{label}} of {{amount}}, which should be treated as debt at closing."
                   if trap else "Debt-like items: we reviewed any {{label}} and identify no amount to be treated as "
                   "debt at closing.")
        elif f.placement in ("footnote", "contradicted"):
            note = ("Note 12 — Commitments and contingencies. The Company has a {{label}} of {{amount}}, payable "
                    "within twelve months of closing." if trap else
                    "Note 12 — Commitments and contingencies. The Company has no {{label}}.")
```

with:

```python
    else:
        docs = {"explicit": ["qoe"], "footnote": ["audited"], "calculation": ["audited"],
                "contradicted": ["cim", "audited"]}[f.placement]
        if f.placement == "explicit":
            qoe = "Debt-like items: we identify a {{label}} of {{amount}}, which should be treated as debt at closing."
        elif f.placement in ("footnote", "contradicted"):
            note = ("Note 12 — Commitments and contingencies. The Company has a {{label}} of {{amount}}, payable "
                    "within twelve months of closing.")
```

In `acqlab/generator/render.py`, replace:

```python
        elif f.placement == "range":
            note = ("Note 12 — Commitments and contingencies. Management estimates the {{label}} at between {{low}} "
                    "and {{high}}; the supporting {{support}} is referenced but was not provided.")
    ev_formula, ev_vals = _range_evidence(f, vals, ev_formula, ev_vals)
    sites = {"cim.debt"
```

with:

```python
    ev_formula, ev_vals = _range_evidence(f, vals, ev_formula, ev_vals)
    if f.documented:
        vals["amount"] = _span(f)
    sites = {"cim.debt"
```

In `acqlab/generator/render.py`, replace:

```python
    notice = "Purchase volumes are reviewed with {{customer}} each year."
```

with:

```python
    notice = "Purchase volumes of {{purchases}} are reviewed with {{customer}} each year."  # one $ figure, as always
```

In `acqlab/generator/render.py`, replace:

```python
            "calculation": ["cim", "contract_1"], "range": ["contract_1"]}[f.placement]
    if f.placement in ("explicit", "contradicted"):
        notice = ("{{customer}} has notified the Company that, because {{reason}}, it will reduce annual purchases by "
                  "{{amount}} from {{fy_next}}." if trap else "{{customer}} has confirmed it will renew on the same "
                  "terms.")
    elif f.placement == "footnote":
        note = ("Note 14 — Subsequent events. After year end, {{customer}} gave notice that, because {{reason}}, it "
                "will reduce annual purchases by {{amount}}." if trap else
                "Note 14 — Subsequent events. After year end, {{customer}} confirmed its purchase commitments for the "
                "coming year.")
    elif f.placement == "calculation":
        fraction = f.amount / purchases if trap else 0.0
        notice = ("{{customer}} has given notice that, because {{reason}}, it will move {{fraction}} of its volume to "
                  "another supplier." if trap else "{{customer}} has confirmed it will keep all of its volume.")
```

with:

```python
            "calculation": ["cim", "contract_1"]}[f.placement]
    if f.placement in ("explicit", "contradicted"):
        notice = ("{{customer}} has set out its purchase plans for {{fy_next}}: annual purchases will fall by "
                  "{{amount}}.")
    elif f.placement == "footnote":
        note = ("Note 14 — Subsequent events. After year end, {{customer}} set out its purchase plans: annual "
                "purchases will fall by {{amount}}.")
    elif f.placement == "calculation":
        fraction = f.amount / purchases if trap else 0.0
        notice = ("{{customer}} has set out its purchase plans for {{fy_next}}: it will move {{fraction}} of its "
                  "{{purchases}} of annual purchases to another supplier.")
```

In `acqlab/generator/render.py`, replace:

```python
    elif f.placement == "range":
        notice = ("{{customer}} is re-tendering this contract and the outcome is expected after closing. Management "
                  "estimates that {{low}} to {{high}} of annual revenue is at risk.")
    ev_formula, ev_vals = _range_evidence(f, vals, ev_formula, ev_vals)
```

with:

```python
    ev_formula, ev_vals = _range_evidence(f, vals, ev_formula, ev_vals)
    if f.documented:
        vals["amount"] = _span(f)
```

In `acqlab/generator/render.py`, replace:

```python
    docs = {"explicit": ["qoe"], "contradicted": ["cim", "qoe"], "footnote": ["audited"], "calculation": ["qoe"],
            "range": ["qoe"]}[f.placement]
    extra: list = []
    if f.placement in ("explicit", "contradicted"):
        qoe = ("At closing, net working capital is expected to be {{amount}} below the peg because of {{label}}."
               if trap else "At closing, net working capital is expected to be in line with the peg; we found no "
               "{{label}}.")
    elif f.placement == "footnote":
        note = ("Note 6 — Working capital. At year end, {{label}} reduced net working capital by {{amount}} below "
                "normal levels." if trap else "Note 6 — Working capital. At year end, net working capital was at "
                "normal levels, with no {{label}}.")
```

with:

```python
    docs = {"explicit": ["qoe"], "contradicted": ["cim", "qoe"], "footnote": ["audited"],
            "calculation": ["qoe"]}[f.placement]
    extra: list = []
    if f.placement in ("explicit", "contradicted"):
        qoe = ("At closing, net working capital is expected to be {{amount}} below the peg; our review covered "
               "{{label}}.")
    elif f.placement == "footnote":
        note = ("Note 6 — Working capital. At year end, net working capital was {{amount}} below normal levels; the "
                "review covered {{label}}.")
```

In `acqlab/generator/render.py`, replace:

```python
    elif f.placement == "range":
        qoe = ("Net working capital at closing could fall between {{low}} and {{high}} below the peg; the closing "
               "balance sheet was not provided.")
    ev_formula, ev_vals = _range_evidence(f, vals, ev_formula, ev_vals)
```

with:

```python
    ev_formula, ev_vals = _range_evidence(f, vals, ev_formula, ev_vals)
    if f.documented:
        vals["amount"] = _span(f)
```

In `acqlab/generator/render.py`, replace:

```python
            "calculation": ["assets"], "range": ["assets"]}[f.placement]
    if f.placement in ("explicit", "contradicted"):
        review = ("Condition review: {{label}} requires additional capital expenditure of {{amount}} per year over "
                  "the plan." if trap else "Condition review: we found no {{label}}; no additional capital "
                  "expenditure is required.")
    elif f.placement == "footnote":
        note = ("Note 7 — Property, plant and equipment. Because of {{label}}, management expects additional capital "
                "expenditure of {{amount}} per year." if trap else "Note 7 — Property, plant and equipment. "
                "Management expects no additional capital expenditure; there is no {{label}}.")
    elif f.placement == "calculation":
        gross = round(f.amount * 5, 1)
        review = ("Replacement cost of {{label}}: {{gross}}, to be spent evenly over the {{years}}-year plan."
                  if trap else "Replacement cost of {{label}}: none identified.")
```

with:

```python
            "calculation": ["assets"]}[f.placement]
    if f.placement in ("explicit", "contradicted"):
        review = ("Condition review: additional capital expenditure for {{label}} of {{amount}} per year is required "
                  "over the plan.")
    elif f.placement == "footnote":
        note = ("Note 7 — Property, plant and equipment. Management expects additional capital expenditure for "
                "{{label}} of {{amount}} per year.")
    elif f.placement == "calculation":
        gross = round(f.amount * 5, 1)
        review = "Replacement cost of {{label}}: {{gross}}, to be spent evenly over the {{years}}-year plan."
```

In `acqlab/generator/render.py`, replace:

```python
    elif f.placement == "range":
        review = ("An engineering survey was commissioned but not provided. Management estimates additional capital "
                  "expenditure for {{label}} of {{low}} to {{high}} per year.")
    ev_formula, ev_vals = _range_evidence(f, vals, ev_formula, ev_vals)
```

with:

```python
    ev_formula, ev_vals = _range_evidence(f, vals, ev_formula, ev_vals)
    if f.documented:
        vals["amount"] = _span(f)
```

- [ ] **Step 5: Check ranges as they are written** (`acqlab/generator/validate.py`)

In `acqlab/generator/validate.py`, replace:

```python
from acqlab.generator.render import FILLER, LABELS, Evidence, answer
```

with:

```python
from acqlab.generator.render import FILLER, LABELS, Evidence, answer, span
```

In `acqlab/generator/validate.py`, replace:

```python
        for name, v in ev.values.items():
            shown = pct(v) if name == "fraction" else money(v)
            if shown not in body:
```

with:

```python
        shown_all = ({"range": span(ev.values["low"], ev.values["high"])} if ev.formula == "range" else
                     {name: pct(v) if name == "fraction" else money(v) for name, v in ev.values.items()})
        for name, shown in shown_all.items():
            if shown not in body:
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `uv run pytest -q`
Expected: 209 passed (207 before this task, plus the two new render tests).

- [ ] **Step 7: Commit**

```bash
git add acqlab/generator/render.py acqlab/generator/truth.py acqlab/generator/validate.py tests/generator/test_render.py tests/generator/test_validate.py tests/generator/test_padding.py tests/routers/test_track_a.py
git commit -m "feat(generator): search-safe reveal wording and role-blind placement (generator 4.0.0)

A real problem and a clean fact now share every reveal sentence (only the numbers differ), and placement
no longer depends on the fact's role: word leaks on 500 deals fall from 48 to 0.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Search comes back, and every system gets the same diligence knowledge

**Files:**
- Create: `acqlab/agents/knowledge.py`
- Modify: `acqlab/agents/server.py`, `acqlab/agents/prompts.py`, `acqlab/dataroom/tools.py`, `acqlab/generator/batch.py`
- Modify: `tests/agents/test_server.py`, `tests/agents/test_solver.py`, `tests/generator/test_tools.py`, `tests/generator/test_batch.py`

**Interfaces:**
- Consumes: Task 1's shared wording, which is what makes search safe.
- Produces:
  - **`acqlab.agents.knowledge`:**
    - `DILIGENCE_MAP: dict[str, tuple[str, ...]]`
    - `typical_high(trap: str, t: Teaser) -> float`
    - `GUIDE: str`

    `server.py` no longer defines these; it imports them.
  - **The `search` tool** (both systems): `{"query": str}` → a list of up to 5 document ids. It costs 1 unit.
  - **`batch.run`:**
    - Word leaks on a batch of ≥ 100 deals are batch problems, in the form `"word leak: ..."`.
    - It always writes `<out>/problems.json`, the list of problems.

- [ ] **Step 1: Write the failing tests**

In `tests/agents/test_server.py`, replace:

```python
from acqlab.agents.server import MAX_CALLS, Session, tool_names
```

with:

```python
from acqlab.agents.knowledge import typical_high
from acqlab.agents.server import MAX_CALLS, Session, tool_names
```

In `tests/agents/test_server.py`, replace:

```python
def test_search_is_not_offered(data, tmp_path):
    """Search hit counts give traps away until the reveal wording is fixed (Plan 4b)."""
    assert "search" not in tool_names(router=True)
    assert _session(data, tmp_path).call("search", {"query": "confirmed"})["isError"]
```

with:

```python
def test_search_costs_one_unit_and_returns_document_ids_but_no_text(data, tmp_path):
    s = _session(data, tmp_path, router=False)
    assert "search" in tool_names(router=False) and "search" in tool_names(router=True)
    got = _out(s.call("search", {"query": "working capital peg"}))
    assert got and all(d in s.pages for d in got) and len(got) == len(set(got)) <= 5
    assert _trace(tmp_path)[0]["cost"] == 1.0 and "$" not in json.dumps(got)
```

In `tests/agents/test_server.py`, replace:

```python
    hi = {t: max(h, server.typical_high(t, s.face.teaser))
```

with:

```python
    hi = {t: max(h, typical_high(t, s.face.teaser))
```

In `tests/agents/test_solver.py`, replace:

```python
from acqlab.agents.prompts import ROUTER, system_prompt, user_prompt
```

with:

```python
from acqlab.agents.knowledge import GUIDE
from acqlab.agents.prompts import ROUTER, system_prompt, user_prompt
```

In `tests/agents/test_solver.py`, replace:

```python
    assert system_prompt(True).replace(ROUTER, "") == system_prompt(False)
```

with:

```python
    assert system_prompt(True).replace(ROUTER, "") == system_prompt(False)
    assert GUIDE in system_prompt(False) and "search" in system_prompt(False)  # the same knowledge for every system
```

In `tests/generator/test_tools.py`, replace:

```python
    assert all(len(h["snippet"]) <= 150 and h["doc_id"] for h in hits)
```

with:

```python
    assert all(len(h["snippet"]) <= 150 and h["doc_id"] for h in hits)
    assert dr.search("0 2025") == []  # letters only: numbers such as a clean fact's $0.0M can't be searched for
```

In `tests/generator/test_batch.py`, replace:

```python
    assert batch.run(tmp_path, COUNTS, mc=20) == []
    splits = json.loads((tmp_path / "splits.json").read_text())
```

with:

```python
    assert batch.run(tmp_path, COUNTS, mc=20) == []
    assert json.loads((tmp_path / "problems.json").read_text()) == []  # saved for the calibration check
    splits = json.loads((tmp_path / "splits.json").read_text())
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest -q tests/agents tests/generator/test_tools.py tests/generator/test_batch.py`
Expected: FAIL. `acqlab.agents.knowledge` doesn't exist yet.

- [ ] **Step 3: Create `acqlab/agents/knowledge.py`**

Create `acqlab/agents/knowledge.py`:

```python
"""General diligence knowledge every system gets (reframe design §3, fairness): where each issue type is usually
settled, and its usual size. S4 and the router use it in code; single-agent systems get the same facts in their prompt.
The same for every deal: nothing here is read from a deal."""
from acqlab.generator.sample import Teaser

# Where an analyst looks first. "contract" means the customer contracts in id order.
DILIGENCE_MAP = {"addback": ("qoe", "audited", "cim"), "debt_like": ("audited", "legal", "qoe"),
                 "concentration": ("contract", "cim", "audited"), "nwc": ("qoe", "audited"),
                 "capex": ("assets", "cim", "audited")}


def typical_high(trap: str, t: Teaser) -> float:
    """Top of the usual size range ($M) for each issue type, from teaser numbers only.
    ponytail: the generator's worst-case ranges re-expressed in visible numbers; swap in sourced industry ranges when
    those exist."""
    return {"addback": min(t.claimed_addbacks, 0.25 * t.adj_ebitda), "debt_like": 0.20 * t.asking_price,
            "concentration": 0.25 * t.revenue_ltm, "nwc": 0.20 * t.nwc_pct * t.revenue_ltm,
            "capex": 0.03 * t.revenue_ltm}[trap]


GUIDE = """Where problems usually show up, and how big they usually are (general practice; any document may hold \
the answer):
- Add-backs that are not really one-time: the QoE report first, then the audited notes, then the CIM. Usually up to \
the claimed add-backs, and at most 25% of adjusted EBITDA.
- Debt-like items payable at closing: the audited notes first, then the legal letter, then the QoE. Usually up to 20% \
of the asking price.
- Revenue lost from a customer: the customer contracts first, then the CIM, then the audited notes. Usually up to 25% \
of revenue a year.
- Net working capital below normal at closing: the QoE report first, then the audited notes. Usually up to 20% of \
normal net working capital (the teaser's percentage of revenue).
- Extra capital expenditure: the fixed asset schedule first, then the CIM, then the audited notes. Usually up to 3% of \
revenue a year."""
```

- [ ] **Step 4: The server imports the knowledge and offers search** (`acqlab/agents/server.py`)

In `acqlab/agents/server.py`, replace:

```python
"""Tool server for one solver run (Plan 4a design §2): the data room, the engine, issue notes and, for the router
system, router 6. No search: its hit counts give traps away until Plan 4b fixes the reveal wording (see
validate.word_leaks). Speaks MCP over stdio (one JSON-RPC message per line) with the standard library only. It reads only
```

with:

```python
"""Tool server for one solver run (Plan 4a design §2): the data room, search, the engine, issue notes and, for the
router system, router 6. Search came back in Plan 4b, once a real problem and a clean fact share every reveal word
(validate.word_leaks is empty); it returns document ids, never text. Speaks MCP over stdio (one JSON-RPC message per
line) with the standard library only. It reads only
```

In `acqlab/agents/server.py`, replace:

```python
from acqlab.dataroom.tools import BudgetExceeded, DataRoom
```

with:

```python
from acqlab.agents.knowledge import DILIGENCE_MAP, typical_high
from acqlab.dataroom.tools import BudgetExceeded, DataRoom
```

In `acqlab/agents/server.py`, replace:

```python
MAX_CALLS = 80  # after this many calls only submit is accepted
# Router v3: where an analyst looks first to settle each issue type, the same for every deal (general diligence
# practice, not read from any deal). "contract" means the customer contracts in id order.
DILIGENCE_MAP = {"addback": ("qoe", "audited", "cim"), "debt_like": ("audited", "legal", "qoe"),
                 "concentration": ("contract", "cim", "audited"), "nwc": ("qoe", "audited"),
                 "capex": ("assets", "cim", "audited")}


def typical_high(trap: str, t: Teaser) -> float:
    """Router v4: the top of the usual size range for each issue type, from teaser numbers only; the router widens
    a note's range up to this. ponytail: the generator's worst-case ranges re-expressed in visible numbers; swap in
    sourced industry ranges when those exist."""
    return {"addback": min(t.claimed_addbacks, 0.25 * t.adj_ebitda), "debt_like": 0.20 * t.asking_price,
            "concentration": 0.25 * t.revenue_ltm, "nwc": 0.20 * t.nwc_pct * t.revenue_ltm,
            "capex": 0.03 * t.revenue_ltm}[trap]
N_WORLDS = 400
```

with:

```python
MAX_CALLS = 80  # after this many calls only submit is accepted
N_WORLDS = 400
```

In `acqlab/agents/server.py`, replace:

```python
    "open_document": ("Costs 1 unit per page. The document's full text. With the router, needs at least one open "
```

with:

```python
    "search": ("Costs 1 unit. The ids of up to 5 documents with paragraphs matching the most of your words (letters "
               "only, no numbers). No text: open a document to read it.",
               {**_OBJ, "properties": {"query": {"type": "string"}}, "required": ["query"]}),
    "open_document": ("Costs 1 unit per page. The document's full text. With the router, needs at least one open "
```

In `acqlab/agents/server.py`, replace:

```python
    def _open_document(self, doc_id: str) -> str:
```

with:

```python
    def _search(self, query: str) -> list[str]:
        """Where words appear, not what the documents say: text costs pages, so a 1-unit search can't read an answer."""
        return list(dict.fromkeys(h["doc_id"] for h in self.room.search(str(query))))

    def _open_document(self, doc_id: str) -> str:
```

- [ ] **Step 5: Search sees letters only** (`acqlab/dataroom/tools.py`)

In `acqlab/dataroom/tools.py`, replace:

```python
def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))
```

with:

```python
def _words(text: str) -> set[str]:
    """Letters only: search sees what validate.doc_words audits, so a number (such as a clean fact's $0.0M) can't be
    searched for."""
    return set(re.findall(r"[a-z]+", text.lower()))
```

- [ ] **Step 6: Put search and the guide in every prompt** (`acqlab/agents/prompts.py`)

In `acqlab/agents/prompts.py`, replace:

```python
"""Solver prompts (Plan 4a design §2). The two systems differ only by the rank_issues paragraph; any edit made after
the smoke run goes to both and is logged in docs/results/plan-4a-prompt-log.md."""
```

with:

```python
"""Solver prompts (Plan 4a design §2). The two systems differ only by the router paragraph; any edit made after
the smoke run goes to both and is logged in docs/results/plan-4a-prompt-log.md. Every system gets the same general
diligence knowledge (knowledge.GUIDE; reframe design §3)."""
from acqlab.agents.knowledge import GUIDE
```

In `acqlab/agents/prompts.py`, replace:

```python
Tools that do not read documents are free.
```

with:

```python
search costs 1 unit and tells you which documents mention your words, without their text. Other tools are free.
```

In `acqlab/agents/prompts.py`, replace:

```python
difference."""
```

with:

```python
difference.

{guide}"""
```

In `acqlab/agents/prompts.py`, replace:

```python
    return _BASE.format(router=ROUTER if router else "")
```

with:

```python
    return _BASE.format(router=ROUTER if router else "", guide=GUIDE)
```

- [ ] **Step 7: Word leaks are batch problems, and problems are saved** (`acqlab/generator/batch.py`)

In `acqlab/generator/batch.py`, replace:

```python
        print(f"NOTE: {len(leaks)} word-level leaks (see word_leaks.json); agents get no search tool until Plan 4b")
    if extract is not None:
        problems += _recoverability(out, keys, splits, recover, extract)
```

with:

```python
        # agents can search since Plan 4b, so a word that separates trap deals from clean ones is a real leak
        problems += [f"word leak: {r['word']!r} in {r['doc']} (AUC {r['auc']}) for {r['trap']}" for r in leaks]
    if extract is not None:
        problems += _recoverability(out, keys, splits, recover, extract)
    (out / "problems.json").write_text(json.dumps(problems, indent=2))  # the calibration check reads it
```

- [ ] **Step 8: Run the tests to see them pass**

Run: `uv run pytest -q`
Expected: 209 passed. Tests were replaced and extended, not added, so the count doesn't change.

- [ ] **Step 9: Commit**

```bash
git add acqlab/agents/knowledge.py acqlab/agents/server.py acqlab/agents/prompts.py acqlab/dataroom/tools.py acqlab/generator/batch.py tests/agents/test_server.py tests/agents/test_solver.py tests/generator/test_tools.py tests/generator/test_batch.py
git commit -m "feat(agents): search returns (document ids, letters only); every system gets the same diligence guide

Word leaks are now batch problems, and each batch saves problems.json.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Difficulty profiles and the board minutes

**Files:**
- Modify: `acqlab/generator/truth.py`, `acqlab/generator/render.py`, `acqlab/generator/padding.py`, `acqlab/generator/validate.py`, `acqlab/generator/batch.py`
- Modify: `tests/generator/test_truth.py`, `tests/generator/test_render.py`, `tests/generator/test_batch.py`, `tests/generator/test_validate.py`

**Interfaces:**
- Consumes:
  - `truth._role_blind`, `truth.PLACEMENT` and `render.span` (Task 1).
  - `problems.json` (Task 2).
- Produces:
  - **`truth.PROFILES`:** `{"base", "r1", "r2", "r3"}`. Each profile is `{"case_mix", "placement", "budget_share", "clean_item_power"}`.
  - **Profile threading:**
    - `DealTruth.profile: str = "base"`
    - `generate(..., profile="base")`
    - `batch.build(..., profile=)`
    - `batch.run(..., profile=)`
    - `batch --profile`
  - **The `board_minutes` document:** in every room, with domain `"governance"`. Under `r2` and `r3` it can hold a fact (placement `"minutes"`).
  - **`render.MINUTES_TITLE`.**
  - **Filler:** three to four random filler documents instead of four to five.

- [ ] **Step 1: Write the failing tests**

In `tests/generator/test_truth.py`, replace:

```python
from acqlab.generator.truth import cross_fit, generate, prior_draws, simulate, value_groups, value_of_knowing
```

with:

```python
from acqlab.generator.truth import (PROFILES, cross_fit, generate, prior_draws, simulate, value_groups,
                                   value_of_knowing)
```

Append to `tests/generator/test_truth.py`:

```python


def test_profiles_raise_the_share_of_interaction_deals_and_make_placement_role_blind():
    base = [generate(f"b{s}", "test", s, mc=4) for s in range(60)]
    hard = [generate(f"h{s}", "test", s, mc=4, profile="r2") for s in range(60)]
    assert all(t.profile == "base" for t in base) and all(t.profile == "r2" for t in hard)
    assert sum(t.case_type == "interaction" for t in hard) > sum(t.case_type == "interaction" for t in base)
    for t in hard:  # r2: every role draws from the same placements; unresolvable facts too, less calculation
        for f in t.facts:
            assert f.placement in PROFILES["r2"]["placement"][f.role]
            assert f.role != "unresolvable" or f.placement != "calculation"
    assert any(f.placement == "minutes" for t in hard for f in t.facts)
    assert PROFILES["r3"]["budget_share"] < PROFILES["r2"]["budget_share"]
```

In `tests/generator/test_render.py`, replace:

```python
from acqlab.generator.truth import generate
```

with:

```python
from acqlab.generator.truth import generate
from acqlab.generator.validate import check_consistency
```

In `tests/generator/test_render.py`, replace:

```python
CORE = {"cim", "qoe", "audited", "credit", "contract_1", "assets", "legal"}
```

with:

```python
CORE = {"cim", "qoe", "audited", "credit", "contract_1", "assets", "legal", "board_minutes"}
```

In `tests/generator/test_render.py`, replace:

```python
        assert 4 <= sum(d.domain == "filler" for d in docs) <= 5
```

with:

```python
        assert 3 <= sum(d.domain == "filler" for d in docs) <= 4
```

In `tests/generator/test_render.py`, replace:

```python
        for placement in ("explicit", "footnote", "calculation", "contradicted"):
```

with:

```python
        for placement in ("explicit", "footnote", "calculation", "contradicted", "minutes"):
```

Append to `tests/generator/test_render.py`:

```python


def test_board_minutes_hold_a_line_on_every_topic_and_the_answer_when_placed_there():
    deals = [generate(f"m{s}", "test", s, mc=4, profile="r2") for s in range(30)]
    placed = 0
    for t in deals:
        docs, evidence = render(t)
        minutes = next(d for d in docs if d.id == "board_minutes").render()
        assert minutes.count("The board reviewed") == 5, t.id
        assert check_consistency(t, docs, evidence) == [], t.id
        for f, ev in zip(t.facts, evidence):
            if f.placement == "minutes":
                placed += 1
                assert ev.docs == ["board_minutes"]
    assert placed >= 10
```

In `tests/generator/test_batch.py`, replace:

```python
from acqlab.generator import batch
```

with:

```python
from acqlab.generator import batch
from acqlab.generator.truth import PROFILES
```

In `tests/generator/test_batch.py`, replace:

```python
def test_cli_runs_without_an_llm(tmp_path):
```

with:

```python
def test_a_profile_sets_the_deals_and_the_budget_share(tmp_path):
    assert batch.run(tmp_path, {"dev": 2, "test": 0, "hand": 0, "showcase": 0}, mc=20, profile="r3") == []
    key = json.loads((tmp_path / "truth" / "dev-000.json").read_text())
    pages = sum(d["pages"] for d in DataRoom(tmp_path / "deals" / "dev-000" / "room").list_documents())
    assert key["truth"]["profile"] == "r3" and key["budget"] == math.ceil(PROFILES["r3"]["budget_share"] * pages)


def test_cli_runs_without_an_llm(tmp_path):
```

In `tests/generator/test_validate.py`, replace:

```python
    assert word_leaks(deals, words) == []  # Plan 4b: a real problem and a clean fact share every reveal word
```

with:

```python
    assert word_leaks(deals, words) == []  # Plan 4b: a real problem and a clean fact share every reveal word
    from acqlab.generator.padding import pad
    hard = [generate(f"q{s}", "test", s, mc=4, profile="r2") for s in range(100)]  # the hardest placements too
    assert word_leaks(hard, {t.id: doc_words(pad(render(t)[0], t.base, t.style, t.seed)) for t in hard}) == []
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest -q tests/generator`
Expected: FAIL. `PROFILES` can't be imported.

- [ ] **Step 3: Add the profiles** (`acqlab/generator/truth.py`)

In `acqlab/generator/truth.py`, replace:

```python
PLACEMENT = _role_blind({"explicit": 2, "footnote": 2, "calculation": 2, "contradicted": 1})
```

with:

```python
PLACEMENT = _role_blind({"explicit": 2, "footnote": 2, "calculation": 2, "contradicted": 1})
# Reframe design §4: the difficulty levers, pulled in this order by calibration (base, then r1, r2, r3). Fixed before
# any calibration run.
# - r1: two-issue interaction deals 2.5x as common; flip + interaction stays at 35% so the go rate stays near half.
# - r2: evidence more buried: less explicit, more contradicted, and the board minutes as a place.
# - r3: a tighter budget.
# clean_item_power shapes a clean add-back's line item to match trap sizes under that case mix (render).
_MULTI_ISSUE = {"clean": 0.15, "flip": 0.10, "interaction": 0.25, "none": 0.50}
_BURIED = _role_blind({"explicit": 1, "footnote": 2, "calculation": 2, "contradicted": 2, "minutes": 2})
PROFILES = {
    "base": {"case_mix": CASE_MIX, "placement": PLACEMENT, "budget_share": 0.25, "clean_item_power": 0.7},
    "r1": {"case_mix": _MULTI_ISSUE, "placement": PLACEMENT, "budget_share": 0.25, "clean_item_power": 1.0},
    "r2": {"case_mix": _MULTI_ISSUE, "placement": _BURIED, "budget_share": 0.25, "clean_item_power": 1.0},
}
PROFILES["r3"] = PROFILES["r2"] | {"budget_share": 0.20}
```

In `acqlab/generator/truth.py`, replace:

```python
    case_type: str

```

with:

```python
    case_type: str
    profile: str = "base"  # difficulty profile (PROFILES); deals before generator 4.0.0 are "base"

```

In `acqlab/generator/truth.py`, replace:

```python
             max_tries: int = 500) -> DealTruth:
    rng = np.random.default_rng(seed)
    dev = split == "dev"
    case = force_case or _pick(rng, CASE_MIX)  # drawn once, so hard cases aren't swapped for easy ones on retry
```

with:

```python
             max_tries: int = 500, profile: str = "base") -> DealTruth:
    rng = np.random.default_rng(seed)
    dev = split == "dev"
    prof = PROFILES[profile]
    case = force_case or _pick(rng, prof["case_mix"])  # drawn once, so hard cases aren't swapped for easy ones on retry
```

In `acqlab/generator/truth.py`, replace:

```python
        facts = _facts(rng, b, roles, placed, dev)
        truth = _finish(deal_id, split, seed, rng, b, facts, mc)
```

with:

```python
        facts = _facts(rng, b, roles, placed, dev, prof["placement"])
        truth = _finish(deal_id, split, seed, rng, b, facts, mc, profile)
```

In `acqlab/generator/truth.py`, replace:

```python
def _facts(rng, b: BaseDeal, roles: dict[str, str], placed: dict[str, dict], dev: bool) -> list[Fact]:
```

with:

```python
def _facts(rng, b: BaseDeal, roles: dict[str, str], placed: dict[str, dict], dev: bool,
           placement: dict[str, dict[str, float]]) -> list[Fact]:
```

In `acqlab/generator/truth.py`, replace:

```python
                          placement=_pick(rng, PLACEMENT[roles[t]]), worst=worst, amount=amount,
```

with:

```python
                          placement=_pick(rng, placement[roles[t]]), worst=worst, amount=amount,
```

In `acqlab/generator/truth.py`, replace:

```python
def _finish(deal_id, split, seed, rng, b: BaseDeal, facts: list[Fact], mc: int) -> DealTruth | None:
```

with:

```python
def _finish(deal_id, split, seed, rng, b: BaseDeal, facts: list[Fact], mc: int, profile: str) -> DealTruth | None:
```

In `acqlab/generator/truth.py`, replace:

```python
                     case_type=case_type([f.role for f in facts]))
```

with:

```python
                     case_type=case_type([f.role for f in facts]), profile=profile)
```

- [ ] **Step 4: Add the board minutes and profile-shaped clean items** (`acqlab/generator/render.py`)

In `acqlab/generator/render.py`, replace:

```python
from acqlab.generator.truth import DealTruth, Fact
```

with:

```python
from acqlab.generator.truth import PROFILES, DealTruth, Fact
```

In `acqlab/generator/render.py`, replace:

```python
FILLER = {
    "board_minutes": "Board Meeting Minutes", "hr_policy": "Human Resources Policy Manual",
```

with:

```python
MINUTES_TITLE = "Board Meeting Minutes"  # a core document: under profiles r2 and r3 it can hold a fact's answer
FILLER = {
    "hr_policy": "Human Resources Policy Manual",
```

In `acqlab/generator/render.py`, replace:

```python
def _clean_item_severity(rng: np.random.Generator) -> float:
    """Severity for a clean add-back's line item, shaped like trap severities (quartiles about 0.5/0.7/0.9), so the
    item's size relative to the claimed add-backs says nothing about the fact's role."""
    return 0.2 + 0.8 * float(rng.random()) ** 0.7
```

with:

```python
def _minutes(sid: str, neutral: str, reveal: str, f: Fact, **vals: str) -> list:
    """The board minutes' line on a topic, in every deal: the reveal only when the fact is placed there ("minutes"),
    else a neutral line. Placement is role-blind, so the choice leaks nothing."""
    return [slot(sid, "Record the board's review of this topic", reveal if f.placement == "minutes" else neutral,
                 **vals)]


def _clean_item_severity(rng: np.random.Generator, power: float) -> float:
    """Severity for a clean add-back's line item, shaped like trap severities under the deal's case mix (base: quartiles
    about 0.5/0.7/0.9), so the item's size relative to the claimed add-backs says nothing about the fact's role."""
    return 0.2 + 0.8 * float(rng.random()) ** power
```

In `acqlab/generator/render.py`, replace:

```python
    clean_item = min(claimed, max(0.1, round(_clean_item_severity(rng) * f.worst, 1)))  # drawn for every role
```

with:

```python
    power = PROFILES[t.profile]["clean_item_power"]
    clean_item = min(claimed, max(0.1, round(_clean_item_severity(rng, power) * f.worst, 1)))  # drawn for every role
```

In `acqlab/generator/render.py`, replace:

```python
    sites["audited.is_rows"] = [rows] if rows else []
    doc = {"explicit": ["qoe"], "contradicted": ["cim", "qoe"], "footnote": ["audited"],
           "calculation": ["audited"]}[f.placement]
```

with:

```python
    sites["audited.is_rows"] = [rows] if rows else []
    sites["minutes.addback"] = _minutes("minutes_addback", "The board reviewed the add-back for {{label}}.",
                                        "The board reviewed the add-back for {{label}}: {{recurring}} of it recurs "
                                        "every year.", f, **vals)
    doc = {"explicit": ["qoe"], "contradicted": ["cim", "qoe"], "footnote": ["audited"],
           "calculation": ["audited"], "minutes": ["board_minutes"]}[f.placement]
```

In `acqlab/generator/render.py`, replace:

```python
        docs = ["cim", "legal"] if f.placement == "contradicted" else ["legal"]
```

with:

```python
        docs = {"contradicted": ["cim", "legal"], "minutes": ["board_minutes"]}.get(f.placement, ["legal"])
```

In `acqlab/generator/render.py`, replace:

```python
                "contradicted": ["cim", "audited"]}[f.placement]
```

with:

```python
                "contradicted": ["cim", "audited"], "minutes": ["board_minutes"]}[f.placement]
```

In `acqlab/generator/render.py`, replace:

```python
             "legal.letter": [slot("legal", "Write the litigation paragraph of a legal letter", legal, **vals)]}
```

with:

```python
             "legal.letter": [slot("legal", "Write the litigation paragraph of a legal letter", legal, **vals)],
             "minutes.debt": _minutes("minutes_debt", "The board reviewed any {{label}}.",
                                      "The board reviewed a {{label}} of {{amount}}, payable at closing.", f, **vals)}
```

In `acqlab/generator/render.py`, replace:

```python
            "calculation": ["cim", "contract_1"]}[f.placement]
```

with:

```python
            "calculation": ["cim", "contract_1"], "minutes": ["board_minutes"]}[f.placement]
```

In `acqlab/generator/render.py`, replace:

```python
             "audited.note14": _note("note14", "Write the subsequent-events note", note, **vals)}
```

with:

```python
             "audited.note14": _note("note14", "Write the subsequent-events note", note, **vals),
             "minutes.customer": _minutes("minutes_customer", "The board reviewed {{customer}}'s purchase plans.",
                                          "The board reviewed {{customer}}'s purchase plans: annual purchases will "
                                          "fall by {{amount}}.", f, **vals)}
```

In `acqlab/generator/render.py`, replace:

```python
            "calculation": ["qoe"]}[f.placement]
```

with:

```python
            "calculation": ["qoe"], "minutes": ["board_minutes"]}[f.placement]
```

In `acqlab/generator/render.py`, replace:

```python
             "cim.nwc": [slot("cim_nwc", "Comment on working capital", cim, **vals)]}
```

with:

```python
             "cim.nwc": [slot("cim_nwc", "Comment on working capital", cim, **vals)],
             "minutes.nwc": _minutes("minutes_nwc", "The board reviewed net working capital at closing.",
                                     "The board reviewed net working capital at closing: {{amount}} below the peg, "
                                     "covering {{label}}.", f, **vals)}
```

In `acqlab/generator/render.py`, replace:

```python
            "calculation": ["assets"]}[f.placement]
```

with:

```python
            "calculation": ["assets"], "minutes": ["board_minutes"]}[f.placement]
```

In `acqlab/generator/render.py`, replace:

```python
             "audited.note7": _note("note7", "Write the fixed-asset note", note, **vals)}
```

with:

```python
             "audited.note7": _note("note7", "Write the fixed-asset note", note, **vals),
             "minutes.capex": _minutes("minutes_capex", "The board reviewed {{label}}.",
                                       "The board reviewed {{label}}: additional capital expenditure of {{amount}} per "
                                       "year.", f, **vals)}
```

In `acqlab/generator/render.py`, replace:

```python
                                                                     *sites["legal.letter"], *boiler(1)]),
    ]
    for key in rng.choice(list(FILLER), int(rng.integers(4, 6)), replace=False):
```

with:

```python
                                                                     *sites["legal.letter"], *boiler(1)]),
        Doc(id="board_minutes", title=MINUTES_TITLE, domain="governance", blocks=[
            heading(style, 1, "Matters reviewed"), *sites["minutes.addback"], *sites["minutes.debt"],
            *sites["minutes.customer"], *sites["minutes.nwc"], *sites["minutes.capex"], *boiler(1)]),
    ]
    for key in rng.choice(list(FILLER), int(rng.integers(3, 5)), replace=False):
```

- [ ] **Step 5: Padding, validation and batch** (`padding.py`, `validate.py`, `batch.py`)

In `acqlab/generator/padding.py`, replace:

```python
def _kind(d: Doc) -> str:
    return "contract" if d.id.startswith("contract_") else "filler" if d.domain == "filler" else d.id
```

with:

```python
def _kind(d: Doc) -> str:
    """Padding kind. The board minutes pad like filler: neutral text around their per-topic lines."""
    return "contract" if d.id.startswith("contract_") else "filler" if d.domain == "filler" or d.id == "board_minutes" \
        else d.id
```

In `acqlab/generator/validate.py`, replace:

```python
from acqlab.generator.render import FILLER, LABELS, Evidence, answer, span
```

with:

```python
from acqlab.generator.render import FILLER, LABELS, MINUTES_TITLE, Evidence, answer, span
```

In `acqlab/generator/validate.py`, replace:

```python
               "Fixed Asset and Lease Schedule", "Legal Letter"} | set(FILLER.values()) | set(EXTRA_FILLER.values())
```

with:

```python
               "Fixed Asset and Lease Schedule", "Legal Letter", MINUTES_TITLE} | set(FILLER.values()) \
    | set(EXTRA_FILLER.values())
```

In `acqlab/generator/validate.py`, replace:

```python
PAGE_DOCS = ("cim", "qoe", "audited", "contract_1", "assets", "legal")  # every trap's evidence lives in these
PAGE_Z = 4.0  # flag a length gap wider than 4 standard errors (35 comparisons per batch, so false alarms are rare)
```

with:

```python
# every trap's evidence lives in these
PAGE_DOCS = ("cim", "qoe", "audited", "contract_1", "assets", "legal", "board_minutes")
PAGE_Z = 4.0  # flag a length gap wider than 4 standard errors (40 comparisons per batch, so false alarms are rare)
```

In `acqlab/generator/batch.py`, replace:

```python
  uv run python -m acqlab.generator.batch --out data --dev 50 --test 120 --hand 10
```

with:

```python
  uv run python -m acqlab.generator.batch --out data --dev 50 --test 120 --hand 10 [--profile r1]
```

In `acqlab/generator/batch.py`, replace:

```python
from acqlab.generator.truth import DealTruth, generate
```

with:

```python
from acqlab.generator.truth import PROFILES, DealTruth, generate
```

In `acqlab/generator/batch.py`, replace:

```python
def build(deal_id: str, split: str, seed: int, *, mc: int, llm=None) -> tuple[AnswerKey, list[Doc], str]:
```

with:

```python
def build(deal_id: str, split: str, seed: int, *, mc: int, llm=None,
          profile: str = "base") -> tuple[AnswerKey, list[Doc], str]:
```

In `acqlab/generator/batch.py`, replace:

```python
        t = generate(deal_id, split, seed + k * RETRY_SEED, mc=mc, force_case="flip" if split == "showcase" else None)
```

with:

```python
        t = generate(deal_id, split, seed + k * RETRY_SEED, mc=mc, force_case="flip" if split == "showcase" else None,
                     profile=profile)
```

In `acqlab/generator/batch.py`, replace:

```python
        extract=None) -> list[str]:
```

with:

```python
        extract=None, profile: str = "base") -> list[str]:
```

In `acqlab/generator/batch.py`, replace:

```python
            key, docs, teaser = build(deal_id, split, seed + SEED_OFFSET[split] + i, mc=mc, llm=llm)
            face = {"teaser": key.truth.base.teaser.model_dump(), "deal": key.truth.deal.model_dump()}
            key.budget = write_room(out / "deals" / deal_id / "room", teaser, docs, engine=face)
```

with:

```python
            key, docs, teaser = build(deal_id, split, seed + SEED_OFFSET[split] + i, mc=mc, llm=llm, profile=profile)
            face = {"teaser": key.truth.base.teaser.model_dump(), "deal": key.truth.deal.model_dump()}
            key.budget = write_room(out / "deals" / deal_id / "room", teaser, docs,
                                    budget_share=PROFILES[profile]["budget_share"], engine=face)
```

In `acqlab/generator/batch.py`, replace:

```python
    ap.add_argument("--seed", type=int, default=0)
```

with:

```python
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--profile", choices=list(PROFILES), default="base", help="difficulty profile (reframe design §4)")
```

In `acqlab/generator/batch.py`, replace:

```python
                       extract=extract)
```

with:

```python
                       extract=extract, profile=args.profile)
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `uv run pytest -q`
Expected: 212 passed. That's 209 plus the profile, minutes and batch-profile tests; the r2 word-leak check extends an existing test.

- [ ] **Step 7: Commit**

```bash
git add acqlab/generator tests/generator
git commit -m "feat(generator): difficulty profiles (base, r1, r2, r3) and the board minutes as an evidence place

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: S0, repeat runs and S3 in the pilot runner

**Files:**
- Modify: `acqlab/bench/pilot.py`
- Modify: `tests/bench/test_pilot.py`

**Interfaces:**
- Consumes: `solve` (Plan 4a) and the rooms' `index.json` page counts.
- Produces:
  - `SYSTEMS = {"s1b": False, "s1b_router": True, "s0": False}` and `UNBUDGETED = {"s0"}`.
  - `floors(key)` also returns `"ask"` and `"true_walk_away"`.
  - `run(data, n, systems, solver=solve, reps=1, flip_only=False) -> list[dict]`.
    - Repeat `k > 0` is saved as `<deal>.r<k>.json`, and every row carries `"rep"`.
    - S0's budget is the whole room.
  - `s3_rows(rows, n) -> dict[str, dict]`: the majority go of the first n S1b runs (a tie is no-go), the median walk-away, and summed pages, tokens and cost.
  - `summarize(rows, s3_n=None)`: each system over its own deals, using first runs only. The checkpoint appears only when both S1b and S1b + router ran.
  - New CLI flags: `--reps`, `--flip-only`, `--s3`. The default `--systems` is now `s1b,s1b_router`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/bench/test_pilot.py`:

```python


def test_s0_reads_with_the_whole_room_as_budget_and_flip_only_skips_the_rest(fresh):
    got = []

    def solver(room, budget, trace, router):
        got.append((room.parent.name, budget))
        trace.write_text(json.dumps(_row("submit", {"go": False, "walk_away": 1.0, "reason": "r"})) + "\n")
        return {"usage": {}}
    keys = {d: _key(fresh, d) for d in ("dev-000", "dev-001")}
    run(fresh, 2, ["s0"], solver=solver, flip_only=True)
    flips = [d for d, k in keys.items() if k.truth.go != k.truth.face_go]
    assert [d for d, _ in got] == flips
    for d, budget in got:
        index = json.loads((fresh / "deals" / d / "room" / "index.json").read_text())
        assert budget == sum(x["pages"] for x in index["documents"]) > keys[d].budget


def test_repeats_are_saved_apart_and_resumed(fresh):
    calls = []

    def solver(room, budget, trace, router):
        calls.append(trace.name)
        trace.write_text(json.dumps(_row("submit", {"go": True, "walk_away": 1.0, "reason": "r"})) + "\n")
        return {"usage": {}}
    rows = run(fresh, 1, ["s1b"], solver=solver, reps=3)
    assert [r["rep"] for r in rows] == [0, 1, 2]
    assert calls == ["dev-000.trace.jsonl", "dev-000.r1.trace.jsonl", "dev-000.r2.trace.jsonl"]
    assert run(fresh, 1, ["s1b"], solver=solver, reps=3) == [] and len(calls) == 3


def test_s3_is_the_majority_decision_of_s1b_runs_with_summed_costs():
    fl = {"always_go": 0.3, "always_no": 0.0, "b0": 0.3, "b0_walk_away_error": 0.1, "ask_walk_away_error": 0.1,
          "headroom": 0.02, "ask": 100.0, "true_walk_away": 90.0}  # a bad deal: going costs 0.3

    def rep(k, go, wa):
        return _fake_row("d0", "s1b", 0.3 if go else 0.0, True) | {
            "rep": k, "go": go, "walk_away": wa, "status": "ok", "floors": fl, "cost_usd": 0.1,
            "tokens": dict.fromkeys(("input_tokens", "output_tokens", "cache_read_input_tokens",
                                     "cache_creation_input_tokens"), 5)}
    rows = [rep(0, True, 95.0), rep(1, False, 88.0), rep(2, False, 91.0)]
    s3 = pilot.s3_rows(rows, 3)["d0"]
    assert s3["go"] is False and s3["regret"] == 0.0 and s3["correct"] and s3["walk_away"] == 91.0
    assert s3["walk_away_error"] == pytest.approx(0.01) and s3["tokens"]["input_tokens"] == 15
    assert s3["cost_usd"] == pytest.approx(0.3) and s3["pages"] == 30
    assert pilot.s3_rows(rows[:2], 2)["d0"]["go"] is False  # a 1-1 tie is the cautious no-go
    assert pilot.s3_rows(rows, 4) == {}  # not enough runs
    s = summarize(rows, s3_n=3)
    assert s["systems"]["s3"]["regret"] == 0.0 and s["systems"]["s1b"]["regret"] == 0.3  # s1b: its first run only


def test_a_summary_with_only_s1b_has_floors_but_no_checkpoint():
    s = summarize([_fake_row(f"d{i}", "s1b", 0.05, True) for i in range(3)])
    assert s["n_deals"] == 3 and set(s["systems"]) == {"s1b"} and "checkpoint" not in s
    assert s["floors"]["b0"] == pytest.approx(0.1) and not s["b0_warning"]
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest -q tests/bench/test_pilot.py`
Expected: FAIL. `run()` has no `flip_only` or `reps`, and there is no `s3_rows`.

- [ ] **Step 3: Implement** (`acqlab/bench/pilot.py`)

In `acqlab/bench/pilot.py`, replace:

```python
"""Plan 4a pilot: S1b and S1b + router on dev deals, scored against the answer keys (design §3).

  uv run python -m acqlab.bench.pilot --data data/v3 --n 3 --confirm-claude     # runs (uses the Claude subscription)
  uv run python -m acqlab.bench.pilot --data data/v3 --report                   # checkpoint summary, no Claude

Each run goes to <data>/runs/<system>/<deal>.json (its tool trace beside it); reruns skip finished runs.
```

with:

```python
"""Pilot runner: single-agent systems on dev deals, scored against the answer keys (Plan 4a design §3; Plan 4b adds
S0 and S3, reframe design §4).

  uv run python -m acqlab.bench.pilot --data data/v3 --n 3 --confirm-claude     # runs (uses the Claude subscription)
  uv run python -m acqlab.bench.pilot --data D --n 30 --systems s0 --flip-only --confirm-claude   # S0 on flip deals
  uv run python -m acqlab.bench.pilot --data D --n 30 --reps 3 --systems s1b --confirm-claude     # runs for S3
  uv run python -m acqlab.bench.pilot --data data/v3 --report [--s3 3]           # summary, no Claude

Each run goes to <data>/runs/<system>/<deal>.json (repeat k>0: <deal>.r<k>.json; its tool trace beside it); reruns
skip finished runs.
```

In `acqlab/bench/pilot.py`, replace:

```python
SYSTEMS = {"s1b": False, "s1b_router": True}  # name -> offered rank_issues
```

with:

```python
SYSTEMS = {"s1b": False, "s1b_router": True, "s0": False}  # name -> offered the router
UNBUDGETED = {"s0"}  # the reading ceiling: its budget is the whole room (main spec §4)
```

In `acqlab/bench/pilot.py`, replace:

```python
            "headroom": t.face_walk_away / ask - 1}  # face-value margin, visible to any agent via the free engine
```

with:

```python
            "headroom": t.face_walk_away / ask - 1,  # face-value margin, visible to any agent via the free engine
            "ask": ask, "true_walk_away": t.walk_away}  # reference numbers, for combining runs (S3)
```

In `acqlab/bench/pilot.py`, replace:

```python
def run(data: Path, n: int, systems: list[str], solver: Callable = solve) -> list[dict]:
    """Run each system on the first n dev deals, skipping finished runs. Raises LLMUnavailable to stop the batch."""
    deals = json.loads((data / "splits.json").read_text())["dev"][:n]
    rows = []
    for deal in deals:
        key = AnswerKey.model_validate_json((data / "truth" / f"{deal}.json").read_text())
        for system in systems:
            out = data / "runs" / system / f"{deal}.json"
            if out.exists():
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            trace_path = out.with_suffix(".trace.jsonl")
            trace_path.unlink(missing_ok=True)
            try:
                cli, status = solver(data / "deals" / deal / "room", key.budget, trace_path, SYSTEMS[system]), "ok"
            except RunTimeout:
                cli, status = None, "timeout"
            trace = [json.loads(x) for x in trace_path.read_text().splitlines()] if trace_path.exists() else []
            if status == "ok" and not trace:
                raise LLMUnavailable(f"{system}/{deal}: the tool server never ran (no trace)")
            row = score(key, system, trace, cli, status)
            out.write_text(json.dumps(row, indent=2))
            rows.append(row)
            print(f"{system:10s} {deal}: regret {row['regret']:.3f} answered={row['answered']} pages={row['pages']}")
    return rows
```

with:

```python
def run(data: Path, n: int, systems: list[str], solver: Callable = solve, reps: int = 1,
        flip_only: bool = False) -> list[dict]:
    """Run each system `reps` times on the first n dev deals (only the decision-flip ones if flip_only), skipping
    finished runs. Raises LLMUnavailable to stop the batch."""
    deals = json.loads((data / "splits.json").read_text())["dev"][:n]
    rows = []
    for deal in deals:
        key = AnswerKey.model_validate_json((data / "truth" / f"{deal}.json").read_text())
        if flip_only and key.truth.go == key.truth.face_go:
            continue
        room = data / "deals" / deal / "room"
        whole = float(sum(d["pages"] for d in json.loads((room / "index.json").read_text())["documents"]))
        for system in systems:
            for rep in range(reps):
                out = data / "runs" / system / (f"{deal}.json" if rep == 0 else f"{deal}.r{rep}.json")
                if out.exists():
                    continue
                out.parent.mkdir(parents=True, exist_ok=True)
                trace_path = out.with_suffix(".trace.jsonl")
                trace_path.unlink(missing_ok=True)
                budget = whole if system in UNBUDGETED else key.budget
                try:
                    cli, status = solver(room, budget, trace_path, SYSTEMS[system]), "ok"
                except RunTimeout:
                    cli, status = None, "timeout"
                trace = [json.loads(x) for x in trace_path.read_text().splitlines()] if trace_path.exists() else []
                if status == "ok" and not trace:
                    raise LLMUnavailable(f"{system}/{deal}: the tool server never ran (no trace)")
                row = score(key, system, trace, cli, status) | {"rep": rep}
                out.write_text(json.dumps(row, indent=2))
                rows.append(row)
                print(f"{system:10s} {deal} r{rep}: regret {row['regret']:.3f} answered={row['answered']} "
                      f"pages={row['pages']}")
    return rows


def s3_rows(rows: list[dict], n: int) -> dict[str, dict]:
    """S3 (main spec §4), deal -> row: the majority go/no-go of the first n S1b runs (a tie is no-go, the cautious
    call) and their median walk-away. Pages, tokens and cost add up over the n runs. Deals with fewer runs are left
    out."""
    reps: dict[str, list[dict]] = {}
    for r in rows:
        if r["system"] == "s1b" and r.get("rep", 0) < n:
            reps.setdefault(r["deal"], []).append(r)
    out = {}
    for deal, rs in reps.items():
        if len(rs) < n:
            continue
        f, go = rs[0]["floors"], 2 * sum(r["go"] for r in rs) > n
        wa = float(np.median([r["walk_away"] for r in rs]))
        out[deal] = {
            "deal": deal, "system": "s3", "status": "timeout" if any(r["status"] == "timeout" for r in rs) else "ok",
            "answered": all(r["answered"] for r in rs), "go": go, "walk_away": wa,
            "regret": f["always_go"] if go else f["always_no"], "correct": go == (f["always_go"] <= f["always_no"]),
            "walk_away_error": abs(wa - f["true_walk_away"]) / f["ask"], "flip": rs[0]["flip"],
            "case_type": rs[0]["case_type"], "pages": sum(r["pages"] for r in rs),
            "decoy_pages": sum(r["decoy_pages"] for r in rs),
            "opened_relevant": None if rs[0]["opened_relevant"] is None else any(r["opened_relevant"] for r in rs),
            "rank_calls": 0, "prior_inside": None, "floors": f,
            "tokens": {k: sum(r["tokens"][k] for r in rs) for k in rs[0]["tokens"]},
            "cost_usd": sum(r["cost_usd"] or 0 for r in rs)}
    return out
```

In `acqlab/bench/pilot.py`, replace:

```python
def summarize(rows: list[dict]) -> dict:
    """The checkpoint (design §3), on deals both systems finished. Regret is normalised by asking price."""
    by = {s: {r["deal"]: r for r in rows if r["system"] == s} for s in SYSTEMS}
    deals = sorted(set(by["s1b"]) & set(by["s1b_router"]))
    out: dict = {"n_deals": len(deals), "systems": {}}
    for s in SYSTEMS:
        rs = [by[s][d] for d in deals]
```

with:

```python
def summarize(rows: list[dict], s3_n: int | None = None) -> dict:
    """Each system over its own finished deals (first runs only; S3 from S1b's repeats), the no-AI floors over S1b's
    deals, and the Plan 4a checkpoint on deals both S1b and S1b + router finished. Regret is normalised by asking
    price."""
    first = [r for r in rows if r.get("rep", 0) == 0]
    by = {s: {r["deal"]: r for r in first if r["system"] == s} for s in SYSTEMS}
    if s3_n:
        by["s3"] = s3_rows(rows, s3_n)
    out: dict = {"n_deals": len(by["s1b"]), "systems": {}}
    for s in [s for s in by if by[s]]:
        rs = [by[s][d] for d in sorted(by[s])]
```

In `acqlab/bench/pilot.py`, replace:

```python
    base = [by["s1b"][d] for d in deals]
```

with:

```python
    base = [by["s1b"][d] for d in sorted(by["s1b"])]
```

In `acqlab/bench/pilot.py`, replace:

```python
    flip = [d for d in deals if by["s1b"][d]["flip"]]
```

with:

```python
    flip = [d for d in sorted(set(by["s1b"]) & set(by["s1b_router"])) if by["s1b"][d]["flip"]]
```

In `acqlab/bench/pilot.py`, replace:

```python
    s1b = out["systems"]["s1b"]["regret"]
```

with:

```python
    s1b = out["systems"]["s1b"]["regret"] if base else None
```

In `acqlab/bench/pilot.py`, replace:

```python
    ap.add_argument("--systems", default=",".join(SYSTEMS))
```

with:

```python
    ap.add_argument("--systems", default="s1b,s1b_router", help=f"comma-separated, from {', '.join(SYSTEMS)}")
    ap.add_argument("--reps", type=int, default=1, help="runs per system and deal (S3 combines S1b's)")
    ap.add_argument("--flip-only", action="store_true", help="only the decision-flip deals (S0's calibration use)")
    ap.add_argument("--s3", type=int, default=0, help="with --report: add S3 over this many S1b runs per deal")
```

In `acqlab/bench/pilot.py`, replace:

```python
        summary = summarize(rows)
```

with:

```python
        summary = summarize(rows, s3_n=args.s3 or None)
```

In `acqlab/bench/pilot.py`, replace:

```python
        run(args.data, args.n, [s for s in args.systems.split(",") if s])
```

with:

```python
        run(args.data, args.n, [s for s in args.systems.split(",") if s], reps=args.reps, flip_only=args.flip_only)
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest -q`
Expected: 216 passed (212 plus 4).

- [ ] **Step 5: Commit**

```bash
git add acqlab/bench/pilot.py tests/bench/test_pilot.py
git commit -m "feat(bench): S0 (whole room as budget), repeat runs and S3 (majority of S1b runs) in the pilot runner

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The calibration check

**Files:**
- Create: `acqlab/bench/calibrate.py`
- Create: `tests/bench/test_calibrate.py`

**Interfaces:**
- Consumes:
  - `pilot.floors` and `pilot.summarize` (Task 4).
  - S1b and S0 run files under `<data>/runs/`.
  - `<audit>/problems.json` (Task 2).
  - `validate._auc`.
- Produces:
  - `python -m acqlab.bench.calibrate --data D --audit A`. It writes `D/calibration.json` and exits 0 if every target is met, else 1.
  - `deals_needed(regrets, effect=0.25) -> float`, `margin_auc(keys) -> float` and `check(data, audit) -> dict`.

**The power model.** The spec says: "a 25% reduction must be detectable at the planned test size (power from the round's data)". We model the unknown S4 as removing all of S1b's regret on a random 25% of deals, which cuts mean regret by exactly 25%. For paired differences at two-sided 5% and 80% power, that gives n = Z² (E[r²] / (0.25·E[r]²) − 1), with Z = 1.96 + 0.84. Replace it with the measured paired variance once S4 has dev runs (Plan 5).

- [ ] **Step 1: Write the failing tests**

Create `tests/bench/test_calibrate.py`:

```python
import json
import math
import shutil

import pytest

from acqlab.bench import calibrate
from acqlab.bench.pilot import run
from acqlab.generator.batch import AnswerKey


def test_deals_needed_follows_the_fix_a_quarter_model():
    # regret 0.1 on one deal in four: E[r] = 0.025, E[r^2] = 0.0025, so n = Z^2 (0.0025 / (0.25 * 0.025^2) - 1)
    assert calibrate.deals_needed([0, 0, 0, 0.1]) == math.ceil(calibrate.Z ** 2 * 15)
    assert calibrate.deals_needed([0.05, 0.05]) < calibrate.deals_needed([0, 0.1])  # rarer, bigger misses need more
    assert calibrate.deals_needed([0.0, 0.0]) == math.inf


def _stub(go_for):
    """A solver that submits go_for(room, budget) and reads nothing."""
    def solver(room, budget, trace, router):
        trace.write_text(json.dumps({"tool": "submit", "args": {"go": go_for(room, budget), "walk_away": 1.0,
                                                                 "reason": "r"}, "cost": 0.0, "refused": False}) + "\n")
        return {"usage": {}}
    return solver


@pytest.fixture
def round_dir(data, tmp_path):
    """The two shared dev deals as a calibration round, with S1b always wrong and S0 always right."""
    d = shutil.copytree(data, tmp_path / "round")
    truth = {k.truth.id: k.truth for k in calibrate._keys(d)}
    run(d, 2, ["s1b"], solver=_stub(lambda room, b: not truth[room.parent.name].go))
    run(d, 2, ["s0"], solver=_stub(lambda room, b: truth[room.parent.name].go), flip_only=True)
    return d


def test_a_round_is_checked_against_every_target(round_dir):
    result = calibrate.check(round_dir, round_dir)  # the round doubles as a (too small) audit batch
    met = {t["target"]: t["met"] for t in result["targets"]}
    assert met["S1b wrong on flip deals"] is (result["n_s1b_flip"] > 0)
    assert met["S0 right on flip deals"] is (result["n_s0"] > 0)
    assert not met["audit deals"]  # 2 deals, not 500
    assert met["audit batch problems (incl. word leaks)"]  # the fixture's batch saved problems.json = []
    assert not met["S1b regret minus B0's"] or not met["S1b regret minus the margin rule's"]  # always wrong loses
    assert result["passed"] is False and len(result["targets"]) == 8


def test_the_cli_writes_the_result_and_exits_1_when_a_target_is_missed(round_dir):
    (round_dir / "problems.json").write_text('["word leak: something"]')
    assert calibrate.main(["--data", str(round_dir), "--audit", str(round_dir)]) == 1
    saved = json.loads((round_dir / "calibration.json").read_text())
    assert not next(t for t in saved["targets"] if t["target"].startswith("audit batch problems"))["met"]


def test_margin_auc_is_one_when_thin_margins_are_exactly_the_flip_deals(data):
    key = AnswerKey.model_validate_json((data / "truth" / "dev-000.json").read_text())
    ask = key.truth.deal.asking_price

    def variant(headroom, flip):
        t = key.truth.model_copy(update={"face_walk_away": ask * (1 + headroom), "face_go": True, "go": not flip})
        return key.model_copy(update={"truth": t})
    keys = [variant(0.01, True), variant(0.02, True), variant(0.2, False), variant(0.3, False)]
    assert calibrate.margin_auc(keys) == 1.0
    assert math.isnan(calibrate.margin_auc(keys[:2]))  # no non-flip deals: nothing to compare
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest -q tests/bench/test_calibrate.py`
Expected: FAIL. `acqlab.bench.calibrate` doesn't exist yet.

- [ ] **Step 3: Implement**

Create `acqlab/bench/calibrate.py`:

```python
"""Calibration check (reframe design §4): does one round's hard benchmark meet every target? No Claude calls: it reads
the round's finished S1b and S0 runs (pilot) and the round's 500-deal audit batch.

  uv run python -m acqlab.bench.calibrate --data data/cal-r1 --audit /tmp/acqlab-audit-r1

Writes <data>/calibration.json. Exit codes: 0 every target met; 1 a target missed (printed).
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np

from acqlab.bench.pilot import floors, summarize
from acqlab.generator.batch import AnswerKey
from acqlab.generator.validate import _auc

FLIP_WRONG_MIN = 0.30  # S1b gets at least 30% of flip deals wrong
S0_FLIP_RIGHT_MIN = 0.80  # S0 (reading everything) gets at least 80% of flip deals right
TEST_DEALS = 100  # the planned test size (main spec §4)
EFFECT = 0.25  # H1's noticeable difference
Z = 1.959964 + 0.841621  # paired test at two-sided 5%, 80% power
AUDIT_DEALS = 500
MARGIN_AUC_MAX = 0.72  # generator 3.0.0's margin shortcut


def deals_needed(regrets: list[float], effect: float = EFFECT) -> float:
    """Test deals needed to detect an `effect` cut in mean regret, modelling S4 as removing all of S1b's regret on a
    random `effect` share of deals (which cuts the mean by exactly `effect`). With S1b's per-deal regret r:
    n = Z² (E[r²] / (effect E[r]²) - 1). ponytail: a model of the unknown S4; use the paired variance once S4 has
    dev runs."""
    r = np.asarray(regrets, dtype=float)
    m1, m2 = r.mean(), (r ** 2).mean()
    return math.inf if m1 == 0 else float(math.ceil(Z ** 2 * (m2 / (effect * m1 ** 2) - 1)))


def margin_auc(keys: list[AnswerKey]) -> float:
    """How well a thin face-value margin picks out decision-flip deals (0.5 = not at all; NaN if one group is empty)."""
    h = np.array([abs(k.truth.face_walk_away / k.truth.deal.asking_price - 1) for k in keys])
    flip = np.array([k.truth.go != k.truth.face_go for k in keys])
    return 1 - _auc(h[flip], h[~flip]) if flip.any() and not flip.all() else math.nan


def _keys(data: Path) -> list[AnswerKey]:
    return [AnswerKey.model_validate_json(p.read_text()) for p in sorted((data / "truth").glob("*.json"))]


def check(data: Path, audit: Path) -> dict:
    """Every target with its measured value; `passed` only if all are met."""
    rows = [json.loads(p.read_text()) for s in ("s1b", "s0") for p in sorted((data / "runs" / s).glob("*.json"))]
    for r in rows:
        r["floors"] = floors(AnswerKey.model_validate_json((data / "truth" / f"{r['deal']}.json").read_text()))
    s1b = [r for r in rows if r["system"] == "s1b" and r.get("rep", 0) == 0]
    s0 = [r for r in rows if r["system"] == "s0" and r.get("rep", 0) == 0 and r["flip"]]
    flip = [r for r in s1b if r["flip"]]
    summary = summarize(rows) if s1b else {"floors": {}}
    regret = float(np.mean([r["regret"] for r in s1b])) if s1b else math.nan
    keys = _keys(audit)
    problems = json.loads((audit / "problems.json").read_text()) if (audit / "problems.json").exists() else None
    targets = [
        ("S1b wrong on flip deals", 1 - np.mean([r["correct"] for r in flip]) if flip else math.nan,
         ">=", FLIP_WRONG_MIN),
        ("test deals needed to detect a 25% cut", deals_needed([r["regret"] for r in s1b]) if s1b else math.inf,
         "<=", TEST_DEALS),
        ("S0 right on flip deals", np.mean([r["correct"] for r in s0]) if s0 else math.nan, ">=", S0_FLIP_RIGHT_MIN),
        ("S1b regret minus B0's", regret - summary["floors"].get("b0", math.nan), "<", 0.0),
        ("S1b regret minus the margin rule's", regret - summary["floors"].get("margin_rule", math.nan), "<", 0.0),
        ("audit deals", float(len(keys)), ">=", AUDIT_DEALS),
        ("audit batch problems (incl. word leaks)", math.inf if problems is None else float(len(problems)), "<=", 0.0),
        ("margin shortcut AUC (audit)", margin_auc(keys) if keys else math.nan, "<=", MARGIN_AUC_MAX),
    ]
    ops = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b, "<": lambda a, b: a < b}
    out = [{"target": name, "value": float(v), "need": f"{op} {want}", "met": bool(ops[op](float(v), want))}
           for name, v, op, want in targets]  # a NaN (no runs) never meets its target
    return {"targets": out, "passed": all(t["met"] for t in out), "n_s1b": len(s1b), "n_s1b_flip": len(flip),
            "n_s0": len(s0)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True, help="the round's deals, with S1b and S0 runs")
    ap.add_argument("--audit", type=Path, required=True, help="the round's 500-deal audit batch")
    args = ap.parse_args(argv)
    result = check(args.data, args.audit)
    (args.data / "calibration.json").write_text(json.dumps(result, indent=2))
    for t in result["targets"]:
        print(f"{'ok  ' if t['met'] else 'MISS'} {t['target']}: {t['value']:.3f} (need {t['need']})")
    print("PASSED: every target met" if result["passed"] else "FAILED: a target was missed")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `uv run pytest -q`
Expected: 220 passed (216 plus 4).

- [ ] **Step 5: Commit**

```bash
git add acqlab/bench/calibrate.py tests/bench/test_calibrate.py
git commit -m "feat(bench): calibration check against the reframe design's targets (power, S0, floors, leaks)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Calibration rounds, freeze and pre-registration (controller, not a subagent)

This task makes real Claude calls, **only with the user's OK before each round**, at about $5–10 a round.

**Round K** uses profile `rK` for K = 1, 2, 3, in that order. Stop at the first round that passes.

- [ ] **Step 1: Generate the round's deals and its audit batch** (no Claude calls; about 3 minutes)

```bash
uv run python -m acqlab.generator.batch --out data/cal-rK --dev 30 --test 0 --hand 0 --showcase 0 --seed 6K0000 --profile rK
uv run python -m acqlab.generator.batch --out /tmp/acqlab-audit-rK --dev 250 --test 250 --hand 0 --showcase 0 --seed 7K0000 --profile rK
```

For K = 1 the seeds are 610000 and 710000. For K = 2 they are 620000 and 720000, and so on.

Expected: `0 batch problems` from both commands. If the audit batch reports problems, stop and report them; they are a plan defect, not something to tune in a calibration round.

- [ ] **Step 2: Ask the user before the round's runs**

The round is:
- about 30 S1b runs
- S0 on that round's flip deals, about 14 runs

Together about $5–10 on the user's subscription.

- [ ] **Step 3: Run S1b and S0** (after the OK)

```bash
export CLAUDE_BIN="$HOME/Library/Application Support/Claude/claude-code/2.1.280/claude.app/Contents/MacOS/claude"
uv run python -m acqlab.bench.pilot --data data/cal-rK --n 30 --systems s1b --confirm-claude
uv run python -m acqlab.bench.pilot --data data/cal-rK --n 30 --systems s0 --flip-only --confirm-claude
```

Exit code 2 means a usage limit. Rerun after the reset; finished runs are kept.

- [ ] **Step 4: Check the round**

```bash
uv run python -m acqlab.bench.calibrate --data data/cal-rK --audit /tmp/acqlab-audit-rK
```

Record every target's value in `docs/results/plan-4b-calibration.md`, under a heading for round K.

- If it **FAILED** and K < 3, go to round K+1.
- If it **FAILED** at K = 3, stop and decide with the user (spec §4).
- If the only miss is "test deals needed", tell the user the measured number: raising the test size is their call (main spec §4: "adjust deal count before the main run").

- [ ] **Step 5: Freeze** (after the first passing round)

In `acqlab/generator/batch.py`, set the passing profile as the default. Replace:

```python
    ap.add_argument("--profile", choices=list(PROFILES), default="base", help="difficulty profile (reframe design §4)")
```

with this, where `rK` is the passing profile:

```python
    ap.add_argument("--profile", choices=list(PROFILES), default="rK", help="difficulty profile (reframe design §4; "
                    "frozen by calibration round K)")
```

- [ ] **Step 6: Pre-register H1–H6**

Write `docs/results/plan-4b-preregistration.md` with:
- H1–H6, verbatim from the spec, §3.
- The frozen profile and generator version 4.0.0.
- The test size: max(100, the passing round's "test deals needed").
- The analysis:
  - paired bootstrap 95% CIs
  - ≥ 25% lower regret for H1
  - results by case type
- The rule for S3's N: round(S4 tokens per deal ÷ S1b tokens per deal), measured on dev deals in Plan 5.

The test set itself is generated once, in Plan 6 (spec §6).

- [ ] **Step 7: Update the handoff and commit**

In `docs/HANDOFF.md`:
- add a Plan 4b section with the rounds' results, the frozen profile and the pre-registration's path
- make the next step Plan 5, S4

```bash
git add acqlab/generator/batch.py docs/results/plan-4b-calibration.md docs/results/plan-4b-preregistration.md docs/HANDOFF.md
git commit -m "docs: Plan 4b calibration (profile rK frozen) and H1-H6 pre-registration

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
