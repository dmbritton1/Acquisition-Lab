import json
import time

import pytest

from acqlab.agents.knowledge import typical_high
from acqlab.agents.record import N_WORLDS
from acqlab.app.board import BoardRecord, apply, compute, face
from acqlab.engine import Params, is_go, walk_away
from acqlab.generator.traps import TRAPS
from tests.conftest import make_full

D = make_full()
NUMBERS = {"revenue_ltm": 200.0, "reported_ebitda": 28.0, "claimed_addbacks": 2.0, "adj_ebitda": 30.0, "growth": 0.05,
           "capex_pct": 0.03, "nwc_pct": 0.10, "da_pct": 0.025, "tax_rate": 0.25}
SETTINGS = {"financing": D.financing.model_dump(), "policy": D.policy.model_dump()}
f = face(NUMBERS, SETTINGS, D.asking_price, "Acme", "Services")
# make_full() at its asking price is already a no-go (walk-away 223 < 230), so no debt_like size can flip it; the flip
# test uses g, the same company priced at 200, where the headroom is positive.
g = face(NUMBERS, SETTINGS, 200.0, "Acme", "Services")
room = walk_away(g.deal, Params()) - 200.0  # g's headroom
big, tiny = 3 * room, room / 1000


def worry(chance, low, high):
    return {"chance": chance, "low": low, "high": high, "reason": "r", "quotes": [], "dropped_quotes": []}


worries = {"debt_like": worry(0.5, 0, 20.0), "capex": worry(0.3, 0, 5.0), "nwc": {"not_priced": "no"}}
all_five = {t: worry(0.4, 0, 10.0) for t in TRAPS}


def test_with_no_worries_the_call_is_the_engine_s_at_face_value():
    out = compute(f, {}, set())
    assert out["go"] == is_go(f.deal, Params()) and out["walk_away"] == pytest.approx(walk_away(f.deal, Params()), rel=1e-3)


def test_a_size_you_set_is_used_as_set_below_the_typical_floor():
    floor = typical_high("debt_like", f.teaser)
    r = BoardRecord(f, {"debt_like": worry(0.5, 0, floor / 10)}, {"debt_like"})
    assert r.issue("debt_like").hi == pytest.approx(floor / 10)


def test_an_opus_size_keeps_the_typical_floor():
    floor = typical_high("debt_like", f.teaser)
    assert BoardRecord(f, {"debt_like": worry(0.5, 0, floor / 10)}, set()).issue("debt_like").hi == pytest.approx(floor)


def test_compute_reports_the_floored_size_it_prices():
    floor = typical_high("debt_like", f.teaser)
    w = {"debt_like": worry(0.5, 0, floor / 10), "capex": worry(0.5, 0, 1e3)}
    sizes = compute(f, w, set())["sizes"]
    assert sizes["debt_like"] == {"size": pytest.approx(floor), "floored": True}
    assert sizes["capex"] == {"size": 1e3, "floored": False}
    assert compute(f, w, {"debt_like"})["sizes"]["debt_like"] == {"size": pytest.approx(floor / 10), "floored": False}


def test_moving_only_the_chance_at_the_reported_size_never_flips_the_call():
    # the reviewer's case: Opus's $3M debt_like is priced at the usual $42.8M; touching the chance by one point must
    # keep that size, not drop to $3M (which flipped NO-GO to GO)
    h = face(NUMBERS, SETTINGS, 214.0, "Acme", "Services")
    w = {"debt_like": worry(0.6, 0, 3.0)}
    before = compute(h, w, set())
    size = before["sizes"]["debt_like"]["size"]
    after = compute(h, *apply(w, {"debt_like": {"chance": 0.61, "high": size}}))
    assert before["go"] is False and after["go"] is False and after["clears"] == pytest.approx(before["clears"], abs=0.02)


def test_flip_sizes_are_reported_or_none():
    out = compute(g, {"debt_like": worry(0.5, 0, big), "capex": worry(0.1, 0, 0.01)}, {"capex"})
    assert out["flips"]["debt_like"] > 0 and out["flips"]["capex"] is None


def test_the_pairs_strip_is_the_record_s_flagged_pairs():
    r = BoardRecord(f, worries, set())
    assert compute(f, worries, set())["pairs"] == [list(p) for p in r.flagged_pairs()]


def test_the_worry_that_matters_most_tops_the_ask_list():
    out = compute(g, {"debt_like": worry(0.5, 0, big), "capex": worry(0.5, 0, tiny)}, {"debt_like", "capex"})
    assert out["ask"][0]["type"] == "debt_like" and out["ask"][0]["docs"][0] == "Audited accounts and notes"


def test_the_histogram_covers_every_world():
    out = compute(f, worries, set())
    assert sum(out["hist"]["counts"]) == N_WORLDS
    json.dumps(out)


def test_a_recalculation_takes_under_a_second():
    t = time.perf_counter(); compute(f, all_five, set()); assert time.perf_counter() - t < 1.0


BAD_OVERRIDES = [{"chance": 1.5, "high": 1}, {"chance": 0.5, "high": -1}, {"chance": float("nan"), "high": 1},
                 {"chance": "0.5", "high": 1}, {"chance": None, "high": 1}, {"chance": 0.5}, {"chance": True, "high": 1},
                 {"chance": 0.5, "high": float("inf")}, 3, None]


@pytest.mark.parametrize("bad", BAD_OVERRIDES)
def test_impossible_overrides_are_refused(bad):
    with pytest.raises(ValueError):
        apply(worries, {"capex": bad})


def test_an_unknown_worry_type_is_refused():
    with pytest.raises(ValueError):
        apply(worries, {"mystery": {"chance": 0.5, "high": 1}})


@pytest.mark.parametrize("price", [0, -5, float("nan"), float("inf"), True, "230", None])
def test_a_bad_price_is_refused(price):
    with pytest.raises(ValueError):
        face(NUMBERS, SETTINGS, price, "Acme", "Services")


@pytest.mark.parametrize("bad", [None, "x", True, float("nan")])
def test_a_missing_or_non_numeric_number_is_refused(bad):
    with pytest.raises(ValueError, match="tax_rate"):
        face(NUMBERS | {"tax_rate": bad}, SETTINGS, 230.0, "Acme", "Services")
    with pytest.raises(ValueError, match="tax_rate"):
        face({k: v for k, v in NUMBERS.items() if k != "tax_rate"}, SETTINGS, 230.0, "Acme", "Services")


@pytest.mark.parametrize("bad", [{"mystery": worry(0.5, 0, 1)}, {"capex": 3}, {"capex": {"chance": "x", "low": 0, "high": 1}},
                                 {"capex": {"chance": 0.5}}])
def test_a_malformed_worry_is_refused(bad):
    with pytest.raises(ValueError):
        compute(f, bad, set())
