from collections import Counter

import pytest

from acqlab.generator.documents import money
from acqlab.generator.render import LABELS, render, teaser_text
from acqlab.generator.truth import generate
from acqlab.generator.validate import (check_batch, check_consistency, check_engine, check_leaks, doc_words,
                                      word_leaks)
from acqlab.generator import validate
from acqlab.generator.validate import TOPIC_WORDS

DEALS = [generate(f"d{s}", "test", s, mc=20) for s in range(20)]


def test_generated_deals_pass_every_check():
    for t in DEALS:
        docs, evidence = render(t)
        assert check_engine(t) == [] and check_leaks(t, docs, teaser_text(t)) == []
        assert check_consistency(t, docs, evidence) == []


def _first(role):
    return next((t, i) for t in DEALS for i, f in enumerate(t.facts) if f.role == role)


def test_engine_check_catches_a_mislabelled_fact_and_a_wrong_decision():
    t, i = _first("clean")
    bad = t.model_copy(deep=True)
    bad.facts[i].amount = 1.0
    assert any("clean fact" in p for p in check_engine(bad))
    t, i = _first("flipper")
    bad = t.model_copy(deep=True)
    bad.facts[i].amount = 0.0
    assert any("flipper" in p for p in check_engine(bad)) and any("stored go" in p for p in check_engine(bad))


def test_consistency_catches_llm_digits_and_missing_evidence():
    t = DEALS[0]
    docs, evidence = render(t)
    slot = next(b for b in docs[0].blocks if not isinstance(b, str))
    slot.text = "Revenue grew 12 percent."
    assert any("LLM prose" in p for p in check_consistency(t, docs, evidence))
    docs, evidence = render(t)
    ev = next(e for e in evidence if e.formula != "none")
    ev.values = {k: v + 50 for k, v in ev.values.items()}
    assert check_consistency(t, docs, evidence)


def test_leak_check_catches_revealing_titles_and_teasers():
    t = DEALS[0]
    docs, _ = render(t)
    docs[0].title = "Disallowed add-backs memo"
    problems = check_leaks(t, docs, teaser_text(t) + " Seller has an unfunded pension.")
    assert any("title" in p for p in problems) and any("unfunded" in p for p in problems)


def test_batch_check_flags_uneven_topic_mentions():
    texts = {t.id: " ".join(d.render() for d in render(t)[0]) for t in DEALS}
    assert check_batch(DEALS, texts) == []
    skewed = {tid: text + (" debt" * 200 if any(f.trap == "debt_like" and f.role != "clean" for f in t.facts) else "")
              for (tid, text), t in zip(texts.items(), DEALS)}
    assert any("presence" in p for p in check_batch(DEALS, skewed))


def test_decoy_move_check():
    """Prove decoy move check fires: decoy with zero amount should fail."""
    t, i = _first("decoy")
    bad = t.model_copy(deep=True)
    bad.facts[i].amount = 0.0
    assert any("decoy moves walk-away by only" in p for p in check_engine(bad))


def test_interaction_pair_flip_check():
    """Prove interaction pair flip check fires: setting one pair member to zero should fail."""
    t, i = _first("interaction")
    bad = t.model_copy(deep=True)
    bad.facts[i].amount = 0.0
    assert any("does not flip together" in p for p in check_engine(bad))


def test_unresolvable_width_check():
    """Prove unresolvable width check fires: documented range with zero width should fail."""
    t, i = _first("unresolvable")
    bad = t.model_copy(deep=True)
    bad.facts[i].documented = (bad.facts[i].documented[0], bad.facts[i].documented[0])
    assert any("wrong width" in p for p in check_engine(bad))


def test_margin_rule_check():
    """Prove margin rule check fires: high capex should fail margin rule."""
    t = DEALS[0]
    bad = t.model_copy(deep=True)
    capex_idx = next(i for i, f in enumerate(bad.facts) if f.trap == "capex")
    bad.facts[capex_idx].amount = 0.3 * t.base.teaser.revenue_ltm
    assert any("margin rule" in p for p in check_engine(bad))


def test_haircut_monotonicity_check(monkeypatch):
    """Prove haircut monotonicity check fires: when walk_away increases with haircut."""
    t = DEALS[0]
    # Monkeypatch walk_away to return revenue_haircut so it increases with higher haircut
    monkeypatch.setattr(validate, "walk_away", lambda deal, params: params.revenue_haircut)
    assert any("haircut raises walk-away" in p for p in check_engine(t))


