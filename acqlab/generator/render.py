"""Render a deal's data room from its answer key. Every trap topic appears in every deal (presence rule);
only the reveal passage differs between a real problem and a clean fact."""
import numpy as np
from pydantic import BaseModel

from acqlab.generator.documents import PLACEHOLDER, Doc, heading, money, pct, slot, table
from acqlab.generator.sample import FISCAL_YEARS
from acqlab.generator.truth import DealTruth, Fact

FY_LAST, FY_NEXT = str(FISCAL_YEARS[-1]), str(FISCAL_YEARS[-1] + 1)
TERM = "Term: renews annually each fiscal year."  # the same in every contract, so the term never leaks or conflicts
LABELS = {
    "restructuring": "restructuring costs", "consulting": "strategic consulting fees",
    "owner_comp": "owner compensation adjustments",
    "earnout": "earnout payable to the sellers of an acquired business", "pension": "unfunded pension obligation",
    "deferred_revenue": "customer prepayments that require future service", "litigation": "pending customer lawsuit",
    "expiring": "its contract is expiring and it will not renew in full",
    "rfp": "it is re-tendering the contract", "acquired": "it was acquired by a competitor",
    "stretched_payables": "stretched supplier payments", "pulled_collections": "customer collections pulled forward",
    "aged_equipment": "equipment past its useful life", "deferred_maintenance": "deferred maintenance",
    "lease_return": "lease return conditions on leased equipment",
}
SUPPORT = {"earnout": "earnout calculation", "pension": "actuarial valuation",
           "deferred_revenue": "deferred revenue roll-forward"}
BOILERPLATE = (
    "This document has been prepared solely for the use of prospective acquirers in connection with the proposed "
    "transaction. It does not purport to contain all information a prospective acquirer may require.",
    "Recipients should conduct their own investigation and analysis of the business and the data set out herein. "
    "No representation or warranty is made as to the accuracy or completeness of this document.",
    "The Company operates from owned and leased facilities and serves customers through a direct sales team "
    "supported by regional distributors and a customer service function.",
    "Management has invested in systems and processes that support the scalability of the platform, including an "
    "enterprise resource planning system and monthly management reporting.",
    "The Company's workforce is non-unionized. Employee turnover has been in line with industry norms and senior "
    "management has an average tenure of more than ten years.",
    "Information in this document is based on management accounts and discussions with management. It has not "
    "been independently verified except where stated.",
    "The Company maintains insurance coverage that management considers adequate for a business of its size, "
    "including property, general liability, product liability and cyber policies.",
    "Pricing is reviewed annually. Historically the Company has been able to pass through the majority of input "
    "cost increases to customers with a short lag.",
    "Capital allocation decisions are reviewed by the board. Investment proposals above a set threshold require a "
    "written business case and a post-investment review.",
    "Terms not otherwise defined have the meaning given in the purchase agreement. Headings are for convenience "
    "only and do not affect interpretation.",
)
FILLER = {
    "board_minutes": "Board Meeting Minutes", "hr_policy": "Human Resources Policy Manual",
    "insurance": "Insurance Certificates", "it_policy": "IT and Information Security Policy",
    "environmental": "Environmental, Health and Safety Policy",
}
_CUSTOMERS = ("Meridian", "Castell", "Northwind", "Bramble", "Oakhurst", "Selwyn", "Tavira", "Wexford")
_CUSTOMER_KIND = ("Retail", "Foods", "Logistics", "Health", "Supply", "Distribution")


class Evidence(BaseModel):
    """Where a fact's answer sits and how to compute it from what the documents state."""
    trap: str
    docs: list[str]
    formula: str  # none | value | difference | product | per_year | gap | range
    values: dict[str, float]


def answer(ev: Evidence) -> float | tuple[float, float]:
    v = ev.values
    return {"none": lambda: 0.0, "value": lambda: v["amount"], "difference": lambda: v["gross"] - v["settled"],
            "product": lambda: v["purchases"] * v["fraction"], "per_year": lambda: v["gross"] / 5,
            "gap": lambda: v["peg"] - v["latest"], "range": lambda: (v["low"], v["high"])}[ev.formula]()


