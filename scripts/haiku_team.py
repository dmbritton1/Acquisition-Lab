"""The Haiku team's final analysis (spec docs/superpowers/specs/2026-10-10-haiku-team-design.md §5), run once on the
finished final test. Reads answer keys and runs; never calls a model. From the repository root:

  .venv/bin/python scripts/haiku_team.py --out docs/results/haiku-team.json"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from acqlab.bench import analysis, haiku
from acqlab.bench.referee import rows as trace_rows
from debate_pilot import versus
from upside_pilot import keys, load, stats

ROOT = Path(__file__).resolve().parents[1] / "data"
OPUS, OPUS_MODEL = ("s1b", "s4"), "claude-opus-5-5"
EPS = 1e-9


def systems() -> tuple[str, ...]:
    """The final test's systems: the Opus baselines, the two Haiku controls and the frozen winner (once)."""
    if haiku.FINAL is None:
        raise ValueError("no frozen winner: haiku.FINAL is set at the freeze")
    return tuple(dict.fromkeys((*OPUS, "haiku_solo", "haiku_team", haiku.FINAL)))


def pairs(winner: str) -> list[tuple[str, str]]:
    """Spec §5's comparisons, a − b; one that would compare a system with itself is left out."""
    return [(a, b) for a, b in ((winner, "s1b"), (winner, "s4"), (winner, "haiku_solo"), ("haiku_team", "s4"))
            if a != b]


def verdict(c: dict) -> str:
    """Spec §5's wording for winner − s1b."""
    if analysis.below(c):
        return "better"
    if analysis.above(c):
        return "worse"
    return f"no clear difference: at most {c['ci95'][1]:.4f} worse"


def check(by: dict[str, dict[str, dict]], ks: dict, name: str) -> None:
    """Refuse a final test that is not the pre-registered one: a system missing deals, a row on the wrong model (a
    timed-out row may show none), or a Haiku row made with prompts other than the frozen ones."""
    for s, rows in by.items():
        if set(rows) != set(ks):
            raise ValueError(f"{name}: {s} runs cover {sorted(set(rows) ^ set(ks))} differently from the test split")
    want = {s: [OPUS_MODEL] if s in OPUS else [haiku.MODEL] for s in by}
    wrong = [f"{name}/{s}/{d}" for s, rows in by.items() for d, r in rows.items() if r["models"] != want[s]
             and not (not r["models"] and (r["status"] == "timeout" or r["timeouts"] >= r["sessions"]))]
    if wrong:
        raise ValueError(f"rows on the wrong model: {wrong}")
    stale = [f"{name}/{s}/{d}" for s in by if s not in OPUS for d, r in by[s].items()
             if r.get("prompts") != haiku.prompt_sha(s)]
    if stale:
        raise ValueError(f"rows not made with the frozen prompts: {stale}")


def card(rows: list[dict], refused: list[int]) -> dict:
    if not rows:
        return {"n": 0}
    listed = [c for r in rows if (c := haiku.list_cost(r)) is not None]
    return stats(rows) | {"session_timeouts": sum(r["timeouts"] for r in rows),
                          "list_cost": sum(listed) / len(listed) if listed else None,  # the user's cost basis
                          "decoy_pages": float(np.mean([r["decoy_pages"] for r in rows])),
                          "over_budget": sum(r["spent"] > r["budget"] + EPS for r in rows if "spent" in r),
                          "refused_calls": int(sum(refused))}


def one_set(by: dict[str, dict[str, dict]], refused: dict[str, dict[str, int]], winner: str) -> dict:
    """Everything spec §5 reports for one deal set (by: system -> deal -> row)."""
    cmp = {f"{a}-{b}": versus(by[a], by[b]) for a, b in pairs(winner)}
    cost = {s: c for s in by if (c := card(list(by[s].values()), [0])["list_cost"])}  # list price, from tokens
    ids = sorted(next(iter(by.values())))
    cases = sorted({by["s1b"][d]["case_type"] for d in ids})
    return {
        "n": len(ids), "verdict": verdict(cmp[f"{winner}-s1b"]), "versus": cmp,
        "cost_ratio": {f"{o}/{h}": cost[o] / cost[h] if o in cost and h in cost else None
                       for o in OPUS for h in by if h not in OPUS},
        "systems": {s: {"all": card(list(rows.values()), list(refused[s].values())),
                        "by_case": {c: card([r for r in rows.values() if r["case_type"] == c],
                                            [refused[s][d] for d, r in rows.items() if r["case_type"] == c])
                                    for c in cases}}
                    for s, rows in by.items()},
    }


def analyse(root: Path) -> dict:
    names, winner = systems(), haiku.FINAL
    by, refused = {}, {}
    for name in haiku.TEST_SETS:
        ks = keys(root / name, "test")
        by[name] = {s: load(root / name, s) for s in names}
        check(by[name], ks, name)
        lost = [f"{name}/{s}/{d}" for s in names for d in ks
                if not (root / name / "runs" / s / f"{d}.trace.jsonl").exists()]
        if lost:
            raise ValueError(f"runs without a trace: {lost}")
        refused[name] = {s: {d: sum(bool(x.get("refused")) for x in trace_rows(root / name / "runs" / s /
                                                                                 f"{d}.trace.jsonl"))
                             for d in ks} for s in names}
    together = {s: {f"{n}/{d}": r for n in haiku.TEST_SETS for d, r in by[n][s].items()} for s in names}
    refused_all = {s: {f"{n}/{d}": c for n in haiku.TEST_SETS for d, c in refused[n][s].items()} for s in names}
    sets = {n: one_set(by[n], refused[n], winner) for n in haiku.TEST_SETS} | {
        "all": one_set(together, refused_all, winner)}
    verdicts = {n: sets[n]["verdict"] for n in sets}
    return {"winner": winner, "systems": list(names), "verdicts": verdicts,
            "sets_agree": len({sets[n]["verdict"].split(":")[0] for n in haiku.TEST_SETS}) == 1, "sets": sets}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=ROOT, help="the directory holding the two test sets")
    ap.add_argument("--out", type=Path, required=True, help="where the analysis goes (never overwritten)")
    args = ap.parse_args(argv)
    if args.out.exists():  # one-shot, like the earlier pilots: never overwrite a result already written
        print(f"Refusing: {args.out} already exists")
        return 1
    try:
        out = analyse(args.root)
    except ValueError as e:
        print(f"Refusing: {e}")
        return 1
    args.out.write_text(json.dumps(out, indent=2))
    print(json.dumps({"winner": out["winner"], "verdicts": out["verdicts"], "sets_agree": out["sets_agree"],
                      "cost_ratio": out["sets"]["all"]["cost_ratio"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