def test_go_rate_check():
    """Prove go rate batch check fires: 100 all-false deals should fail go rate check."""
    # Take a deal with go=False
    false_go_deal = next(t for t in DEALS if not t.go)
    texts = {false_go_deal.id: " ".join(d.render() for d in render(false_go_deal)[0])}
    # Call check_batch with 100 copies of the same deal
    problems = check_batch([false_go_deal] * 100, texts)
    assert any("go rate" in p for p in problems)


def _addback_batch(ratio):
    """25 deals with a clean add-back and 25 with a trap add-back; each CIM shows item = ratio(role) x claimed."""
    clean = next(t for t in DEALS if t.facts[0].role == "clean")
    trap = next(t for t in DEALS if t.facts[0].role != "clean")
    truths, texts = [], {}
    for i in range(25):
        for t in (clean, trap):
            copy = t.model_copy(update={"id": f"{t.id}-{i}"})
            lab = LABELS[t.facts[0].variant]
            item = ratio(t.facts[0].role != "clean", i) * t.base.teaser.claimed_addbacks
            truths.append(copy)
            texts[copy.id] = f"| {lab[0].upper() + lab[1:]} | {money(item)} | " + " ".join(TOPIC_WORDS.values())
    return truths, texts


def test_batch_check_flags_addback_items_that_reveal_the_role():
    skewed = _addback_batch(lambda trap, i: 0.9 if trap else 0.4)
    assert any("add-back" in p for p in check_batch(*skewed))
    even = _addback_batch(lambda trap, i: 0.3 + 0.02 * i)
    assert not any("add-back" in p for p in check_batch(*even))


def test_generated_addback_items_look_the_same_for_clean_and_trap_facts():
    deals = [generate(f"a{s}", "test", s, mc=4) for s in range(100)]
    assert sum(t.facts[0].role != "clean" for t in deals) >= 20  # enough for the check to run
    texts = {t.id: " ".join(d.render() for d in render(t)[0]) for t in deals}
    assert not any("add-back" in p for p in check_batch(deals, texts))


@pytest.fixture(scope="module")
def big_batch():
    """100 padded test deals: (truths, texts, pages, words)."""
    from acqlab.generator.padding import pad
    deals = [generate(f"p{s}", "test", s, mc=4) for s in range(100)]
    rooms = {t.id: pad(render(t)[0], t.base, t.style, t.seed) for t in deals}
    texts = {tid: " ".join(d.render() for d in docs) for tid, docs in rooms.items()}
    pages = {tid: {d.id: d.pages for d in docs} for tid, docs in rooms.items()}
    return deals, texts, pages, {tid: doc_words(docs) for tid, docs in rooms.items()}


def test_batch_check_flags_documents_that_are_longer_in_trap_deals(big_batch):
    deals, texts, pages, _ = big_batch
    assert not any("pages" in p for p in check_batch(deals, texts, pages))
    debt = {t.id for t in deals if any(f.trap == "debt_like" and f.role != "clean" for f in t.facts)}
    skewed = {tid: dict(p, legal=p["legal"] + 2 * (tid in debt)) for tid, p in pages.items()}
    assert any("pages: legal" in p for p in check_batch(deals, texts, skewed))


def test_word_leaks_finds_a_planted_word_and_the_reveal_wording_has_none(big_batch):
    deals, _, _, words = big_batch
    assert word_leaks(deals, words) == []  # Plan 4b: a real problem and a clean fact share every reveal word
    from acqlab.generator.padding import pad
    hard = [generate(f"q{s}", "test", s, mc=4, profile="r2") for s in range(100)]  # the hardest placements too
    assert word_leaks(hard, {t.id: doc_words(pad(render(t)[0], t.base, t.style, t.seed)) for t in hard}) == []
    capex = {t.id for t in deals if any(f.trap == "capex" and f.role != "clean" for f in t.facts)}
    planted = {tid: dict(w, qoe=w["qoe"] + Counter({"zebra": tid in capex})) for tid, w in words.items()}
    assert ("capex", "qoe", "zebra") in {(r["trap"], r["doc"], r["word"]) for r in word_leaks(deals, planted)}
    assert not any(r["word"] == "zebra" for r in word_leaks(deals, words))
