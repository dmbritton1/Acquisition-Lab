"""Tool server for one solver run (Plan 4a design §2): the data room, search, the engine, issue notes and, for the
router system, router 6. Search came back in Plan 4b, once a real problem and a clean fact share every reveal word
(validate.word_leaks is empty); it returns document ids, never text. Speaks MCP over stdio (one JSON-RPC message per
line) with the standard library only. It reads only
its room folder, never an answer key, and writes every call to a trace file (one JSON object per line).

  python -m acqlab.agents.server --room <room> --budget 22 --trace <file.jsonl> [--router]
"""
import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

from acqlab.agents.knowledge import typical_high
from acqlab.agents.record import load_face, next_doc
from acqlab.dataroom.tools import BudgetExceeded, DataRoom
from acqlab.engine import is_go, walk_away
from acqlab.generator.traps import TRAPS, params_for
from acqlab.routers.beliefs import HAIRCUT_CAP, Issue, draw, walk_aways
from acqlab.routers.routers import decide, score_regret

MAX_CALLS = 80  # after this many calls only submit is accepted
N_WORLDS = 400
PROTOCOL = "2025-06-18"
ADJUSTMENTS = ("Adjustments in $M, each optional and >= 0: addback = claimed add-backs that are not really one-time "
               "(reduces EBITDA); debt_like = debt-like items payable at closing; concentration = annual revenue that "
               "will be lost; nwc = amount by which closing net working capital falls short of normal; capex = extra "
               "capital expenditure needed per year.")
_OBJ = {"type": "object"}
TOOLS = {
    "list_documents": ("Free. Every document's id, title, domain and page count.", {**_OBJ, "properties": {}}),
    "search": ("Costs 1 unit. The ids of the documents holding the 5 paragraphs that match the most of your words "
               "(letters only, no numbers) — so often fewer than 5 documents. No text: open a document to read it.",
               {**_OBJ, "properties": {"query": {"type": "string"}}, "required": ["query"]}),
    "open_document": ("Costs 1 unit per page. The document's full text. With the router, needs at least one open "
                      "note first, and the router's ranking follows the text.",
                      {**_OBJ, "properties": {"doc_id": {"type": "string"}}, "required": ["doc_id"]}),
    "evaluate": ("Free. Walk-away price (the most the sponsor should pay, $M) and whether the deal clears at the "
                 "asking price, given your adjustments. " + ADJUSTMENTS,
                 {**_OBJ, "properties": {"adjustments": {
                     **_OBJ, "properties": {t: {"type": "number", "minimum": 0} for t in TRAPS},
                     "additionalProperties": False}}, "required": ["adjustments"]}),
    "note_issue": ("Free. Record your belief about one issue type (one note per type; a new note replaces the old): "
                   "the chance it is real (0 to 1), its size range in $M if real (same units as evaluate), and the "
                   "document ids that would settle it. Use chance 1 once confirmed.",
                   {**_OBJ, "properties": {
                       "name": {"type": "string"}, "type": {"type": "string", "enum": list(TRAPS)},
                       "chance": {"type": "number", "minimum": 0, "maximum": 1},
                       "low": {"type": "number", "minimum": 0}, "high": {"type": "number", "minimum": 0},
                       "docs": {"type": "array", "items": {"type": "string"}}},
                    "required": ["name", "type", "chance", "low", "high", "docs"]}),
    "rank_issues": ("Free. Ranks your open notes (chance below 1) by the expected $M of decision regret removed per "
                    "page, from a pricing model built on your own notes; each issue's page cost is the next unread "
                    "document where analysts usually settle it (named as next_doc). Advice only.",
                    {**_OBJ, "properties": {}}),
    "submit": ("Free. Your final answer; ends the run. go = buy at the asking price; walk_away in $M.",
               {**_OBJ, "properties": {"go": {"type": "boolean"}, "walk_away": {"type": "number"},
                                       "reason": {"type": "string"}}, "required": ["go", "walk_away", "reason"]}),
}


def tool_names(router: bool) -> list[str]:
    return [t for t in TOOLS if router or t != "rank_issues"]


class ToolError(Exception):
    """A refused or invalid call: reported to the solver as a tool error, not a crash."""


