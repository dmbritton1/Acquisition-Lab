import pytest

from acqlab.agents.committer import check, norm, numbers
from acqlab.generator import batch
from acqlab.generator.batch import AnswerKey
from acqlab.generator.documents import money, pct
from acqlab.generator.render import span

TEXTS = {
    "qoe": "## Add-backs\n\nWe reviewed the add-back for restructuring costs of $1.8M. Of this, $1.2M recurred in each "
           "of the last three years and is expected to continue, so we exclude it from adjusted EBITDA.",
    "audited": "| Restructuring costs | $1.1M | $1.3M | $1.2M |\n\nNote 12 — Commitments and contingencies. Gross "
               "earnout: $9.4M. Amounts settled or funded to date: $3.1M.",
    "contract_1": "Wexford Foods has set out its purchase plans for FY2026: it will move 25.0% of its $12.0M of annual "
                  "purchases to another supplier.",
    "assets": "Replacement cost of aged equipment: $7.5M, to be spent evenly over the five-year plan.",
    "legal": "We represent the Company in a pending customer lawsuit. We expect it to settle for $3.0–$6.2M, payable "
             "by the Company.",
    "cim": "The business has no earnout. Restructuring costs of $1.8M were a one-time cost and will not recur.",
}


def q(doc, text):
    return {"doc_id": doc, "text": text}


def test_a_quoted_amount_is_committed_and_quotes_match_despite_markdown_case_and_dashes():
    c, errs = check({"type": "addback", "status": "value", "value": 1.2,
                     "quotes": [q("qoe", "of this, $1.2M RECURRED in each of the last three years")]}, TEXTS)
    assert errs == [] and c["kind"] == "quoted" and (c["low"], c["high"]) == (1.2, 1.2) and c["docs"] == ["qoe"]
    c, errs = check({"type": "addback", "status": "value", "value": 1.2,
                     "quotes": [q("audited", "Restructuring costs  $1.1M  $1.3M  $1.2M")]}, TEXTS)  # a table row
    assert errs == [] and c["low"] == 1.2
    assert norm("Note 12 — Gross | *x*") == "note 12 - gross x"


def test_a_quote_must_be_real_long_enough_and_from_a_document_that_was_read():
    base = {"type": "addback", "status": "value", "value": 1.2}
    assert check(base | {"quotes": [q("qoe", "$1.2M recurred every year and will continue")]}, TEXTS)[1]
    assert check(base | {"quotes": [q("hr_policy", "of this, $1.2M recurred")]}, TEXTS)[1] == [
        "addback: quote from 'hr_policy', which you have not read",
        "addback: 1.2 does not appear in your quotes"]  # a refused quote supports nothing
    assert "word for word" in check(base | {"quotes": [q("qoe", "$1.2M")]}, TEXTS)[1][0]  # too short
    assert check(base | {"quotes": []}, TEXTS)[1][0] == "addback: a value needs a quote"


def test_a_value_must_appear_in_the_quotes_except_zero():
    errs = check({"type": "addback", "status": "value", "value": 1.5,
                  "quotes": [q("qoe", "of this, $1.2M recurred in each")]}, TEXTS)[1]
    assert errs == ["addback: 1.5 does not appear in your quotes"]
    c, errs = check({"type": "debt_like", "status": "value", "value": 0,
                     "quotes": [q("cim", "The business has no earnout.")]}, TEXTS)
    assert errs == [] and c["low"] == 0.0


@pytest.mark.parametrize("finding, expected", [
    ({"type": "debt_like", "op": "difference", "inputs": [9.4, 3.1],
      "quotes": [q("audited", "Gross earnout: $9.4M. Amounts settled or funded to date: $3.1M.")]}, 6.3),
    ({"type": "concentration", "op": "product", "inputs": [12.0, 25.0],
      "quotes": [q("contract_1", "it will move 25.0% of its $12.0M of annual purchases")]}, 3.0),
    ({"type": "concentration", "op": "product", "inputs": [12.0, 0.25],
      "quotes": [q("contract_1", "it will move 25.0% of its $12.0M of annual purchases")]}, 3.0),
    ({"type": "concentration", "op": "product", "inputs": [25.0, 12.0],  # F2: either order
      "quotes": [q("contract_1", "it will move 25.0% of its $12.0M of annual purchases")]}, 3.0),
    ({"type": "concentration", "op": "product", "inputs": [0.25, 12.0],
      "quotes": [q("contract_1", "it will move 25.0% of its $12.0M of annual purchases")]}, 3.0),
    ({"type": "capex", "op": "divide", "inputs": [7.5, 5],
      "quotes": [q("assets", "$7.5M, to be spent evenly over the five-year plan")]}, 1.5),
])
def test_a_computed_value_is_code_arithmetic_on_quoted_numbers(finding, expected):
    c, errs = check({"status": "value", "value": 999} | finding, TEXTS)  # the model's own value is ignored
    assert errs == [] and c["kind"] == "computed" and c["low"] == pytest.approx(expected)


def test_a_computed_value_needs_its_inputs_in_the_quotes():
    errs = check({"type": "debt_like", "status": "value", "op": "difference", "inputs": [9.4, 2.0],
                  "quotes": [q("audited", "Gross earnout: $9.4M. Amounts settled")]}, TEXTS)[1]
    assert errs == ["debt_like: input 2.0 does not appear in your quotes"]
    assert check({"type": "capex", "status": "value", "op": "divide", "inputs": [7.5]}, TEXTS)[1][-1] == \
        "capex: inputs must be two numbers"


