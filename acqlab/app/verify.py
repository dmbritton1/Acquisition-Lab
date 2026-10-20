"""The quote check: a number from a CIM is filled in only if a real quote backs it; anything else stays blank."""
import math

from acqlab.agents.committer import MIN_QUOTE, TOL, norm, numbers

FIELDS = ("revenue_ltm", "reported_ebitda", "claimed_addbacks", "adj_ebitda", "growth", "capex_pct", "nwc_pct",
          "da_pct", "tax_rate")
RATES = ("growth", "capex_pct", "nwc_pct", "da_pct", "tax_rate")  # stored as fractions, quoted as percentages
OPS = {"sum": lambda a, b: a + b, "difference": lambda a, b: a - b, "product": lambda a, b: a * b,
       "divide": lambda a, b: a / b}


def quote_ok(q: dict, texts: dict[str, str]) -> bool:
    """The quote's document exists, and its text is long enough and appears in that document."""
    doc = texts.get(q.get("doc_id"))
    text = norm(q.get("text") or "")
    return doc is not None and len(text) >= MIN_QUOTE and text in norm(doc)


def has(x: float, q: dict, rate: bool = False) -> bool:
    """x appears in the quote. A rate is a fraction, so it is compared as a percentage."""
    x = x * 100 if rate else x
    return any(abs(x - n) <= TOL or math.isclose(x, n, rel_tol=1e-6) for n in numbers(q.get("text") or ""))


def _blank(why: str, quotes=()) -> dict:
    return {"value": None, "status": "blank", "quotes": list(quotes), "calc": "none", "inputs": [], "why": why}


def check_quotes(quotes: list[dict], texts) -> tuple[list[dict], int]:
    """The quotes that pass quote_ok, and how many were dropped."""
    kept = [q for q in quotes if quote_ok(q, texts)]
    return kept, len(quotes) - len(kept)


def check_number(field: str, answer: dict | None, texts) -> dict:
    """Quoted, calculated, conflict or blank (with a reason) for one field's answer."""
    if not answer or answer.get("value") is None or not answer.get("quotes"):
        return _blank("not stated")
    value, quotes, calc, inputs = answer["value"], answer["quotes"], answer.get("calc", "none"), answer.get("inputs", [])
    if not all(quote_ok(q, texts) for q in quotes):
        return _blank("quote not found")
    rate = field in RATES
    if calc == "none":
        if not all(has(value, q, rate) for q in quotes):
            return _blank("number not in quote")
    elif calc in OPS and len(inputs) == len(quotes) == 2:
        if not all(has(x, q) for x, q in zip(inputs, quotes)):  # inputs are amounts, never rates
            return _blank("number not in quote")
        try:
            ok = math.isclose(OPS[calc](*inputs), value, rel_tol=1e-3)
        except ZeroDivisionError:
            ok = False
        if not ok:
            return _blank("calculation doesn't check")
    else:
        return _blank("calculation doesn't check")
    scale = 100 if rate else 1
    seen = list(quotes)
    conflict = False
    for o in answer.get("other_values") or []:
        oq, ov = o.get("quote") or {}, o.get("value")
        if ov is not None and quote_ok(oq, texts) and has(ov, oq, rate):
            seen.append(oq)
            conflict |= abs(ov - value) * scale > TOL
    if conflict:
        return {**_blank("documents disagree", seen), "status": "conflict"}
    return {"value": value, "status": "quoted" if calc == "none" else "calculated", "quotes": quotes, "calc": calc,
            "inputs": list(inputs), "why": ""}
