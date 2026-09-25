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
    """Padding kind. The board minutes pad like filler: neutral text around their per-topic lines."""
    return "contract" if d.id.startswith("contract_") else "filler" if d.domain == "filler" or d.id == "board_minutes" \
        else d.id


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
