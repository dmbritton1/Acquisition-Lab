"""The mixed-model practice scorecard (spec docs/superpowers/specs/2026-10-11-mixed-models-design.md §2): every
system and every cascade on the 90 practice deals, by regret and cost, and the frontier the freeze takes. Reads answer
keys and runs; writes nothing and never calls a model. From the repository root:

  .venv/bin/python scripts/mix_practice.py
  .venv/bin/python scripts/mix_practice.py --keep mix_h_sonnet3b --over mix_h_sonnet3   # a tuning round's verdict"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from acqlab.bench import haiku, mix
from upside_pilot import load

ROOT = Path(__file__).resolve().parents[1] / "data"
BASELINES = ("s1b", "s4")
CHEAP = ("mix_haiku_solo", "mix_h_haiku3", "mix_h_sonnet3", "mix_h_opus1", "mix_sonnet_solo")
STRONG = ("s1b", "s4", "mix_opus_low", "mix_sonnet_solo")


def rows(root: Path, name: str) -> dict[str, dict]:
    """'<set>/<deal>' -> row over the practice sets' dev deals; a candidate the Haiku track already ran is read from
    its Haiku-track name (mix.ALIASES)."""
    out = {}
    for s in haiku.PRACTICE:
        deals = set(json.loads((root / s / "splits.json").read_text())["dev"])
        got = load(root / s, name) or load(root / s, mix.ALIASES.get(name, name))
        out |= {f"{s}/{d}": r for d, r in got.items() if d in deals}
    return out


def teasers(root: Path) -> dict[str, str]:
    return {f"{s}/{d}": json.loads((root / s / "deals" / d / "room" / "index.json").read_text())["teaser"]
            for s in haiku.PRACTICE for d in json.loads((root / s / "splits.json").read_text())["dev"]}


def plain(rs: dict[str, dict]) -> dict[str, dict]:
    return {k: {"go": r["go"], "correct": r["correct"], "regret": r["regret"], "case_type": r["case_type"],
                "cost": mix.row_cost(r) or 0.0, "escalated": False} for k, r in rs.items()}


def summary(results: dict[str, dict], total: int) -> dict:
    v = list(results.values())
    if not v:
        return {"n": 0}
    return {"n": len(v), "partial": len(v) < total, "regret": float(np.mean([x["regret"] for x in v])),
            "correct": float(np.mean([x["correct"] for x in v])),
            "false_go": sum(x["go"] and not x["correct"] for x in v),
            "false_nogo": sum(not x["go"] and not x["correct"] for x in v),
            "relief_false_nogo": sum(not x["go"] and not x["correct"] for x in v if x["case_type"] == "relief"),
            "confirmed_false_go": sum(x["go"] and not x["correct"] for x in v if x["case_type"] == "confirmed"),
            "cost": float(np.mean([x["cost"] for x in v])), "escalated": float(np.mean([x["escalated"] for x in v]))}


def scorecard(root: Path) -> dict[str, dict]:
    """name -> summary for the baselines, every candidate and every cascade with both parts run."""
    tz = teasers(root)
    runs = {n: rows(root, n) for n in (*BASELINES, *mix.CANDIDATES)}
    out = {n: summary(plain(r), len(tz)) for n, r in runs.items() if r}
    for c in CHEAP:
        for s in STRONG:
            if c == s or not runs[c] or not runs[s]:
                continue
            for sig in mix.SIGNALS:
                both = sorted(set(runs[c]) & set(runs[s]))  # s4 has no practice-r2u runs: those cascades are partial
                out[f"cascade:{c}>{s}@{sig}"] = summary({k: mix.cascade(runs[c][k], runs[s][k], sig, tz[k])
                                                         for k in both}, len(tz))
    return out


def picks(card: dict[str, dict]) -> list[str]:
    """Spec §1's frontier rule over the candidates and cascades scored on every practice deal (not the baselines, and
    not a partial cascade, which would be compared on easier, fewer deals)."""
    points = {n: (c["regret"], c["cost"]) for n, c in card.items()
              if n not in BASELINES and c["n"] and not c["partial"]}
    return mix.frontier(points, card["s1b"]["cost"], card["s4"]["cost"])


def table(card: dict[str, dict], chosen: list[str]) -> str:
    lines = [f"{'system':58s} {'n':>3s} {'regret':>7s} {'right':>6s} {'fGO':>4s} {'fNOGO':>5s} {'$/deal':>7s} "
             f"{'up':>5s}"]
    for n, c in sorted(card.items(), key=lambda kv: (kv[1].get("cost", 0), kv[0])):
        if not c["n"]:
            continue
        mark = (" *" if n in chosen else "") + (" (partial)" if c["partial"] else "")
        lines.append(f"{n:58s} {c['n']:3d} {c['regret']:7.4f} {c['correct']:6.1%} {c['false_go']:4d} "
                     f"{c['false_nogo']:5d} {c['cost']:7.4f} {c['escalated']:5.0%}{mark}")
    lines.append(f"frontier picks (*): {chosen}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=ROOT, help="the directory holding the practice sets")
    ap.add_argument("--keep", help="a tuning change's system: is it kept over --over? (the Haiku track's keep rule)")
    ap.add_argument("--over", help="the current best system")
    args = ap.parse_args(argv)
    if args.keep:
        if not args.over:
            ap.error("--keep needs --over")
        from haiku_practice import keeps, scorecard as haiku_scorecard
        cards = haiku_scorecard(args.root, [args.keep, args.over])
        print(f"keep {args.keep} over {args.over}: {keeps(cards[args.keep], cards[args.over])}")
        return 0
    card = scorecard(args.root)
    print(table(card, picks(card)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
