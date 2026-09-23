"""LBO-typical industries, from Damodaran (NYU Stern) US industry data, January 2026 update.

Read 2026-09-23 from pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/:
  margin.html  EBITDA/Sales; Pre-tax Unadjusted Operating Margin
  capex.html   Cap Ex/Deprecn
  wcdata.html  Non-cash WC/Sales
Derived: D&A % = EBITDA/Sales - pre-tax unadjusted operating margin; capex % = D&A % x Cap Ex/Deprecn.
Public-company figures stand in for mid-market targets (a stated proxy).
"""
from typing import Literal, NamedTuple


class Industry(NamedTuple):
    name: str
    kind: Literal["services", "manufacturing"]
    ebitda_margin: float
    op_margin: float
    capex_to_dep: float
    nwc_pct: float

    @property
    def da_pct(self) -> float:
        return self.ebitda_margin - self.op_margin

    @property
    def capex_pct(self) -> float:
        return self.da_pct * self.capex_to_dep


INDUSTRIES = (
    Industry("Business & Consumer Services", "services", 0.1565, 0.1227, 0.6525, 0.1452),
    Industry("Machinery", "manufacturing", 0.1962, 0.1586, 0.6786, 0.2442),
    Industry("Healthcare Products", "manufacturing", 0.2034, 0.1534, 0.7954, 0.2565),
    Industry("Building Materials", "manufacturing", 0.1732, 0.1264, 1.0863, 0.1844),
    Industry("Packaging & Container", "manufacturing", 0.1436, 0.0958, 0.8984, 0.1266),
    Industry("Electrical Equipment", "manufacturing", 0.1265, 0.0953, 1.1106, 0.2944),
    Industry("Chemical (Specialty)", "manufacturing", 0.1801, 0.1217, 1.5528, 0.2380),
    Industry("Food Processing", "manufacturing", 0.1525, 0.1063, 1.3435, 0.0668),
    Industry("Information Services", "services", 0.1728, 0.1189, 0.3519, 0.1662),
)
