import pytest

import acqlab.agents.record as record_mod
from acqlab.agents.knowledge import typical_high
from acqlab.agents.record import Record, load_face, next_doc
from acqlab.engine import is_go
from acqlab.generator.batch import AnswerKey
from acqlab.generator.traps import params_for


def _record(data, deal="dev-000") -> Record:
    return Record(load_face(data / "deals" / deal / "room"))


def _key(data, deal="dev-000") -> AnswerKey:
    return AnswerKey.model_validate_json((data / "truth" / f"{deal}.json").read_text())


def _issue(t, chance=0.5, low=0.0, high=1.0, docs=(), name="n"):
    return {"type": t, "name": name, "chance": chance, "low": low, "high": high, "docs": list(docs)}


def test_with_nothing_proposed_the_engine_calls_the_deal_at_face_value(data):
    r = _record(data)
    go, wa = r.decide()
    assert go == _key(data).truth.face_go
    assert wa == pytest.approx(_key(data).truth.face_walk_away, rel=1e-3)


def test_the_lead_s_ranges_are_priced_over_at_least_the_usual_size(data):
    r = _record(data)
    r.plan([_issue("debt_like", 0.4, 0, 1.0)])
    assert r.issue("debt_like").hi == typical_high("debt_like", r.face.teaser) > 1.0
    r.plan([_issue("debt_like", 0.4, 0, 1e4)])
    assert r.issue("debt_like").hi == 1e4
    assert not r.issue("nwc").proposed  # never proposed: worlds assume no problem


def test_commits_stand_when_the_lead_replans_and_not_found_only_records_what_was_read(data):
    r = _record(data)
    r.plan([_issue("debt_like"), _issue("nwc")])
    narrowed = r.apply([{"type": "debt_like", "kind": "quoted", "low": 4.0, "high": 4.0, "quotes": [{"doc_id": "legal",
                                                                                                   "text": "x"}]},
                        {"type": "nwc", "kind": "not_found", "docs": ["qoe"], "quotes": []}])
    assert narrowed and r.entries["debt_like"].known == (4.0, 4.0) and r.entries["nwc"].searched == ["qoe"]
    r.plan([_issue("debt_like", 0.1, 0, 0.5), _issue("nwc", 0.2, 0, 3)])
    assert r.entries["debt_like"].known == (4.0, 4.0) and r.entries["nwc"].chance == 0.2
    assert not r.apply([{"type": "debt_like", "kind": "quoted", "low": 4.0, "high": 4.0, "quotes": []}])
    assert r.priority == ["debt_like", "nwc"]


def test_a_later_commit_that_disagrees_widens_what_is_known_and_keeps_every_quote(data):
    """F1: a later commit used to overwrite an earlier one (QoE's 1.2 replaced by the CIM's 0.0, its quote lost)."""
    qoe, cim = {"doc_id": "qoe", "text": "$1.2M recurred"}, {"doc_id": "cim", "text": "will not recur"}
    r = _record(data)
    assert r.apply([{"type": "addback", "kind": "quoted", "low": 1.2, "high": 1.2, "quotes": [qoe]}])
    assert r.apply([{"type": "addback", "kind": "quoted", "low": 0.0, "high": 0.0, "quotes": [cim]}])
    e = r.entries["addback"]
    assert (e.known, e.kind, e.quotes) == ((0.0, 1.2), "range", [qoe, cim])
    assert not r.apply([{"type": "addback", "kind": "computed", "low": 0.5, "high": 0.5, "quotes": []}])  # inside
    assert (e.known, e.kind) == ((0.0, 1.2), "range")
    assert not r.apply([{"type": "addback", "kind": "range", "low": 0.0, "high": 1.2, "quotes": [qoe]}])  # the same
    assert (e.known, e.quotes) == ((0.0, 1.2), [qoe, cim])


def test_an_open_issue_the_lead_leaves_out_is_dropped(data):
    """F3: the Lead's list is the whole plan; an open issue it leaves out gets chance 0 (what was read stays)."""
    r = _record(data)
    r.plan([_issue("debt_like", 0.6), _issue("nwc", 0.4), _issue("capex", 0.3)])
    r.apply([{"type": "capex", "kind": "quoted", "low": 2.0, "high": 2.0, "quotes": []},
             {"type": "nwc", "kind": "not_found", "docs": ["qoe"], "quotes": []}])
    r.entries["nwc"].tries = 1
    r.plan([_issue("debt_like", 0.6)])
    nwc = r.entries["nwc"]
    assert (nwc.chance, nwc.searched, nwc.tries) == (0.0, ["qoe"], 1) and r.issue("nwc").p_real == 0.0
    assert r.entries["capex"].known == (2.0, 2.0) and r.entries["debt_like"].chance == 0.6


def test_a_pending_objection_outlasts_a_re_plan_until_it_is_investigated(data):
    """R1: a re-plan that leaves out an objected issue used to drop it to chance 0, so the router never checked the
    objection. R2: a re-plan that re-lists it used to overwrite the Challenger's widening."""
    r = _record(data)
    r.plan([_issue("debt_like", 0.5, 0, 1.0), _issue("nwc", 0.2, 0, 1.0)])
    r.challenge([{"type": "nwc", "kind": "bigger", "chance": 0.7, "low": 0, "high": 40, "docs": [], "reason": "r"},
                 {"type": "debt_like", "kind": "bigger", "chance": 0.6, "low": 0, "high": 30, "docs": [],
                  "reason": "r"}])
    r.plan([_issue("debt_like", 0.1, 0, 2.0)])
    nwc, debt = r.entries["nwc"], r.entries["debt_like"]
    assert (nwc.chance, nwc.high) == (0.7, 40) and r.rank(["nwc"], {"nwc": 5.0})["nwc"] > 0  # R1: not dropped
    assert (debt.chance, debt.high) == (0.6, 30)  # R2: the Lead can't lower it below the objection
    debt.objections = nwc.objections = []  # answered by the extra look
    r.plan([_issue("debt_like", 0.1, 0, 2.0)])
    assert (debt.chance, debt.high) == (0.1, 2.0) and nwc.chance == 0.0  # now the Lead sets it freely