def test_a_negative_difference_and_a_product_without_a_quoted_percent_are_refused():
    """F2: a difference below zero used to commit 0.0, a committed "no problem"; a product with no percent in the
    quotes has no input code can tell is the percent."""
    errs = check({"type": "debt_like", "status": "value", "op": "difference", "inputs": [3.1, 9.4],
                  "quotes": [q("audited", "Gross earnout: $9.4M. Amounts settled or funded to date: $3.1M.")]},
                 TEXTS)[1]
    assert len(errs) == 1 and "report value 0 with a quote" in errs[0]
    c, errs = check({"type": "debt_like", "status": "value", "op": "difference", "inputs": [9.4, 0],
                     "quotes": [q("audited", "Gross earnout: $9.4M. Amounts settled or funded to date: $0.0M.")]},
                    TEXTS | {"audited": "Gross earnout: $9.4M. Amounts settled or funded to date: $0.0M."})
    assert errs == [] and c["low"] == 9.4  # a difference never divides: a quoted 0 used to raise ZeroDivisionError
    errs = check({"type": "debt_like", "status": "value", "op": "product", "inputs": [9.4, 3.1],
                  "quotes": [q("audited", "Gross earnout: $9.4M. Amounts settled or funded to date: $3.1M.")]},
                 TEXTS)[1]
    assert errs == ["debt_like: product needs a percent from your quotes as one input (25.0 or 0.25 for 25.0%)"]


def test_a_range_is_committed_from_a_stated_range_or_from_documents_that_disagree():
    c, errs = check({"type": "debt_like", "status": "range", "low": 3.0, "high": 6.2,
                     "quotes": [q("legal", "We expect it to settle for $3.0–$6.2M, payable by the Company.")]}, TEXTS)
    assert errs == [] and c["kind"] == "range" and (c["low"], c["high"]) == (3.0, 6.2)
    c, errs = check({"type": "addback", "status": "range", "low": 0, "high": 1.2,
                     "quotes": [q("cim", "Restructuring costs of $1.8M were a one-time cost"),
                                q("qoe", "Of this, $1.2M recurred in each of the last three years")]}, TEXTS)
    assert errs == [] and c["docs"] == ["cim", "qoe"]
    assert check({"type": "addback", "status": "range", "low": 0, "high": 2.5,
                  "quotes": [q("qoe", "Of this, $1.2M recurred in each")]}, TEXTS)[1] == [
        "addback: 2.5 does not appear in your quotes"]


def test_not_found_names_documents_that_were_read_and_open_is_a_bare_belief():
    c, errs = check({"type": "nwc", "status": "not_found", "docs": ["qoe", "audited"]}, TEXTS)
    assert errs == [] and c["kind"] == "not_found" and c["docs"] == ["qoe", "audited"]
    assert check({"type": "nwc", "status": "not_found", "docs": ["hr_policy"]}, TEXTS)[1] == [
        "nwc: you have not read 'hr_policy'"]
    c, errs = check({"type": "nwc", "status": "open", "chance": 0.3, "low": 0, "high": 4}, TEXTS)
    assert errs == [] and (c["chance"], c["high"]) == (0.3, 4.0)
    assert check({"type": "nwc", "status": "open", "chance": 2, "low": 0, "high": 4}, TEXTS)[1]
    assert check({"type": "fraud", "status": "open"}, TEXTS)[1][0].startswith("type must be one of")


def test_numbers_reads_amounts_percentages_ranges_and_number_words():
    assert numbers("$3.0–$6.2M") == [3.0, 6.2]
    assert numbers("25.0% of $1,200.5M") == [25.0, 0.25, 1200.5]
    assert numbers("the five-year plan") == [5.0]


def _line(texts: dict[str, str], docs: list[str], needle: str) -> dict:
    for d in docs:
        for line in texts[d].splitlines():
            if needle in line:
                return q(d, line.strip())
    raise AssertionError(f"{needle!r} not in {docs}")


def test_every_real_value_and_range_can_be_committed_from_its_documents(tmp_path):
    """The Committer on real rooms: for 40 r2 deals, quote the line holding each problem fact's evidence, as an
    Investigator would, and commit the answer-key amount."""
    assert batch.run(tmp_path, {"dev": 40, "test": 0, "hand": 0, "showcase": 0}, mc=20, profile="r2") == []
    seen = set()
    for p in sorted((tmp_path / "truth").glob("*.json")):
        key = AnswerKey.model_validate_json(p.read_text())
        room = tmp_path / "deals" / key.truth.id / "room"
        texts = {d.stem: d.read_text() for d in room.glob("*.md")}
        facts = {f.trap: f for f in key.truth.facts}
        for e in key.evidence:
            v = e.values
            if e.formula == "value":
                f = {"status": "value", "value": v["amount"], "quotes": [_line(texts, e.docs, money(v["amount"]))]}
            elif e.formula == "range":
                f = {"status": "range", "low": v["low"], "high": v["high"],
                     "quotes": [_line(texts, e.docs, span(v["low"], v["high"]))]}
            elif e.formula in ("difference", "gap"):
                a, b = (v["gross"], v["settled"]) if e.formula == "difference" else (v["peg"], v["latest"])
                f = {"status": "value", "op": "difference", "inputs": [round(a, 1), round(b, 1)],
                     "quotes": [_line(texts, e.docs, money(a)), _line(texts, e.docs, money(b))]}
            elif e.formula == "product":
                f = {"status": "value", "op": "product",
                     "inputs": [round(v["purchases"], 1), round(v["fraction"] * 100, 1)],
                     "quotes": [_line(texts, e.docs, pct(v["fraction"]))]}
            else:
                continue
            c, errs = check({"type": e.trap} | f, texts)
            assert errs == [], (key.truth.id, e)
            assert c["high"] == pytest.approx(facts[e.trap].realized if e.formula != "range" else v["high"],
                                              abs=0.1 + 0.01 * c["high"])
            seen.add(e.formula)
    assert {"value", "range"} <= seen