def _cap(s: str) -> str:
    return s[0].upper() + s[1:]


def _note(sid: str, brief: str, template: str, **values: str) -> list:
    """Audited-accounts note: the numbered heading is code-written, so only the digit-free body is prose."""
    head, body = template.split(". ", 1)
    return [PLACEHOLDER.sub(lambda m: values[m.group(1)], head) + ".", slot(sid, brief, body, **values)]


def _trap_side(f: Fact) -> bool:
    return f.role != "clean"


def _point_evidence(f: Fact) -> tuple[str, dict]:
    """A problem fact's answer is its amount; a clean fact's answer is zero."""
    return ("value", {"amount": f.amount}) if _trap_side(f) else ("none", {})


def _range_evidence(f: Fact, vals: dict, formula: str, values: dict) -> tuple[str, dict]:
    """Unresolvable facts state a range instead of a value: add it to the prose values and use it as the evidence."""
    if not f.documented:
        return formula, values
    vals |= dict(low=money(f.documented[0]), high=money(f.documented[1]))
    return "range", {"low": f.documented[0], "high": f.documented[1]}


def _clean_item_severity(rng: np.random.Generator) -> float:
    """Severity for a clean add-back's line item, shaped like trap severities (quartiles about 0.5/0.7/0.9), so the
    item's size relative to the claimed add-backs says nothing about the fact's role."""
    return 0.2 + 0.8 * float(rng.random()) ** 0.7


def _addback(f: Fact, t: DealTruth, rng: np.random.Generator) -> tuple[dict, Evidence]:
    lab, claimed, style = LABELS[f.variant], t.base.teaser.claimed_addbacks, t.style
    clean_item = min(claimed, max(0.1, round(_clean_item_severity(rng) * f.worst, 1)))  # drawn for every role
    item = f.documented[1] if f.documented else (f.amount if _trap_side(f) else clean_item)
    sites = {"cim.addback": [table(style, ["Add-back", "Amount"], [[_cap(lab), money(item)],
                                                                      ["Other one-time items", money(claimed - item)],
                                                                      ["Total add-backs", money(claimed)]])]}
    claim = "{{label_cap}} of {{item}} were a one-time cost and will not recur."
    sites["cim.addback"].append(slot("cim_addback", "Explain the add-back schedule", claim, label_cap=_cap(lab),
                                     item=money(item)))
    qoe = "We reviewed the add-back for {{label}} of {{item}}; its history is set out in the audited financial statements."
    note = "Note 9 — {{label_cap}}. {{label_cap}} are included in operating expenses."
    rows = None
    trap = _trap_side(f)
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
    elif f.placement == "calculation":
        past = [round(item * k, 1) for k in (0.92, 1.05)] if trap else [0.0, 0.0]
        rows = [_cap(lab)] + [money(x) for x in past + [item]]
        note = "Note 9 — {{label_cap}}. {{label_cap}} are shown separately in the income statement."
    elif f.placement == "range":
        qoe = ("We could not determine whether {{label}} will recur. Between {{low}} and {{high}} of the {{item}} "
               "add-back may prove recurring; supporting invoices were not provided.")
    vals = dict(label=lab, label_cap=_cap(lab), item=money(item), fy_last=FY_LAST)
    if f.documented:
        vals |= dict(low=money(f.documented[0]), high=money(f.documented[1]))
    sites["qoe.addback"] = [slot("qoe_addback", "Give the QoE view on this add-back", qoe, **vals)]
    sites["audited.note9"] = _note("note9", "Write the note on this cost line", note, **vals)
    sites["audited.is_rows"] = [rows] if rows else []
    doc = {"explicit": ["qoe"], "contradicted": ["cim", "qoe"], "footnote": ["audited"],
           "calculation": ["audited"], "range": ["qoe"]}[f.placement]
    if f.documented:
        ev = Evidence(trap=f.trap, docs=doc, formula="range", values={"low": f.documented[0], "high": f.documented[1]})
    else:
        ev = Evidence(trap=f.trap, docs=doc, formula="value" if trap else "none",
                      values={"amount": item} if trap else {})
    return sites, ev


