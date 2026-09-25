from acqlab.agents.knowledge import DILIGENCE_MAP, GUIDE, typical_high
from acqlab.generator.sample import Teaser

# A word (case-insensitive substring) GUIDE uses for each document kind in DILIGENCE_MAP. Read off GUIDE's own text
# (knowledge.py ~21-32), not invented here, so a doc-kind rename that GUIDE forgets to follow fails this test.
_KIND_WORD = {"qoe": "qoe", "audited": "audited", "cim": "cim", "contract": "contract", "legal": "legal",
             "assets": "asset"}

_BULLETS = GUIDE.split("\n- ")[1:]  # one per trap, same order as DILIGENCE_MAP (checked below)


def test_guide_names_each_traps_diligence_map_documents_in_order():
    """F5: GUIDE hand-restates DILIGENCE_MAP with no test tying them together. If a trap is added to (or reordered
    in) DILIGENCE_MAP without updating GUIDE's prose, this fails."""
    assert len(_BULLETS) == len(DILIGENCE_MAP)
    for bullet, (trap, kinds) in zip(_BULLETS, DILIGENCE_MAP.items()):
        positions = [bullet.lower().find(_KIND_WORD[k]) for k in kinds]
        assert all(p >= 0 for p in positions), f"{trap}: {kinds} not all named in {bullet!r}"
        assert positions == sorted(positions), f"{trap}: {kinds} not in DILIGENCE_MAP's order in {bullet!r}"


def test_guide_states_the_typical_high_each_trap_is_built_from():
    """F5: the percentage GUIDE quotes per trap must match the coefficient typical_high() actually uses. A synthetic
    teaser with a huge claimed_addbacks forces addback's typical_high onto its EBITDA cap rather than the (smaller,
    teaser-specific) claimed-addbacks cap, so every trap here resolves to a plain fraction of a teaser figure."""
    t = Teaser(name="x", industry="services", revenue_ltm=100.0, reported_ebitda=20.0, claimed_addbacks=1_000.0,
              adj_ebitda=40.0, growth=0.1, capex_pct=0.05, nwc_pct=0.15, asking_price=200.0)
    fractions = {"addback": typical_high("addback", t) / t.adj_ebitda,
                "debt_like": typical_high("debt_like", t) / t.asking_price,
                "concentration": typical_high("concentration", t) / t.revenue_ltm,
                "nwc": typical_high("nwc", t) / (t.nwc_pct * t.revenue_ltm),
                "capex": typical_high("capex", t) / t.revenue_ltm}
    for bullet, (trap, pct) in zip(_BULLETS, fractions.items()):
        assert f"{pct:.0%}" in bullet, f"{trap}: typical_high is {pct:.0%} but not named in {bullet!r}"
