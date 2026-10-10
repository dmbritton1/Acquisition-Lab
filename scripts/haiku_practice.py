"""The Haiku team's practice scorecard (spec docs/superpowers/specs/2026-10-10-haiku-team-design.md §3): each system's
runs on the 90 practice deals, by practice set and by deal type, and the rule for keeping a tuning change. Reads
answer keys and runs; writes nothing and never calls a model, so it can run as often as needed. From the repository
root:

  .venv/bin/python scripts/haiku_practice.py --systems s1b,s4,haiku_solo,haiku_team,haiku_lean
  .venv/bin/python scripts/haiku_practice.py --keep haiku_lean2 --over haiku_lean"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from acqlab.bench import analysis, haiku
from upside_pilot import load, stats

ROOT = Path(__file__).resolve().parents[1] / "data"
EPS = 1e-9


def card(rows: list[dict]) -> dict:
    """upside_pilot.stats plus the health counts: deals over budget (Haiku rows record spent) and the models seen."""
    if not rows:
        return {"n": 0}
    return stats(rows) | {"session_timeouts": sum(r["timeouts"] for r in rows),
                          "total_cost": float(sum(r["cost_usd"] or 0 for r in rows)),
                          "over_budget": sum(r["spent"] > r["budget"] + EPS for r in rows if "spent" in r),
                          "models": sorted({m for r in rows for m in r["models"]})}


def scorecard(root: Path, systems: list[str]) -> dict:
    """system -> its card over all practice deals, per practice set and per deal type, and its missing runs."""
    deals = {s: json.loads((root / s / "splits.json").read_text())["dev"] for s in haiku.PRACTICE}
    out = {}
    for name in systems:
        by = {s: {d: r for d, r in load(root / s, name).items() if d in deals[s]} for s in haiku.PRACTICE}
        rows = [r for s in haiku.PRACTICE for r in by[s].values()]
        out[name] = {"all": card(rows), "missing": sum(len(deals[s]) - len(by[s]) for s in haiku.PRACTICE),
                     "sets": {s: card(list(by[s].values())) for s in haiku.PRACTICE},
                     "by_case": {c: card([r for r in rows if r["case_type"] == c]) for c in analysis.CASES}}
    return out


def keeps(new: dict, old: dict) -> bool:
    """Spec §3 step 4 on two scorecard entries, both complete: lower mean practice regret, and no more relief false
    NO-GOs or confirmed false GOs."""
    def n(entry, case, field):
        return entry["by_case"][case].get(field, 0)

    return (new["missing"] == old["missing"] == 0 and new["all"]["regret"] < old["all"]["regret"]
            and n(new, "relief", "false_nogo") <= n(old, "relief", "false_nogo")
            and n(new, "confirmed", "false_go") <= n(old, "confirmed", "false_go"))


def table(card_by: dict) -> str:
    head = f"{'system':14s} {'set':13s} {'n':>3s} {'regret':>7s} {'right':>6s} {'fGO':>4s} {'fNOGO':>5s} " \
           f"{'$/deal':>7s} {'pages':>6s} {'sess':>5s} {'noans':>5s} {'t/o':>4s} {'over':>4s} {'st/o':>4s} {'$total':>7s}"
    lines = [head]
    for name, e in card_by.items():
        for label, c in [("all", e["all"]), *e["sets"].items(), *[(f"case:{k}", v) for k, v in e["by_case"].items()]]:
            if not c["n"]:
                continue
            cost = f"{c['cost']:.4f}" if c["cost"] is not None else "-"
            lines.append(f"{name:14s} {label:13s} {c['n']:3d} {c['regret']:7.4f} {c['correct']:6.1%} "
                         f"{c['false_go']:4d} {c['false_nogo']:5d} {cost:>7s} {c['pages']:6.1f} "
                         f"{c['sessions']:5.1f} {c['no_answer']:5d} {c['timeouts']:4d} {c['over_budget']:4d} "
                         f"{c['session_timeouts']:4d} {c['total_cost']:7.3f}")
        lines.append(f"{name:14s} missing runs: {e['missing']}; models: {e['all'].get('models', [])}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=ROOT, help="the directory holding the practice sets")
    ap.add_argument("--systems", default="s1b,s4,haiku_solo,haiku_team,haiku_lean")
    ap.add_argument("--keep", help="a tuning change's system: is it kept over --over? (spec §3 step 4)")
    ap.add_argument("--over", help="the current best system")
    args = ap.parse_args(argv)
    if args.keep:
        if not args.over:
            ap.error("--keep needs --over")
        cards = scorecard(args.root, [args.keep, args.over])
        print(table(cards))
        print(f"keep {args.keep} over {args.over}: {keeps(cards[args.keep], cards[args.over])}")
        return 0
    print(table(scorecard(args.root, [s for s in args.systems.split(",") if s])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
