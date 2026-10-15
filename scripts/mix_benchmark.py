"""The full mixed-model benchmark (docs/results/mix-benchmark-prereg.md): every system and frozen mix on the same 300
deals, the 200 held-out and the 100 fresh, run once after mix_opus_low and mix_sonnet_solo have run on the held-out
sets. Reads answer keys and runs; never calls a model. From the repository root:

  .venv/bin/python scripts/mix_benchmark.py --out docs/results/mix-benchmark.json"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from acqlab.bench import mix
from mix_confirm import TEAM, one, pooled
from mix_final import OPUS_BASELINES, check
from upside_pilot import keys, load

ROOT = Path(__file__).resolve().parents[1] / "data"
HELD, FRESH = mix.CONFIRM_SETS, mix.TEST_SETS
# each run system, by its run name on each set: the Haiku track's names on the held-out sets, the mix names (the
# same prompts, pinned by test_mix's freeze test) on the fresh sets
RUNS = {"s4": "s4", "s1b": "s1b", "mix_h_opus1": "mix_h_opus1", "mix_opus_low": "mix_opus_low",
        "mix_sonnet_solo": "mix_sonnet_solo"}
OLD = {"mix_haiku_solo": "haiku_solo", "mix_h_haiku3": TEAM["test-r2"]}  # rows checked by the Haiku track's analysis


def run_name(system: str, name: str) -> str:
    return OLD[system] if system in OLD and name in HELD else system


def rows(root: Path, name: str) -> dict[str, dict[str, dict]]:
    """Every run system's rows on one set, refused unless each covers the test split; the rows this benchmark adds
    or the mix test made are also refused unless traced, on the right models and made with the frozen mixes."""
    ks = keys(root / name, "test")
    by = {s: load(root / name, run_name(s, name)) for s in (*RUNS, *OLD)}
    check({s: r for s, r in by.items() if s not in OLD or name in FRESH}, ks, root, name)
    if bad := [s for s, r in by.items() if set(r) != set(ks)]:
        raise ValueError(f"{name}: {bad} do not cover the test split")
    return by


def results(by: dict[str, dict[str, dict]], tz: dict[str, str], system: str) -> dict[str, dict]:
    """deal -> {go, correct, regret, case_type, cost, escalated, minutes} for a run system or a frozen cascade; a cascade waits
    for its strong system only on an escalated deal."""
    def one_row(r):
        return {"go": r["go"], "correct": r["correct"], "regret": r["regret"], "case_type": r["case_type"],
                "cost": mix.row_cost(r) or 0.0, "escalated": False, "minutes": (r.get("duration_ms") or 0) / 60_000}
    if (p := mix.parse(system)) is None:
        return {d: one_row(r) for d, r in by[system].items()}
    cheap, strong, signal = p
    out = {}
    for d in by[cheap]:
        c = mix.cascade(by[cheap][d], by[strong][d], signal, tz[d])
        out[d] = c | {"minutes": one_row(by[cheap][d])["minutes"]
                      + (one_row(by[strong][d])["minutes"] if c["escalated"] else 0.0)}
    return out


def card(res: dict[str, dict[str, dict]]) -> dict:
    """One deal set: every system's summary with its median and 90th-percentile minutes per deal, and each system
    other than the baselines against s1b and s4 (the paired range, verdict and cost ratio)."""
    others = [s for s in res if s not in OPUS_BASELINES]
    each = {s: one(res, s) for s in others}
    out = {"n": len(res["s1b"]), "systems": each[others[0]]["systems"]}
    for s, r in res.items():
        m = [x["minutes"] for x in r.values()]
        out["systems"][s] |= {"minutes_median": float(np.median(m)), "minutes_p90": float(np.percentile(m, 90))}
    for k in ("versus", "verdicts", "cost_ratio"):
        out[k] = {s: c[k] for s, c in each.items()}
    return out


def analyse(root: Path) -> dict:
    systems = (*RUNS, *OLD, *[m for m in mix.FINAL if mix.parse(m)])
    res = {}
    for name in (*HELD, *FRESH):
        by = rows(root, name)
        tz = {d: json.loads((root / name / "deals" / d / "room" / "index.json").read_text())["teaser"] for d in by["s1b"]}
        res[name] = {s: results(by, tz, s) for s in systems}
    sets = {"all": (*HELD, *FRESH), "held_out": HELD, "fresh": FRESH}
    return {"systems": list(systems), "frozen": list(mix.FINAL),
            "sets": {label: card(pooled(res, names)) for label, names in sets.items()}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=ROOT, help="the directory holding the deal sets")
    ap.add_argument("--out", type=Path, required=True, help="where the analysis goes (never overwritten)")
    args = ap.parse_args(argv)
    if args.out.exists():  # one-shot: never overwrite a result already written
        print(f"Refusing: {args.out} already exists")
        return 1
    try:
        out = analyse(args.root)
    except ValueError as e:
        print(f"Refusing: {e}")
        return 1
    args.out.write_text(json.dumps(out, indent=2))
    print(json.dumps(out["sets"]["all"]["verdicts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