def _debt(f: Fact, t: DealTruth, rng: np.random.Generator) -> tuple[dict, Evidence]:
    lab, trap, lit = LABELS[f.variant], _trap_side(f), f.variant == "litigation"
    vals = dict(label=lab, label_cap=_cap(lab), amount=money(f.amount), support=SUPPORT.get(f.variant, ""))
    cim = ("The business will be delivered cash-free and debt-free; the price excludes items such as any {{label}}. "
           "The business has no {{label}}.")
    qoe = "Debt-like items, including any {{label}}: see the notes to the audited financial statements."
    note = ("Note 12 — Commitments and contingencies. The Company has operating leases and purchase commitments "
            "in the ordinary course of business.")
    legal = "We are not aware of any material pending litigation against the Company."
    ev_formula, ev_vals = _point_evidence(f)
    if lit:
        docs = ["cim", "legal"] if f.placement == "contradicted" else ["legal"]
        if f.placement in ("explicit", "footnote", "contradicted"):
            legal = ("We represent the Company in a {{label}}. We expect it to settle for {{amount}}, payable by the "
                     "Company." if trap else "The {{label}} against the Company was dismissed; there is no liability.")
        elif f.placement == "calculation":
            gross = round(f.amount + (float(np.round(f.worst * 0.3, 1)) if trap else 0.0), 1) if trap else 0.0
            insured = round(gross - f.amount, 1) if trap else 0.0
            legal = ("A {{label}} claims damages of {{gross}}. Insurance available to cover the claim is {{settled}}; "
                     "the Company bears the rest." if trap else
                     "The {{label}} against the Company was dismissed; there is no liability.")
            vals |= dict(gross=money(gross), settled=money(insured))
            if trap:
                ev_formula, ev_vals = "difference", {"gross": gross, "settled": insured}
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
        elif f.placement == "calculation":
            settled = round(float(np.round(f.worst * 0.5, 1)), 1)
            gross = round(settled + f.amount, 1) if trap else settled
            note = ("Note 12 — Commitments and contingencies. Gross {{label}}: {{gross}}. Amounts settled or funded to "
                    "date: {{settled}}.")
            vals |= dict(gross=money(gross), settled=money(settled))
            if trap:
                ev_formula, ev_vals = "difference", {"gross": gross, "settled": settled}
        elif f.placement == "range":
            note = ("Note 12 — Commitments and contingencies. Management estimates the {{label}} at between {{low}} "
                    "and {{high}}; the supporting {{support}} is referenced but was not provided.")
    ev_formula, ev_vals = _range_evidence(f, vals, ev_formula, ev_vals)
    sites = {"cim.debt": [slot("cim_debt", "State the cash-free, debt-free basis", cim, **vals)],
             "qoe.debt": [slot("qoe_debt", "Summarise debt-like items", qoe, **vals)],
             "audited.note12": _note("note12", "Write the commitments note", note, **vals),
             "legal.letter": [slot("legal", "Write the litigation paragraph of a legal letter", legal, **vals)]}
    return sites, Evidence(trap=f.trap, docs=docs, formula=ev_formula, values=ev_vals)


