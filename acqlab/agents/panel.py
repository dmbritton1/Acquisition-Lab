"""S4, the multi-agent panel (main spec §3; reframe design §5). Code holds the Deal Record and runs the loop; each
role turn is one sandboxed `claude -p` session on the tool server, and the role's closing tool call (propose,
report, challenge) is read back from the trace. The engine makes the go/no-go call.

The loop: the Deal Lead proposes issues; Investigators check them one at a time with intent briefs, their findings
going through the Committer; the Lead re-plans after each; the Challenger objects and the pair screen flags issues
that flip the call together; objections are investigated; a residual sweep reads what nobody opened. Build steps
(reframe design §5) are configs: STAGES."""
import json
import math
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import NamedTuple

from acqlab.agents import panel_prompts as prompts
from acqlab.agents.record import Record, load_face, next_doc, on_map
from acqlab.agents.server import ROLES
from acqlab.agents.solver import RunTimeout, run_session
from acqlab.generator.traps import TRAPS

SWEEP_SHARE = 0.10  # budget held back for the residual sweep (main spec §3)
SUB_SHARE = 0.5  # an Investigator's budget: its first document plus 2 units, and at least half the deal budget
MAX_TRIES = 2  # investigations per issue: once, and once more after an objection
CHALLENGE_ROUNDS = 2
SYSTEM = {"lead": prompts.LEAD, "investigator": prompts.INVESTIGATOR, "challenger": prompts.CHALLENGER}
USAGE = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")


class Config(NamedTuple):
    lead: bool = True  # False: build step 1, one Investigator reads for every issue type
    challenger: bool = True
    router: bool = True  # True: code picks by decision value per page (the Lead's order when nothing scores) and
    # the Lead's stop is ignored. False: the Lead's order; the first investigation always runs, and the Lead's stop
    # ends later rounds
    sweep: bool = True


STAGES = {"s4_1": Config(False, False, False, False), "s4_2": Config(True, False, False, False),
          "s4_3": Config(True, True, False, False), "s4": Config()}


