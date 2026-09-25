# Plan 4a: Router Checkpoint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build everything the week-4 checkpoint needs, S1b vs S1b + router on real Claude runs: bigger data rooms, a sandboxed tool server, a `claude -p` adapter and a resumable pilot runner. Then generate the new deals, and stop before any real pilot run.

**Architecture:**
- **Generator.** A new `acqlab/generator/padding.py` brings every document to a seeded target length with neutral, code-written sections, and adds contracts and filler. Padding sees no fact, so page counts reveal nothing.
- **Leak checks.** `validate.py` gains a page-length check and a word-level leak report.
- **`acqlab/agents/server.py`** is a stdlib MCP stdio server. It offers the data room, the engine, issue notes and, for the router system, router 6 over the agent's own notes.
- **`acqlab/agents/solver.py`** runs one sandboxed `claude -p` call against that server.
- **`acqlab/bench/pilot.py`** runs both systems on dev deals, scores them against the answer keys and prints the pre-registered checkpoint.

**Tech Stack:** Python 3.12, uv, pydantic 2, numpy 2, pytest. Claude Code CLI 2.1.280 or newer as the solver, on the user's subscription.

**Spec:** `docs/superpowers/specs/2026-09-24-plan-4a-checkpoint-design.md` (this plan's design, including its "Revisions from pre-verification"). It sits under `docs/superpowers/specs/2026-09-22-acquisition-lab-design.md` §4, which is the binding authority.

**Where this fits:** Plan 4a of the project. Plan 4b adds S0, S1a, S3, router 2 and the reveal-wording fix that lets search come back.

## Global Constraints

**Dependencies and money**
- Python `>=3.12`, with no new dependencies. The MCP server uses the standard library only.
- All money is in **$M**. Convert $M amounts to engine inputs only with `acqlab.generator.traps.params_for`.
- The engine is the only source of financial numbers. This plan does not change `acqlab/engine` or `acqlab/routers`.

**Isolation**
- **The tool server never reads an answer key.** It reads only its room folder: `index.json`, `engine.json` and the documents. A test enforces this.
- **Padding never sees a fact.** `pad()` takes the documents, the visible base deal, the style and the seed, and nothing else.
- **No search tool for agents in Plan 4a.** Search hit counts give traps away until Plan 4b fixes the reveal wording. `DataRoom.search` stays as it is and unused.

**Claude calls**
- **No test ever calls Claude or Codex.** Tests use `tests/agents/fake_claude.py`.
- Subagents must never make a real Claude or Codex call.
- Real pilot runs happen only after the user's OK, and only with `--confirm-claude`.

**Git and subagents**
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Subagents must never modify settings or permissions files, and must stop and report if a git operation is blocked.

**Tests**
- Never edit golden test numbers to make a test pass.
- The two Track A test changes in Task 2 change a scenario's budget, not an expected number. Each keeps its test's premise, which is that there is room to retry or to choose.

## Findings from pre-verifying this plan (read before starting)

All the code below was run before this plan was written: 197 tests pass in about 47 s. The spec's "Revisions from pre-verification" records the design changes these findings caused.

1. **Room size.** Rooms are 67–105 pages, 87 on average (300 deals). Every document lands exactly on its drawn target, whatever the reveal says.
2. **Budget share 0.25.** The default budget, about 22 pages:
   - covers every evidence document in 21% of deals (the spec asks for under 30%)
   - covers the decision-relevant documents in 86% of the deals that have them

   At 0.35 those figures were 62% and 99%.
3. **The statistical leak audit passes.** The batch checks found 0 problems on 500 deals. Those checks are:
   - the go rate
   - topic presence
   - add-back size
   - the new page-length check: no document is longer when a trap is real
4. **Search leaked answers.** In a word-level audit on 500 deals, 48 (trap, document, word) triples separate trap deals from clean ones. One 1-unit search for "confirmed" identifies concentration traps perfectly.

   The cause is Plan 2's reveal wording: trap and clean sentences use different words, and the range wording appears only for unresolvable facts. The user decided:
   - agents get no search tool in 4a
   - the word-level check ships now as a report (`word_leaks.json`)
   - the wording rewrite is Plan 4b's job

   With trap labels shuffled, the report finds 0 leaks at 500 deals: no false alarms.
5. **A real sandbox check passed** (one call, with the user's OK, $0.03):
   - The model saw exactly our tools and nothing else.
   - None of the user's hooks, skills or CLAUDE.md text reached it. The CLI does add the user's account email; this is harmless.
   - The tool server connected and logged the call.
   - The usage fields are `input_tokens`, `output_tokens`, `cache_read_input_tokens` and `cache_creation_input_tokens`, plus `total_cost_usd`.
6. **The `claude` on PATH (2.1.266) cannot run Opus 5.5,** which needs 2.1.280 or newer. The desktop app bundles 2.1.280 at `~/Library/Application Support/Claude/claude-code/2.1.280/claude.app/Contents/MacOS/claude`. Pilot runs set `CLAUDE_BIN` to that path.
7. **The CLI waits 3 s for stdin** unless it is given an empty stdin. The adapter passes `stdin=DEVNULL`.
8. **`rank_issues` takes about 0.2 s** (400 worlds). The tool server's startup is dominated by imports.

## File map

| File | Task | Responsibility |
|---|---|---|
| `acqlab/generator/padding.py` | 1 | Neutral sections, extra contracts and filler, and pad-to-target |
| `acqlab/generator/batch.py` | 1–3 | Calls `pad`, writes `engine.json`, reports page and word leaks |
| `acqlab/generator/truth.py` | 1 | `GENERATOR_VERSION = "3.0.0"` |
| `acqlab/generator/validate.py` | 1, 3 | New filler titles, the page-length check, `doc_words`, `word_leaks` |
| `acqlab/dataroom/tools.py` | 2 | `BUDGET_SHARE = 0.25`; `write_room(..., engine=)` |
| `acqlab/agents/server.py` | 4 | MCP stdio tool server, budget, trace, call cap, `rank_issues` |
| `acqlab/agents/prompts.py` | 5 | The two systems' prompts |
| `acqlab/agents/solver.py` | 5 | One sandboxed `claude -p` run |
| `acqlab/bench/pilot.py` | 6 | Runner, scoring, no-AI floors, checkpoint summary |
| `tests/agents/fake_claude.py` | 5 | A stand-in for `claude -p` that drives the server |

---

### Task 1: Pad every room to full size

**Files:**
- Create: `acqlab/generator/padding.py`
- Create: `tests/generator/test_padding.py`
- Modify: `acqlab/generator/batch.py` (import, one call in `build`)
- Modify: `acqlab/generator/truth.py` (`GENERATOR_VERSION`)
- Modify: `acqlab/generator/validate.py` (the new filler titles are allowed)

**Interfaces:**
- Consumes: `render(t) -> (docs, evidence)`; `Doc`, `heading`, `table`, `money`, `pct`, `WORDS_PER_PAGE` from `documents.py`; `TERM`, `BOILERPLATE`, `FY_LAST`, `_CUSTOMERS`, `_CUSTOMER_KIND` from `render.py`.
- Produces: `pad(docs: list[Doc], b: BaseDeal, style: str, seed: int) -> list[Doc]`; `EXTRA_FILLER: dict[str, str]` (id → title), used by `validate.py`; `TARGET_PAGES`, `CONTRACTS`, `FILLER_DOCS`, `SENTENCES`, `TITLES`, `_kind(doc)`, `_table(kind, b, style, rng)`.

Padding runs in `build()` after the optional Codex prose pass, so every document lands exactly on its target page count. The padding uses its own random stream (`[seed, 3]`), so `render()` output is unchanged. New contracts state `TERM` as plain text, not a prose slot: padding runs after the prose pass, and `prose_fallbacks` counts slots.

- [ ] **Step 1: Write the failing tests**

Create `tests/generator/test_padding.py`:

```python
import re

import numpy as np
import pytest

from acqlab.generator.padding import (CONTRACTS, EXTRA_FILLER, FILLER_DOCS, SENTENCES, TARGET_PAGES, TITLES, _kind,
                                      _table, pad)
from acqlab.generator.render import LABELS, SUPPORT, TERM, render, teaser_text
from acqlab.generator.truth import generate
from acqlab.generator.validate import LEAK_WORDS, TOPIC_WORDS, check_leaks

# Padding must never talk about a trap topic: no topic or leak words, no trap labels, no trap-adjacent terms.
BANNED = (tuple(TOPIC_WORDS.values()) + LEAK_WORDS + tuple(LABELS.values()) + tuple(SUPPORT.values())
          + ("pension", "earnout", "litigation", "settle", "peg", "renew", "tender", "capex"))


@pytest.fixture(scope="module")
def deals():
    out = []
    for seed in range(12):
        t = generate(f"d{seed}", "test" if seed % 2 else "dev", seed, mc=20)  # dev deals are all style A
        docs, _ = render(t)
        out.append((t, docs, pad(docs, t.base, t.style, t.seed)))
    return out


def test_every_document_lands_in_its_page_range(deals):
    for _, _, padded in deals:
        for d in padded:
            lo, hi = TARGET_PAGES[_kind(d)]
            assert lo <= d.pages <= hi, (d.id, d.pages)


def test_rooms_have_three_to_six_contracts_and_six_to_nine_filler_documents(deals):
    for _, _, padded in deals:
        contracts = [d for d in padded if d.id.startswith("contract_")]
        assert CONTRACTS[0] <= len(contracts) <= CONTRACTS[1]
        assert [d.id for d in contracts] == [f"contract_{i + 1}" for i in range(len(contracts))]
        assert len({d.title for d in contracts}) == len(contracts)
        assert all(TERM in d.render() for d in contracts)  # presence rule: every contract states the term
        assert FILLER_DOCS[0] <= sum(d.domain == "filler" for d in padded) <= FILLER_DOCS[1]
        assert len({d.id for d in padded}) == len(padded)


def _plain(block):
    """A block with any style-B section number removed (padding renumbers sections)."""
    return re.sub(r"^SECTION \d+\. ", "SECTION ", block) if isinstance(block, str) else block.render()


def test_padding_keeps_every_original_block_in_order(deals):
    for _, docs, padded in deals:
        by_id = {d.id: d for d in padded}
        for d in docs:
            rest = iter(_plain(b) for b in by_id[d.id].blocks)
            assert all(_plain(b) in rest for b in d.blocks), d.id  # an in-order subsequence


def test_page_counts_do_not_depend_on_what_the_reveal_says(deals):
    """The same deal with longer reveal passages pads to the same page counts."""
    t, docs, padded = deals[0]
    longer = [d.model_copy(update={"blocks": d.blocks + ["An extra sentence of forty words. " * 5]})
              if d.id in ("qoe", "contract_1", "legal") else d for d in docs]
    assert [(d.id, d.pages) for d in pad(longer, t.base, t.style, t.seed)] == [(d.id, d.pages) for d in padded]


def test_padding_is_deterministic(deals):
    t, docs, padded = deals[1]
    assert [d.render() for d in pad(docs, t.base, t.style, t.seed)] == [d.render() for d in padded]


def test_style_b_sections_are_numbered_in_order(deals):
    b = next(p for t, _, p in deals if t.style == "B")
    for d in b:
        nums = [int(m.group(1)) for x in d.blocks if isinstance(x, str) for m in [re.match(r"SECTION (\d+)\. ", x)]
                if m]
        assert nums == list(range(1, len(nums) + 1)), d.id


def test_padding_text_never_mentions_a_trap_topic(deals):
    t = deals[0][0]
    texts = [s for pool in SENTENCES.values() for s in pool] + [x for pool in TITLES.values() for x in pool]
    texts += list(EXTRA_FILLER.values())
    rng = np.random.default_rng(0)
    texts += [_table(kind, t.base, style, rng) or "" for kind in TITLES for style in "AB" for _ in range(5)]
    for text in texts:
        low = text.lower()
        assert not [w for w in BANNED if w in low], text


def test_padded_rooms_pass_the_title_check(deals):
    for t, _, padded in deals:
        assert check_leaks(t, padded, teaser_text(t)) == []
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/generator/test_padding.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'acqlab.generator.padding'`.

- [ ] **Step 3: Implement**

Create `acqlab/generator/padding.py`:

```python
"""Neutral bulk for the data room (Plan 4a design §1): code-written sections that bring every document to a target
length drawn from the seed, plus extra contracts and filler documents. Padding sees only the documents, the visible
base deal, the style and the seed, never a fact, so page counts and padding text say nothing about the traps."""
import re

import numpy as np

from acqlab.generator.documents import WORDS_PER_PAGE, Doc, heading, money, pct, table
from acqlab.generator.render import _CUSTOMER_KIND, _CUSTOMERS, BOILERPLATE, FY_LAST, TERM
from acqlab.generator.sample import FISCAL_YEARS, BaseDeal

TARGET_PAGES = {"cim": (10, 15), "qoe": (8, 12), "audited": (10, 14), "credit": (4, 6), "assets": (3, 5),
                "legal": (2, 2), "contract": (2, 3), "filler": (2, 6)}
CONTRACTS = (3, 6)  # contracts per room
FILLER_DOCS = (6, 9)  # filler documents per room
EXTRA_FILLER = {
    "code_of_conduct": "Code of Conduct", "data_protection": "Data Protection Policy",
    "travel": "Travel and Expenses Policy", "procurement": "Procurement Policy",
    "continuity": "Business Continuity Plan", "whistleblowing": "Whistleblowing Policy",
    "quality": "Quality Manual", "org_chart": "Organisation Chart and Job Descriptions",
    "marketing": "Marketing Plan",
}
TITLES = {
    "cim": ("Market overview", "Competitive landscape", "Growth strategy", "Products and services",
            "Sales and marketing", "Management team", "Company history", "Geographic footprint",
            "Technology and systems", "People and culture", "Sustainability", "Investment highlights", "Pricing",
            "Supply chain", "Quality and accreditation"),
    "qoe": ("Basis of preparation", "Procedures performed", "Revenue analysis", "Gross margin analysis", "Overheads",
            "Payroll and headcount", "Cash proof", "Systems and controls", "Foreign exchange", "Related parties",
            "Management reporting", "Seasonality"),
    "audited": ("Independent auditor's report", "Statement of changes in equity", "Accounting policies",
                "Revenue recognition", "Inventories", "Leases", "Taxation", "Intangible assets", "Share capital",
                "Employee information", "Financial instruments", "Going concern", "Related party transactions"),
    "credit": ("Definitions and interpretation", "Conditions precedent", "Representations",
               "Information undertakings", "General undertakings", "Events of default", "Fees and expenses",
               "Payments", "Assignments and transfers", "Governing law"),
    "assets": ("Asset register", "Depreciation policy", "Insurance valuations", "Site list", "Vehicle fleet",
               "Information technology"),
    "legal": ("Corporate matters", "Share capital and ownership", "Intellectual property", "Data protection",
              "Employment matters", "Real estate", "Regulatory matters"),
    "contract": ("Definitions", "Supply of goods and services", "Pricing and payment", "Delivery", "Warranties",
                 "Limitation of liability", "Confidentiality", "Ending the agreement", "Force majeure",
                 "Governing law"),
    "filler": ("Purpose", "Scope", "Responsibilities", "Procedures", "Monitoring", "Training", "Records", "Review"),
}
SENTENCES = {
    "cim": (
        "{name} has built its position in the {industry} market over more than {n} years of trading.",
        "Management estimates that the addressable market grows at around {g} a year, supported by long-term "
        "structural trends.",
        "The Company competes on service quality, breadth of range and speed of delivery rather than on price alone.",
        "Sales are led by a team of {n} account managers organised by region, each with clear targets and a "
        "quarterly review.",
        "The senior team combines long industry experience with recent hires in finance, operations and digital.",
        "The Company has invested in its website and online ordering, which now handle about {p} of orders.",
        "Operations run from {n} sites, with a central hub handling planning, sourcing and quality control.",
        "Staff engagement surveys are run every year and scores have improved in each of the last three years.",
        "The Company holds the quality accreditations expected in its sector and has passed every external audit "
        "in recent years.",
        "Management sees opportunities to extend the product range, enter adjacent regions and pursue selective "
        "bolt-on acquisitions.",
        "Pricing is set centrally, with discounts approved by the commercial director above a set threshold.",
        "The brand is well recognised among trade buyers, and its satisfaction scores are ahead of the sector "
        "average.",
        "Energy use and waste per unit of output have fallen by {p} since {fy0}, and the Company reports against a "
        "recognised framework.",
        "Key suppliers are long-standing partners, and no single supplier accounts for more than {p} of total spend.",
        "The board meets monthly and receives a standard pack covering trading, cash, safety and people.",
    ),
    "qoe": (
        "Our procedures were limited to inquiry of management and analysis of the financial information made "
        "available to us.",
        "We have not audited or otherwise verified the information provided, and our work should not be relied on "
        "as an audit.",
        "Revenue by month was reconciled to the general ledger without exception for the periods under review.",
        "Gross margin moved within a narrow band of about {p} across the review period, with seasonal peaks in the "
        "second half.",
        "Headcount changed by {n} over the period, mainly in operations and sales.",
        "Payroll costs were agreed to payroll reports for a sample of {n} months without material differences.",
        "Cash receipts were agreed to bank statements for the review period, and bank reconciliations were up to "
        "date.",
        "Overheads were analysed by nature; rent, utilities and insurance together account for about {p} of the "
        "cost base.",
        "Management accounts are prepared monthly within {n} working days of month end and are reviewed by the "
        "finance director.",
        "Foreign exchange exposure is limited, with about {p} of sales invoiced in other currencies.",
        "The Company changed its accounting system in {fy0}; we compared totals before and after the migration and "
        "found no break in the series.",
        "Accruals were reviewed at each year end and appear consistent with prior periods.",
        "Related-party transactions were limited to office rent paid to an entity controlled by a shareholder, at a "
        "market rate.",
        "We held discussions with the finance director and the financial controller on {n} occasions during our "
        "work.",
    ),
    "audited": (
        "In our opinion the financial statements give a true and fair view of the state of the Company's affairs at "
        "the end of the year.",
        "We conducted our audit in accordance with applicable auditing standards; our responsibilities are "
        "described in this report.",
        "The financial statements have been prepared on the historical cost basis and in accordance with applicable "
        "accounting standards.",
        "Revenue is recognised when control of goods or services passes to the buyer, at the amount the Company "
        "expects to receive.",
        "Inventories are stated at the lower of cost and net realisable value, cost being determined on a first-in, "
        "first-out basis.",
        "Intangible assets are amortised on a straight-line basis over their estimated lives of {n} years.",
        "Current tax is provided at amounts expected to be paid using the tax rates enacted at the balance sheet "
        "date.",
        "The average monthly number of employees during the year was {staff}, most of whom worked in operations.",
        "The directors have assessed the Company's ability to continue as a going concern for at least twelve "
        "months from approval of these statements.",
        "Financial assets are measured at amortised cost; the Company does not use derivatives for speculative "
        "purposes.",
        "Share capital comprises ordinary shares of one class, all fully paid and carrying equal voting rights.",
        "Key management personnel are the directors, whose remuneration is disclosed in aggregate in this note.",
        "Short-term leases and leases of low-value assets are expensed on a straight-line basis over the lease "
        "period.",
        "Foreign currency transactions are translated at the rate on the date of the transaction, and differences "
        "are taken to profit or loss.",
        "Judgements made in applying accounting policies are reviewed each year, and none is considered critical.",
    ),
    "credit": (
        "Terms defined in this agreement have the same meaning in each finance document unless the context requires "
        "otherwise.",
        "The first utilisation is conditional on the agent receiving the documents listed in the schedule in form "
        "and substance satisfactory to it.",
        "Each obligor makes the representations in this clause on the date of this agreement and on each "
        "utilisation date.",
        "The borrower shall supply its audited annual financial statements within {n} days after the end of each "
        "financial year.",
        "The borrower shall supply a compliance certificate with each set of financial statements, signed by two "
        "directors.",
        "No obligor shall create or permit to subsist any security over its assets, except as this agreement "
        "permits.",
        "It is an event of default if an obligor does not pay on the due date any amount payable under a finance "
        "document.",
        "While an event of default is continuing, the agent may cancel the commitments and declare the loans due.",
        "All payments by an obligor shall be made in full without set-off or counterclaim.",
        "This agreement is governed by the laws of the jurisdiction set out in the schedule.",
        "A lender may assign any of its rights or transfer its rights and obligations to another bank or financial "
        "institution.",
        "The borrower shall pay an arrangement fee in the amount and at the times agreed in a fee letter.",
    ),
    "assets": (
        "The asset register is maintained in the accounting system and reconciled to the general ledger each month.",
        "Assets are tagged on acquisition, and a physical verification is performed at each site every year.",
        "Depreciation rates are reviewed annually; there were no changes in the period.",
        "Insurance valuations were last updated in {fy0} by an external valuer on a reinstatement cost basis.",
        "Vehicles are replaced on a rolling cycle of about {n} years, and the fleet is tracked by a telematics "
        "system.",
        "IT hardware is refreshed on a standard cycle, and core systems are hosted by a third-party data centre.",
        "Fully depreciated assets still in use are kept on the register at nil net book value.",
        "Disposals in the year generated proceeds broadly equal to net book value.",
    ),
    "legal": (
        "The Company is duly incorporated and validly existing, and its statutory registers appear to be up to date.",
        "The issued share capital is fully paid, and we have seen no options or rights over unissued shares.",
        "The Company owns the registered trade marks used in the business, and registrations are maintained by an "
        "external agent.",
        "The Company has a data protection policy and a register of processing activities, and no reportable "
        "breaches have been recorded.",
        "Employees are engaged on standard terms; senior staff contracts include restrictive covenants of {n} "
        "months.",
        "The Company's premises are held on leases on standard commercial terms.",
        "We have reviewed the regulatory permissions relevant to the business and found them to be current.",
        "This letter is given for the purpose of the proposed transaction only and may not be relied on by any other "
        "person.",
    ),
    "contract": (
        "In this agreement, words in the singular include the plural, and headings do not affect interpretation.",
        "The supplier shall supply the goods and services described in the schedule with reasonable skill and care.",
        "Invoices are payable within {n} days of the invoice date by electronic transfer to the account the "
        "supplier nominates.",
        "Prices are set out in the price schedule and are exclusive of value added tax.",
        "Delivery shall be made to the delivery address during normal business hours, and risk passes on delivery.",
        "The supplier warrants that the goods will conform to their specification and be free from material defects "
        "for {n} months.",
        "Neither party limits its liability for death or personal injury caused by its negligence, or for fraud.",
        "Subject to the above, each party's total liability in each contract year is limited to the charges paid in "
        "that year.",
        "Each party shall keep the other's confidential information secret and use it only to perform this "
        "agreement.",
        "Either party may end this agreement for a material breach that is not remedied within {n} days of a "
        "written request.",
        "Neither party is liable for delay caused by events beyond its reasonable control.",
        "This agreement is governed by the law of the jurisdiction stated in the schedule.",
    ),
    "filler": (
        "This document applies to all employees, contractors and agency staff working on behalf of the Company.",
        "This document is owned by the {owner} and reviewed at least once a year.",
        "Any breach of this document will be investigated and may lead to disciplinary action.",
        "Questions about this document should be raised with a line manager in the first instance.",
        "Training on this document is given at induction and refreshed every {n} months.",
        "Records made under this document are kept for {n} years and then securely destroyed.",
        "Exceptions must be approved in writing and recorded in the exceptions log.",
        "The board receives a summary report on compliance with this document each quarter.",
        "This document was last approved by the board in {fy}.",
        "Where local law sets a higher standard than this document, local law applies.",
    ),
}
OWNERS = ("finance director", "operations director", "head of people", "company secretary", "head of IT")
REGIONS = ("North", "South", "East", "West", "Central", "International")
LINES = ("Core range", "Premium range", "Services", "Spares", "Digital", "Other")
FUNCTIONS = ("Operations", "Sales", "Finance", "IT", "Management", "Support")
SECTION = re.compile(r"SECTION \d+\. ")


def _kind(d: Doc) -> str:
    return "contract" if d.id.startswith("contract_") else "filler" if d.domain == "filler" else d.id


def _words(block) -> int:
    return len((block if isinstance(block, str) else block.render()).split())


def _sentences(kind: str, b: BaseDeal, rng: np.random.Generator) -> list[str]:
    """The kind's sentences with this document's numbers filled in once, so a repeated sentence repeats exactly."""
    rev = b.teaser.revenue_ltm
    return [s.format(name=b.teaser.name, industry=b.teaser.industry.lower(), n=int(rng.integers(3, 31)),
                     p=pct(float(rng.uniform(0.05, 0.35))), g=pct(float(rng.uniform(0.02, 0.08))), fy=FY_LAST,
                     fy0=FISCAL_YEARS[0], staff=int(rev * float(rng.uniform(3, 8))), owner=str(rng.choice(OWNERS)))
            for s in SENTENCES[kind]]


def _paragraph(sentences: list[str], pool: list[str], rng: np.random.Generator) -> str:
    out = []
    for _ in range(int(rng.integers(2, 4))):
        if not pool:  # refill once every sentence has been used in this document
            pool.extend(rng.permutation(sentences).tolist())
        out.append(pool.pop())
    return " ".join(out)


def _table(kind: str, b: BaseDeal, style: str, rng: np.random.Generator) -> str | None:
    """A code-written table of neutral numbers, or None for kinds without tables."""
    years = [h.fiscal_year for h in b.history]
    if kind == "cim":
        labels = list(rng.choice(REGIONS if rng.random() < 0.5 else LINES, 4, replace=False))
        shares = rng.dirichlet(np.ones(4))
        return table(style, ["Revenue by " + ("region" if labels[0] in REGIONS else "line")]
                     + [f"FY{y}" for y in years],
                     [[str(lab)] + [money(h.revenue * s) for h in b.history] for lab, s in zip(labels, shares)])
    if kind == "qoe":
        start = int(rng.integers(0, 7))
        return table(style, ["Month", "Revenue", "Gross margin"],
                     [[f"Month {start + i + 1}", money(b.teaser.revenue_ltm / 12 * float(rng.uniform(0.9, 1.1))),
                       pct(float(rng.uniform(0.25, 0.45)))] for i in range(6)])
    if kind == "audited":
        staff = b.teaser.revenue_ltm * float(rng.uniform(3, 8))
        return table(style, ["Average employees"] + [f"FY{y}" for y in years],
                     [[f] + [str(int(staff * s * float(rng.uniform(0.9, 1.1)))) for _ in years]
                      for f, s in zip(FUNCTIONS[:4], (0.6, 0.2, 0.1, 0.1))])
    if kind == "assets":
        return table(style, ["Site", "Floor area (sq m)", "Staff"],
                     [[f"Site {i + 1}", f"{int(rng.integers(800, 12000)):,}", str(int(rng.integers(10, 200)))]
                      for i in range(int(rng.integers(3, 7)))])
    return None


def _sections(d: Doc, b: BaseDeal, style: str, target: int, rng: np.random.Generator) -> list[list]:
    """Padding sections (a heading, then paragraphs and tables) until the document is just over target - 1 pages."""
    kind, pool, sections = _kind(d), [], []
    sentences = _sentences(kind, b, rng)
    titles = list(rng.permutation(TITLES[kind]))
    words, limit = _words(d.render()), (target - 1) * WORDS_PER_PAGE
    while words <= limit:
        title = titles[len(sections) % len(titles)] + ("" if len(sections) < len(titles) else " (continued)")
        section = [heading(style, 1, str(title))]
        words += _words(section[0])
        for _ in range(int(rng.integers(1, 4))):
            tab = _table(kind, b, style, rng) if rng.random() < 0.3 else None
            block = tab or _paragraph(sentences, pool, rng)
            section.append(block)
            words += _words(block)
            if words > limit:
                break
        sections.append(section)
    return sections


def _insert(d: Doc, sections: list[list], style: str, rng: np.random.Generator) -> Doc:
    """Place each padding section before a random existing heading (never the first) or at the end, then renumber."""
    blocks = d.blocks
    heads = [i for i, x in enumerate(blocks) if isinstance(x, str) and (x.startswith("## ") or SECTION.match(x))]
    cuts = sorted(heads[1:] + [len(blocks)])
    at: dict[int, list] = {}
    for s in sections:
        at.setdefault(int(rng.choice(cuts)), []).extend(s)
    out = []
    for i in range(len(blocks) + 1):
        out += at.get(i, [])
        if i < len(blocks):
            out.append(blocks[i])
    if style == "B":
        n = 0

        def renumber(x):
            nonlocal n
            if isinstance(x, str) and SECTION.match(x):
                n += 1
                return SECTION.sub(f"SECTION {n}. ", x, count=1)
            return x
        out = [renumber(x) for x in out]
    return d.model_copy(update={"blocks": out})


def pad(docs: list[Doc], b: BaseDeal, style: str, seed: int) -> list[Doc]:
    """The room at full size: 3-6 contracts, 6-9 filler documents, and every document padded to its target length."""
    rng = np.random.default_rng([seed, 3])  # its own stream, so render's draws are unchanged
    contracts = [d for d in docs if d.id.startswith("contract_")]
    fillers = [d for d in docs if d.domain == "filler"]
    used = {d.title.removeprefix("Customer Agreement — ") for d in contracts}
    names = [n for n in (f"{c} {k}" for c in _CUSTOMERS for k in _CUSTOMER_KIND) if n not in used]
    n_new = max(0, int(rng.integers(CONTRACTS[0], CONTRACTS[1] + 1)) - len(contracts))
    new_contracts = [
        Doc(id=f"contract_{len(contracts) + i + 1}", title=f"Customer Agreement — {name}", domain="commercial",
            blocks=[heading(style, 1, "Agreement"), TERM,  # plain text: padding runs after the prose pass
                    str(rng.choice(BOILERPLATE))])
        for i, name in enumerate(rng.choice(names, n_new, replace=False))]
    free = [k for k in EXTRA_FILLER if k not in {d.id for d in fillers}]
    n_fill = max(0, int(rng.integers(FILLER_DOCS[0], FILLER_DOCS[1] + 1)) - len(fillers))
    new_fillers = [Doc(id=str(k), title=EXTRA_FILLER[k], domain="filler", blocks=[heading(style, 1, EXTRA_FILLER[k])])
                   for k in rng.choice(free, n_fill, replace=False)]
    last_contract = max(i for i, d in enumerate(docs) if d.id.startswith("contract_"))
    docs = docs[:last_contract + 1] + new_contracts + docs[last_contract + 1:] + new_fillers
    targets = [int(rng.integers(TARGET_PAGES[_kind(d)][0], TARGET_PAGES[_kind(d)][1] + 1)) for d in docs]
    return [_insert(d, _sections(d, b, style, t, rng), style, rng) for d, t in zip(docs, targets)]
```

In `acqlab/generator/batch.py`, replace:

```python
from acqlab.generator.documents import Doc
from acqlab.generator.render import Evidence, render, teaser_text
```

with:

```python
from acqlab.generator.documents import Doc
from acqlab.generator.padding import pad
from acqlab.generator.render import Evidence, render, teaser_text
```

In `acqlab/generator/batch.py`, replace:

```python
        if not check_consistency(t, docs, evidence):
            pages = {d.id: d.pages for d in docs}
```

with:

```python
        docs = pad(docs, t.base, t.style, t.seed)  # after the prose pass, so every document lands on its target length
        if not check_consistency(t, docs, evidence):
            pages = {d.id: d.pages for d in docs}
```

In `acqlab/generator/truth.py`, replace:

```python
GENERATOR_VERSION = "2.0.0"
```

with:

```python
GENERATOR_VERSION = "3.0.0"
```

In `acqlab/generator/validate.py`, replace:

```python
from acqlab.generator.documents import PLACEHOLDER, Doc, money, pct
from acqlab.generator.render import FILLER, LABELS, Evidence, answer
```

with:

```python
from acqlab.generator.documents import PLACEHOLDER, Doc, money, pct
from acqlab.generator.padding import EXTRA_FILLER
from acqlab.generator.render import FILLER, LABELS, Evidence, answer
```

In `acqlab/generator/validate.py`, replace:

```python
               "Fixed Asset and Lease Schedule", "Legal Letter"} | set(FILLER.values())
```

with:

```python
               "Fixed Asset and Lease Schedule", "Legal Letter"} | set(FILLER.values()) | set(EXTRA_FILLER.values())
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest -q`
Expected: all pass (167: the 159 existing plus 8 new). No existing test changes in this task: `BUDGET_SHARE` is still 0.35.

- [ ] **Step 5: Commit**

```bash
git add acqlab/generator/padding.py tests/generator/test_padding.py acqlab/generator/batch.py acqlab/generator/truth.py acqlab/generator/validate.py
git commit -m "feat(generator): pad every room to full size (generator 3.0.0)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Budget share and the engine file

**Files:**
- Modify: `acqlab/dataroom/tools.py` (`BUDGET_SHARE`, and `write_room` takes `engine=`)
- Modify: `acqlab/generator/batch.py` (`run` writes `engine.json`)
- Modify: `tests/generator/test_tools.py`, `tests/generator/test_batch.py`, `tests/routers/test_track_a.py`

**Interfaces:**
- Produces: `write_room(room, teaser, docs, budget_share=BUDGET_SHARE, engine: dict | None = None) -> float`. Every generated room gets `engine.json = {"teaser": Teaser.model_dump(), "deal": Deal.model_dump()}`: the face-value deal, visible numbers only. Task 4's server reads it.

**Why the Track A tests change.** At the new share, with big rooms, a checklist retry no longer fits in `keys[0]`'s budget, and at a 50% budget no router has a choice to make. Each test gets back the room its premise needs:
- the retry test gets an explicit budget of 4 × the costliest fact
- the veto test uses the full budget

No expected number changes.

- [ ] **Step 1: Update the tests**

In `tests/generator/test_tools.py`, replace:

```python
import math

import pytest
```

with:

```python
import json
import math

import pytest
```

Append to `tests/generator/test_tools.py`:

```python


def test_engine_file_is_written_only_when_given(tmp_path):
    t = generate("d1", "test", 1, mc=20)
    docs, _ = render(t)
    write_room(tmp_path / "a", teaser_text(t), docs)
    face = {"teaser": t.base.teaser.model_dump(), "deal": t.deal.model_dump()}
    write_room(tmp_path / "b", teaser_text(t), docs, engine=face)
    assert not (tmp_path / "a" / "engine.json").exists()
    assert json.loads((tmp_path / "b" / "engine.json").read_text()) == face
```

In `tests/generator/test_batch.py`, replace:

```python
from acqlab.dataroom.tools import DataRoom
```

with:

```python
from acqlab.dataroom.tools import BUDGET_SHARE, DataRoom
```

In `tests/generator/test_batch.py`, replace:

```python
            assert not any(p.name.endswith(".json") and p.name != "index.json" for p in room.iterdir())
            dr = DataRoom(room)
            pages = sum(d["pages"] for d in dr.list_documents())
            assert key["budget"] == dr.budget == math.ceil(0.35 * pages)
```

with:

```python
            assert {p.name for p in room.iterdir() if p.suffix == ".json"} == {"index.json", "engine.json"}
            assert set(json.loads((room / "engine.json").read_text())) == {"teaser", "deal"}  # visible numbers only
            dr = DataRoom(room)
            pages = sum(d["pages"] for d in dr.list_documents())
            assert key["budget"] == dr.budget == math.ceil(BUDGET_SHARE * pages)
```

In `tests/routers/test_track_a.py`, replace:

```python
        s = Setting("regret+veto", "perfect", "medium", 0.5)
        want, left = [], 0.5 * k.budget
```

with:

```python
        s = Setting("regret+veto", "perfect", "medium", 1.0)  # the full budget leaves routers a choice in big rooms
        want, left = [], 1.0 * k.budget
```

In `tests/routers/test_track_a.py`, replace:

```python
    monkeypatch.setattr(ta, "FAIL_P", 1.0)
    k = keys[0]
```

with:

```python
    monkeypatch.setattr(ta, "FAIL_P", 1.0)
    k = keys[0].model_copy(update={"budget": 4 * max(keys[0].retrieval_cost.values())})  # room for a retry
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/generator/test_tools.py tests/generator/test_batch.py -q`
Expected: 2 failures. `write_room()` got an unexpected keyword argument `engine`, and the room's `.json` files are `{"index.json"}`.

- [ ] **Step 3: Implement**

In `acqlab/dataroom/tools.py`, replace:

```python
BUDGET_SHARE = 0.35  # default budget buys ~35% of the room's total page cost (design §5)
```

with:

```python
BUDGET_SHARE = 0.25  # the default budget covers every evidence document in ~21% of deals (Plan 4a design §1)
```

In `acqlab/dataroom/tools.py`, replace:

```python
def write_room(room: Path, teaser: str, docs: list[Doc], budget_share: float = BUDGET_SHARE) -> float:
    """Write documents and index; return the default budget."""
```

with:

```python
def write_room(room: Path, teaser: str, docs: list[Doc], budget_share: float = BUDGET_SHARE,
               engine: dict | None = None) -> float:
    """Write documents and index (and, given it, engine.json: the face-value deal the engine tool prices);
    return the default budget."""
```

In `acqlab/dataroom/tools.py`, replace:

```python
    (room / "index.json").write_text(json.dumps(index, indent=2))
    return budget
```

with:

```python
    (room / "index.json").write_text(json.dumps(index, indent=2))
    if engine is not None:
        (room / "engine.json").write_text(json.dumps(engine, indent=2))
    return budget
```

In `acqlab/generator/batch.py`, replace:

```python
            key.budget = write_room(out / "deals" / deal_id / "room", teaser, docs)
```

with:

```python
            face = {"teaser": key.truth.base.teaser.model_dump(), "deal": key.truth.deal.model_dump()}
            key.budget = write_room(out / "deals" / deal_id / "room", teaser, docs, engine=face)
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest -q`
Expected: all pass (168).

- [ ] **Step 5: Commit**

```bash
git add acqlab/dataroom/tools.py acqlab/generator/batch.py tests/generator/test_tools.py tests/generator/test_batch.py tests/routers/test_track_a.py
git commit -m "feat(dataroom): budget share 0.25 for big rooms; rooms carry the face-value deal

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Page-length check and word-level leak report

**Files:**
- Modify: `acqlab/generator/validate.py`
- Modify: `acqlab/generator/batch.py` (`run` collects pages and word counts, and reports)
- Modify: `tests/generator/test_validate.py`

**Interfaces:**
- Produces:
  - `check_batch(truths, texts, pages: dict[str, dict[str, int]] | None = None) -> list[str]`. Page problems read `"pages: <doc> is +x.xx pages longer on average when '<trap>' is a trap"`.
  - `doc_words(docs) -> dict[str, Counter]`, for the evidence documents only.
  - `word_leaks(truths, words) -> list[dict]`, with rows `{"trap", "doc", "word", "auc"}`, most separating first.
  - `PAGE_DOCS = ("cim", "qoe", "audited", "contract_1", "assets", "legal")`.
- `batch.run` writes `<out>/word_leaks.json` and prints a `NOTE:` line when a batch has ≥ 100 deals. Word leaks are a report, not a batch problem, and they don't change the exit code.

**The statistics.**
- **Page check:** a Welch gap test per (trap, document or whole room). It flags a gap wider than 4 standard errors, and runs only on batches of ≥ 100 deals with groups of ≥ 10. With exact targets, a zero-variance gap is flagged if it isn't zero.
- **Word report:** a Mann–Whitney AUC per (trap, evidence document, word). It flags when |AUC − 0.5| exceeds both 0.15 and 5 null standard errors, so small groups stay quiet. On 500 deals with shuffled labels it finds 0 leaks; on the real labels it finds 48.

- [ ] **Step 1: Write the failing tests**

In `tests/generator/test_validate.py`, replace:

```python
from acqlab.generator.documents import money
from acqlab.generator.render import LABELS, render, teaser_text
from acqlab.generator.truth import generate
from acqlab.generator.validate import check_batch, check_consistency, check_engine, check_leaks
```

with:

```python
from collections import Counter

import pytest

from acqlab.generator.documents import money
from acqlab.generator.render import LABELS, render, teaser_text
from acqlab.generator.truth import generate
from acqlab.generator.validate import (check_batch, check_consistency, check_engine, check_leaks, doc_words,
                                      word_leaks)
```

Append to `tests/generator/test_validate.py`:

```python


@pytest.fixture(scope="module")
def big_batch():
    """100 padded test deals: (truths, texts, pages, words)."""
    from acqlab.generator.padding import pad
    deals = [generate(f"p{s}", "test", s, mc=4) for s in range(100)]
    rooms = {t.id: pad(render(t)[0], t.base, t.style, t.seed) for t in deals}
    texts = {tid: " ".join(d.render() for d in docs) for tid, docs in rooms.items()}
    pages = {tid: {d.id: d.pages for d in docs} for tid, docs in rooms.items()}
    return deals, texts, pages, {tid: doc_words(docs) for tid, docs in rooms.items()}


def test_batch_check_flags_documents_that_are_longer_in_trap_deals(big_batch):
    deals, texts, pages, _ = big_batch
    assert not any("pages" in p for p in check_batch(deals, texts, pages))
    debt = {t.id for t in deals if any(f.trap == "debt_like" and f.role != "clean" for f in t.facts)}
    skewed = {tid: dict(p, legal=p["legal"] + 2 * (tid in debt)) for tid, p in pages.items()}
    assert any("pages: legal" in p for p in check_batch(deals, texts, skewed))


def test_word_leaks_finds_a_planted_word_and_the_known_template_leak(big_batch):
    deals, _, _, words = big_batch
    found = {(r["trap"], r["doc"], r["word"]) for r in word_leaks(deals, words)}
    assert ("concentration", "contract_1", "confirmed") in found  # Plan 2's reveal wording; fixed in Plan 4b
    capex = {t.id for t in deals if any(f.trap == "capex" and f.role != "clean" for f in t.facts)}
    planted = {tid: dict(w, qoe=w["qoe"] + Counter({"zebra": tid in capex})) for tid, w in words.items()}
    assert ("capex", "qoe", "zebra") in {(r["trap"], r["doc"], r["word"]) for r in word_leaks(deals, planted)}
    assert not any(r["word"] == "zebra" for r in word_leaks(deals, words))
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/generator/test_validate.py -q`
Expected: collection error, `ImportError: cannot import name 'doc_words'`.

- [ ] **Step 3: Implement**

In `acqlab/generator/validate.py`, replace:

```python
import re

import numpy as np
```

with:

```python
import re
from collections import Counter

import numpy as np
```

In `acqlab/generator/validate.py`, replace:

```python
ADDBACK_MIN_GROUP = 20  # smaller groups are too noisy to compare
```

with:

```python
ADDBACK_MIN_GROUP = 20  # smaller groups are too noisy to compare
PAGE_DOCS = ("cim", "qoe", "audited", "contract_1", "assets", "legal")  # every trap's evidence lives in these
PAGE_Z = 4.0  # flag a length gap wider than 4 standard errors (35 comparisons per batch, so false alarms are rare)
PAGE_MIN_GROUP = 10
WORD_LEAK_AUC = 0.15  # |AUC - 0.5| above this: a word's count in a document tells trap deals from clean ones
WORD_LEAK_Z = 5.0  # ...and above 5 null standard errors, so hundreds of words tested on small groups stay quiet
```

In `acqlab/generator/validate.py`, replace:

```python
def check_batch(truths: list[DealTruth], texts: dict[str, str]) -> list[str]:
    """Batch-level checks: go rate near 50%, topic mentions equally common in trap and clean deals, and add-back
    line items the same size for clean and trap facts."""
```

with:

```python
def _page_problems(truths: list[DealTruth], pages: dict[str, dict[str, int]]) -> list[str]:
    """Bigger rooms must not make a trap's document (or the room) longer: mean pages by role, per trap."""
    problems = []
    for trap in TOPIC_WORDS:
        for doc in PAGE_DOCS + ("room",):
            by: dict[bool, list[int]] = {True: [], False: []}
            for t in truths:
                role = next(f.role for f in t.facts if f.trap == trap)
                by[role != "clean"].append(sum(pages[t.id].values()) if doc == "room" else pages[t.id][doc])
            a, c = np.array(by[True], float), np.array(by[False], float)
            if min(len(a), len(c)) < PAGE_MIN_GROUP:
                continue
            gap = a.mean() - c.mean()
            se = np.sqrt(a.var(ddof=1) / len(a) + c.var(ddof=1) / len(c))
            if (abs(gap) > PAGE_Z * se) if se > 0 else gap != 0:
                problems.append(f"pages: {doc} is {gap:+.2f} pages longer on average when {trap!r} is a trap")
    return problems


def check_batch(truths: list[DealTruth], texts: dict[str, str], pages: dict[str, dict[str, int]] | None = None
                ) -> list[str]:
    """Batch-level checks: go rate near 50%, topic mentions equally common in trap and clean deals, add-back line
    items the same size for clean and trap facts, and (given page counts) documents the same length."""
```

In `acqlab/generator/validate.py`, replace:

```python
    return problems + _addback_problems(truths, texts)
```

with:

```python
    if pages is not None and len(truths) >= 100:  # smaller batches are too noisy to judge
        problems += _page_problems(truths, pages)
    return problems + _addback_problems(truths, texts)


def doc_words(docs: list[Doc]) -> dict[str, Counter]:
    """Word counts of the evidence documents, as a search tool would see them."""
    return {d.id: Counter(re.findall(r"[a-z]+", d.render().lower())) for d in docs if d.id in PAGE_DOCS}


def _auc(a: np.ndarray, b: np.ndarray) -> float:
    """Chance a random trap-deal count beats a random clean-deal count, ties counted half (Mann-Whitney)."""
    _, inv = np.unique(np.concatenate([a, b]), return_inverse=True)
    n = np.bincount(inv)
    rank = np.cumsum(n) - n + (n + 1) / 2
    return float((rank[inv[:len(a)]].sum() - len(a) * (len(a) + 1) / 2) / (len(a) * len(b)))


def word_leaks(truths: list[DealTruth], words: dict[str, dict[str, Counter]]) -> list[dict]:
    """(trap, document, word) triples where the word's count separates trap deals from clean ones: what a search
    tool returning hit counts would leak. A report, not a validation failure: search stays off until Plan 4b
    rewrites the reveal wording."""
    out = []
    for trap in TOPIC_WORDS:
        real = np.array([next(f.role for f in t.facts if f.trap == trap) != "clean" for t in truths])
        if min(real.sum(), (~real).sum()) < PAGE_MIN_GROUP:
            continue
        n1, n0 = int(real.sum()), int((~real).sum())
        bar = max(WORD_LEAK_AUC, WORD_LEAK_Z * np.sqrt((n1 + n0 + 1) / (12 * n1 * n0)))
        for doc in PAGE_DOCS:
            for w in sorted(set().union(*(words[t.id][doc] for t in truths))):
                x = np.array([words[t.id][doc][w] for t in truths])
                auc = _auc(x[real], x[~real])
                if abs(auc - 0.5) > bar:
                    out.append({"trap": trap, "doc": doc, "word": w, "auc": round(auc, 3)})
    return sorted(out, key=lambda r: -abs(r["auc"] - 0.5))
```

In `acqlab/generator/batch.py`, replace:

```python
from acqlab.generator.validate import check_batch, check_consistency, check_engine, check_leaks
```

with:

```python
from acqlab.generator.validate import (check_batch, check_consistency, check_engine, check_leaks, doc_words,
                                      word_leaks)
```

In `acqlab/generator/batch.py`, replace:

```python
    keys, texts = [], {}
```

with:

```python
    keys, texts, pages, words = [], {}, {}, {}
```

In `acqlab/generator/batch.py`, replace:

```python
            texts[deal_id] = " ".join(d.render() for d in docs)
    (out / "splits.json").write_text(json.dumps(splits, indent=2))
    problems = check_batch([k.truth for k in keys], texts)
```

with:

```python
            texts[deal_id] = " ".join(d.render() for d in docs)
            pages[deal_id] = {d.id: d.pages for d in docs}
            words[deal_id] = doc_words(docs)
    (out / "splits.json").write_text(json.dumps(splits, indent=2))
    problems = check_batch([k.truth for k in keys], texts, pages)
    if len(keys) >= 100:  # smaller batches are too noisy to judge
        leaks = word_leaks([k.truth for k in keys], words)
        (out / "word_leaks.json").write_text(json.dumps(leaks, indent=2))
        print(f"NOTE: {len(leaks)} word-level leaks (see word_leaks.json); agents get no search tool until Plan 4b")
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest -q`
Expected: all pass (170).

- [ ] **Step 5: Commit**

```bash
git add acqlab/generator/validate.py acqlab/generator/batch.py tests/generator/test_validate.py
git commit -m "feat(generator): page-length leak check and word-level leak report

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: MCP tool server

**Files:**
- Create: `acqlab/agents/__init__.py` (empty), `acqlab/agents/server.py`
- Create: `tests/agents/__init__.py` (empty), `tests/agents/test_server.py`
- Modify: `tests/conftest.py` (a session-scoped `data` fixture: two generated dev deals)

**Interfaces:**
- Consumes:
  - `DataRoom`, `BudgetExceeded`
  - `params_for`, `TRAPS`
  - `walk_away`, `is_go`, `Deal`, `Teaser`
  - from routers: `Issue`, `draw`, `walk_aways`, `HAIRCUT_CAP`, `decide`, `score_regret`
  - the room's `engine.json` (Task 2)
- Produces:
  - `python -m acqlab.agents.server --room R --budget B --trace T.jsonl [--router]`
  - `tool_names(router: bool) -> list[str]`
  - `Session(room, budget, trace, router).call(name, args) -> {"content": [{"type": "text", "text": ...}], "isError": bool}`
  - constants `MAX_CALLS = 80` and `N_WORLDS = 400`
  - trace rows `{"i", "tool", "args", "cost", "remaining", "refused", "error"[, "result"]}`, one JSON object per line. `result` is present for successful calls except `open_document`, whose text is not copied.

**Tools:**
- `list_documents` (free)
- `open_document` (costs its pages)
- `evaluate(adjustments)` (free), with `{trap: $M ≥ 0}`
- `note_issue(name, type, chance, low, high, docs)` (free), one note per trap type
- `rank_issues()` (free, router system only)
- `submit(go, walk_away, reason)` (free, ends the run)

**`rank_issues`:**
- **Notes to beliefs.** A note with chance < 1 becomes an open `Issue(p_real=chance, hi=high)`. A note with chance 1 becomes known `(low, high)`. Types with no note are unproposed.
- **Worlds:** `draw(beliefs, 400, default_rng(0))`.
- **Cost** is the pages of the note's docs not yet opened, with a minimum of 1.
- **Scores** come from router 6's `score_regret`, including pair screening.

- [ ] **Step 1: Write the failing tests**

Create empty `tests/agents/__init__.py`.

In `tests/conftest.py`, replace:

```python
import pytest

from acqlab.engine import Company, Deal, Financing, Params, Policy
```

with:

```python
import pytest

from acqlab.engine import Company, Deal, Financing, Params, Policy
from acqlab.generator import batch
```

Append to `tests/conftest.py`:

```python


@pytest.fixture(scope="session")
def data(tmp_path_factory):
    """Two generated dev deals (rooms, answer keys, splits), shared by the agents tests."""
    out = tmp_path_factory.mktemp("data")
    assert batch.run(out, {"dev": 2, "test": 0, "hand": 0, "showcase": 0}, mc=20) == []
    return out
```

Create `tests/agents/test_server.py`:

```python
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

import acqlab.agents.server as server
from acqlab.agents.server import MAX_CALLS, Session, tool_names
from acqlab.engine import walk_away
from acqlab.generator.batch import AnswerKey
from acqlab.generator.traps import params_for
from acqlab.routers.beliefs import Issue, draw, walk_aways
from acqlab.routers.routers import score_regret


def _key(data: Path) -> AnswerKey:
    return AnswerKey.model_validate_json((data / "truth" / "dev-000.json").read_text())


def _session(data, tmp_path, router=True, budget=None):
    key = _key(data)
    return Session(data / "deals" / "dev-000" / "room", budget or key.budget, tmp_path / "t.jsonl", router)


def _out(reply: dict):
    text = reply["content"][0]["text"]
    return text if reply["isError"] else json.loads(text)


def _trace(tmp_path) -> list[dict]:
    return [json.loads(line) for line in (tmp_path / "t.jsonl").read_text().splitlines()]


def test_the_server_speaks_mcp_over_stdio(data, tmp_path):
    room, trace = data / "deals" / "dev-000" / "room", tmp_path / "t.jsonl"
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "list_documents", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
             "params": {"name": "submit", "arguments": {"go": True, "walk_away": 100, "reason": "r"}}},
            {"jsonrpc": "2.0", "id": 5, "method": "resources/list"}]
    proc = subprocess.run([sys.executable, "-m", "acqlab.agents.server", "--room", str(room), "--budget", "10",
                           "--trace", str(trace)], input="".join(json.dumps(m) + "\n" for m in msgs),
                          capture_output=True, text=True, timeout=60)
    replies = [json.loads(line) for line in proc.stdout.splitlines()]
    assert [r["id"] for r in replies] == [1, 2, 3, 4, 5]  # the notification got no reply
    assert replies[0]["result"]["protocolVersion"] == "2025-06-18"
    assert [t["name"] for t in replies[1]["result"]["tools"]] == tool_names(router=False)
    assert "rank_issues" not in tool_names(router=False) and "rank_issues" in tool_names(router=True)
    assert json.loads(replies[2]["result"]["content"][0]["text"])[0]["id"] == "cim"
    assert replies[4]["error"]["code"] == -32601
    assert [r["tool"] for r in map(json.loads, trace.read_text().splitlines())] == ["list_documents", "submit"]


