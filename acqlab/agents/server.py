"""Tool server for one solver run (Plan 4a design §2): the data room, search, the engine, issue notes and, for the
router system, router 6. With --role it serves one S4 panel role instead (Plan 5): the Deal Lead proposes, an
Investigator reads and reports through the Committer, the Challenger objects. Search came back in Plan 4b, once a
real problem and a clean fact share every reveal word (validate.word_leaks is empty); it returns document ids, never
text. Speaks MCP over stdio (one JSON-RPC message per
line) with the standard library only. It reads only
its room folder, never an answer key, and writes every call to a trace file (one JSON object per line).

  python -m acqlab.agents.server --room <room> --budget 22 --trace <file.jsonl> [--router]
  python -m acqlab.agents.server --room <room> --budget 9 --trace <file.jsonl> --role investigator --paid qoe,cim
"""
import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

from acqlab.agents.committer import check
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
_TYPE = {"type": "string", "enum": list(TRAPS)}
_DOCS = {"type": "array", "items": {"type": "string"}}
_QUOTES = {"type": "array", "items": {**_OBJ, "properties": {"doc_id": {"type": "string"}, "text": {"type": "string"}},
                                      "required": ["doc_id", "text"]}}
_ISSUE = {**_OBJ, "properties": {"type": _TYPE, "name": {"type": "string"},
                                 "chance": {"type": "number", "minimum": 0, "maximum": 1},
                                 "low": {"type": "number", "minimum": 0}, "high": {"type": "number", "minimum": 0},
                                 "docs": _DOCS}, "required": ["type", "name", "chance", "low", "high", "docs"]}
PANEL_TOOLS = {
    "propose": ("Free. Your issue list, most important first; ends your turn. One entry per issue type: the chance "
                "it is real (0 to 1), its size range in $M if real, and the documents that would settle it. Set "
                "stop to true when nothing left is worth reading.",
                {**_OBJ, "properties": {"issues": {"type": "array", "items": _ISSUE}, "stop": {"type": "boolean"},
                                        "reason": {"type": "string"}}, "required": ["issues", "stop", "reason"]}),
    "report": ("Free. Your findings; ends your turn once every finding passes the Committer's checks (a refused "
               "report says why; fix it and call report again). One finding per issue type. status: value (an "
               "amount: quote the sentence or table row stating it; if it must be calculated from two or more "
               "quoted numbers, give op and the two inputs and code does the arithmetic), range (low and high, each "
               "0 or a number in your quotes), not_found (docs: what you read that doesn't settle it), or open "
               "(chance, low, high: a belief without evidence). Quotes must be copied word for word from documents "
               "you have read.",
               {**_OBJ, "properties": {"findings": {"type": "array", "items": {**_OBJ, "properties": {
                   "type": _TYPE, "status": {"type": "string", "enum": ["value", "range", "not_found", "open"]},
                   "value": {"type": "number", "minimum": 0},
                   "op": {"type": "string", "enum": ["none", "difference", "product", "divide"]},
                   "inputs": {"type": "array", "items": {"type": "number"}},
                   "low": {"type": "number", "minimum": 0}, "high": {"type": "number", "minimum": 0},
                   "chance": {"type": "number", "minimum": 0, "maximum": 1},
                   "quotes": _QUOTES, "docs": _DOCS}, "required": ["type", "status"]}}}, "required": ["findings"]}),
    "challenge": ("Free. Your objections; ends your turn. kind: bigger (it could be larger than the record says), "
                  "elsewhere (the evidence could be in another document) or evidence (a committed value's quote "
                  "may not show what it claims). Each gives the chance you'd put on it, a size range in $M and the "
                  "documents to check. Answer every flagged pair: check (investigate both) or ruled_out (say why).",
                  {**_OBJ, "properties": {
                      "objections": {"type": "array", "items": {**_OBJ, "properties": {
                          "type": _TYPE, "kind": {"type": "string", "enum": ["bigger", "elsewhere", "evidence"]},
                          "chance": {"type": "number", "minimum": 0, "maximum": 1},
                          "low": {"type": "number", "minimum": 0}, "high": {"type": "number", "minimum": 0},
                          "docs": _DOCS, "reason": {"type": "string"}},
                          "required": ["type", "kind", "chance", "low", "high", "docs", "reason"]}},
                      "pairs": {"type": "array", "items": {**_OBJ, "properties": {
                          "a": _TYPE, "b": _TYPE, "answer": {"type": "string", "enum": ["check", "ruled_out"]},
                          "reason": {"type": "string"}}, "required": ["a", "b", "answer", "reason"]}}},
                   "required": ["objections", "pairs"]}),
}
ROLES = {"lead": ["propose"], "investigator": ["list_documents", "search", "open_document", "report"],
         "challenger": ["evaluate", "challenge"]}
ENDS_TURN = {"submit", "propose", "report", "challenge"}


def tool_names(router: bool, role: str | None = None) -> list[str]:
    return ROLES[role] if role else [t for t in TOOLS if router or t != "rank_issues"]


def tool_spec(name: str) -> tuple[str, dict]:
    return TOOLS.get(name) or PANEL_TOOLS[name]


class ToolError(Exception):
    """A refused or invalid call: reported to the solver as a tool error, not a crash."""