def _customer(f: Fact, t: DealTruth, customer: str, rng: np.random.Generator) -> tuple[dict, Evidence]:
    trap, share, rev = _trap_side(f), t.base.top_customer_share, t.base.teaser.revenue_ltm
    purchases = round(share * rev, 1)
    vals = dict(customer=customer, share=pct(share), purchases=money(purchases), amount=money(f.amount),
                reason=LABELS[f.variant], fy_next=FY_NEXT)
    cim = ("Our largest customer, {{customer}}, accounts for {{share}} of revenue. {{customer}} has renewed its "
           "contract on a long-term basis.")
    terms = TERM + " Annual purchases under this agreement: {{purchases}}."
    notice = "Purchase volumes are reviewed with {{customer}} each year."
    note = ("Note 14 — Subsequent events. Management evaluated subsequent events through the date these statements "
            "were issued.")
    ev_formula, ev_vals = _point_evidence(f)
    docs = {"explicit": ["contract_1"], "contradicted": ["cim", "contract_1"], "footnote": ["audited"],
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
        vals |= dict(fraction=pct(fraction))
        if trap:
            ev_formula, ev_vals = "product", {"purchases": share * rev, "fraction": fraction}
    elif f.placement == "range":
        notice = ("{{customer}} is re-tendering this contract and the outcome is expected after closing. Management "
                  "estimates that {{low}} to {{high}} of annual revenue is at risk.")
    ev_formula, ev_vals = _range_evidence(f, vals, ev_formula, ev_vals)
    sites = {"cim.customer": [slot("cim_customer", "Describe customer relationships", cim, **vals)],
             "contract_1.terms": [slot("contract_terms", "State the contract term and volumes", terms, **vals)],
             "contract_1.notice": [slot("contract_notice", "State the customer's current position", notice, **vals)],
             "audited.note14": _note("note14", "Write the subsequent-events note", note, **vals)}
    return sites, Evidence(trap=f.trap, docs=docs, formula=ev_formula, values=ev_vals)


def _nwc(f: Fact, t: DealTruth, rng: np.random.Generator) -> tuple[dict, Evidence]:
    trap, lab, style = _trap_side(f), LABELS[f.variant], t.style
    peg = round(t.base.teaser.nwc_pct * t.base.teaser.revenue_ltm, 1)
    vals = dict(peg=money(peg), amount=money(f.amount), label=lab)
    hint = "The purchase agreement sets a normal level of net working capital (the peg) of {{peg}}."
    qoe = "We compared expected closing net working capital with the peg; see the notes to the audited accounts."
    note = "Note 6 — Working capital. Working capital comprises receivables, inventory and payables."
    cim = "Net working capital is managed closely and is at normal levels."
    ev_formula, ev_vals = _point_evidence(f)
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
    elif f.placement == "calculation":
        latest = round(peg - f.amount, 1) if trap else peg
        months = [money(round(peg * float(rng.uniform(0.97, 1.03)), 1)) for _ in range(5)] + [money(latest)]
        qoe = "Monthly net working capital is shown below; closing is expected at the latest month's level."
        extra = [table(style, ["Month", "Net working capital"], [[f"Month {i + 1}", m] for i, m in enumerate(months)])]
        if trap:
            ev_formula, ev_vals = "gap", {"peg": peg, "latest": latest}
    elif f.placement == "range":
        qoe = ("Net working capital at closing could fall between {{low}} and {{high}} below the peg; the closing "
               "balance sheet was not provided.")
    ev_formula, ev_vals = _range_evidence(f, vals, ev_formula, ev_vals)
    sites = {"qoe.nwc": [slot("qoe_peg", "Explain the working-capital peg", hint, **vals),
                         slot("qoe_nwc", "Give the closing working-capital view", qoe, **vals)] + extra,
             "audited.note6": _note("note6", "Write the working-capital note", note, **vals),
             "cim.nwc": [slot("cim_nwc", "Comment on working capital", cim, **vals)]}
    return sites, Evidence(trap=f.trap, docs=docs, formula=ev_formula, values=ev_vals)


def _capex(f: Fact, t: DealTruth, rng: np.random.Generator) -> tuple[dict, Evidence]:
    trap, lab = _trap_side(f), LABELS[f.variant]
    tz = t.base.teaser
    vals = dict(label=lab, amount=money(f.amount), capex=money(tz.capex_pct * tz.revenue_ltm), fy_last=FY_LAST,
                years="five")
    cim = "The asset base is well maintained; capital expenditure was {{capex}} in {{fy_last}}. There is no {{label}}."
    review = "The schedule above lists fixed assets by class."
    note = "Note 7 — Property, plant and equipment. Assets are depreciated on a straight-line basis."
    ev_formula, ev_vals = _point_evidence(f)
    docs = {"explicit": ["assets"], "contradicted": ["cim", "assets"], "footnote": ["audited"],
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
        vals |= dict(gross=money(gross))
        if trap:
            ev_formula, ev_vals = "per_year", {"gross": gross}
    elif f.placement == "range":
        review = ("An engineering survey was commissioned but not provided. Management estimates additional capital "
                  "expenditure for {{label}} of {{low}} to {{high}} per year.")
    ev_formula, ev_vals = _range_evidence(f, vals, ev_formula, ev_vals)
    sites = {"cim.capex": [slot("cim_capex", "Describe the asset base", cim, **vals)],
             "assets.review": [slot("asset_review", "Summarise the equipment condition review", review, **vals)],
             "audited.note7": _note("note7", "Write the fixed-asset note", note, **vals)}
    return sites, Evidence(trap=f.trap, docs=docs, formula=ev_formula, values=ev_vals)


def teaser_text(t: DealTruth) -> str:
    tz, fin, pol = t.base.teaser, t.deal.financing, t.deal.policy
    covs = ", ".join(f"{c:.2f}x" for c in fin.covenant_max_leverage)
    return "\n".join([
        f"# {tz.name} — Teaser", f"Industry: {tz.industry}",
        f"LTM revenue: {money(tz.revenue_ltm)}; revenue growth: {pct(tz.growth)} per year",
        f"Reported EBITDA: {money(tz.reported_ebitda)}; claimed add-backs: {money(tz.claimed_addbacks)}; "
        f"adjusted EBITDA: {money(tz.adj_ebitda)}",
        f"Capex: {pct(tz.capex_pct)} of revenue; net working capital: {pct(tz.nwc_pct)} of revenue",
        f"Asking price: {money(tz.asking_price)}",
        f"Lender terms: up to {fin.max_leverage:.2f}x adjusted EBITDA at {pct(fin.interest_rate)}; amortization "
        f"{pct(fin.amortization_pct)} per year; cash sweep {pct(fin.cash_sweep)}; fees {pct(fin.fees_pct)} of price; "
        f"maximum net leverage covenant by year: {covs}",
        f"Sponsor policy: IRR hurdle {pct(pol.irr_hurdle)}; hold {pol.hold_years} years; exit at "
        f"{pol.exit_multiple:.2f}x EBITDA; minimum equity {pct(pol.min_equity_pct)}; downside case revenue "
        f"{pct(pol.downside_revenue_shock)}, margin {pct(pol.downside_margin_shock)}",
    ])


def render(t: DealTruth) -> tuple[list[Doc], list[Evidence]]:
    rng = np.random.default_rng([t.seed, 1])  # seed + 1 would replay the next deal's generate() stream
    style, tz = t.style, t.base.teaser
    customers = [f"{c} {k}" for c, k in zip(rng.choice(_CUSTOMERS, 3, replace=False),
                                            rng.choice(_CUSTOMER_KIND, 3, replace=False))]
    by_trap = {f.trap: f for f in t.facts}
    sites: dict[str, list] = {}
    evidence = []
    for part in (_addback(by_trap["addback"], t, rng), _debt(by_trap["debt_like"], t, rng),
                 _customer(by_trap["concentration"], t, customers[0], rng), _nwc(by_trap["nwc"], t, rng),
                 _capex(by_trap["capex"], t, rng)):
        sites |= part[0]
        evidence.append(part[1])

    def boiler(k: int) -> list[str]:
        return [BOILERPLATE[i] for i in rng.choice(len(BOILERPLATE), k, replace=False)]

    hist = [[str(h.fiscal_year), money(h.revenue), money(h.reported_ebitda)] for h in t.base.history]
    is_rows = [[f"FY{h.fiscal_year}" for h in t.base.history]]
    is_table = table(style, ["Line"] + is_rows[0],
                     [["Revenue"] + [money(h.revenue) for h in t.base.history],
                      ["Reported EBITDA"] + [money(h.reported_ebitda) for h in t.base.history]]
                     + sites["audited.is_rows"])
    fin = t.deal.financing
    n_contracts = int(rng.integers(1, 4))
    docs = [
        Doc(id="cim", title="Confidential Information Memorandum", domain="commercial", blocks=[
            heading(style, 1, f"{tz.name} — Overview"),
            slot("cim_overview", f"Introduce a {tz.industry} company", "{{name}} operates in the {{industry}} sector.",
                 name=tz.name, industry=tz.industry.lower()),
            *boiler(2), heading(style, 2, "Financial summary"),
            table(style, ["Fiscal year", "Revenue", "Reported EBITDA"], hist),
            heading(style, 3, "Adjusted EBITDA"), *sites["cim.addback"],
            heading(style, 4, "Customers"), *sites["cim.customer"],
            heading(style, 5, "Operations and assets"), *sites["cim.capex"], *sites["cim.nwc"],
            heading(style, 6, "Transaction"), *sites["cim.debt"]]),
        Doc(id="qoe", title="Quality of Earnings Report", domain="accounting", blocks=[
            heading(style, 1, "Scope"), *boiler(2), heading(style, 2, "Adjusted EBITDA"), *sites["qoe.addback"],
            heading(style, 3, "Net working capital"), *sites["qoe.nwc"],
            heading(style, 4, "Debt-like items"), *sites["qoe.debt"]]),
        Doc(id="audited", title=f"Audited Financial Statements FY{FISCAL_YEARS[0]}–FY{FISCAL_YEARS[-1]}",
            domain="accounting", blocks=[
                heading(style, 1, "Income statement"), is_table, heading(style, 2, "Notes"),
                *sites["audited.note6"], *sites["audited.note7"], *sites["audited.note9"],
                *sites["audited.note12"], *sites["audited.note14"], *boiler(1)]),
        Doc(id="credit", title="Credit Agreement Excerpt", domain="credit", blocks=[
            heading(style, 1, "Term loan"),
            table(style, ["Term", "Value"], [
                ["Maximum leverage at close", f"{fin.max_leverage:.2f}x adjusted EBITDA"],
                ["Interest rate", pct(fin.interest_rate)], ["Amortization", f"{pct(fin.amortization_pct)} per year"],
                ["Excess cash flow sweep", pct(fin.cash_sweep)], ["Fees", f"{pct(fin.fees_pct)} of price"]]
                + [[f"Maximum net leverage, year {i + 1}", f"{c:.2f}x"]
                   for i, c in enumerate(fin.covenant_max_leverage)]),
            *boiler(1)]),
        Doc(id="contract_1", title=f"Customer Agreement — {customers[0]}", domain="commercial", blocks=[
            heading(style, 1, "Agreement"), *sites["contract_1.terms"], *sites["contract_1.notice"], *boiler(1)]),
        *[Doc(id=f"contract_{i + 1}", title=f"Customer Agreement — {customers[i]}", domain="commercial", blocks=[
            heading(style, 1, "Agreement"),
            slot("contract_terms", "State the contract term", TERM), *boiler(1)])
          for i in range(1, n_contracts)],
        Doc(id="assets", title="Fixed Asset and Lease Schedule", domain="accounting", blocks=[
            heading(style, 1, "Fixed assets"),
            table(style, ["Asset class", "Gross cost", "Average age (years)"], [
                [c, money(tz.revenue_ltm * float(rng.uniform(0.02, 0.12))), f"{rng.uniform(3, 15):.0f}"]
                for c in ("Plant and machinery", "Vehicles", "IT equipment", "Leasehold improvements")]),
            *sites["assets.review"]]),
        Doc(id="legal", title="Legal Letter", domain="legal", blocks=[heading(style, 1, "Litigation"),
                                                                     *sites["legal.letter"], *boiler(1)]),
    ]
    for key in rng.choice(list(FILLER), int(rng.integers(4, 6)), replace=False):
        docs.append(Doc(id=str(key), title=FILLER[key], domain="filler",
                        blocks=[heading(style, 1, FILLER[key]), *boiler(int(rng.integers(4, 11)))]))
    return docs, evidence