def test_reading_is_charged_and_over_budget_calls_are_refused(data, tmp_path):
    s = _session(data, tmp_path, budget=5)
    opened = s.call("open_document", {"doc_id": "legal"})
    assert not opened["isError"] and "Litigation" in opened["content"][0]["text"]
    refused = s.call("open_document", {"doc_id": max(s.pages, key=s.pages.get)})
    assert refused["isError"] and "left" in _out(refused)
    rows = _trace(tmp_path)
    assert rows[0]["cost"] == s.pages["legal"] and rows[0]["remaining"] == 5 - s.pages["legal"]
    assert "result" not in rows[0]  # document text is not copied into the trace
    assert rows[1]["refused"] and rows[1]["cost"] == 0


def test_search_is_not_offered(data, tmp_path):
    """Search hit counts give traps away until the reveal wording is fixed (Plan 4b)."""
    assert "search" not in tool_names(router=True)
    assert _session(data, tmp_path).call("search", {"query": "confirmed"})["isError"]


def test_after_the_call_limit_only_submit_is_accepted_and_submit_ends_the_run(data, tmp_path):
    s = _session(data, tmp_path)
    for _ in range(MAX_CALLS):
        assert not s.call("list_documents", {})["isError"]
    assert "limit" in _out(s.call("list_documents", {}))
    assert _out(s.call("submit", {"go": False, "walk_away": 90.5, "reason": "r"})) == {"submitted": True}
    assert "over" in _out(s.call("evaluate", {"adjustments": {}}))


