"""Replace template prose with LLM prose, one call per document. The LLM never writes a number: every value stays a
{{placeholder}}. Paragraphs that come back broken are retried one at a time; after ATTEMPTS they keep the template."""
import json
import re
from collections.abc import Callable

from acqlab.generator.documents import PLACEHOLDER, Doc, Slot

ATTEMPTS = 3  # one whole-document call, then up to two single-paragraph retries
Complete = Callable[..., tuple[str, int]]
RULES = ("Write no digits. Keep each placeholder exactly as written, at least once, and use no other placeholders. "
         "Do not add amounts, dates, percentages, names or facts beyond the placeholders.")
# Spelled-out numbers slip past the digit check. "one" is left out: it is common English ("one-time").
NUMBER_WORDS = re.compile(
    r"\b(two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|"
    r"eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion|"
    r"percent|half|third|quarter|dozen)\b", re.I)


def _names(s: Slot) -> str:
    names = sorted(set(PLACEHOLDER.findall(s.template)))
    return ", ".join("{{" + n + "}}" for n in names) or "none"


def _context(context: str) -> str:
    """Names the deal, so two deals with identical templates never share a prompt (or a cached reply)."""
    return f"The fictional company is {context}. Use this for tone only; do not name it."


def doc_prompt(doc: Doc, slots: list[Slot], context: str) -> str:
    lines = [
        f"You are writing the prose paragraphs of a {doc.title} for a fictional company.", _context(context),
        "Write each paragraph as two to four sentences of professional prose. Keep each paragraph to its own "
        "meaning: do not mention one paragraph's subject in another.",
        f"Rules for every paragraph: {RULES}",
        "Return JSON mapping each paragraph id to its text.", "Paragraphs:",
    ]
    for s in slots:
        lines += [f"- id: {s.id}", f"  purpose: {s.brief}", f'  meaning: "{s.template}"',
                  f"  placeholders: {_names(s)}"]
    return "\n".join(lines)


def doc_schema(slots: list[Slot]) -> dict:
    return {"type": "object", "properties": {s.id: {"type": "string"} for s in slots},
            "required": [s.id for s in slots], "additionalProperties": False}


def prompt_for(doc: Doc, s: Slot, attempt: int, context: str) -> str:
    """Single-paragraph retry. The attempt number changes the prompt, so a retry is never served from the cache."""
    return "\n".join([
        f"You are writing one passage of a {doc.title} for a fictional company. Attempt {'I' * (attempt + 1)}.",
        _context(context),
        f"Purpose: {s.brief}.",
        f'Convey exactly this meaning, in two to four sentences of professional prose: "{s.template}"',
        f"Placeholders: {_names(s)}. {RULES}",
        "Return only the passage.",
    ])


def _number_words(text: str) -> set[str]:
    return {w.lower() for w in NUMBER_WORDS.findall(text)}


def acceptable(text: object, template: str) -> bool:
    return (isinstance(text, str) and bool(text.strip()) and not re.search(r"\d", text)
            and not _number_words(text) - _number_words(template)
            and set(PLACEHOLDER.findall(text)) == set(PLACEHOLDER.findall(template)))


def _parse(text: str) -> dict:
    try:
        got = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return got if isinstance(got, dict) else {}


def fill(docs: list[Doc], complete: Complete, *, context: str) -> tuple[list[Doc], int, int]:
    """Returns (docs with prose, tokens used, paragraphs left as template). `context` names the deal."""
    tokens = fallbacks = 0
    out = []
    for doc in docs:
        slots = [b for b in doc.blocks if isinstance(b, Slot)]
        if not slots:
            out.append(doc)
            continue
        text, used = complete(doc_prompt(doc, slots, context), schema=doc_schema(slots))
        tokens += used
        replies = _parse(text)
        written: dict[str, str] = {}
        for s in slots:
            reply = replies.get(s.id)
            attempt = 1
            while not acceptable(reply, s.template) and attempt < ATTEMPTS:
                reply, used = complete(prompt_for(doc, s, attempt, context))
                tokens += used
                attempt += 1
            if acceptable(reply, s.template):
                written[s.id] = reply
            else:
                fallbacks += 1
        blocks = [b.model_copy(update={"text": written[b.id]}) if isinstance(b, Slot) and b.id in written else b
                  for b in doc.blocks]
        out.append(doc.model_copy(update={"blocks": blocks}))
    return out, tokens, fallbacks