class Session:
    def __init__(self, room: Path, budget: float, trace: Path, router: bool):
        self.room = DataRoom(room, budget)
        self.face = load_face(room)
        self.pages = {d["id"]: d["pages"] for d in json.loads((room / "index.json").read_text())["documents"]}
        self.trace, self.router = trace, router
        self.opened: set[str] = set()
        self.notes: dict[str, dict] = {}
        self.calls = 0
        self.submitted = False

    def call(self, name: str, args: dict) -> dict:
        """One tools/call: run it, log it, and wrap the result as MCP content."""
        self.calls += 1
        spent = self.room.spent
        try:
            if name not in tool_names(self.router):
                raise ToolError(f"unknown tool {name!r}")
            if self.submitted:
                raise ToolError("the run is over: you already submitted")
            if self.calls > MAX_CALLS and name != "submit":
                raise ToolError(f"tool-call limit ({MAX_CALLS}) reached: call submit now")
            result, error = getattr(self, "_" + name)(**args), None
        except (ToolError, BudgetExceeded, KeyError, TypeError, ValueError) as e:
            result, error = None, str(e).strip("'\"")
        except Exception as e:  # a malformed argument the specific handlers above don't catch (e.g. wrong type
            result, error = None, f"{type(e).__name__}: {e}"  # deep inside a handler): a tool error, not a crash
        row = {"i": self.calls, "tool": name, "args": args, "cost": self.room.spent - spent,
               "remaining": self.room.remaining, "refused": error is not None, "error": error}
        if name != "open_document" and error is None:
            row["result"] = result
        self._log(row)
        text = error if error is not None else (result if isinstance(result, str) else json.dumps(result))
        return {"content": [{"type": "text", "text": text}], "isError": error is not None}

    def _log(self, row: dict) -> None:
        with self.trace.open("a") as f:
            f.write(json.dumps(row) + "\n")

    def log_initialize(self) -> None:
        """One trace row for a session that started but whose model called no tool at all, so the pilot's "did the
        server run" check (a non-empty trace file) doesn't mistake "no tool calls" for "never started" (F7)."""
        self._log({"i": 0, "tool": "initialize", "args": {}, "cost": 0.0, "remaining": self.room.remaining,
                   "refused": False, "error": None})

    def _list_documents(self) -> list[dict]:
        return self.room.list_documents()

    def _search(self, query: str) -> list[str]:
        """Where words appear, not what the documents say: text costs pages, so a 1-unit search can't read an answer."""
        return list(dict.fromkeys(h["doc_id"] for h in self.room.search(str(query))))

    def _open_document(self, doc_id: str) -> str:
        # the router gate (pilot v2, docs/results/plan-4a-prompt-log.md): in the router system every read is made
        # with the router's advice in view, so reading needs something for the router to price
        if self.router and not any(n["chance"] < 1 for n in self.notes.values()):
            raise ToolError("record at least one open suspicion with note_issue (chance below 1) before opening a "
                            "document, so the router can price it")
        text = self.room.open_document(doc_id)
        self.opened.add(doc_id)
        return text + "\n\n---\nRouter ranking now: " + json.dumps(self._rank_issues()) if self.router else text

    def _amounts(self, adjustments: dict) -> dict[str, float]:
        out = {}
        for trap, v in adjustments.items():
            if trap not in TRAPS or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
                raise ToolError(f"bad adjustment {trap}={v!r}: use {', '.join(TRAPS)} with $M amounts >= 0")
            out[trap] = float(v)
        if "concentration" in out:  # the engine needs a haircut below 100% of revenue
            out["concentration"] = min(out["concentration"], HAIRCUT_CAP * self.face.teaser.revenue_ltm)
        return out

    def _evaluate(self, adjustments: dict) -> dict:
        p = params_for(self._amounts(adjustments), self.face)
        return {"walk_away": round(walk_away(self.face.deal, p), 2), "asking_price": round(self.face.deal.asking_price, 2),
                "go": is_go(self.face.deal, p)}

    def _note_issue(self, name: str, type: str, chance: float, low: float, high: float, docs: list) -> dict:
        if type not in TRAPS:
            raise ToolError(f"type must be one of {', '.join(TRAPS)}")
        if not (0 <= chance <= 1 and 0 <= low <= high and math.isfinite(high)) or not isinstance(docs, list):
            raise ToolError("need 0 <= chance <= 1, 0 <= low <= high and a list of document ids")
        self.notes[type] = {"name": str(name), "chance": float(chance), "low": float(low), "high": float(high),
                            "docs": [str(d) for d in docs]}
        out = {"noted": type, "notes": len(self.notes)}
        return {**out, "router": self._rank_issues()} if self.router else out

    def _rank_issues(self) -> dict:
        beliefs = {t: Issue(proposed=False) for t in TRAPS}  # un-noted types: nobody thought of them, so 0
        for t, n in self.notes.items():
            beliefs[t] = Issue(known=(n["low"], n["high"])) if n["chance"] >= 1 else Issue(
                p_real=n["chance"], hi=max(n["high"], typical_high(t, self.face.teaser)))
        open_ = [t for t, n in self.notes.items() if n["chance"] < 1]
        values = draw(beliefs, N_WORLDS, np.random.default_rng(0))
        w = walk_aways(self.face, values)
        ask = self.face.deal.asking_price
        go, median = decide(w, ask)
        nxt = {t: next_doc(t, self.pages, self.opened) for t in open_}
        costs = {t: max(1, self.pages[nxt[t]]) if nxt[t] else 1 for t in open_}
        scores = score_regret(values, w, ask, costs, open_) if open_ else {}
        ranking = [{"type": t, "name": self.notes[t]["name"], "regret_removed_per_page": round(s, 4),
                    "next_doc": nxt[t], "pages_to_check": costs[t], "size_high_used": round(beliefs[t].hi, 2)}
                   for t, s in sorted(scores.items(), key=lambda kv: -kv[1])]
        return {"ranking": ranking, "current_decision": {"go": go, "walk_away_median": round(median, 2)}}

    def _submit(self, go: bool, walk_away: float, reason: str) -> dict:
        if not isinstance(go, bool) or not isinstance(walk_away, (int, float)) or not math.isfinite(walk_away):
            raise ToolError("go must be true/false and walk_away a number")
        self.submitted = True
        return {"submitted": True}


