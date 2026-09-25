import re

import numpy as np
import pytest

from acqlab.generator.padding import (CONTRACTS, EXTRA_FILLER, FILLER_DOCS, SENTENCES, TARGET_PAGES, TITLES, _kind,
                                      _table, pad)
from acqlab.generator.render import LABELS, TERM, render, teaser_text
from acqlab.generator.truth import generate
from acqlab.generator.validate import LEAK_WORDS, TOPIC_WORDS, check_leaks

# Padding must never talk about a trap topic: no topic or leak words, no trap labels, no trap-adjacent terms.
BANNED = (tuple(TOPIC_WORDS.values()) + LEAK_WORDS + tuple(LABELS.values())
          + ("pension", "earnout", "litigation", "settle", "peg", "renew", "tender", "capex"))


@pytest.fixture(scope="module")
def deals():
    out = []
    for seed in range(12):
        t = generate(f"d{seed}", "test" if seed % 2 else "dev", seed, mc=20)  # dev deals are all style A
        docs, _ = render(t)
        out.append((t, docs, pad(docs, t.base, t.style, t.seed)))
    return out


def test_every_document_lands_in_its_page_range(deals):
    for _, _, padded in deals:
        for d in padded:
            lo, hi = TARGET_PAGES[_kind(d)]
            assert lo <= d.pages <= hi, (d.id, d.pages)


def test_rooms_have_three_to_six_contracts_and_six_to_nine_filler_documents(deals):
    for _, _, padded in deals:
        contracts = [d for d in padded if d.id.startswith("contract_")]
        assert CONTRACTS[0] <= len(contracts) <= CONTRACTS[1]
        assert [d.id for d in contracts] == [f"contract_{i + 1}" for i in range(len(contracts))]
        assert len({d.title for d in contracts}) == len(contracts)
        assert all(TERM in d.render() for d in contracts)  # presence rule: every contract states the term
        assert FILLER_DOCS[0] <= sum(d.domain == "filler" for d in padded) <= FILLER_DOCS[1]
        assert len({d.id for d in padded}) == len(padded)


def _plain(block):
    """A block with any style-B section number removed (padding renumbers sections)."""
    return re.sub(r"^SECTION \d+\. ", "SECTION ", block) if isinstance(block, str) else block.render()


def test_padding_keeps_every_original_block_in_order(deals):
    for _, docs, padded in deals:
        by_id = {d.id: d for d in padded}
        for d in docs:
            rest = iter(_plain(b) for b in by_id[d.id].blocks)
            assert all(_plain(b) in rest for b in d.blocks), d.id  # an in-order subsequence


def test_page_counts_do_not_depend_on_what_the_reveal_says(deals):
    """The same deal with longer reveal passages pads to the same page counts."""
    t, docs, padded = deals[0]
    longer = [d.model_copy(update={"blocks": d.blocks + ["An extra sentence of forty words. " * 5]})
              if d.id in ("qoe", "contract_1", "legal") else d for d in docs]
    assert [(d.id, d.pages) for d in pad(longer, t.base, t.style, t.seed)] == [(d.id, d.pages) for d in padded]


def test_padding_is_deterministic(deals):
    t, docs, padded = deals[1]
    assert [d.render() for d in pad(docs, t.base, t.style, t.seed)] == [d.render() for d in padded]


def test_style_b_sections_are_numbered_in_order(deals):
    b = next(p for t, _, p in deals if t.style == "B")
    for d in b:
        nums = [int(m.group(1)) for x in d.blocks if isinstance(x, str) for m in [re.match(r"SECTION (\d+)\. ", x)]
                if m]
        assert nums == list(range(1, len(nums) + 1)), d.id


def test_padding_text_never_mentions_a_trap_topic(deals):
    t = deals[0][0]
    texts = [s for pool in SENTENCES.values() for s in pool] + [x for pool in TITLES.values() for x in pool]
    texts += list(EXTRA_FILLER.values())
    rng = np.random.default_rng(0)
    texts += [_table(kind, t.base, style, rng) or "" for kind in TITLES for style in "AB" for _ in range(5)]
    for text in texts:
        low = text.lower()
        assert not [w for w in BANNED if w in low], text


def test_padded_rooms_pass_the_title_check(deals):
    for t, _, padded in deals:
        assert check_leaks(t, padded, teaser_text(t)) == []
