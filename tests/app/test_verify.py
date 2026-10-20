"""The quote check: a number is filled in only when a real quote backs it."""
from acqlab.app.verify import check_number, check_quotes

TEXTS = {"cim": "[page 1]\nLTM revenue of $162.8M grew 7.7% a year. Capex was $7.8M last year.\n"
                "Revenue last year: $162,798 thousand.",
         "teaser": "[page 1]\nRevenue: $160.0M (LTM)"}


def q(doc, text): return {"doc_id": doc, "text": text}
def ans(value, quotes, calc="none", inputs=(), other=()):
    return {"value": value, "quotes": list(quotes), "calc": calc, "inputs": list(inputs), "other_values": list(other)}


def test_a_quoted_number_is_filled_in():
    r = check_number("revenue_ltm", ans(162.8, [q("cim", "LTM revenue of $162.8M grew")]), TEXTS)
    assert (r["status"], r["value"]) == ("quoted", 162.8)


def test_a_percentage_is_checked_as_its_fraction():
    assert check_number("growth", ans(0.077, [q("cim", "grew 7.7% a year")]), TEXTS)["status"] == "quoted"


def test_a_calculated_number_shows_its_inputs():
    r = check_number("capex_pct", ans(7.8 / 162.8, [q("cim", "Capex was $7.8M last year"),
                                                    q("cim", "LTM revenue of $162.8M")],
                                      calc="divide", inputs=[7.8, 162.8]), TEXTS)
    assert r["status"] == "calculated" and r["inputs"] == [7.8, 162.8]


def test_no_quote_or_null_value_is_blank():
    assert check_number("revenue_ltm", ans(None, []), TEXTS)["why"] == "not stated"
    assert check_number("revenue_ltm", None, TEXTS)["status"] == "blank"


def test_a_quote_not_in_the_text_is_blank():
    r = check_number("revenue_ltm", ans(162.8, [q("cim", "LTM revenue of $162.8 million")]), TEXTS)
    assert r["why"] == "quote not found"


def test_a_quote_without_the_number_is_blank():
    r = check_number("revenue_ltm", ans(150.0, [q("cim", "LTM revenue of $162.8M grew")]), TEXTS)
    assert r["why"] == "number not in quote"


def test_a_short_quote_proves_nothing():
    assert check_number("capex_pct", ans(7.8, [q("cim", "$7.8M")]), TEXTS)["status"] == "blank"


def test_numbers_in_thousands_stay_blank_rather_than_wrong():
    r = check_number("revenue_ltm", ans(162.8, [q("cim", "Revenue last year: $162,798 thousand")]), TEXTS)
    assert r["status"] == "blank"


def test_documents_that_disagree_leave_it_blank_with_both_quotes():
    r = check_number("revenue_ltm", ans(162.8, [q("cim", "LTM revenue of $162.8M grew")],
                     other=[{"value": 160.0, "quote": q("teaser", "Revenue: $160.0M (LTM)")}]), TEXTS)
    assert r["status"] == "conflict" and r["value"] is None and len(r["quotes"]) == 2


def test_worry_quotes_from_unknown_documents_are_dropped_and_counted():
    kept, dropped = check_quotes([q("cim", "Capex was $7.8M last year"), q("qoe", "anything at all here ok")], TEXTS)
    assert len(kept) == 1 and dropped == 1


def test_a_rate_must_match_its_percentage():
    r = check_number("growth", ans(0.03, [q("cim", "grew 7.7% a year")]), TEXTS)
    assert r["status"] == "blank" and r["why"] == "number not in quote"
