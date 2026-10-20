"""The quote check: a number from a CIM is filled in only if a real quote backs it; anything else stays blank."""
import math
import re

from acqlab.agents.committer import MIN_QUOTE, TOL, norm

FIELDS = ("revenue_ltm", "reported_ebitda", "claimed_addbacks", "adj_ebitda", "growth", "capex_pct", "nwc_pct",
          "da_pct", "tax_rate")
RATES = ("growth", "capex_pct", "nwc_pct", "da_pct", "tax_rate")  # stored as fractions, quoted as percentages
_NUM = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(%?)")  # a number and whether a % sign follows it
# a money quote in thousands or billions: the number in it is not $M, whatever the reader copied
SCALE = re.compile(r"000s|\(\$?000\)|thousand|billion|\bbn\b|\d\s*bn\b|\$k\b|\d[\d,]*(?:\.\d+)?k\b", re.I)
OPS = {"sum": lambda a, b: a + b, "difference": lambda a, b: a - b, "product": lambda a, b: a * b,
       "divide": lambda a, b: a / b}


def _num(x) -> bool:
    """A real number: model output may be anything, and a bool or a string is not one."""
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def quote_ok(q: dict, texts: dict[str, str]) -> bool:
    """The quote's document exists, and its text is long enough and appears in that document."""
    if not (isinstance(q, dict) and isinstance(q.get("doc_id"), str) and isinstance(q.get("text"), str)):
        return False
    doc = texts.get(q["doc_id"])
    text = norm(q["text"])
    return doc is not None and len(text) >= MIN_QUOTE and text in norm(doc)


def has(x: float, q: dict, rate: bool = False) -> bool:
    """x appears in the quote. A rate is a fraction and must match a number written with a % sign, as a percentage;
    an amount must match a number written without one."""
    if not _num(x):
        return False
    x = x * 100 if rate else x
    found = [float(d.replace(",", "")) for d, pct in _NUM.findall(q["text"]) if bool(pct) == rate]
    return any(abs(x - n) <= TOL or math.isclose(x, n, rel_tol=1e-6) for n in found)


def _blank(why: str, quotes=()) -> dict:
    return {"value": None, "status": "blank", "quotes": list(quotes), "calc": "none", "inputs": [], "why": why}


def check_quotes(quotes: list[dict], texts) -> tuple[list[dict], int]:
    """The quotes that pass quote_ok, and how many were dropped."""
    kept = [q for q in quotes if quote_ok(q, texts)]
    return kept, len(quotes) - len(kept)


def check_number(field: str, answer: dict | None, texts) -> dict:
    """Quoted, calculated, conflict or blank (with a reason) for one field's answer. Malformed answers are blank."""
    if not isinstance(answer, dict) or not _num(answer.get("value")) or not answer.get("quotes"):
        return _blank("not stated")
    value, quotes, calc, inputs = answer["value"], answer["quotes"], answer.get("calc", "none"), answer.get("inputs")
    if not isinstance(quotes, list) or not all(quote_ok(q, texts) for q in quotes):
        return _blank("quote not found")
    inputs = inputs if isinstance(inputs, list) else []
    rate = field in RATES
    if not rate and any(SCALE.search(q["text"]) for q in quotes):
        return _blank("units look off", quotes)
    if calc == "none":
        if not all(has(value, q, rate) for q in quotes):
            return _blank("number not in quote")
    elif isinstance(calc, str) and calc in OPS and len(inputs) == len(quotes) == 2:
        if not all(has(x, q) for x, q in zip(inputs, quotes)):  # inputs are amounts, never rates
            return _blank("number not in quote")
        try:
            ok = math.isclose(OPS[calc](*inputs), value, rel_tol=1e-3)
        except (ZeroDivisionError, OverflowError):
            ok = False
        if not ok:
            return _blank("calculation doesn't check")
    else:
        return _blank("calculation doesn't check")
    scale = 100 if rate else 1
    seen = list(quotes)
    conflict = False
    others = answer.get("other_values")
    for o in others if isinstance(others, list) else []:
        if not isinstance(o, dict):
            continue
        oq, ov = o.get("quote"), o.get("value")
        if quote_ok(oq, texts) and has(ov, oq, rate):
            seen.append(oq)
            conflict |= abs(ov - value) * scale > TOL
    if conflict:
        return {**_blank("documents disagree", seen), "status": "conflict"}
    return {"value": value, "status": "quoted" if calc == "none" else "calculated", "quotes": quotes, "calc": calc,
            "inputs": inputs, "why": ""}