def test_evaluate_prices_dollar_adjustments_with_the_engine(data, tmp_path):
    key, s = _key(data), _session(data, tmp_path)
    face = _out(s.call("evaluate", {"adjustments": {}}))
    assert face["walk_away"] == pytest.approx(key.truth.face_walk_away, abs=0.01) and face["go"] == key.truth.face_go
    got = _out(s.call("evaluate", {"adjustments": {"debt_like": 5.0, "concentration": 3.0}}))
    want = walk_away(key.truth.deal, params_for({"debt_like": 5.0, "concentration": 3.0}, key.truth.base))
    assert got["walk_away"] == pytest.approx(want, abs=0.01)
    for bad in ({"debt_like": -1}, {"goodwill": 2}, {"nwc": "big"}):
        assert s.call("evaluate", {"adjustments": bad})["isError"]


def test_rank_issues_is_router_6_on_the_agents_own_notes(data, tmp_path):
    s = _session(data, tmp_path)
    s.call("open_document", {"doc_id": "contract_1"})
    s.call("note_issue", {"name": "add-back", "type": "addback", "chance": 0.4, "low": 0, "high": 8,
                          "docs": ["qoe", "audited"]})
    s.call("note_issue", {"name": "big client", "type": "concentration", "chance": 0.3, "low": 0, "high": 30,
                          "docs": ["contract_1", "cim"]})
    s.call("note_issue", {"name": "debt", "type": "debt_like", "chance": 1, "low": 2, "high": 4, "docs": ["legal"]})
    got = _out(s.call("rank_issues", {}))
    beliefs = {t: Issue(proposed=False) for t in ("addback", "debt_like", "concentration", "nwc", "capex")}
    beliefs |= {"addback": Issue(p_real=0.4, hi=8), "concentration": Issue(p_real=0.3, hi=30),
                "debt_like": Issue(known=(2, 4))}
    values = draw(beliefs, server.N_WORLDS, np.random.default_rng(0))
    w = walk_aways(s.face, values)
    costs = {"addback": s.pages["qoe"] + s.pages["audited"], "concentration": s.pages["cim"]}  # contract_1 is read
    want = score_regret(values, w, s.face.deal.asking_price, costs, ["addback", "concentration"])
    assert {r["type"]: r["regret_removed_per_page"] for r in got["ranking"]} == {
        t: round(v, 4) for t, v in want.items()}
    assert {r["type"]: r["pages_to_check"] for r in got["ranking"]} == costs
    assert "rank_issues" in {r["tool"] for r in _trace(tmp_path)}


