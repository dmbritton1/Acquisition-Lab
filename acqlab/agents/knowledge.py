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
