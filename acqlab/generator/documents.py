"""Document model. Code writes every number; prose slots hold {{placeholders}} that code fills in."""
import math
import re

from pydantic import BaseModel

WORDS_PER_PAGE = 120  # a budget unit, not a printed page
PLACEHOLDER = re.compile(r"\{\{([a-z_]+)\}\}")  # names never contain digits, so prose can be digit-checked


class Slot(BaseModel):
    id: str
    brief: str  # what an LLM writer is asked to say (no numbers)
    template: str  # plain template prose with {{placeholders}}
    values: dict[str, str]  # placeholder -> formatted value
    text: str | None = None  # LLM prose with the same placeholders; None -> use template

    def render(self) -> str:
        return PLACEHOLDER.sub(lambda m: self.values[m.group(1)], self.text or self.template)


class Doc(BaseModel):
    id: str
    title: str
    domain: str  # accounting | legal | credit | commercial | filler
    blocks: list[str | Slot]

    def render(self) -> str:
        return "\n\n".join(b if isinstance(b, str) else b.render() for b in self.blocks)

    @property
    def pages(self) -> int:
        return max(1, math.ceil(len(self.render().split()) / WORDS_PER_PAGE))


def money(x: float) -> str:
    return f"${x:,.1f}M"


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def slot(sid: str, brief: str, template: str, **values: str) -> Slot:
    return Slot(id=sid, brief=brief, template=template, values=values)


def heading(style: str, n: int, text: str) -> str:
    return f"## {text}" if style == "A" else f"SECTION {n}. {text.upper()}"


def table(style: str, header: list[str], rows: list[list[str]]) -> str:
    if style == "A":
        lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
        return "\n".join(lines + ["| " + " | ".join(r) + " |" for r in rows])
    return "\n".join([" / ".join(header)] + [f"{r[0]} ........ " + " / ".join(r[1:]) for r in rows])
