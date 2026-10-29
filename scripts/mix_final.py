"""The mixed-model final analysis (spec docs/superpowers/specs/2026-10-11-mixed-models-design.md §1), run once on the
finished final test over the fresh deals. Reads answer keys and runs; never calls a model. From the repository root:

  .venv/bin/python scripts/mix_final.py --out docs/results/mix.json"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from acqlab.bench import mix
from debate_pilot import versus
from haiku_team import verdict
from upside_pilot import keys, load

ROOT = Path(__file__).resolve().parents[1] / "data"
OPUS_BASELINES = ("s1b", "s4")
REFERENCE = "mix_haiku_solo"


def parts() -> tuple[str, ...]:
    """Every system with runs in the final test: the baselines, the reference and each frozen mix's parts."""
    if not mix.FINAL:
        raise ValueError("no frozen mixes: mix.FINAL is set at the freeze")
    got = [*OPUS_BASELINES, REFERENCE]
    for n in mix.FINAL:
        got += list(mix.parse(n)[:2]) if mix.parse(n) else [n]
    return tuple(dict.fromkeys(got))


def check(by: dict[str, dict[str, dict]], ks: dict, root: Path, name: str) -> None:
    """Refuse a final test that is not the pre-registered one: a system missing deals or traces, a row on the wrong
    models (a run with timed-out steps may show fewer; a timed-out run none), or a mix row whose fingerprint is not
    the frozen one."""
    for s, rows in by.items():
        if set(rows) != set(ks):
            raise ValueError(f"{name}: {s} runs cover {sorted(set(rows) ^ set(ks))} differently from the test split")
    lost = [f"{name}/{s}/{d}" for s in by for d in ks if not (root / name / "runs" / s / f"{d}.trace.jsonl").exists()]
    if lost:
        raise ValueError(f"runs without a trace: {lost}")
    wrong = []
    for s, rows in by.items():
        want = set([mix.OPUS] if s in OPUS_BASELINES else mix.models_of(s))
        for d, r in rows.items():
            got = set(r["models"])
            if got != want and not (r["timeouts"] and got < want) and not (not got and r["status"] == "timeout"):
                wrong.append(f"{name}/{s}/{d}")
    if wrong:
        raise ValueError(f"rows on the wrong models: {wrong}")
    stale = [f"{name}/{s}/{d}" for s in by if s not in OPUS_BASELINES for d, r in by[s].items()
             if r.get("prompts") != mix.fingerprint(s)]
    if stale:
        raise ValueError(f"rows not made with the frozen mixes: {stale}")


def results(by: dict[str, dict[str, dict]], tz: dict[str, str], system: str) -> dict[str, dict]:
    """deal -> {go, correct, regret, case_type, cost, escalated} for a run system or a frozen cascade."""
    if (p := mix.parse(system)) is not None:
        cheap, strong, signal = p
        return {d: mix.cascade(by[cheap][d], by[strong][d], signal, tz[d]) for d in by[cheap]}
    return {d: {"go": r["go"], "correct": r["correct"], "regret": r["regret"], "case_type": r["case_type"],
                "cost": mix.row_cost(r) or 0.0, "escalated": False} for d, r in by[system].items()}


def summary(res: dict[str, dict]) -> dict:
    v = list(res.values())
    return {"n": len(v), "regret": float(np.mean([x["regret"] for x in v])),
            "correct": float(np.mean([x["correct"] for x in v])),
            "false_go": sum(x["go"] and not x["correct"] for x in v),
            "false_nogo": sum(not x["go"] and not x["correct"] for x in v),
            "cost": float(np.mean([x["cost"] for x in v])), "escalated": float(np.mean([x["escalated"] for x in v]))}


def one_set(res: dict[str, dict[str, dict]]) -> dict:
    """Spec §1 for one deal set: each frozen mix against s1b and s4, with verdicts and cost ratios, and every
    system's summary (the quality-against-cost table)."""
    cards = {s: summary(r) for s, r in res.items()}
    out = {"n": cards["s1b"]["n"], "systems": cards, "versus": {}, "verdicts": {}, "cost_ratio": {}}
    for m in mix.FINAL:
        for b in OPUS_BASELINES:
            c = versus(res[m], res[b])
            out["versus"][f"{m}-{b}"] = c
            out["verdicts"][f"{m}-{b}"] = verdict(c)
            out["cost_ratio"][f"{b}/{m}"] = cards[b]["cost"] / cards[m]["cost"] if cards[m]["cost"] else None
    return out


def readings(card: dict) -> dict:
    """The two named readings on a set: the mixes cheaper than the baseline and not "worse" than it."""
    sys_ = card["systems"]
    return {f"cheaper_and_not_worse_than_{b}": [m for m in mix.FINAL if sys_[m]["cost"] < sys_[b]["cost"]
                                                 and card["verdicts"][f"{m}-{b}"] != "worse"]
            for b in OPUS_BASELINES}


def analyse(root: Path) -> dict:
    names = parts()
    res, tz_all = {}, {}
    for name in mix.TEST_SETS:
        ks = keys(root / name, "test")
        by = {s: load(root / name, s) for s in names}
        check(by, ks, root, name)
        tz = {d: json.loads((root / name / "deals" / d / "room" / "index.json").read_text())["teaser"] for d in ks}
        res[name] = {s: results(by, tz, s) for s in (*names, *mix.FINAL) if not mix.parse(s) or s in mix.FINAL}
    res["all"] = {s: {f"{n}/{d}": x for n in mix.TEST_SETS for d, x in res[n][s].items()} for s in res[mix.TEST_SETS[0]]}
    sets = {n: one_set(r) for n, r in res.items()}
    return {"frozen": list(mix.FINAL), "systems": list(res["all"]), "sets": sets,
            "readings": {n: readings(c) for n, c in sets.items()}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=ROOT, help="the directory holding the two fresh sets")
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
    print(json.dumps({"verdicts": out["sets"]["all"]["verdicts"], "readings": out["readings"]["all"],
                      "cost": {s: c["cost"] for s, c in out["sets"]["all"]["systems"].items()}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