class Session:
    def __init__(self, room: Path, budget: float, trace: Path, router: bool, role: str | None = None,
                 paid: tuple[str, ...] = (), pairs: tuple[tuple[str, str], ...] = ()):
        self.room = DataRoom(room, budget)
        self.face = load_face(room)
        self.pages = {d["id"]: d["pages"] for d in json.loads((room / "index.json").read_text())["documents"]}
        self.trace, self.router, self.role = trace, router, role
        self.paid = set(paid) & set(self.pages)  # read earlier in this panel run: free to read again
        self.pairs = [tuple(p) for p in pairs]  # the pair screen's flagged pairs, which the Challenger must answer
        self.opened: set[str] = set()
        self.notes: dict[str, dict] = {}
        self.calls = 0
        self.submitted = False

    def call(self, name: str, args: dict) -> dict:
        """One tools/call: run it, log it, and wrap the result as MCP content."""
        self.calls += 1
        spent = self.room.spent
        try:
            if name not in tool_names(self.router, self.role):
                raise ToolError(f"unknown tool {name!r}")
            if self.submitted:
                raise ToolError("the run is over: you already submitted")
            closing = ROLES[self.role][-1] if self.role else "submit"
            if self.calls > MAX_CALLS and name != closing:
                raise ToolError(f"tool-call limit ({MAX_CALLS}) reached: call {closing} now")
            result, error = getattr(self, "_" + name)(**args), None
            self.submitted = name in ENDS_TURN
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
        if doc_id in self.paid:  # already paid for in this panel run
            text = self.room._text(doc_id)
        else:
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
        return {"submitted": True}

    def _propose(self, issues: list, stop: bool, reason: str) -> dict:
        if not isinstance(issues, list) or not isinstance(stop, bool):
            raise ToolError("issues must be a list and stop true/false")
        types = [i.get("type") if isinstance(i, dict) else None for i in issues]
        if len(set(types)) != len(types):
            raise ToolError("one entry per issue type")
        for i in issues:
            ok = (isinstance(i, dict) and i.get("type") in TRAPS and isinstance(i.get("name"), str)
                  and isinstance(i.get("docs"), list) and all(isinstance(d, str) for d in i.get("docs", []))
                  and all(isinstance(i.get(k), (int, float)) and math.isfinite(i[k])
                          for k in ("chance", "low", "high")))
            if not ok or not (0 <= i["chance"] <= 1 and 0 <= i["low"] <= i["high"]):
                raise ToolError(f"bad issue {i!r}: need a type from {', '.join(TRAPS)}, a string name, "
                                "0 <= chance <= 1, 0 <= low <= high and a list of document ids (strings)")
        return {"planned": len(issues)}

    def _report(self, findings: list) -> dict:
        if not isinstance(findings, list):
            raise ToolError("findings must be a list")
        types = [f.get("type") if isinstance(f, dict) else None for f in findings]
        if len(set(types)) != len(types):
            raise ToolError("one finding per issue type")
        texts = {d: self.room._text(d) for d in self.opened | self.paid}
        commits, errors = [], []
        for f in findings:
            commit, errs = check(f, texts) if isinstance(f, dict) else (None, [f"bad finding {f!r}"])
            commits.append(commit)
            errors += errs
        if errors:
            raise ToolError("Committer refused the report (nothing was committed):\n- " + "\n- ".join(errors))
        return {"commits": commits}

    def _challenge(self, objections: list, pairs: list) -> dict:
        if not isinstance(objections, list) or not isinstance(pairs, list):
            raise ToolError("objections and pairs must be lists")
        for o in objections:
            ok = (isinstance(o, dict) and o.get("type") in TRAPS and o.get("kind") in ("bigger", "elsewhere",
                  "evidence") and isinstance(o.get("reason"), str) and isinstance(o.get("docs"), list)
                  and all(isinstance(d, str) for d in o.get("docs", []))
                  and all(isinstance(o.get(k), (int, float)) and math.isfinite(o[k])
                          for k in ("chance", "low", "high")))
            if not ok or not (0 <= o["chance"] <= 1 and 0 <= o["low"] <= o["high"]):
                raise ToolError(f"bad objection {o!r}: need a type from {', '.join(TRAPS)}, a kind of "
                                "bigger/elsewhere/evidence, a string reason, a list of document ids (strings), "
                                "0 <= chance <= 1 and 0 <= low <= high")
        for p in pairs:
            ok = (isinstance(p, dict) and p.get("a") in TRAPS and p.get("b") in TRAPS and p.get("a") != p.get("b")
                  and p.get("answer") in ("check", "ruled_out") and isinstance(p.get("reason"), str))
            if not ok:
                raise ToolError(f"bad pair {p!r}: need a and b each from {', '.join(TRAPS)} and different, "
                                "answer check or ruled_out, and a string reason")
        answered = {frozenset((p["a"], p["b"])) for p in pairs}
        missing = [f"{a}+{b}" for a, b in self.pairs if frozenset((a, b)) not in answered]
        if missing:
            raise ToolError(f"answer every flagged pair (check or ruled_out): {', '.join(missing)}")
        return {"objections": len(objections), "checks": sum(p["answer"] == "check" for p in pairs)}


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
                reply["result"] = {"tools": [{"name": n, "description": tool_spec(n)[0], "inputSchema": tool_spec(n)[1]}
                                             for n in tool_names(session.router, session.role)]}
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
    ap.add_argument("--role", choices=list(ROLES), help="serve one S4 panel role instead")
    ap.add_argument("--paid", default="", help="comma-separated documents already paid for in this panel run")
    ap.add_argument("--pairs", default="[]", help="JSON list of [a, b] pairs the Challenger must answer")
    args = ap.parse_args(argv)
    serve(Session(args.room, args.budget, args.trace, args.router, args.role,
                  tuple(d for d in args.paid.split(",") if d), tuple(map(tuple, json.loads(args.pairs)))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