class Panel:
    def __init__(self, room: Path, budget: float, trace: Path, cfg: Config, session: Callable):
        self.room, self.budget, self.trace, self.cfg, self.session = room, budget, trace, cfg, session
        index = json.loads((room / "index.json").read_text())
        self.teaser, self.docs = index["teaser"], index["documents"]
        self.pages = {d["id"]: d["pages"] for d in self.docs}
        self.record = Record(load_face(room))
        self.reserve = SWEEP_SHARE * budget if cfg.sweep else 0.0
        self.cli = {"usage": dict.fromkeys(USAGE, 0), "total_cost_usd": 0.0, "num_turns": 0, "duration_ms": 0,
                    "modelUsage": {}, "sessions": 0, "timeouts": 0, "env_keys": None}

    def rows(self) -> list[dict]:
        return [json.loads(x) for x in self.trace.read_text().splitlines()] if self.trace.exists() else []

    def spent(self) -> float:
        return sum(r["cost"] for r in self.rows())

    def read(self) -> set[str]:
        return {r["args"]["doc_id"] for r in self.rows() if r["tool"] == "open_document" and not r["refused"]}

    def avail(self) -> float:
        """Budget for directed reading: what is left, less the sweep's reserve."""
        return self.budget - self.spent() - self.reserve

    def turn(self, role: str, prompt: str, budget: float, extra: list[str] | None = None) -> dict | None:
        """One role session; its last accepted closing call (trace row), or None if it never made one."""
        n = len(self.rows())
        args = ["--role", role, "--paid", ",".join(sorted(self.read()))] + (extra or [])
        try:
            out = self.session(self.room, max(0.0, budget), self.trace, prompt, SYSTEM[role], ROLES[role], args)
        except RunTimeout:
            self.cli["timeouts"] += 1
            out = None
        self.cli["sessions"] += 1
        if out:
            for k in USAGE:
                self.cli["usage"][k] += int(out.get("usage", {}).get(k, 0))
            for k in ("total_cost_usd", "num_turns", "duration_ms"):
                self.cli[k] += out.get(k) or 0
            self.cli["modelUsage"] |= out.get("modelUsage", {})
            self.cli["env_keys"] = out.get("env_keys")
        done = [r for r in self.rows()[n:] if r["tool"] in ("propose", "report", "challenge") and not r["refused"]]
        return done[-1] if done else None

    def lead(self) -> bool:
        """The Deal Lead's (re-)plan; True if it says stop (or made no plan)."""
        row = self.turn("lead", prompts.lead_prompt(self.teaser, self.docs, self.record, self.read(),
                                                    self.budget - self.spent()), 0)
        if row is None:
            return True
        self.record.plan(row["args"]["issues"])
        return row["args"]["stop"]

    def candidates(self) -> list[str]:
        """Issues due an investigation: open ones not yet tried, and any with an unanswered objection."""
        return [t for t, e in self.record.entries.items() if e.tries < MAX_TRIES and (
            e.objections or (e.open and e.chance > 0 and e.tries == 0))]

    def where(self, t: str) -> list[str]:
        e = self.record.entries[t]
        return [d for d in dict.fromkeys(e.docs + [next_doc(t, self.pages, self.read())]) if d in self.pages]

    def first_cost(self, t: str) -> float:
        """Pages of the first unread document to check for issue t (1 if all are read: a search)."""
        read = self.read()
        return float(next((self.pages[d] for d in self.where(t) if d not in read), 1))

    def pick(self) -> str | None:
        cands = self.candidates()
        if not cands:
            return None
        if self.cfg.router:
            scores = self.record.rank(cands, {t: self.first_cost(t) for t in cands})
            best = max(cands, key=lambda t: (scores[t], -TRAPS.index(t)))
            if scores[best] > 0:
                return best
        # No router, or no single check can flip the call (dev-006: every issue at 35-50% over wide ranges). Unspent
        # budget earns nothing under the regret score, and issues that only matter together score 0 one at a time,
        # so keep reading in the Lead's order.
        order = self.record.priority
        return min(cands, key=lambda t: (order.index(t) if t in order else len(order), TRAPS.index(t)))

    def investigate(self, t: str) -> None:
        e = self.record.entries[t]
        where = self.where(t)
        sub = min(self.avail(), max(self.first_cost(t) + 2, math.ceil(SUB_SHARE * self.budget)))
        prompt = prompts.brief(self.teaser, self.docs, self.record, t, where, self.read(), sub)
        e.tries += 1
        e.objections = []  # answered by this investigation, whatever it finds
        if sub >= 1:
            row = self.turn("investigator", prompt, sub)
            self.record.apply(row["result"]["commits"] if row else [])

    def directed(self) -> None:
        while self.avail() >= 1 and (t := self.pick()) is not None:
            self.investigate(t)
            if self.lead() and not self.cfg.router:
                break

    def challenge(self) -> None:
        for _ in range(CHALLENGE_ROUNDS):
            pairs = self.record.flagged_pairs()
            row = self.turn("challenger", prompts.challenger_prompt(self.teaser, self.docs, self.record, pairs,
                                                                   self.read(), self.budget - self.spent()), 0,
                            ["--pairs", json.dumps(pairs)])
            if row is None:
                return
            objections = list(row["args"]["objections"])
            for p in row["args"]["pairs"]:
                if p["answer"] == "check":
                    for t, other in ((p["a"], p["b"]), (p["b"], p["a"])):
                        e = self.record.entries[t]
                        objections.append({"type": t, "kind": "pair", "chance": e.chance, "low": e.low,
                                           "high": e.high, "docs": [], "reason": f"with {other}, it could flip "
                                           "the call: " + p["reason"]})
            if not objections:
                return
            self.record.challenge(objections)
            self.directed()

    def sweep(self) -> None:
        """Undirected reads by coverage, of documents on the diligence map: untouched domains first, then the
        shortest."""
        left, read = self.budget - self.spent(), self.read()
        touched = {d["domain"] for d in self.docs if d["id"] in read}
        picked: list[str] = []
        for d in sorted((d for d in self.docs if d["id"] not in read and on_map(d["id"])),
                        key=lambda d: (d["domain"] in touched, d["pages"], d["id"])):
            if sum(self.pages[p] for p in picked) + d["pages"] <= left:
                picked.append(d["id"])
        if picked:
            row = self.turn("investigator", prompts.sweep_prompt(self.teaser, self.docs, picked, read, left), left)
            self.record.apply(row["result"]["commits"] if row else [])

    def run(self) -> dict:
        if not self.cfg.lead:
            row = self.turn("investigator", prompts.reader_prompt(self.teaser, self.docs, self.budget), self.budget)
            self.record.apply(row["result"]["commits"] if row else [])
        else:
            self.lead()
            self.directed()
            if self.cfg.challenger:
                self.challenge()
            if self.cfg.sweep:
                self.sweep()
        for e in self.record.entries.values():  # an objection nobody could afford to check changes nothing
            e.objections = []
        go, wa = self.record.decide()
        with self.trace.open("a") as f:
            f.write(json.dumps({"i": 0, "tool": "submit", "args": {"go": go, "walk_away": wa, "reason": "engine"},
                                "cost": 0.0, "remaining": self.budget - self.spent(), "refused": False,
                                "error": None, "result": {"submitted": True}}) + "\n")
        return self.cli


def solve(room: Path, budget: float, trace: Path, cfg: Config, *, claude: str | None = None,
          session: Callable | None = None) -> dict:
    """One S4 run; returns the sessions' summed CLI usage in the single-agent solver's shape. Raises LLMUnavailable
    (usage limit, auth) so the pilot stops and can resume; a timed-out session is skipped."""
    return Panel(room.resolve(), budget, trace.resolve(), cfg, session or partial(run_session, claude=claude)).run()
