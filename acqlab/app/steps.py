"""The three steps: Haiku reads and quotes the numbers, code checks the quotes, Opus prices the five worries, and an
Opus second look repeats both into its own files. Odd shapes in Claude's answer blank a field or leave a worry
unpriced; they never raise."""
import math
from pathlib import Path

from acqlab.app.claude import ask
from acqlab.app.ingest import texts
from acqlab.app.prompts import HAIKU, OPUS, PRICER, READER, documents, face_block
from acqlab.app.store import load, write
from acqlab.app.verify import FIELDS, _num, check_number, check_quotes
from acqlab.bench.mix import price as list_price, usage
from acqlab.engine import Financing, Policy
from acqlab.generator.traps import TRAPS

OUT_TOKENS = 4000  # the estimate's guess at an answer's length


class Incomplete(Exception):
    """A number or setting the pricing needs is blank."""


def _cost(step: str, cli: dict) -> float:
    """List-price dollars from the run's tokens, or the CLI's own total when the model has no list price."""
    u = usage(step, cli)
    c = list_price(u["models"], u["tokens"])
    return c if c is not None else float(cli.get("total_cost_usd") or 0)


def _list(x) -> list:
    return x if isinstance(x, list) else []


def read(deal: Path, *, model: str = HAIKU, claude=None, out: str = "numbers.json") -> dict:
    """Ask for the numbers and worry hints, check every quote, write `out`. Fields the analyst typed (status "you")
    in a saved `out` are kept."""
    t = texts(deal)
    answer, cli = ask(documents(deal), READER, model, claude=claude)
    given = answer.get("numbers")
    given = given if isinstance(given, dict) else {}
    numbers = {f: check_number(f, given.get(f), t) for f in FIELDS}
    saved = (load(deal / out, {}) or {}).get("numbers")
    numbers |= {f: s for f, s in (saved if isinstance(saved, dict) else {}).items()
                if isinstance(s, dict) and s.get("status") == "you"}
    hints = []
    for w in _list(answer.get("worries")):
        if isinstance(w, dict) and w.get("type") in TRAPS and isinstance(w.get("note"), str):
            kept, dropped = check_quotes(_list(w.get("quotes")), t)
            hints.append({"type": w["type"], "note": w["note"], "quotes": kept, "dropped_quotes": dropped})
    name, industry = answer.get("name"), answer.get("industry")
    result = {"name": name if isinstance(name, str) else "", "industry": industry if isinstance(industry, str) else "",
              "numbers": numbers, "hints": hints, "cost": _cost("read", cli)}
    write(deal / out, result)
    return result


def complete(numbers: dict) -> list[str]:
    """The fields with no value (blanks and conflicts)."""
    return [f for f in FIELDS if (numbers.get(f) or {}).get("value") is None]


def values(numbers: dict) -> dict[str, float]:
    """Field to value, for the fields that have one."""
    return {f: v["value"] for f, v in numbers.items() if v.get("value") is not None}


def _missing(numbers: dict, settings: dict) -> list[str]:
    """The blank numbers, then the financing and policy settings that are absent or None."""
    missing = complete(numbers)
    for group, cls in (("financing", Financing), ("policy", Policy)):
        have = settings.get(group)
        have = have if isinstance(have, dict) else {}
        missing += [f"{group}.{k}" for k in cls.model_fields if have.get(k) is None]
    return missing


def _worry(w, t: dict) -> dict:
    """One priced worry, or {"not_priced": why} when its numbers are not in range."""
    chance, low, high = (w.get(k) for k in ("chance", "low", "high"))
    if not (all(_num(x) and math.isfinite(x) for x in (chance, low, high)) and 0 <= chance <= 1 and 0 <= low <= high):
        return {"not_priced": "Opus's answer for it was not valid"}
    kept, dropped = check_quotes(_list(w.get("quotes")), t)
    reason = w.get("reason")
    return {"chance": chance, "low": low, "high": high, "reason": reason if isinstance(reason, str) else "",
            "quotes": kept, "dropped_quotes": dropped}


def price(deal: Path, settings: dict, *, model: str = OPUS, claude=None, numbers: dict | None = None,
          out: str = "worries.json") -> dict:
    """Ask for a price on each of the five worries, given the checked numbers and the settings; write `out`. Raises
    Incomplete, naming the blank fields, before spending anything."""
    if numbers is None:
        numbers = load(deal / "numbers.json", {}).get("numbers", {})
    if missing := _missing(numbers, settings):
        raise Incomplete("fill in first: " + ", ".join(missing))
    t = texts(deal)
    face = face_block(values(numbers), settings, load(deal / "deal.json")["price"])
    answer, cli = ask(f"{face}\n\n{documents(deal)}", PRICER, model, claude=claude)
    first = {}
    for w in _list(answer.get("worries")):
        if isinstance(w, dict) and w.get("type") in TRAPS:
            first.setdefault(w["type"], w)  # the first answer for a kind counts
    result = {"worries": {k: _worry(first[k], t) if k in first else {"not_priced": "Opus gave none"} for k in TRAPS},
              "cost": _cost("price", cli)}
    write(deal / out, result)
    return result


def second_look(deal: Path, settings: dict, *, claude=None) -> dict:
    """Opus reads and prices again into second_numbers.json and second_worries.json, pricing on the board's own
    numbers; the board's files are untouched."""
    board = load(deal / "numbers.json", {}).get("numbers", {})
    if missing := _missing(board, settings):  # before the read costs anything
        raise Incomplete("fill in first: " + ", ".join(missing))
    nums = read(deal, model=OPUS, claude=claude, out="second_numbers.json")
    return {"numbers": nums, "worries": price(deal, settings, model=OPUS, claude=claude, numbers=board,
                                              out="second_worries.json")}


def estimate(deal: Path, step: str) -> float:
    """List-price dollars for a step ("read", "price" or "second"): the documents and prompt at 4 characters a token,
    and an answer of 4,000 tokens."""
    chars = len(documents(deal))
    runs = {"read": [(READER, HAIKU)], "price": [(PRICER, OPUS)], "second": [(READER, OPUS), (PRICER, OPUS)]}[step]
    return sum(list_price([m], {"input_tokens": (chars + len(s)) / 4, "output_tokens": OUT_TOKENS}) for s, m in runs)
