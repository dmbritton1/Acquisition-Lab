"""The debate pilot's analysis (spec docs/superpowers/specs/2026-10-09-debate-pilot-design.md §3), run once on the
finished runs. Reads answer keys and runs; never calls a model. From the repository root:

  .venv/bin/python scripts/debate_pilot.py --data data/pilot-r2u --out docs/results/debate-pilot.json"""
import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from acqlab.bench import analysis, debate
from acqlab.bench.referee import opened, rows as trace_rows
from upside_pilot import GROUPS, MODEL, group, keys, load, settling_doc, stats

DEBATES = debate.SYSTEMS
SYSTEMS = ("s1b", "s4", *DEBATES)
LIMIT = {"debate_x": 1 + debate.BULL_SHARE, "debate_s": 1.0}  # spec §3: most pages, as a share of the budget
EPS = 1e-9


def mechanics(rows: list[dict], limit: float) -> dict:
    """Spec §3: the referee answers at least 95% of deals (38 of 40), and no deal reads past its limit."""
    m = {"n": len(rows), "answered": sum(r["answered"] for r in rows),
         "over_limit": sum(r["spent"] > limit * r["budget"] + EPS for r in rows)}
    return m | {"passes": m["answered"] >= math.ceil(0.95 * m["n"]) and m["over_limit"] == 0}


def meets(name: str, regret: dict, confirmed_false_go: dict, mech: dict) -> bool:
    """Spec §3's three conditions for one debate system."""
    return (regret[name] < regret["s1b"] and confirmed_false_go[name] <= confirmed_false_go["s1b"] + 1
            and mech[name]["passes"])


def reading(regret: dict, confirmed_false_go: dict, mech: dict) -> str:
    if meets("debate_s", regret, confirmed_false_go, mech):
        return "debate helps at the same budget"
    if meets("debate_x", regret, confirmed_false_go, mech):
        return "debate helps only with extra pages"
    return "debate doesn't help"


def versus(a: dict, b: dict) -> dict:
    """a − b in regret, paired: the bootstrap range and deals won, lost and tied."""
    d = [a[x]["regret"] - b[x]["regret"] for x in sorted(set(a) & set(b))]
    return analysis.compare(a, b) | {"won": sum(x < -EPS for x in d), "lost": sum(x > EPS for x in d),
                                     "tied": sum(abs(x) <= EPS for x in d)}


def overturned(rows: dict[str, dict], groups: dict[str, str]) -> dict:
    """Spec §3 item 4: deals where the referee's call differs from the reader's, four ways, overall and by group.
    A deal whose reader gave no call has nothing to overturn, and one whose referee gave no call has no call to
    compare (pilot.score scores it at face value, so it is not a call); those are counted apart."""
    kinds = [f"{a}_to_{b}_{c}" for a, b in (("nogo", "go"), ("go", "nogo")) for c in ("right", "wrong")]
    out = {g: dict.fromkeys(kinds, 0) for g in ("all", *GROUPS)}
    none = no_ref = 0
    for deal, r in rows.items():
        before = r["calls"]["reader"]
        if before is None:
            none += 1
            continue
        if r["calls"]["referee"] is None:
            no_ref += 1
            continue
        if before["go"] != r["go"]:
            k = f"{'go' if before['go'] else 'nogo'}_to_{'go' if r['go'] else 'nogo'}_" \
                f"{'right' if r['correct'] else 'wrong'}"
            out["all"][k] += 1
            out[groups[deal]][k] += 1
    return out | {"no_reader_call": none, "no_referee_call": no_ref}


def by_step(rows: dict[str, dict], traces: dict[str, list[dict]]) -> dict:
    """Each step's mean cost and pages per deal (a timed-out step's cost is unknown and left out), and spec §3 item 8's
    counts: deals where the step gave no call (no_call) and deals with no CLI result for it (timeouts)."""
    out = {}
    for s in ("reader", "bull", "bear", "referee"):
        costs = [r["step_cost"][s] for r in rows.values() if r["step_cost"][s] is not None]
        out[s] = {"cost": float(np.mean(costs)) if costs else None,
                  "pages": float(np.mean([sum(x["cost"] for x in traces[d] if x.get("step") == s
                                              and x["tool"] == "open_document" and not x.get("refused"))
                                          for d in rows])),
                  "no_call": sum(r["calls"][s] is None for r in rows.values()),
                  "timeouts": sum(r["step_cost"][s] is None for r in rows.values())}
    return out