def serve(session: Session, inp=sys.stdin, out=sys.stdout) -> None:
    """MCP's stdio transport: initialize, tools/list, tools/call, ping. Notifications get no reply."""
    for line in inp:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
            out.write(json.dumps(reply) + "\n")
            out.flush()
            continue
        if "id" not in msg:
            continue
        method, params = msg.get("method"), msg.get("params") or {}
        reply = {"jsonrpc": "2.0", "id": msg["id"]}
        try:
            if method == "initialize":
                reply["result"] = {"protocolVersion": params.get("protocolVersion", PROTOCOL),
                                   "capabilities": {"tools": {}}, "serverInfo": {"name": "room", "version": "1"}}
                session.log_initialize()
            elif method == "tools/list":
                reply["result"] = {"tools": [{"name": n, "description": TOOLS[n][0], "inputSchema": TOOLS[n][1]}
                                             for n in tool_names(session.router)]}
            elif method == "tools/call":
                reply["result"] = session.call(params.get("name", ""), params.get("arguments") or {})
            elif method == "ping":
                reply["result"] = {}
            else:
                reply["error"] = {"code": -32601, "message": f"method not found: {method}"}
        except Exception as e:  # a bug in a handler must not kill the loop: the pilot would misread this as a
            reply = {"jsonrpc": "2.0", "id": msg["id"],  # crashed run rather than one clean tool error (F2)
                     "error": {"code": -32603, "message": f"{type(e).__name__}: {e}"}}
        out.write(json.dumps(reply) + "\n")
        out.flush()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--room", type=Path, required=True)
    ap.add_argument("--budget", type=float, required=True)
    ap.add_argument("--trace", type=Path, required=True)
    ap.add_argument("--router", action="store_true", help="offer rank_issues (the S1b + router system)")
    args = ap.parse_args(argv)
    serve(Session(args.room, args.budget, args.trace, args.router))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
