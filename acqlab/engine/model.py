"""Deal inputs and engine outputs. All money in $M, rates as decimals."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Input(BaseModel):
    """Inputs reach the engine from the generator and from LLM-proposed updates: reject typos and NaN/inf."""
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Company(_Input):
    revenue_ltm: float
    reported_adj_ebitda: float
    growth: float
    capex_pct: float
    nwc_pct: float
    da_pct: float
    tax_rate: float


class Financing(_Input):
    max_leverage: float  # lender cap, x lender-accepted EBITDA at close
    interest_rate: float
    amortization_pct: float  # of initial principal, per year
    cash_sweep: float  # share of post-amortization FCF repaying debt
    covenant_max_leverage: list[float]  # net debt / EBITDA ceiling, years 1..hold
    fees_pct: float  # of price


class Policy(_Input):
    irr_hurdle: float = 0.20
    hold_years: int = 5
    exit_multiple: float
    min_equity_pct: float = Field(default=0.40, gt=0, le=1)
    downside_revenue_shock: float = -0.10
    downside_margin_shock: float = -0.02


class Params(_Input):
    """Generic hidden-fact parameters. Zero = teaser taken at face value."""
    ebitda_adjustment: float = 0.0  # $M added to reported adj. EBITDA (negative = disallowed add-back)
    debt_like: float = Field(default=0.0, ge=0)  # $M funded at close
    revenue_haircut: float = Field(default=0.0, ge=0, lt=1)  # fraction of projected revenue lost
    nwc_adjustment: float = Field(default=0.0, ge=0)  # $M cash needed at close (peg shortfall)
    capex_adjustment_pct: float = 0.0  # extra capex, % of revenue


PARAM_NAMES = tuple(Params.model_fields)


class Deal(_Input):
    company: Company
    financing: Financing
    policy: Policy
    asking_price: float

    @model_validator(mode="after")
    def _covenant_schedule_matches_hold_years(self) -> "Deal":
        if len(self.financing.covenant_max_leverage) != self.policy.hold_years:
            raise ValueError("covenant_max_leverage must have one entry per hold year")
        return self


class Year(BaseModel):
    revenue: float
    ebitda: float
    interest: float
    fcf: float  # after interest, taxes, capex, change in NWC
    debt: float  # closing gross debt
    cash: float  # closing cash (negative = revolver drawn, charged interest_rate next year)
    net_debt: float
    leverage: float  # net debt / EBITDA (inf if EBITDA <= 0)


class EquityBridge(BaseModel):
    """entry_equity + ebitda_growth + multiple_change + debt_paydown + closing_costs = exit_equity."""
    entry_equity: float
    ebitda_growth: float  # (exit EBITDA - accepted EBITDA) x entry multiple (price / accepted EBITDA)
    multiple_change: float  # (exit multiple - entry multiple) x exit EBITDA
    debt_paydown: float  # opening debt - exit net debt
    closing_costs: float  # -(fees + debt-like items + NWC adjustment) funded by equity at close
    exit_equity: float


class Result(BaseModel):
    price: float
    uses: float
    debt: float
    equity: float
    exit_equity: float
    irr: float
    moic: float
    base: list[Year]
    downside: list[Year]
    covenant_headroom: list[float] = Field(description="covenant max - downside leverage, per year")
    debt_caps: dict[str, float]  # lender_cap, covenant, min_equity: debt is the smallest
    debt_limit: Literal["lender_cap", "covenant", "min_equity"]  # which cap set the debt
    bridge: EquityBridge
