import re

from acqlab.generator.documents import PLACEHOLDER, Slot
from acqlab.generator.render import LABELS, answer, render, teaser_text
from acqlab.generator.truth import generate

DEALS = [generate(f"d{s}", "test", s, mc=20) for s in range(40)]
CORE = {"cim", "qoe", "audited", "credit", "contract_1", "assets", "legal"}
TOPICS = ("add-back", "debt", "customer", "working capital", "capital expenditure", "litigation")


def test_every_room_has_the_core_documents_contracts_and_filler():
    for t in DEALS:
        docs, _ = render(t)
        ids = {d.id for d in docs}
        assert CORE <= ids
        assert 4 <= sum(d.domain == "filler" for d in docs) <= 5
        assert 1 <= sum(i.startswith("contract_") for i in ids) <= 3


def test_evidence_reproduces_every_answer_and_sits_in_the_named_documents():
    for t in DEALS:
        docs, evidence = render(t)
        for f, ev in zip(t.facts, evidence):
            want = f.documented if f.documented else (f.amount if f.role != "clean" else 0.0)
            got = answer(ev)
            assert got == want if isinstance(want, tuple) else abs(got - want) <= max(0.1, 0.01 * want)
            assert set(ev.docs) <= {d.id for d in docs}


def test_templates_hold_no_digits_so_llm_prose_can_be_digit_checked():
    for t in DEALS:
        for d in render(t)[0]:
            for b in d.blocks:
                if isinstance(b, Slot):
                    assert not re.search(r"\d", b.template), (d.id, b.id)
                    assert set(PLACEHOLDER.findall(b.template)) <= set(b.values)


def test_every_topic_appears_in_every_deal():
    for t in DEALS:
        text = " ".join(d.render() for d in render(t)[0]).lower()
        assert all(topic in text for topic in TOPICS), t.id


def test_every_cim_makes_all_five_assertive_claims():
    for t in DEALS:
        cim = next(d for d in render(t)[0] if d.id == "cim").render()
        by = {f.trap: f for f in t.facts}
        assert "were a one-time cost and will not recur" in cim, t.id
        assert f"The business has no {LABELS[by['debt_like'].variant]}." in cim, t.id
        assert "has renewed its contract on a long-term basis" in cim, t.id
        assert "Net working capital is managed closely and is at normal levels." in cim, t.id
        assert f"There is no {LABELS[by['capex'].variant]}." in cim, t.id


def test_default_passages_assert_nothing_about_the_fact():
    """A default sentence that says a problem is absent would contradict a same-tier reveal document."""
    asserting = ("has not given notice", "No events requiring disclosure", "found nothing further", "Term: through")
    neutral_legal = "We are not aware of any material pending litigation against the Company."
    for t in DEALS:
        docs = {d.id: d.render() for d in render(t)[0]}
        assert not any(a in text for a in asserting for text in docs.values()), t.id
        assert all("Term: renews annually each fiscal year." in text for i, text in docs.items()
                   if i.startswith("contract_")), t.id
        if next(f for f in t.facts if f.trap == "debt_like").variant != "litigation":
            assert neutral_legal in docs["legal"], t.id


def test_teaser_shows_visible_terms_only():
    t = DEALS[0]
    text = teaser_text(t)
    assert t.base.teaser.name in text and f"${t.deal.asking_price:,.1f}M" in text
    assert "disallow" not in text.lower() and "lawsuit" not in text.lower()

