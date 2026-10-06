"""The referee kill test (docs/results/referee-kill-test-prereg.md): on a deal where the team (S4) and single Claude
(S1b) disagree, one sandboxed turn sees every document either opened and both analysts' work, prices with evaluate and
submits. It pools both runs' reading, so it screens the idea; it is not a fair result.

It reads the room and the two traces only, never an answer key.

  uv run python -m acqlab.bench.referee --data data/test-r2 --confirm-claude"""
import argparse
import json
import random
from pathlib import Path

from acqlab.agents.knowledge import GUIDE
from acqlab.agents.solver import RunTimeout, run_session
from acqlab.bench import valuer
from acqlab.generator.batch import AnswerKey
from acqlab.llm import LLMUnavailable

SYSTEM = """You are a private-equity analyst refereeing a disagreement about a leveraged buyout: should the sponsor \
buy the company at its asking price?

Two analysts did diligence on this deal, each with a limited reading budget, and reached opposite calls. You get the \
teaser, with the lender terms and the sponsor's policy; the full text of every document either of them read; and each \
analyst's findings. You cannot read anything else.

Find what the disagreement turns on, and settle it from the documents: a finding counts where a document supports it, \
and an issue neither analyst could check stays uncertain. All amounts are in $M: addback = claimed add-backs that are \
not really one-time (they reduce EBITDA); debt_like = debt-like items payable at closing; concentration = annual \
revenue that will be lost; nwc = how far closing net working capital falls short of normal; capex = extra capital \
expenditure needed per year.

Use evaluate to price your adjustments: it returns the walk-away price (the most the sponsor should pay) and whether \
the deal clears at the asking price. Then call submit once, with go (true to buy at the asking price), walk_away in $M \
and a one-line reason. You are judged on the decision: buying a deal worth less than its price, or passing on one \
worth more, costs the difference.

{guide}"""


NO_READING = "You cannot read anything else."
READING = ("You can also read more before deciding, with a budget of {left:g} units: list_documents shows every "
           "document, opening one costs 1 unit per page and search costs 1 unit. The documents above are already "
           "paid for.")
READ_TOOLS = ["list_documents", "search", "open_document", "evaluate", "submit"]


def rows(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines()]


def opened(trace: list[dict]) -> list[str]:
    return [r["args"]["doc_id"] for r in trace if r["tool"] == "open_document" and not r.get("refused")]


def submitted(trace: list[dict]) -> dict:
    return next(r for r in trace if r["tool"] == "submit" and not r.get("refused"))["args"]


def team_view(room: Path, trace: list[dict]) -> str:
    """S4's final Deal Record as its own roles saw it, and its submitted call."""
    s = submitted(trace)
    return (valuer.replay(room, trace).view() +
            f"\nCall: {'GO' if s['go'] else 'NO-GO'}, walk-away ${s['walk_away']:,.1f}M.")


def note_lines(trace: list[dict]) -> list[str]:
    """An analyst's last note per issue type, one line each."""
    notes = {r["args"]["type"]: r["args"] for r in trace if r["tool"] == "note_issue" and not r.get("refused")}
    return [f"- {t}: chance {n['chance']:g}, ${n['low']:g}M to ${n['high']:g}M if real ({n.get('name', '')})"
            for t, n in notes.items()] or ["- no issues noted"]


def solo_view(trace: list[dict]) -> str:
    """S1b's last note per issue type, its last evaluate, and its submitted call and reason."""
    ok = [r for r in trace if not r.get("refused")]
    lines = note_lines(ok)
    ev = [r for r in ok if r["tool"] == "evaluate"]
    if ev:
        res = ev[-1].get("result") or {}
        lines.append(f"Last priced adjustments: {json.dumps(ev[-1]['args']['adjustments'])} -> walk-away "
                     f"${res.get('walk_away', float('nan')):,.1f}M")
    s = next((r["args"] for r in ok if r["tool"] == "submit"), None)
    lines.append(f"Call: {'GO' if s['go'] else 'NO-GO'}, walk-away ${s['walk_away']:,.1f}M. Reason: {s['reason']}"
                 if s else "Call: none; the analyst's run ended without submitting one.")
    return "\n".join(lines)


