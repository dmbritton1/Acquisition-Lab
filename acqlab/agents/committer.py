"""The Committer (main spec §3; reframe design §5): code accepts a finding only when its evidence checks out.
LLMs read and judge; this file checks quotes and does the arithmetic. It sees only the text of documents the
session has read, never an answer key.

A finding is one issue type's result:
- value: an amount, quoted (a number in a verbatim quote) or computed (code applies op to two quoted numbers)
- range: low and high, each 0 or a number in a quote (an unresolvable amount, or documents that disagree)
- not_found: the documents read that don't settle it
- open: a belief with no evidence yet (chance and range)
"""
import math
import re

from acqlab.generator.traps import TRAPS

OPS = ("none", "difference", "product", "divide")
MIN_QUOTE = 12  # characters, after normalising: shorter quotes prove nothing
TOL = 0.051  # $M: amounts print with one decimal
_NUM = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(%?)")
_WORDS = {w: float(i) for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve".split())}


def norm(text: str) -> str:
    """Lower case, one kind of dash, markdown table and emphasis marks dropped, whitespace collapsed."""
    text = text.lower().replace("–", "-").replace("—", "-").replace("’", "'")
    return " ".join(re.sub(r"[|*#`>]", " ", text).split())


def numbers(quote: str) -> list[float]:
    """Every number in a quote. A percentage also counts as its fraction (25.0% gives 25.0 and 0.25); number words
    up to twelve count too ("five-year plan")."""
    out = []
    for digits, percent in _NUM.findall(quote):
        x = float(digits.replace(",", ""))
        out += [x, x / 100] if percent else [x]
    out += [_WORDS[w] for w in re.findall(r"[a-z]+", quote.lower()) if w in _WORDS]
    return out


def _in(x: float, nums: list[float]) -> bool:
    return any(abs(x - n) <= TOL or math.isclose(x, n, rel_tol=1e-6) for n in nums)


def _num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def check(finding: dict, texts: dict[str, str]) -> tuple[dict | None, list[str]]:
    """(commit, errors). `texts` maps each document the session may cite to its text. A commit is
    {"type", "kind": quoted|computed|range|not_found|open, "low", "high", "chance", "quotes", "docs"}."""
    t, status = finding.get("type"), finding.get("status")
    if t not in TRAPS:
        return None, [f"type must be one of {', '.join(TRAPS)}"]
    errors: list[str] = []
    quotes = finding.get("quotes") or []
    nums: list[float] = []
    pcts: list[float] = []  # percent figures as printed: 25.0 for "25.0%"
    for q in quotes:
        doc, text = (q.get("doc_id"), q.get("text")) if isinstance(q, dict) else (None, None)
        if doc not in texts:
            errors.append(f"{t}: quote from {doc!r}, which you have not read")
        elif not isinstance(text, str) or len(norm(text)) < MIN_QUOTE or norm(text) not in norm(texts[doc]):
            errors.append(f"{t}: the quote {text!r} is not in {doc} word for word (copy at least {MIN_QUOTE} "
                          "characters exactly)")
        else:
            nums += numbers(text)
            pcts += [float(d.replace(",", "")) for d, p in _NUM.findall(text) if p]
    base = {"type": t, "chance": 1.0, "quotes": quotes, "docs": sorted({q["doc_id"] for q in quotes
                                                                          if isinstance(q, dict) and "doc_id" in q})}
    if status == "value":
        op = finding.get("op", "none")
        if op not in OPS:
            return None, errors + [f"{t}: op must be one of {', '.join(OPS)}"]
        if op == "none":
            v = _num(finding.get("value"))
            if not quotes:
                errors.append(f"{t}: a value needs a quote")
            if v is None or v < 0:
                errors.append(f"{t}: value must be a number >= 0")
            elif v > 0 and not _in(v, nums):
                errors.append(f"{t}: {v} does not appear in your quotes")
            return (None, errors) if errors else ({**base, "kind": "quoted", "low": v, "high": v}, [])
        inputs = finding.get("inputs")
        a, b = (_num(inputs[0]), _num(inputs[1])) if isinstance(inputs, list) and len(inputs) == 2 else (None, None)
        if not quotes:
            errors.append(f"{t}: a computed value needs quotes holding both inputs")
        if a is None or b is None:
            return None, errors + [f"{t}: inputs must be two numbers"]
        for x in (a, b):
            if not _in(x, nums):
                errors.append(f"{t}: input {x} does not appear in your quotes")
        if op == "divide" and b <= 0:
            errors.append(f"{t}: cannot divide by {b}")
        if op == "difference" and a < b:
            errors.append(f"{t}: {a} - {b} is negative; if there is no shortfall or remaining amount, report value 0 "
                          "with a quote")
        # product: the percent input, in either order: first one given as a quoted percent's fraction (0.25), else
        # one given as its printed figure (25.0), which counts as its fraction
        fracs = [p / 100 for p in pcts]
        pct = next((x for x in (b, a) if _in(x, fracs)), next((x for x in (b, a) if _in(x, pcts)), None))
        if op == "product" and pct is None:
            errors.append(f"{t}: product needs a percent from your quotes as one input (25.0 or 0.25 for 25.0%)")
        if errors:
            return None, errors
        v = a - b if op == "difference" else a / b if op == "divide" else a * b / (1 if _in(pct, fracs) else 100)
        return {**base, "kind": "computed", "low": v, "high": v}, []
    if status == "range":
        lo, hi = _num(finding.get("low")), _num(finding.get("high"))
        if lo is None or hi is None or not 0 <= lo <= hi:
            return None, errors + [f"{t}: need 0 <= low <= high"]
        if not quotes:
            errors.append(f"{t}: a range needs a quote")
        errors += [f"{t}: {x} does not appear in your quotes" for x in (lo, hi) if x > 0 and not _in(x, nums)]
        return (None, errors) if errors else ({**base, "kind": "range", "low": lo, "high": hi}, [])
    if status == "not_found":
        docs = finding.get("docs")
        if not isinstance(docs, list) or not docs:
            return None, errors + [f"{t}: list the documents you read that don't settle it"]
        errors += [f"{t}: you have not read {d!r}" for d in docs if d not in texts]
        return (None, errors) if errors else ({**base, "kind": "not_found", "low": None, "high": None,
                                               "docs": [str(d) for d in docs]}, [])
    if status == "open":
        c, lo, hi = _num(finding.get("chance")), _num(finding.get("low")), _num(finding.get("high"))
        if c is None or lo is None or hi is None or not (0 <= c <= 1 and 0 <= lo <= hi):
            return None, errors + [f"{t}: need 0 <= chance <= 1 and 0 <= low <= high"]
        return (None, errors) if errors else ({**base, "kind": "open", "chance": c, "low": lo, "high": hi}, [])
    return None, [f"{t}: status must be value, range, not_found or open"]
