"""The hidden-upside pilot (spec docs/superpowers/specs/2026-10-08-upside-pilot-design.md): the free checks before any
paid run (--check, §2.2) and the analysis of finished runs (§2.3–2.4). Reads answer keys and runs; never calls a model.
From the repository root:

  .venv/bin/python scripts/upside_pilot.py --data data/pilot-r2u --check
  .venv/bin/python scripts/upside_pilot.py --data data/pilot-r2u --out docs/results/upside-pilot.json"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from acqlab.bench import analysis, pilot
from acqlab.bench.referee import opened, rows as trace_rows
from acqlab.engine import is_go
from acqlab.generator.batch import AnswerKey
from acqlab.generator.roles import LOOK
from acqlab.generator.traps import params_for
from acqlab.generator.truth import PROFILES

SYSTEMS = ("s1b", "s4")
FLAGGED = ("relief", "confirmed")
GROUPS = (*FLAGGED, "ordinary")
MODEL = "claude-opus-5-5"


def keys(data: Path, split: str = "test") -> dict[str, AnswerKey]:
    deals = json.loads((data / "splits.json").read_text())[split]
    return {d: AnswerKey.model_validate_json((data / "truth" / f"{d}.json").read_text()) for d in deals}


def group(key: AnswerKey) -> str:
    return key.truth.case_type if key.truth.case_type in FLAGGED else "ordinary"


def at_half(key: AnswerKey) -> bool:
    """The "price the warning at half" rule's call: the flagged issue at half its bound, nothing else."""
    t = key.truth
    return is_go(t.deal, params_for({t.flag.trap: LOOK * t.flag.bound}, t.base)) if t.flag else t.face_go


def free_checks(ks: dict[str, AnswerKey]) -> dict:
    """Spec §2.2: the counts, the engine on the true amounts, and the two stand-in rules. ok only if every one holds."""
    quota = {c: round(s * len(ks)) for c, s in PROFILES["r2u"]["quota"].items()}
    want = quota | {"ordinary": len(ks) - sum(quota.values())}
    by = {g: [k for k in ks.values() if group(k) == g] for g in GROUPS}
    out = {"counts": {g: len(v) for g, v in by.items()},
           "engine_right": sum(is_go(k.truth.deal, k.truth.params()) == k.truth.go for k in ks.values()),
           "half_right": {g: sum(at_half(k) == k.truth.go for k in by[g]) for g in FLAGGED},
           "ignore_right": {g: sum(k.truth.face_go == k.truth.go for k in by[g]) for g in FLAGGED}}
    out["ok"] = (out["counts"] == want and out["engine_right"] == len(ks)
                 and out["half_right"] == {"relief": 0, "confirmed": want["confirmed"]}
                 and out["ignore_right"] == {"relief": want["relief"], "confirmed": 0})
    return out


def load(data: Path, system: str) -> dict[str, dict]:
    """deal -> row, first runs only (a repeat is <deal>.r<k>.json)."""
    return {p.stem: json.loads(p.read_text()) for p in sorted((data / "runs" / system).glob("*.json"))
            if "." not in p.stem}


def stats(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0}
    return {"n": len(rows), "regret": float(np.mean([r["regret"] for r in rows])),
            "correct": float(np.mean([r["correct"] for r in rows])),
            "false_go": sum(r["go"] and not r["correct"] for r in rows),
            "false_nogo": sum(not r["go"] and not r["correct"] for r in rows),
            "pages": float(np.mean([r["pages"] for r in rows])),
            "no_answer": sum(not r["answered"] for r in rows),  # scored at face value, which is GO on a flagged deal
            "timeouts": sum(r["status"] == "timeout" for r in rows),
            "cost": float(np.mean(c)) if (c := [r["cost_usd"] for r in rows if r["cost_usd"] is not None]) else None,
            "sessions": float(np.mean([r["sessions"] for r in rows]))}


def settling_doc(key: AnswerKey) -> str:
    """The flagged issue's settling document: the last of its evidence (as recon_pilot.reached)."""
    return next(e.docs[-1] for e in key.evidence if e.trap == key.truth.flag.trap)


def warning(system: str, trace: list[dict], trap: str) -> float | bool | None:
    """Spec §2.3 item 6. s4: the chance the Deal Lead's first propose gave the flagged type (0 if left out, None if it
    never proposed). s1b: whether it ever noted the flagged type."""
    ok = [r for r in trace if not r.get("refused")]
    if system == "s4":
        first = next((r for r in ok if r["tool"] == "propose"), None)
        return None if first is None else next((float(i["chance"]) for i in first["args"]["issues"]
                                                if i["type"] == trap), 0.0)
    return any(r["tool"] == "note_issue" and r["args"]["type"] == trap for r in ok)