def build(room: Path, views: list[str], read: list[str], deal: str, left: float | None = None) -> tuple[str, str]:
    """(system, user) for any two analysts' views and the documents read. The views' order is fixed per deal from its
    id, so neither is always first. With `left`, the referee may also read, with that budget (the recon pilot)."""
    index = json.loads((room / "index.json").read_text())
    titles = {d["id"]: d["title"] for d in index["documents"]}
    read = [d for d in titles if d in set(read)]
    docs = "\n\n".join(f"## {titles[d]} ({d})\n\n{(room / f'{d}.md').read_text()}" for d in read)
    views = list(views)
    if random.Random(deal).random() < 0.5:
        views.reverse()
    user = (f"{index['teaser']}\n\n# Documents either analyst read\n\n{docs}\n\n# Analyst 1\n\n{views[0]}\n\n"
            f"# Analyst 2\n\n{views[1]}\n\nSettle the disagreement and submit your decision.")
    system = SYSTEM.format(guide=GUIDE)
    return (system if left is None else system.replace(NO_READING, READING.format(left=left))), user


def prompts(room: Path, team: list[dict], solo: list[dict], deal: str) -> tuple[str, str]:
    """The kill test's (system, user): the team's and single Claude's work, and every document either opened."""
    return build(room, [team_view(room, team), solo_view(solo)], opened(team) + opened(solo), deal)


def judge(room: Path, team: list[dict], solo: list[dict], deal: str, trace: Path, **kw) -> dict:
    """One referee turn: evaluate and submit only, no reading budget. Raises LLMUnavailable like any session."""
    system, user = prompts(room, team, solo, deal)
    return run_session(room, 0, trace, user, system, ["evaluate", "submit"], [], **kw)


def judge_reading(room: Path, views: list[str], read: list[str], deal: str, left: float, trace: Path,
                  **kw) -> dict:
    """A referee turn that may read with `left` units; the documents already read are paid for (the recon pilot)."""
    system, user = build(room, views, read, deal, left)
    paid = list(dict.fromkeys(read))
    return run_session(room, left, trace, user, system, READ_TOOLS, ["--paid", ",".join(paid)] if paid else [], **kw)


def disputed(data: Path) -> list[str]:
    runs = data / "runs"
    both = sorted(p.stem for p in (runs / "s4").glob("*.json") if (runs / "s1b" / p.name).exists())
    return [d for d in both if json.loads((runs / "s4" / f"{d}.json").read_text())["go"]
            != json.loads((runs / "s1b" / f"{d}.json").read_text())["go"]]


def run(data: Path, judge=judge) -> list[dict]:
    """A referee run on every disputed deal without one; raises LLMUnavailable to stop the batch."""
    from acqlab.bench.pilot import score  # scoring reads the answer key, after the referee has submitted
    out = []
    for deal in disputed(data):
        path = data / "runs" / "referee" / f"{deal}.json"
        if path.exists():
            continue
        room = data / "deals" / deal / "room"
        team, solo = (rows(data / "runs" / s / f"{deal}.trace.jsonl") for s in ("s4", "s1b"))
        path.parent.mkdir(parents=True, exist_ok=True)
        trace = path.with_suffix(".trace.jsonl")
        trace.unlink(missing_ok=True)
        try:
            cli, status = judge(room, team, solo, deal, trace), "ok"
        except RunTimeout:
            cli, status = None, "timeout"
        tr = rows(trace) if trace.exists() else []
        if status == "ok" and not tr:
            raise LLMUnavailable(f"referee/{deal}: the tool server never ran (no trace)")
        key = AnswerKey.model_validate_json((data / "truth" / f"{deal}.json").read_text())
        row = score(key, "referee", tr, cli, status) | {"rep": 0}
        path.write_text(json.dumps(row, indent=2))
        out.append(row)
        print(f"referee {deal}: correct={row['correct']} regret {row['regret']:.3f} answered={row['answered']}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--confirm-claude", action="store_true", help="required: this spends real Claude usage")
    args = ap.parse_args(argv)
    if not args.confirm_claude:
        print("Refusing: pass --confirm-claude to spend real Claude usage")
        return 1
    run(args.data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