def test_a_committed_problem_moves_the_engine_s_call(data):
    r = _record(data)
    assert r.decide()[0]  # dev-000 is a go at face value
    big = 2 * r.size_limit("debt_like")
    r.apply([{"type": "debt_like", "kind": "quoted", "low": big, "high": big, "quotes": []}])
    assert not r.decide()[0]


def test_the_flip_amount_is_where_the_engine_s_call_changes(data):
    r = _record(data)
    f = r.flip_amount("debt_like")
    assert f is not None
    assert r._go({"debt_like": 0.99 * f}) and not r._go({"debt_like": 1.01 * f})
    face = r.face
    assert is_go(face.deal, params_for({"debt_like": 0.99 * f}, face))


def test_a_pair_is_flagged_when_it_flips_the_call_together_but_neither_does_alone(data, monkeypatch):
    r = _record(data)
    fd, fn = r.flip_amount("debt_like"), r.flip_amount("nwc")
    monkeypatch.setattr(record_mod, "typical_high", lambda t, teaser: 0.0)  # sizes are exactly the Lead's ranges
    r.plan([_issue("debt_like", 0.5, 0, 0.6 * fd), _issue("nwc", 0.5, 0, 0.6 * fn)])
    assert {frozenset(p) for p in r.flagged_pairs()} == {frozenset(("debt_like", "nwc"))}
    r.plan([_issue("debt_like", 0.5, 0, 0.3 * fd), _issue("nwc", 0.5, 0, 0.3 * fn)])
    assert r.flagged_pairs() == []
    r.plan([_issue("debt_like", 0.5, 0, 1.5 * fd), _issue("nwc", 0.5, 0, 0.6 * fn)])
    assert r.flagged_pairs() == []  # debt_like flips alone: its own flip amount covers it


def test_an_objection_reopens_an_issue_and_widens_an_open_belief(data):
    r = _record(data)
    r.plan([_issue("nwc", 0.2, 0, 1.0)])
    r.apply([{"type": "debt_like", "kind": "quoted", "low": 0.0, "high": 0.0, "quotes": []}])
    r.challenge([{"type": "nwc", "kind": "bigger", "chance": 0.4, "low": 0, "high": 50, "docs": ["audited"],
                  "reason": "r"},
                 {"type": "debt_like", "kind": "elsewhere", "chance": 0.3, "low": 0, "high": 9, "docs": ["legal"],
                  "reason": "r"}])
    nwc, debt = r.entries["nwc"], r.entries["debt_like"]
    assert (nwc.chance, nwc.high, nwc.docs[0]) == (0.4, 50, "audited")
    assert debt.known == (0.0, 0.0) and r.issue("debt_like").known == (0.0, 9)
    debt.objections = []
    assert r.issue("debt_like").known == (0.0, 0.0)

    r2 = _record(data)
    f = r2.flip_amount("debt_like")
    r2.apply([{"type": "debt_like", "kind": "quoted", "low": 1.3 * f, "high": 1.3 * f, "quotes": []}])
    assert not r2.decide()[0]
    r2.challenge([{"type": "debt_like", "kind": "bigger", "chance": 0.3, "low": 0, "high": 1.5 * 1.3 * f,
                   "docs": ["legal"], "reason": "r"}])
    assert not r2.decide()[0]  # a "bigger" objection must not shrink a committed value below its floor
    assert r2.issue("debt_like").known == pytest.approx((1.3 * f, 1.5 * 1.3 * f))


def test_the_router_ranks_open_issues_per_page(data):
    r = _record(data)
    r.plan([_issue("debt_like", 0.6, 0, 1.0), _issue("capex", 0.0, 0, 0.1)])
    scores = r.rank(["debt_like", "capex"], {"debt_like": 5.0, "capex": 5.0})
    assert scores["debt_like"] > 0 == scores["capex"]


def test_next_doc_walks_the_diligence_map():
    pages = {"qoe": 8, "audited": 14, "cim": 11, "contract_1": 3, "contract_2": 2}
    assert next_doc("addback", pages, set()) == "qoe"
    assert next_doc("addback", pages, {"qoe"}) == "audited"
    assert next_doc("concentration", pages, {"contract_1"}) == "contract_2"
    assert next_doc("nwc", pages, {"qoe", "audited"}) is None


def test_the_view_shows_evidence_and_hides_the_lead_s_names_from_the_challenger(data):
    r = _record(data)
    r.plan([_issue("nwc", 0.2, 0, 1.0, name="peg shortfall")])
    r.apply([{"type": "debt_like", "kind": "range", "low": 3.0, "high": 6.2,
              "quotes": [{"doc_id": "legal", "text": "settle for $3.0–$6.2M"}]}])
    v = r.view()
    assert "peg shortfall" in v and 'legal: "settle for $3.0–$6.2M"' in v and "$3.0–$6.2M (range)" in v
    assert "Engine's current call" in v and "capex: not proposed" in v
    assert "peg shortfall" not in r.view(reasons=False)
