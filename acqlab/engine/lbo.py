"""Annual LBO mechanics: projection, debt sizing, returns."""
import math

from acqlab.engine.model import Deal, EquityBridge, Params, Result, Year


def accepted_ebitda(deal: Deal, params: Params) -> float:
    return deal.company.reported_adj_ebitda + params.ebitda_adjustment


def project(deal: Deal, params: Params, debt0: float, downside: bool = False) -> list[Year]:
    c, f, p = deal.company, deal.financing, deal.policy
    margin = accepted_ebitda(deal, params) / c.revenue_ltm
    shock = 1.0
    if downside:
        margin += p.downside_margin_shock
        shock += p.downside_revenue_shock
    capex_pct = c.capex_pct + params.capex_adjustment_pct
    amort = f.amortization_pct * debt0
    debt, cash, prev_rev = debt0, 0.0, c.revenue_ltm
    years = []
    for t in range(1, p.hold_years + 1):
        rev = c.revenue_ltm * (1 + c.growth) ** t * (1 - params.revenue_haircut) * shock
        ebitda = rev * margin
        interest = f.interest_rate * (debt + max(0.0, -cash))  # term loan + revolver drawn at open
        taxes = max(0.0, c.tax_rate * (ebitda - c.da_pct * rev - interest))
        fcf = ebitda - rev * capex_pct - c.nwc_pct * (rev - prev_rev) - taxes - interest
        mandatory = min(amort, debt)
        sweep = min(max(0.0, fcf - mandatory) * f.cash_sweep, debt - mandatory)
        debt -= mandatory + sweep
        cash += fcf - mandatory - sweep
        net = debt - cash
        years.append(Year(revenue=rev, ebitda=ebitda, interest=interest, fcf=fcf, debt=debt,
                          cash=cash, net_debt=net, leverage=net / ebitda if ebitda > 0 else math.inf))
        prev_rev = rev
    return years


def passes_covenants(deal: Deal, params: Params, debt0: float) -> bool:
    down = project(deal, params, debt0, downside=True)
    caps = deal.financing.covenant_max_leverage
    return all(y.leverage <= cap for y, cap in zip(down, caps, strict=True))


def covenant_safe_debt(deal: Deal, params: Params, tol: float = 1e-6) -> float:
    """Largest opening debt whose downside case never breaches a covenant (bisection)."""
    hi = max(0.0, deal.financing.max_leverage * accepted_ebitda(deal, params))
    if passes_covenants(deal, params, hi):
        return hi
    if not passes_covenants(deal, params, 0.0):
        return 0.0
    lo = 0.0
    while hi - lo > tol:
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if passes_covenants(deal, params, mid) else (lo, mid)
    return lo


def uses(deal: Deal, params: Params, price: float) -> float:
    return price * (1 + deal.financing.fees_pct) + params.debt_like + params.nwc_adjustment


def debt_caps(deal: Deal, params: Params, price: float, safe_debt: float | None = None) -> dict[str, float]:
    """The three limits on debt, in tie-break order for reporting which one binds."""
    if safe_debt is None:
        safe_debt = covenant_safe_debt(deal, params)
    return {
        "lender_cap": max(0.0, deal.financing.max_leverage * accepted_ebitda(deal, params)),
        "covenant": safe_debt,
        "min_equity": max(0.0, (1 - deal.policy.min_equity_pct) * uses(deal, params, price)),
    }


def size_debt(deal: Deal, params: Params, price: float, safe_debt: float | None = None) -> float:
    """Sponsor raises the most debt that the lender allows, the downside survives, and min equity permits."""
    return min(debt_caps(deal, params, price, safe_debt).values())


def returns(deal: Deal, params: Params, price: float,
            safe_debt: float | None = None) -> tuple[float, float, float, float, list[Year]]:
    """(irr, moic, debt, equity, base years). Single exit cash flow, so IRR is closed-form."""
    debt = size_debt(deal, params, price, safe_debt)
    equity = uses(deal, params, price) - debt
    base = project(deal, params, debt)
    exit_equity = deal.policy.exit_multiple * base[-1].ebitda - base[-1].net_debt
    moic = exit_equity / equity
    irr = moic ** (1 / deal.policy.hold_years) - 1 if moic > 0 else -1.0
    return irr, moic, debt, equity, base


def equity_bridge(deal: Deal, params: Params, price: float, debt: float, equity: float,
                  base: list[Year]) -> EquityBridge:
    e0, e_exit = accepted_ebitda(deal, params), base[-1].ebitda
    growth = (e_exit - e0) * price / e0 if e0 > 0 else 0.0  # at the entry multiple
    return EquityBridge(
        entry_equity=equity, ebitda_growth=growth,
        multiple_change=deal.policy.exit_multiple * e_exit - price - growth,
        debt_paydown=debt - base[-1].net_debt,
        closing_costs=price - uses(deal, params, price),
        exit_equity=deal.policy.exit_multiple * e_exit - base[-1].net_debt,
    )


def evaluate(deal: Deal, params: Params, price: float | None = None) -> Result:
    price = deal.asking_price if price is None else price
    caps = debt_caps(deal, params, price)
    irr, moic, debt, equity, base = returns(deal, params, price, caps["covenant"])
    down = project(deal, params, debt, downside=True)
    return Result(
        price=price, uses=uses(deal, params, price), debt=debt, equity=equity,
        exit_equity=moic * equity, irr=irr, moic=moic, base=base, downside=down,
        debt_caps=caps, debt_limit=min(caps, key=caps.get),
        bridge=equity_bridge(deal, params, price, debt, equity, base),
        covenant_headroom=[cap - y.leverage
                           for y, cap in zip(down, deal.financing.covenant_max_leverage, strict=True)],
    )