def test_rank_issues_is_refused_without_the_router(data, tmp_path):
    assert _session(data, tmp_path, router=False).call("rank_issues", {})["isError"]


def test_bad_notes_and_bad_arguments_are_tool_errors(data, tmp_path):
    s = _session(data, tmp_path)
    assert s.call("note_issue", {"name": "x", "type": "goodwill", "chance": 0.5, "low": 0, "high": 1, "docs": []})[
        "isError"]
    assert s.call("note_issue", {"name": "x", "type": "nwc", "chance": 0.5, "low": 3, "high": 1, "docs": []})[
        "isError"]
    assert s.call("open_document", {"doc_id": 12})["isError"]
    assert s.call("open_document", {"doc_id": "../../truth/dev-000"})["isError"]
    assert s.call("submit", {"go": "yes", "walk_away": 1, "reason": "r"})["isError"]
    assert s.call("delete_everything", {})["isError"]


def test_the_server_needs_nothing_outside_its_room(data, tmp_path):
    """Isolation: no answer-key types or paths in the source, and it runs on a room copied away from any keys."""
    source = Path(server.__file__).read_text()
    assert not any(word in source for word in ("AnswerKey", "DealTruth", "truth"))
    room = shutil.copytree(data / "deals" / "dev-000" / "room", tmp_path / "alone" / "room")
    s = Session(room, 10, tmp_path / "t.jsonl", router=True)
    assert not s.call("evaluate", {"adjustments": {"capex": 1}})["isError"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/agents -q`
Expected: collection error, `ModuleNotFoundError: No module named 'acqlab.agents'`.

- [ ] **Step 3: Implement**

Create empty `acqlab/agents/__init__.py`, then create `acqlab/agents/server.py`:

```python
"""Tool server for one solver run (Plan 4a design §2): the data room, the engine, issue notes and, for the router
system, router 6. No search: its hit counts give traps away until Plan 4b fixes the reveal wording (see
validate.word_leaks). Speaks MCP over stdio (one JSON-RPC message per line) with the standard library only. It reads only
its room folder, never an answer key, and writes every call to a trace file (one JSON object per line).

  python -m acqlab.agents.server --room <room> --budget 22 --trace <file.jsonl> [--router]
"""
import argparse
import json
import math
import sys
from pathlib import Path
from typing import NamedTuple

import numpy as np

from acqlab.dataroom.tools import BudgetExceeded, DataRoom
from acqlab.engine import Deal, is_go, walk_away
from acqlab.generator.sample import Teaser
from acqlab.generator.traps import TRAPS, params_for
from acqlab.routers.beliefs import HAIRCUT_CAP, Issue, draw, walk_aways
from acqlab.routers.routers import decide, score_regret

MAX_CALLS = 80  # after this many calls only submit is accepted
N_WORLDS = 400
PROTOCOL = "2025-06-18"
ADJUSTMENTS = ("Adjustments in $M, each optional and >= 0: addback = claimed add-backs that are not really one-time "
               "(reduces EBITDA); debt_like = debt-like items payable at closing; concentration = annual revenue that "
               "will be lost; nwc = amount by which closing net working capital falls short of normal; capex = extra "
               "capital expenditure needed per year.")
_OBJ = {"type": "object"}
TOOLS = {
    "list_documents": ("Free. Every document's id, title, domain and page count.", {**_OBJ, "properties": {}}),
    "open_document": ("Costs 1 unit per page. The document's full text.",
                      {**_OBJ, "properties": {"doc_id": {"type": "string"}}, "required": ["doc_id"]}),
    "evaluate": ("Free. Walk-away price (the most the sponsor should pay, $M) and whether the deal clears at the "
                 "asking price, given your adjustments. " + ADJUSTMENTS,
                 {**_OBJ, "properties": {"adjustments": {
                     **_OBJ, "properties": {t: {"type": "number", "minimum": 0} for t in TRAPS},
                     "additionalProperties": False}}, "required": ["adjustments"]}),
    "note_issue": ("Free. Record your belief about one issue type (one note per type; a new note replaces the old): "
                   "the chance it is real (0 to 1), its size range in $M if real (same units as evaluate), and the "
                   "document ids that would settle it. Use chance 1 once confirmed.",
                   {**_OBJ, "properties": {
                       "name": {"type": "string"}, "type": {"type": "string", "enum": list(TRAPS)},
                       "chance": {"type": "number", "minimum": 0, "maximum": 1},
                       "low": {"type": "number", "minimum": 0}, "high": {"type": "number", "minimum": 0},
                       "docs": {"type": "array", "items": {"type": "string"}}},
                    "required": ["name", "type", "chance", "low", "high", "docs"]}),
    "rank_issues": ("Free. Ranks your open notes (chance below 1) by the expected $M of decision regret removed per "
                    "page of reading still needed to settle each, from a pricing model built on your own notes. "
                    "Advice only.", {**_OBJ, "properties": {}}),
    "submit": ("Free. Your final answer; ends the run. go = buy at the asking price; walk_away in $M.",
               {**_OBJ, "properties": {"go": {"type": "boolean"}, "walk_away": {"type": "number"},
                                       "reason": {"type": "string"}}, "required": ["go", "walk_away", "reason"]}),
}


def tool_names(router: bool) -> list[str]:
    return [t for t in TOOLS if router or t != "rank_issues"]


class Face(NamedTuple):
    """The deal at face value, from visible numbers only. Stands in for BaseDeal in params_for and walk_aways, which
    read only .teaser and .deal."""
    teaser: Teaser
    deal: Deal


class ToolError(Exception):
    """A refused or invalid call: reported to the solver as a tool error, not a crash."""


class Session:
    def __init__(self, room: Path, budget: float, trace: Path, router: bool):
        self.room = DataRoom(room, budget)
        engine = json.loads((room / "engine.json").read_text())
        self.face = Face(Teaser(**engine["teaser"]), Deal(**engine["deal"]))
        self.pages = {d["id"]: d["pages"] for d in json.loads((room / "index.json").read_text())["documents"]}
        self.trace, self.router = trace, router
        self.opened: set[str] = set()
        self.notes: dict[str, dict] = {}
        self.calls = 0
        self.submitted = False

    def call(self, name: str, args: dict) -> dict:
        """One tools/call: run it, log it, and wrap the result as MCP content."""
        self.calls += 1
        spent = self.room.spent
        try:
            if name not in tool_names(self.router):
                raise ToolError(f"unknown tool {name!r}")
            if self.submitted:
                raise ToolError("the run is over: you already submitted")
            if self.calls > MAX_CALLS and name != "submit":
                raise ToolError(f"tool-call limit ({MAX_CALLS}) reached: call submit now")
            result, error = getattr(self, "_" + name)(**args), None
        except (ToolError, BudgetExceeded, KeyError, TypeError, ValueError) as e:
            result, error = None, str(e).strip("'\"")
        row = {"i": self.calls, "tool": name, "args": args, "cost": self.room.spent - spent,
               "remaining": self.room.remaining, "refused": error is not None, "error": error}
        if name != "open_document" and error is None:
            row["result"] = result
        with self.trace.open("a") as f:
            f.write(json.dumps(row) + "\n")
        text = error if error is not None else (result if isinstance(result, str) else json.dumps(result))
        return {"content": [{"type": "text", "text": text}], "isError": error is not None}

    def _list_documents(self) -> list[dict]:
        return self.room.list_documents()

    def _open_document(self, doc_id: str) -> str:
        text = self.room.open_document(doc_id)
        self.opened.add(doc_id)
        return text

    def _amounts(self, adjustments: dict) -> dict[str, float]:
        out = {}
        for trap, v in adjustments.items():
            if trap not in TRAPS or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
                raise ToolError(f"bad adjustment {trap}={v!r}: use {', '.join(TRAPS)} with $M amounts >= 0")
            out[trap] = float(v)
        if "concentration" in out:  # the engine needs a haircut below 100% of revenue
            out["concentration"] = min(out["concentration"], HAIRCUT_CAP * self.face.teaser.revenue_ltm)
        return out

    def _evaluate(self, adjustments: dict) -> dict:
        p = params_for(self._amounts(adjustments), self.face)
        return {"walk_away": round(walk_away(self.face.deal, p), 2), "asking_price": round(self.face.deal.asking_price, 2),
                "go": is_go(self.face.deal, p)}

    def _note_issue(self, name: str, type: str, chance: float, low: float, high: float, docs: list) -> dict:
        if type not in TRAPS:
            raise ToolError(f"type must be one of {', '.join(TRAPS)}")
        if not (0 <= chance <= 1 and 0 <= low <= high and math.isfinite(high)) or not isinstance(docs, list):
            raise ToolError("need 0 <= chance <= 1, 0 <= low <= high and a list of document ids")
        self.notes[type] = {"name": str(name), "chance": float(chance), "low": float(low), "high": float(high),
                            "docs": [str(d) for d in docs]}
        return {"noted": type, "notes": len(self.notes)}

    def _rank_issues(self) -> dict:
        beliefs = {t: Issue(proposed=False) for t in TRAPS}  # un-noted types: nobody thought of them, so 0
        for t, n in self.notes.items():
            beliefs[t] = Issue(known=(n["low"], n["high"])) if n["chance"] >= 1 else Issue(p_real=n["chance"],
                                                                                           hi=n["high"])
        open_ = [t for t, n in self.notes.items() if n["chance"] < 1]
        values = draw(beliefs, N_WORLDS, np.random.default_rng(0))
        w = walk_aways(self.face, values)
        ask = self.face.deal.asking_price
        go, median = decide(w, ask)
        costs = {t: max(1, sum(self.pages[d] for d in set(self.notes[t]["docs"])
                               if d in self.pages and d not in self.opened)) for t in open_}
        scores = score_regret(values, w, ask, costs, open_) if open_ else {}
        ranking = [{"type": t, "name": self.notes[t]["name"], "regret_removed_per_page": round(s, 4),
                    "pages_to_check": costs[t]} for t, s in sorted(scores.items(), key=lambda kv: -kv[1])]
        return {"ranking": ranking, "current_decision": {"go": go, "walk_away_median": round(median, 2)}}

    def _submit(self, go: bool, walk_away: float, reason: str) -> dict:
        if not isinstance(go, bool) or not isinstance(walk_away, (int, float)) or not math.isfinite(walk_away):
            raise ToolError("go must be true/false and walk_away a number")
        self.submitted = True
        return {"submitted": True}


def serve(session: Session, inp=sys.stdin, out=sys.stdout) -> None:
    """MCP's stdio transport: initialize, tools/list, tools/call, ping. Notifications get no reply."""
    for line in inp:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
            out.write(json.dumps(reply) + "\n")
            out.flush()
            continue
        if "id" not in msg:
            continue
        method, params = msg.get("method"), msg.get("params") or {}
        reply = {"jsonrpc": "2.0", "id": msg["id"]}
        if method == "initialize":
            reply["result"] = {"protocolVersion": params.get("protocolVersion", PROTOCOL),
                               "capabilities": {"tools": {}}, "serverInfo": {"name": "room", "version": "1"}}
        elif method == "tools/list":
            reply["result"] = {"tools": [{"name": n, "description": TOOLS[n][0], "inputSchema": TOOLS[n][1]}
                                         for n in tool_names(session.router)]}
        elif method == "tools/call":
            reply["result"] = session.call(params.get("name", ""), params.get("arguments") or {})
        elif method == "ping":
            reply["result"] = {}
        else:
            reply["error"] = {"code": -32601, "message": f"method not found: {method}"}
        out.write(json.dumps(reply) + "\n")
        out.flush()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--room", type=Path, required=True)
    ap.add_argument("--budget", type=float, required=True)
    ap.add_argument("--trace", type=Path, required=True)
    ap.add_argument("--router", action="store_true", help="offer rank_issues (the S1b + router system)")
    args = ap.parse_args(argv)
    serve(Session(args.room, args.budget, args.trace, args.router))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest -q`
Expected: all pass (179).

- [ ] **Step 5: Commit**

```bash
git add acqlab/agents tests/agents tests/conftest.py
git commit -m "feat(agents): MCP tool server with budget, trace and router 6 over the agent's notes

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Prompts and the `claude -p` adapter

**Files:**
- Create: `acqlab/agents/prompts.py`, `acqlab/agents/solver.py`
- Create: `tests/agents/fake_claude.py`, `tests/agents/test_solver.py`
- Modify: `tests/conftest.py` (a `fake_claude` fixture)

**Interfaces:**
- Consumes: `tool_names(router)` (Task 4) and `LLMUnavailable` from `acqlab.llm`.
- Produces:
  - `system_prompt(router: bool) -> str`, `user_prompt(teaser: str, budget: float) -> str`, `ROUTER` (the paragraph)
  - `MODEL = "claude-opus-5-5"`, `TIMEOUT = 1200`
  - `class RunTimeout(LLMUnavailable)`
  - `claude_bin()`, which reads `CLAUDE_BIN` and falls back to `claude`
  - `command(claude, prompt, system, mcp_config, router) -> list[str]`
  - `solve(room, budget, trace, router, *, claude=None, timeout=TIMEOUT) -> dict`, the CLI's JSON result
  - the `fake_claude` fixture, which returns the path of an executable fake; select a mode with the `FAKE_CLAUDE` env var: `ok | nosubmit | noserver | limit | sleep`

**Sandbox flags** (verified against CLI 2.1.280):

```text
-p <prompt> --output-format json --model claude-opus-5-5 --tools "" --mcp-config <tmp>/mcp.json --strict-mcp-config
--allowedTools mcp__room__<tool>,... --setting-sources "" --disable-slash-commands --system-prompt <ours>
--no-session-persistence
```

Each run starts in an empty temp directory with `stdin=DEVNULL`.

- [ ] **Step 1: Write the failing tests**

In `tests/conftest.py`, replace:

```python
import pytest

from acqlab.engine import Company, Deal, Financing, Params, Policy
from acqlab.generator import batch
```

with:

```python
import sys
from pathlib import Path

import pytest

from acqlab.engine import Company, Deal, Financing, Params, Policy
from acqlab.generator import batch

FAKE = Path(__file__).parent / "agents" / "fake_claude.py"
```

Append to `tests/conftest.py`:

```python


@pytest.fixture
def fake_claude(tmp_path, monkeypatch):
    """Path to an executable fake `claude`; set FAKE_CLAUDE (mode) with monkeypatch.setenv."""
    exe = tmp_path / "claude"
    exe.write_text(f"#!{sys.executable}\nimport runpy\nrunpy.run_path({str(FAKE)!r}, run_name='__main__')\n")
    exe.chmod(0o755)
    monkeypatch.setenv("FAKE_ARGS", str(tmp_path / "args.json"))
    return str(exe)
```

Create `tests/agents/fake_claude.py`:

```python
"""A stand-in for `claude -p` in tests: it drives our tool server the way Claude would, spending no quota.
FAKE_CLAUDE picks the behaviour: ok | nosubmit | noserver | limit | sleep. FAKE_ARGS, if set, is a file that gets
this call's argv and working directory."""
import json
import os
import subprocess
import sys
import time

mode = os.environ.get("FAKE_CLAUDE", "ok")
argv = sys.argv[1:]
if os.environ.get("FAKE_ARGS"):
    with open(os.environ["FAKE_ARGS"], "w") as f:
        json.dump({"argv": argv, "cwd": os.getcwd(), "files": sorted(os.listdir("."))}, f)
if mode == "limit":
    print(json.dumps({"type": "result", "is_error": True, "result": "Claude AI usage limit reached"}))
    sys.exit(1)
if mode == "sleep":
    time.sleep(60)
calls = []
if mode != "noserver":
    spec = json.load(open(argv[argv.index("--mcp-config") + 1]))["mcpServers"]["room"]
    proc = subprocess.Popen([spec["command"], *spec["args"]], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    n = 0

    def rpc(method, params=None):
        global n
        n += 1
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": n, "method": method, "params": params or {}}) + "\n")
        proc.stdin.flush()
        return json.loads(proc.stdout.readline())["result"]

    def tool(tool_name, **args):
        calls.append(tool_name)
        reply = rpc("tools/call", {"name": tool_name, "arguments": args})
        text = reply["content"][0]["text"]
        return text if tool_name == "open_document" or reply["isError"] else json.loads(text)

    rpc("initialize", {"protocolVersion": "2025-06-18"})
    names = [t["name"] for t in rpc("tools/list")["tools"]]
    docs = tool("list_documents")
    if mode == "ok":
        tool("open_document", doc_id=docs[-1]["id"])  # a short filler document
        face = tool("evaluate", adjustments={})
        tool("note_issue", name="add-back", type="addback", chance=0.5, low=0, high=5, docs=["qoe"])
        if "rank_issues" in names:
            tool("rank_issues")
        tool("submit", go=not face["go"], walk_away=face["walk_away"] - 1, reason="fake")
    proc.stdin.close()
    proc.wait()
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "done", "num_turns": len(calls),
                  "duration_ms": 1234, "total_cost_usd": 0.5,
                  "usage": {"input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": 50,
                            "cache_creation_input_tokens": 10}}))
```

Create `tests/agents/test_solver.py`:

```python
import json

import pytest

from acqlab.agents.prompts import ROUTER, system_prompt, user_prompt
from acqlab.agents.solver import MODEL, RunTimeout, solve
from acqlab.llm import LLMUnavailable


def _room(data):
    return data / "deals" / "dev-000" / "room"


def test_the_two_systems_prompts_differ_only_by_the_router_paragraph():
    assert ROUTER in system_prompt(True) and "rank_issues" not in system_prompt(False)
    assert system_prompt(True).replace(ROUTER, "") == system_prompt(False)
    assert "22 units" in user_prompt("# Teaser", 22.0)


def test_a_run_is_sandboxed_and_returns_the_cli_result(data, tmp_path, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "ok")
    out = solve(_room(data), 20, tmp_path / "trace.jsonl", router=True, claude=fake_claude)
    assert out["usage"]["output_tokens"] == 20
    seen = json.loads((tmp_path / "args.json").read_text())
    argv = seen["argv"]
    assert seen["files"] == ["mcp.json"] and "acquisition" not in seen["cwd"]  # an empty temp dir
    for flag, value in (("--tools", ""), ("--model", MODEL), ("--setting-sources", ""), ("--output-format", "json")):
        assert argv[argv.index(flag) + 1] == value
    assert {"--strict-mcp-config", "--no-session-persistence", "--disable-slash-commands"} <= set(argv)
    allowed = argv[argv.index("--allowedTools") + 1].split(",")
    assert "mcp__room__rank_issues" in allowed and all(t.startswith("mcp__room__") for t in allowed)
    trace = [json.loads(line) for line in (tmp_path / "trace.jsonl").read_text().splitlines()]
    assert trace[-1]["tool"] == "submit" and "rank_issues" in {r["tool"] for r in trace}


def test_the_plain_system_is_not_offered_the_router(data, tmp_path, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "ok")
    solve(_room(data), 20, tmp_path / "trace.jsonl", router=False, claude=fake_claude)
    argv = json.loads((tmp_path / "args.json").read_text())["argv"]
    assert "rank_issues" not in argv[argv.index("--allowedTools") + 1]
    assert "rank_issues" not in {json.loads(x)["tool"] for x in (tmp_path / "trace.jsonl").read_text().splitlines()}


def test_a_usage_limit_raises_llm_unavailable(data, tmp_path, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "limit")
    with pytest.raises(LLMUnavailable, match="usage limit") as e:
        solve(_room(data), 20, tmp_path / "trace.jsonl", router=False, claude=fake_claude)
    assert not isinstance(e.value, RunTimeout)


def test_a_slow_run_raises_run_timeout(data, tmp_path, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "sleep")
    with pytest.raises(RunTimeout):
        solve(_room(data), 20, tmp_path / "trace.jsonl", router=False, claude=fake_claude, timeout=2)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/agents/test_solver.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'acqlab.agents.prompts'`.

- [ ] **Step 3: Implement**

Create `acqlab/agents/prompts.py`:

```python
"""Solver prompts (Plan 4a design §2). The two systems differ only by the rank_issues paragraph; any edit made after
the smoke run goes to both and is logged in docs/results/plan-4a-prompt-log.md."""

_BASE = """You are a private-equity analyst deciding whether a sponsor should buy a company at its asking price in a \
leveraged buyout.

You start with the teaser. The data room holds the deal documents; list_documents shows their titles and page counts. \
Reading costs budget: opening a document costs 1 unit per page. You cannot read everything, so choose what to read. \
Tools that do not read documents are free.

Documents may reveal problems that lower what the company is worth: add-backs that are not really one-time, \
debt-like items payable at closing, revenue that will be lost from a customer, net working capital below normal at \
closing, and extra capital expenditure. Every data room discusses these topics; only what the documents actually say \
counts.

How to work:
- Use evaluate to price the deal. It takes your adjustments in $M and returns the walk-away price (the most the \
sponsor should pay) and whether the deal clears at the asking price.
- When you suspect or find an issue, record it with note_issue: your chance that it is real, its size range in $M, \
and the documents that would settle it. Update the note as you learn more (chance 1 once confirmed).
{router}- When you have enough, call submit with go (true to buy at the asking price) and your walk-away price in $M.

You are judged on the decision: buying a deal worth less than its price, or passing on one worth more, costs the \
difference."""

ROUTER = """- rank_issues ranks your open notes by how much settling each is expected to improve the decision, per \
page of reading still needed. It is advice from a pricing model built on your notes; you decide what to read.
"""


def system_prompt(router: bool) -> str:
    return _BASE.format(router=ROUTER if router else "")


def user_prompt(teaser: str, budget: float) -> str:
    return f"{teaser}\n\nYour diligence budget is {budget:g} units. Review the deal and submit your decision."
```

Create `acqlab/agents/solver.py`:

```python
"""One solver run: `claude -p` on the user's Claude subscription, sandboxed (Plan 4a design §2). It starts in an
empty temp directory with every built-in tool off, no user or project settings, no skills, and one MCP server: ours.

The command is injectable (`claude=`), so tests use a fake and never spend quota."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from acqlab.agents.prompts import system_prompt, user_prompt
from acqlab.agents.server import tool_names
from acqlab.llm import LLMUnavailable

MODEL = "claude-opus-5-5"
TIMEOUT = 20 * 60  # seconds, per run
SERVER = "room"


class RunTimeout(LLMUnavailable):
    """The run hit the hard timeout. The pilot scores it as "no answer" and carries on."""


def claude_bin() -> str:
    return os.environ.get("CLAUDE_BIN", "claude")


def command(claude: str, prompt: str, system: str, mcp_config: Path, router: bool) -> list[str]:
    return [claude, "-p", prompt, "--output-format", "json", "--model", MODEL, "--tools", "",
            "--mcp-config", str(mcp_config), "--strict-mcp-config",
            "--allowedTools", ",".join(f"mcp__{SERVER}__{t}" for t in tool_names(router)),
            "--setting-sources", "", "--disable-slash-commands", "--system-prompt", system,
            "--no-session-persistence"]


def solve(room: Path, budget: float, trace: Path, router: bool, *, claude: str | None = None,
          timeout: float = TIMEOUT) -> dict:
    """One run; the tool server writes the trace. Returns the CLI's JSON result (usage, turns, cost, text).
    Raises RunTimeout after `timeout` seconds, or LLMUnavailable on any other failure (usage limit, auth, crash)."""
    room, trace = room.resolve(), trace.resolve()
    teaser = json.loads((room / "index.json").read_text())["teaser"]
    with tempfile.TemporaryDirectory() as tmp:
        config = Path(tmp) / "mcp.json"
        args = ["-m", "acqlab.agents.server", "--room", str(room), "--budget", str(budget), "--trace", str(trace)]
        config.write_text(json.dumps({"mcpServers": {SERVER: {"command": sys.executable,
                                                              "args": args + (["--router"] if router else [])}}}))
        cmd = command(claude or claude_bin(), user_prompt(teaser, budget), system_prompt(router), config, router)
        try:
            proc = subprocess.run(cmd, cwd=tmp, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                  timeout=timeout)
        except subprocess.TimeoutExpired as e:
            raise RunTimeout(f"claude -p timed out after {timeout:g}s") from e
        except OSError as e:
            raise LLMUnavailable(f"claude -p could not run: {e}") from e
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        out = None
    if proc.returncode != 0 or not isinstance(out, dict) or out.get("is_error"):
        detail = (isinstance(out, dict) and str(out.get("result"))) or proc.stderr.strip()[-500:] or "no output"
        raise LLMUnavailable(f"claude -p failed (exit {proc.returncode}): {detail}")
    return out
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest -q`
Expected: all pass (184).

- [ ] **Step 5: Commit**

```bash
git add acqlab/agents/prompts.py acqlab/agents/solver.py tests/agents/fake_claude.py tests/agents/test_solver.py tests/conftest.py
git commit -m "feat(agents): prompts and sandboxed claude -p adapter, tested with a fake CLI

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Pilot runner and checkpoint report

**Files:**
- Create: `acqlab/bench/__init__.py` (empty), `acqlab/bench/pilot.py`
- Create: `tests/bench/__init__.py` (empty), `tests/bench/test_pilot.py`

**Interfaces:**
- Consumes:
  - `solve`, `RunTimeout` (Task 5)
  - `AnswerKey`
  - `regret(key, go)` and `bootstrap_ci(diff)` from `acqlab.routers.track_a`
- Produces:
  - `python -m acqlab.bench.pilot --data D --n N [--systems s1b,s1b_router] --confirm-claude`. Exit codes: 0 done, 2 Claude stopped, 3 refused.
  - `--report` writes `<D>/runs/summary.json`.
  - `SYSTEMS = {"s1b": False, "s1b_router": True}`
  - `score(key, system, trace, cli, status) -> dict`
  - `run(data, n, systems, solver=solve) -> list[dict]`
  - `summarize(rows) -> dict`, with `checkpoint.verdict` in `keep | reframe | mixed` and `b0_warning`
  - `relevant_docs(key)`, `decoy_docs(key)`, `floors(key)`

**Scoring:**
- Regret and walk-away error are ÷ asking price.
- A run that never submitted gets B0's decision (`face_go`, `face_walk_away`) and `answered=False`.
- **Decision-relevant documents** are the evidence documents of a flipper, an interaction, or an unresolvable fact with `alone_flips`.
- **The checkpoint**, on decision-flip deals (`go != face_go`) that both systems finished:
  - "regret lower" means the router's mean regret is lower
  - "evidence more" means the router's share of flip deals where it opened a decision-relevant document is higher
  - both yes → keep; both no → reframe; otherwise mixed
  - the CI is reported, not required

- [ ] **Step 1: Write the failing tests**

Create empty `tests/bench/__init__.py`, then create `tests/bench/test_pilot.py`:

```python
import json
import shutil
from functools import partial

import pytest

import acqlab.bench.pilot as pilot
from acqlab.agents.solver import RunTimeout, solve
from acqlab.bench.pilot import decoy_docs, relevant_docs, run, score, summarize
from acqlab.generator.batch import AnswerKey
from acqlab.llm import LLMUnavailable


@pytest.fixture
def fresh(data, tmp_path):
    """A private copy of the shared deals, so runs written by one test never make another test resume."""
    return shutil.copytree(data, tmp_path / "data")


def _key(data, deal="dev-000") -> AnswerKey:
    return AnswerKey.model_validate_json((data / "truth" / f"{deal}.json").read_text())


def _row(tool, args, cost=0.0, refused=False):
    return {"tool": tool, "args": args, "cost": cost, "refused": refused}


def test_a_submitted_run_is_scored_against_the_answer_key(data):
    key = _key(data)
    t, ask = key.truth, key.truth.deal.asking_price
    doc = sorted(relevant_docs(key) or {"cim"})[0]
    trace = [_row("open_document", {"doc_id": doc}, 7.0), _row("open_document", {"doc_id": "cim"}, 0, True),
             _row("note_issue", {"type": "capex", "chance": 1.0, "low": 0, "high": 1e9, "docs": []}),
             _row("submit", {"go": t.go, "walk_away": t.walk_away + 0.1 * ask, "reason": "r"})]
    cli = {"usage": {"input_tokens": 5, "output_tokens": 2}, "num_turns": 4}
    r = score(key, "s1b", trace, cli, "ok")
    assert r["answered"] and r["correct"] and r["regret"] == 0
    assert r["walk_away_error"] == pytest.approx(0.1)
    assert r["pages"] == 7.0 and r["prior_inside"] == 1.0 and r["tokens"]["input_tokens"] == 5
    assert r["opened_relevant"] == (True if relevant_docs(key) else None)
    assert r["flip"] == (t.go != t.face_go) and r["floors"]["b0"] == pilot.regret(key, t.face_go) / ask


def test_a_run_that_never_submits_gets_b0s_decision(data):
    key = _key(data)
    r = score(key, "s1b", [], None, "timeout")
    assert not r["answered"] and r["go"] == key.truth.face_go and r["regret"] == r["floors"]["b0"]
    assert r["tokens"]["output_tokens"] == 0


def test_decoy_documents_never_include_decision_relevant_ones(data):
    for deal in ("dev-000", "dev-001"):
        key = _key(data, deal)
        assert not decoy_docs(key) & relevant_docs(key)


def test_runs_are_saved_resumed_and_timeouts_are_scored(fresh):
    calls = []

    def solver(room, budget, trace, router):
        calls.append(router)
        if router:
            raise RunTimeout("slow")
        trace.write_text(json.dumps(_row("submit", {"go": True, "walk_away": 1.0, "reason": "r"})) + "\n")
        return {"usage": {}}

    rows = run(fresh, 2, ["s1b", "s1b_router"], solver=solver)
    assert calls == [False, True, False, True] and len(rows) == 4
    assert {r["status"] for r in rows if r["system"] == "s1b_router"} == {"timeout"}
    assert (fresh / "runs" / "s1b" / "dev-001.json").exists()
    assert run(fresh, 2, ["s1b", "s1b_router"], solver=solver) == [] and len(calls) == 4  # resumed: nothing re-run


def test_a_run_with_no_trace_stops_the_batch(fresh):
    with pytest.raises(LLMUnavailable, match="never ran"):
        run(fresh, 1, ["s1b"], solver=lambda *a: {"usage": {}})


def test_end_to_end_with_a_fake_claude(fresh, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "ok")
    solver = partial(solve, claude=fake_claude)
    rows = run(fresh, 1, ["s1b", "s1b_router"], solver=solver)
    assert [r["answered"] for r in rows] == [True, True]
    assert rows[0]["rank_calls"] == 0 and rows[1]["rank_calls"] == 1 and rows[0]["pages"] > 0
    assert rows[0]["tokens"]["cache_read_input_tokens"] == 50 and rows[0]["cost_usd"] == 0.5


def test_a_usage_limit_exits_2_and_keeps_finished_runs(fresh, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "limit")
    monkeypatch.setenv("CLAUDE_BIN", fake_claude)
    assert pilot.main(["--data", str(fresh), "--n", "2", "--confirm-claude"]) == 2


def test_claude_is_never_called_without_the_confirm_flag(data, monkeypatch):
    monkeypatch.setattr(pilot, "run", lambda *a, **k: pytest.fail("ran without --confirm-claude"))
    assert pilot.main(["--data", str(data), "--n", "1"]) == 3


def _fake_row(deal, system, regret, relevant, flip=True):
    return {"deal": deal, "system": system, "regret": regret, "opened_relevant": relevant, "flip": flip,
            "answered": True, "correct": regret == 0, "walk_away_error": 0.1, "pages": 10, "decoy_pages": 0,
            "prior_inside": None, "rank_calls": 0, "case_type": "flip", "cost_usd": None, "tokens": dict.fromkeys(
                ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"), 0),
            "floors": {"always_go": 0.2, "always_no": 0.2, "b0": 0.1, "b0_walk_away_error": 0.1,
                       "ask_walk_away_error": 0.1}}


@pytest.mark.parametrize("router_regret, router_relevant, verdict", [
    (0.0, True, "keep"), (0.2, False, "reframe"), (0.0, False, "mixed"), (0.2, True, "mixed")])
def test_the_checkpoint_rule(router_regret, router_relevant, verdict):
    rows = []
    for i in range(4):
        rows += [_fake_row(f"d{i}", "s1b", 0.1, i < 2), _fake_row(f"d{i}", "s1b_router", router_regret,
                                                                   router_relevant or i < 1)]
    s = summarize(rows)
    assert s["checkpoint"]["verdict"] == verdict and s["checkpoint"]["n_flip"] == 4
    assert s["b0_warning"]  # s1b's regret (0.1) does not beat B0's (0.1)


def test_report_writes_a_summary_without_claude(fresh, monkeypatch):
    def solver(room, budget, trace, router):
        trace.write_text(json.dumps(_row("submit", {"go": router, "walk_away": 1.0, "reason": "r"})) + "\n")
        return {"usage": {}}
    run(fresh, 2, ["s1b", "s1b_router"], solver=solver)
    monkeypatch.setattr(pilot, "run", lambda *a, **k: pytest.fail("report must not run anything"))
    assert pilot.main(["--data", str(fresh), "--report"]) == 0
    summary = json.loads((fresh / "runs" / "summary.json").read_text())
    assert summary["n_deals"] == 2 and summary["systems"]["s1b_router"]["correct"] is not None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/bench -q`
Expected: collection error, `ModuleNotFoundError: No module named 'acqlab.bench'`.

- [ ] **Step 3: Implement**

Create empty `acqlab/bench/__init__.py`, then create `acqlab/bench/pilot.py`:

```python
"""Plan 4a pilot: S1b and S1b + router on dev deals, scored against the answer keys (design §3).

  uv run python -m acqlab.bench.pilot --data data/v3 --n 3 --confirm-claude     # runs (uses the Claude subscription)
  uv run python -m acqlab.bench.pilot --data data/v3 --report                   # checkpoint summary, no Claude

Each run goes to <data>/runs/<system>/<deal>.json (its tool trace beside it); reruns skip finished runs.
Exit codes: 0 done; 2 Claude stopped (usage limit or a failed call: rerun later to resume); 3 refused (no
--confirm-claude).
"""
import argparse
import json
from collections.abc import Callable
from pathlib import Path

import numpy as np

from acqlab.agents.solver import RunTimeout, solve
from acqlab.generator.batch import AnswerKey
from acqlab.llm import LLMUnavailable
from acqlab.routers.track_a import bootstrap_ci, regret

SYSTEMS = {"s1b": False, "s1b_router": True}  # name -> offered rank_issues


def relevant_docs(key: AnswerKey) -> set[str]:
    """Documents holding a decision-relevant fact: a flipper, an interaction, or an unresolvable fact that flips the
    decision alone."""
    facts = {f.trap: f for f in key.truth.facts}
    return {d for e in key.evidence for d in e.docs
            if facts[e.trap].role in ("flipper", "interaction")
            or (facts[e.trap].role == "unresolvable" and facts[e.trap].alone_flips)}


def decoy_docs(key: AnswerKey) -> set[str]:
    facts = {f.trap: f for f in key.truth.facts}
    return {d for e in key.evidence for d in e.docs if facts[e.trap].role == "decoy"} - relevant_docs(key)


def floors(key: AnswerKey) -> dict:
    """No-AI reference points: normalised regret and walk-away error."""
    t, ask = key.truth, key.truth.deal.asking_price
    return {"always_go": regret(key, True) / ask, "always_no": regret(key, False) / ask,
            "b0": regret(key, t.face_go) / ask, "b0_walk_away_error": abs(t.face_walk_away - t.walk_away) / ask,
            "ask_walk_away_error": abs(ask - t.walk_away) / ask}


def score(key: AnswerKey, system: str, trace: list[dict], cli: dict | None, status: str) -> dict:
    """One run's row. A run that never submitted is scored with B0's decision and marked answered=False."""
    t, ask = key.truth, key.truth.deal.asking_price
    submit = next((r for r in trace if r["tool"] == "submit" and not r["refused"]), None)
    go = submit["args"]["go"] if submit else t.face_go
    wa = float(submit["args"]["walk_away"]) if submit else t.face_walk_away
    reads = [(r["args"]["doc_id"], r["cost"]) for r in trace if r["tool"] == "open_document" and not r["refused"]]
    relevant, decoys = relevant_docs(key), decoy_docs(key)
    notes = {r["args"]["type"]: r["args"] for r in trace if r["tool"] == "note_issue" and not r["refused"]}
    facts = {f.trap: f for f in t.facts}
    inside = [n["low"] <= facts[k].realized <= n["high"] or (facts[k].realized == 0 and n["chance"] < 1)
              for k, n in notes.items()]
    usage = (cli or {}).get("usage", {})
    return {
        "deal": t.id, "system": system, "status": status, "answered": submit is not None, "go": go, "walk_away": wa,
        "regret": regret(key, go) / ask, "correct": go == t.go, "walk_away_error": abs(wa - t.walk_away) / ask,
        "flip": t.go != t.face_go, "case_type": t.case_type,
        "pages": sum(c for _, c in reads), "decoy_pages": sum(c for d, c in reads if d in decoys),
        "opened_relevant": bool(relevant & {d for d, _ in reads}) if relevant else None,
        "tool_calls": len(trace), "rank_calls": sum(r["tool"] == "rank_issues" for r in trace),
        "prior_inside": float(np.mean(inside)) if inside else None,
        "tokens": {k: int(usage.get(k, 0)) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens",
                                                       "cache_creation_input_tokens")},
        "num_turns": (cli or {}).get("num_turns"), "duration_ms": (cli or {}).get("duration_ms"),
        "cost_usd": (cli or {}).get("total_cost_usd"),
        "floors": floors(key),
    }


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


def _mean(rows: list[dict], field: str) -> float | None:
    vals = [r[field] for r in rows if r[field] is not None]
    return float(np.mean(vals)) if vals else None


def summarize(rows: list[dict]) -> dict:
    """The checkpoint (design §3), on deals both systems finished. Regret is normalised by asking price."""
    by = {s: {r["deal"]: r for r in rows if r["system"] == s} for s in SYSTEMS}
    deals = sorted(set(by["s1b"]) & set(by["s1b_router"]))
    out: dict = {"n_deals": len(deals), "systems": {}}
    for s in SYSTEMS:
        rs = [by[s][d] for d in deals]
        flip = [r for r in rs if r["flip"]]
        out["systems"][s] = {
            "regret": _mean(rs, "regret"), "regret_flip": _mean(flip, "regret"), "correct": _mean(rs, "correct"),
            "walk_away_error": _mean(rs, "walk_away_error"), "opened_relevant_flip": _mean(flip, "opened_relevant"),
            "pages": _mean(rs, "pages"), "decoy_pages": _mean(rs, "decoy_pages"),
            "prior_inside": _mean(rs, "prior_inside"), "rank_calls": _mean(rs, "rank_calls"),
            "no_answer": sum(not r["answered"] for r in rs), "cost_usd": _mean(rs, "cost_usd"),
            "tokens": {k: float(np.mean([r["tokens"][k] for r in rs])) if rs else 0.0
                       for k in ("input_tokens", "output_tokens", "cache_read_input_tokens",
                                 "cache_creation_input_tokens")},
            "by_case": {c: _mean([r for r in rs if r["case_type"] == c], "regret")
                        for c in sorted({r["case_type"] for r in rs})},
        }
    base = [by["s1b"][d] for d in deals]
    out["floors"] = {k: float(np.mean([r["floors"][k] for r in base])) if base else None
                     for k in ("always_go", "always_no", "b0", "b0_walk_away_error", "ask_walk_away_error")}
    flip = [d for d in deals if by["s1b"][d]["flip"]]
    if flip:
        diff = np.array([by["s1b_router"][d]["regret"] - by["s1b"][d]["regret"] for d in flip])
        lo, hi = bootstrap_ci(diff) if len(diff) > 1 else (float(diff[0]), float(diff[0]))
        a, b = out["systems"]["s1b_router"], out["systems"]["s1b"]
        regret_lower = bool(diff.mean() < 0)
        evidence_more = (a["opened_relevant_flip"] or 0) > (b["opened_relevant_flip"] or 0)
        out["checkpoint"] = {
            "n_flip": len(flip), "regret_diff": float(diff.mean()), "ci95": [lo, hi],
            "regret_lower": regret_lower, "evidence_more": evidence_more,
            "verdict": "keep" if regret_lower and evidence_more else
                       "reframe" if not (regret_lower or evidence_more) else "mixed"}
    s1b = out["systems"]["s1b"]["regret"]
    out["b0_warning"] = s1b is not None and out["floors"]["b0"] is not None and s1b >= out["floors"]["b0"]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--n", type=int, default=3, help="first n dev deals")
    ap.add_argument("--systems", default=",".join(SYSTEMS))
    ap.add_argument("--confirm-claude", action="store_true", help="required to make real Claude calls")
    ap.add_argument("--report", action="store_true", help="summarise finished runs; no Claude calls")
    args = ap.parse_args(argv)
    if args.report:
        rows = [json.loads(p.read_text()) for s in SYSTEMS for p in sorted((args.data / "runs" / s).glob("*.json"))]
        summary = summarize(rows)
        (args.data / "runs").mkdir(parents=True, exist_ok=True)
        (args.data / "runs" / "summary.json").write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary, indent=2))
        return 0
    if not args.confirm_claude:
        print("Refusing to run: this uses your Claude subscription. Add --confirm-claude to proceed.")
        return 3
    try:
        run(args.data, args.n, [s for s in args.systems.split(",") if s])
    except LLMUnavailable as e:
        print(f"Claude stopped: {e}\nFinished runs are saved. Run the same command again (after any usage limit "
              "resets) to continue where it left off.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest -q`
Expected: all pass (197).

- [ ] **Step 5: Commit**

```bash
git add acqlab/bench tests/bench
git commit -m "feat(bench): Plan 4a pilot runner, scoring and checkpoint report

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: New deals, audit and docs (controller, not a subagent)

This task makes no Claude or Codex call. It ends by asking the user before the smoke run.

- [ ] **Step 1: Generate the version 3.0.0 benchmark set** (about 1 min)

```bash
uv run python -m acqlab.generator.batch --out data/v3 --dev 50 --test 120 --hand 10 --showcase 1
```

Expected:
- `generated 181 deals into data/v3; 0 batch problems`
- a `NOTE:` line with the word-leak count, which goes into the handoff

`data/` is git-ignored. The old `data/` deals and `data/track_a` are never overwritten.

- [ ] **Step 2: Run the statistical leak audit on 500 deals** (about 3 min; the project's standing rule)

```bash
uv run python -m acqlab.generator.batch --out /tmp/acqlab-audit-v3 --dev 250 --test 250 --hand 0 --showcase 0
```

Expected: `0 batch problems`. Record the word-leak count; about 48 were seen in pre-verification. Then remove `/tmp/acqlab-audit-v3`.

- [ ] **Step 3: Measure budget coverage on `data/v3`**

```bash
uv run python -c "
import json, math, numpy as np
from pathlib import Path
from acqlab.generator.batch import AnswerKey
from acqlab.bench.pilot import relevant_docs
d = Path('data/v3'); rows = []
for p in sorted((d / 'truth').glob('*.json')):
    k = AnswerKey.model_validate_json(p.read_text())
    pages = {x['id']: x['pages'] for x in json.loads((d / 'deals' / k.truth.id / 'room' / 'index.json').read_text())['documents']}
    ev = {x for e in k.evidence for x in e.docs}; rel = relevant_docs(k)
    rows.append((sum(pages.values()), k.budget, sum(pages[x] for x in ev), sum(pages[x] for x in rel) if rel else None))
r = np.array([x[:3] for x in rows], float)
print('room pages', r[:, 0].mean(), r[:, 0].min(), r[:, 0].max(), 'budget', r[:, 1].mean())
print('budget covers all evidence', (r[:, 1] >= r[:, 2]).mean())
rel = [(b, x) for _, b, _, x in rows if x is not None]
print('budget covers decision-relevant docs', np.mean([b >= x for b, x in rel]))
"
```

Expected: rooms of about 67–105 pages; "covers all evidence" under 0.30; "covers decision-relevant docs" around 0.85.

- [ ] **Step 4: Update docs**

In `docs/HANDOFF.md`:
- Set the git-state line to: Plan 3 is merged, and Plan 4a is on branch `plan-4`.
- Add a Plan 4a section with:
  - the numbers from Steps 1–3
  - that search is off for agents until Plan 4b fixes the reveal wording
  - the `CLAUDE_BIN` path from Finding 6
  - the pilot commands:

    ```bash
    export CLAUDE_BIN="$HOME/Library/Application Support/Claude/claude-code/2.1.280/claude.app/Contents/MacOS/claude"
    uv run python -m acqlab.bench.pilot --data data/v3 --n 3 --confirm-claude     # smoke: 6 runs
    uv run python -m acqlab.bench.pilot --data data/v3 --n 30 --confirm-claude    # pilot: 60 runs
    uv run python -m acqlab.bench.pilot --data data/v3 --report
    ```

  - that prompt edits after the smoke run are logged in `docs/results/plan-4a-prompt-log.md`

- [ ] **Step 5: Commit**

```bash
git add docs/HANDOFF.md
git commit -m "docs: handoff for Plan 4a (new rooms, leak audit, pilot commands)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Stop and ask the user before the smoke run**

The smoke run is 3 deals × 2 systems = 6 real Opus runs on the user's subscription. Ask first, and report its tokens per run before asking about the 30-deal pilot.
