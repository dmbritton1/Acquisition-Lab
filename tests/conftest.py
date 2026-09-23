import pytest

from acqlab.engine import Company, Deal, Financing, Params, Policy


def make_simple(covenant: float = 5.0) -> Deal:
    """No taxes, growth, capex, NWC, amortization or sweep: every number is hand-checkable."""
    return Deal(
        company=Company(revenue_ltm=100, reported_adj_ebitda=20, growth=0, capex_pct=0,
                        nwc_pct=0, da_pct=0, tax_rate=0),
        financing=Financing(max_leverage=4.0, interest_rate=0.10, amortization_pct=0,
                            cash_sweep=0, covenant_max_leverage=[covenant] * 5, fees_pct=0.02),
        policy=Policy(exit_multiple=8.0),
        asking_price=150,
    )


def make_full() -> Deal:
    """Every mechanic switched on. Golden values come from an independent straight-line calculation."""
    return Deal(
        company=Company(revenue_ltm=200, reported_adj_ebitda=30, growth=0.05, capex_pct=0.03,
                        nwc_pct=0.10, da_pct=0.025, tax_rate=0.25),
        financing=Financing(max_leverage=5.0, interest_rate=0.09, amortization_pct=0.05,
                            cash_sweep=0.5, covenant_max_leverage=[5.5, 5.25, 5.0, 4.75, 4.5],
                            fees_pct=0.02),
        policy=Policy(exit_multiple=8.0),
        asking_price=230,
    )


FULL_PARAMS = Params(ebitda_adjustment=-2, debt_like=5, revenue_haircut=0.05,
                     nwc_adjustment=2, capex_adjustment_pct=0.005)


@pytest.fixture
def simple() -> Deal:
    return make_simple()


@pytest.fixture
def full() -> Deal:
    return make_full()
