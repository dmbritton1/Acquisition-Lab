"""Recoverability check (design §7): a non-solver model, shown only a fact's evidence documents, must recover the
answer; shown an unrelated filler document, it must say the answer is not there."""
import json
import re
from collections.abc import Callable

from acqlab.generator.render import LABELS, Evidence, answer
from acqlab.generator.truth import DealTruth

Complete = Callable[..., tuple[str, int]]
SCHEMA = {"type": "object", "properties": {"low": {"type": ["number", "null"]}, "high": {"type": ["number", "null"]}},
          "required": ["low", "high"], "additionalProperties": False}
QUESTIONS = {
    "addback": "How much of the claimed {label} add-back, in $M, should be disallowed because the cost recurs? "
               "Answer 0 if it is a genuine one-time cost.",
    "debt_like": "What amount, in $M, should be treated as debt at closing for any {label}? Answer 0 if none.",
    "concentration": "By how much, in $M per year, will revenue from the largest customer fall? Answer 0 if it "
                     "will not fall.",
    "nwc": "By how much, in $M, will net working capital at closing fall below the peg? Answer 0 if it will not.",
    "capex": "How much additional capital expenditure, in $M per year, is needed because of {label}? Answer 0 if "
             "none.",
}


def question(trap: str, variant: str) -> str:
    return QUESTIONS[trap].format(label=LABELS[variant])


def prompt_for(docs: list[str], q: str) -> str:
    return "\n\n".join([
        "Answer from the documents below alone.", *docs, f"Question: {q}",
        'Reply with JSON only: {"low": number or null, "high": number or null}. For a single value use low = high. '
        "If the documents give only a range, give that range. If they do not contain the answer, use null for both.",
    ])


def _number(v: object) -> float | None:
    """A JSON number, or None for null, text, booleans or anything else."""
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def parse(text: str) -> tuple[float | None, float | None]:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None, None
    try:
        got = json.loads(match.group(0))
        if not isinstance(got, dict):
            return None, None
        return _number(got.get("low")), _number(got.get("high"))
    except (json.JSONDecodeError, AttributeError):
        return None, None


def _close(a: float | None, b: float) -> bool:
    return a is not None and abs(a - b) <= max(0.15, 0.03 * abs(b))


def check(t: DealTruth, evidence: list[Evidence], texts: dict[str, str], complete: Complete,
          unrelated: str) -> tuple[list[str], int]:
    """Returns (problems, tokens). `unrelated` is the id of a filler document with no answer in it."""
    problems, tokens = [], 0
    for f, ev in zip(t.facts, evidence):
        q = question(f.trap, f.variant)
        want = answer(ev)
        lo_hi = want if isinstance(want, tuple) else (want, want)
        (low, high), used = _ask([texts[d] for d in ev.docs], q, complete)
        tokens += used
        if not (_close(low, lo_hi[0]) and _close(high, lo_hi[1])):
            problems.append(f"{f.trap}: extractor answered {low}-{high}, answer key {lo_hi}")
        (low, high), used = _ask([texts[unrelated]], q, complete)
        tokens += used
        if low is not None or high is not None:
            problems.append(f"{f.trap}: extractor found an answer in unrelated document {unrelated!r}")
    return problems, tokens


def _ask(docs: list[str], q: str, complete: Complete) -> tuple[tuple, int]:
    text, used = complete(prompt_for(docs, q), schema=SCHEMA)
    return parse(text), used