def bull_found(traces: dict[str, list[dict]], settling: dict[str, str], relief: list[str]) -> int:
    """Spec §3 item 5: relief deals where the bull opened the settling document and the reader had not."""
    def did(d, s):
        return settling[d] in opened([x for x in traces[d] if x.get("step") == s])
    return sum(did(d, "bull") and not did(d, "reader") for d in relief)


def check(by: dict[str, dict[str, dict]], ks: dict, split: str) -> None:
    """Refuse a pilot that is not the one pre-registered: a system missing deals, a row on another model, or a
    debate row made with prompts other than the frozen ones."""
    for s, rows in by.items():
        if set(rows) != set(ks):
            raise ValueError(f"{s} runs cover {sorted(set(rows) ^ set(ks))} differently from the {split} split")
    wrong = [f"{s}/{d}" for s, rows in by.items() for d, r in rows.items() if r["models"] != [MODEL]
             and not (not r["models"] and (r["status"] == "timeout" or r["timeouts"] >= r["sessions"]))]
    if wrong:
        raise ValueError(f"rows not run on {MODEL}: {wrong}")
    stale = [f"{s}/{d}" for s in DEBATES for d, r in by[s].items() if r.get("prompts") != debate.PROMPT_SHA]
    if stale:
        raise ValueError(f"rows not made with the frozen prompts: {stale}")


def analyse(data: Path, split: str = "test") -> dict:
    ks = keys(data, split)
    by = {s: load(data, s) for s in SYSTEMS}
    check(by, ks, split)
    missing = {s: sorted(d for d in ks if not (data / "runs" / s / f"{d}.trace.jsonl").exists()) for s in DEBATES}
    traces = {s: {d: [] if d in missing[s] else trace_rows(data / "runs" / s / f"{d}.trace.jsonl") for d in ks}
              for s in DEBATES}
    groups = {d: group(k) for d, k in ks.items()}
    ids = {g: sorted(d for d in ks if groups[d] == g) for g in GROUPS} | {"all": sorted(ks)}
    settling = {d: settling_doc(ks[d]) for d in ids["relief"]}

    def st(rows):
        out = stats(rows)
        return out | {"decoy_pages": float(np.mean([r["decoy_pages"] for r in rows]))} if rows else out

    systems = {s: {g: st([rows[d] for d in v]) for g, v in ids.items()} for s, rows in by.items()}
    mech = {s: mechanics(list(by[s].values()), LIMIT[s]) for s in DEBATES}
    regret = {s: systems[s]["all"]["regret"] for s in SYSTEMS}
    false_go = {s: systems[s]["confirmed"].get("false_go", 0) for s in SYSTEMS}
    return {
        "deals": len(ks), "reading": reading(regret, false_go, mech), "mechanics": mech, "missing_traces": missing,
        "systems": systems,
        "versus": {s: {b: versus(by[s], by[b]) for b in ("s1b", "s4")} for s in DEBATES},
        "x_minus_s": versus(by["debate_x"], by["debate_s"]),
        "overturned": {s: overturned(by[s], groups) for s in DEBATES},
        "bull_found": {s: bull_found(traces[s], settling, ids["relief"]) for s in DEBATES},
        "steps": {s: by_step(by[s], traces[s]) for s in DEBATES},
        "step_timeouts": {s: sum(r["timeouts"] for r in by[s].values()) for s in DEBATES},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--split", default="test")
    ap.add_argument("--out", type=Path, required=True, help="where the analysis goes (never overwritten)")
    args = ap.parse_args(argv)
    if args.out.exists():  # one-shot, like the earlier pilots: never overwrite a result already written
        print(f"Refusing: {args.out} already exists")
        return 1
    try:
        out = analyse(args.data, args.split)
    except ValueError as e:
        print(f"Refusing: {e}")
        return 1
    args.out.write_text(json.dumps(out, indent=2))
    print(json.dumps({"reading": out["reading"], "mechanics": out["mechanics"],
                      "regret": {s: out["systems"][s]["all"]["regret"] for s in SYSTEMS}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