def reading(s4: dict, s1b: dict) -> str:
    """Spec §2.4, on the relief deals."""
    if s4["false_nogo"] - s1b["false_nogo"] >= 3 and s4["regret"] > s1b["regret"]:
        return "team leans on caution"
    if s4["false_nogo"] <= s1b["false_nogo"]:
        return "team weighs evidence fine"
    return "unclear"


def analyse(data: Path, split: str = "test") -> dict:
    ks = keys(data, split)
    by = {s: load(data, s) for s in SYSTEMS}
    for s, rows in by.items():
        if set(rows) != set(ks):
            raise ValueError(f"{s} runs cover {sorted(set(rows) ^ set(ks))} differently from the {split} split")
    wrong = [f"{s}/{d}" for s, rows in by.items() for d, r in rows.items()
             if r["models"] != [MODEL] and not (r["status"] == "timeout" and not r["models"])]
    if wrong:  # spec §2.1: every row must show the pilot model; a timed-out run may show none
        raise ValueError(f"rows not run on {MODEL}: {wrong}")
    missing = {s: sorted(d for d in ks if not (data / "runs" / s / f"{d}.trace.jsonl").exists()) for s in SYSTEMS}
    traces = {s: {d: [] if d in missing[s] else trace_rows(data / "runs" / s / f"{d}.trace.jsonl") for d in ks}
              for s in SYSTEMS}
    ids = {g: sorted(d for d, k in ks.items() if group(k) == g) for g in GROUPS} | {"all": sorted(ks)}
    flagged = ids["relief"] + ids["confirmed"]
    systems = by | {"s1b_matched": pilot.s1b_matched(by["s1b"], by["s4"])}
    looked = {s: {d: settling_doc(ks[d]) in opened(traces[s][d]) for d in flagged} for s in SYSTEMS}
    warn = {s: {d: warning(s, traces[s][d], ks[d].truth.flag.trap) for d in flagged} for s in SYSTEMS}
    chances = [x for x in warn["s4"].values() if x is not None]
    out = {
        "deals": len(ks), "missing_traces": missing,
        "reading_provisional": any(not by[s][d]["answered"] for s in SYSTEMS for d in ids["relief"]),
        "settling_docs": {d: settling_doc(ks[d]) for d in flagged},
        "systems": {s: {g: stats([rows[d] for d in v]) for g, v in ids.items()} for s, rows in systems.items()},
        "by_case": {s: {c: stats([r for r in rows.values() if r["case_type"] == c]) for c in analysis.CASES}
                    for s, rows in by.items()},
        "relief_s4_minus_s1b": analysis.compare(by["s4"], by["s1b"], deals=ids["relief"]),
        "looked": {s: {g: float(np.mean([looked[s][d] for d in ids[g]])) if ids[g] else None for g in FLAGGED}
                   for s in SYSTEMS},
        "relief_misses": {s: {"never_looked": sum(not by[s][d]["correct"] and not looked[s][d] for d in ids["relief"]),
                              "looked_not_believed": sum(not by[s][d]["correct"] and looked[s][d]
                                                         for d in ids["relief"])} for s in SYSTEMS},
        "warning": {"s4_opening_chance": warn["s4"], "s4_median": float(np.median(chances)) if chances else None,
                    "s1b_noted": warn["s1b"],
                    "s1b_share": float(np.mean(list(warn["s1b"].values()))) if flagged else None},
    }
    rel = out["systems"]
    out["reading"] = reading(rel["s4"]["relief"], rel["s1b"]["relief"]) if ids["relief"] else None
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--split", default="test")
    ap.add_argument("--check", action="store_true", help="the free checks before any paid run (spec §2.2)")
    ap.add_argument("--out", type=Path, help="where the analysis goes (never overwritten)")
    args = ap.parse_args(argv)
    if args.check:
        out = free_checks(keys(args.data, args.split))
        print(json.dumps(out, indent=2))
        return 0 if out["ok"] else 1
    if args.out is None:
        ap.error("--out is required without --check")
    if args.out.exists():  # one-shot, like the recon pilot: never overwrite a result already written
        print(f"Refusing: {args.out} already exists")
        return 1
    try:
        out = analyse(args.data, args.split)
    except ValueError as e:
        print(f"Refusing: {e}")
        return 1
    args.out.write_text(json.dumps(out, indent=2))
    print(json.dumps({"reading": out["reading"], "reading_provisional": out["reading_provisional"],
                      "relief": {s: out["systems"][s]["relief"] for s in SYSTEMS}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
