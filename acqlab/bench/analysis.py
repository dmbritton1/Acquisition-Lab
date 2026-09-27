"""The Plan 6 analysis (spec §5; the pre-registration and its addendum): H1-H6 exactly as locked, run once after every
phase of the campaign is complete. Every comparison is a paired per-deal difference with a paired bootstrap 95% CI,
also reported by case type.

  uv run python -m acqlab.bench.analysis --data data/test-r2 --out docs/results/plan-6-main-run.json
"""
import argparse
import json
from pathlib import Path

import numpy as np

from acqlab.bench import campaign, pilot
from acqlab.generator.batch import AnswerKey
from acqlab.routers.track_a import bootstrap_ci

CASES = ("clean", "decoy", "flip", "interaction", "unresolvable")
TARGET = ("interaction", "flip")  # H2: interaction and belief-error deals; belief-error = the flip case type
H1_CUT, H5_FACTOR, H6_MIN = 0.25, 2.0, 5  # H1's 25% cut; "sharply" in H5 = at least double; H6's fewest deals
BOOT, SEED = 2000, 0
EPS = 1e-12  # float noise: a CI that only rounds away from zero does not exclude it


def _ci(d: np.ndarray) -> list:
    return list(bootstrap_ci(d, BOOT, SEED)) if len(d) > 1 else [float(d[0])] * 2 if len(d) else [None, None]


def compare(a: dict, b: dict, field: str = "regret", deals: list | None = None) -> dict:
    """a − b per deal (on `deals`, else the deals both have): n, mean, CI, and the same by case type."""
    ds = sorted(set(a) & set(b) if deals is None else deals)

    def one(sub: list) -> dict:
        d = np.array([a[x][field] - b[x][field] for x in sub], dtype=float)
        return {"n": len(sub), "diff": float(d.mean()) if len(d) else None, "ci95": _ci(d)}

    return one(ds) | {"by_case": {c: one([x for x in ds if a[x]["case_type"] == c]) for c in CASES}}


def below(c: dict) -> bool:
    """The CI lies wholly below zero."""
    return c["ci95"][1] is not None and c["ci95"][1] < -EPS


def above(c: dict) -> bool:
    return c["ci95"][0] is not None and c["ci95"][0] > EPS


def mean(rows: dict, field: str = "regret") -> float:
    return float(np.mean([r[field] for r in rows.values()]))


def gap(s1b: dict, s4: dict) -> dict:
    """H2: the mean gain (S1b − S4 regret) on interaction and flip deals minus the mean gain on the rest, with a
    bootstrap CI that resamples within each group."""
    deals = sorted(set(s1b) & set(s4))
    gain = {d: s1b[d]["regret"] - s4[d]["regret"] for d in deals}
    a = np.array([gain[d] for d in deals if s4[d]["case_type"] in TARGET])
    b = np.array([gain[d] for d in deals if s4[d]["case_type"] not in TARGET])
    if len(a) < 2 or len(b) < 2:
        return {"n_target": len(a), "n_rest": len(b), "gap": None, "ci95": [None, None]}
    rng = np.random.default_rng(SEED)
    boot = (a[rng.integers(0, len(a), (BOOT, len(a)))].mean(axis=1)
            - b[rng.integers(0, len(b), (BOOT, len(b)))].mean(axis=1))
    return {"n_target": len(a), "n_rest": len(b), "gap": float(a.mean() - b.mean()),
            "ci95": [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))]}


def analyse(by: dict[str, dict[str, dict]], real: dict[str, set], first_plan: dict[str, set]) -> dict:
    """by: system -> deal -> row (s1b, s3, s4, the ablations, s1b_matched); real: deal -> the traps with a nonzero
    amount; first_plan: deal -> the issue types in S4's first Deal Lead plan."""
    s1b, s3, s4 = by["s1b"], by["s3"], by["s4"]
    h1 = compare(s4, s1b)
    cut = 1 - mean(s4) / mean(s1b) if mean(s1b) else None
    out = {"H1": {"s4": mean(s4), "s1b": mean(s1b), "s3": mean(s3), "cut": cut, "s4_minus_s1b": h1,
                  "s4_minus_s3": compare(s4, s3),
                  "holds": cut is not None and cut >= H1_CUT and below(h1) and mean(s4) < mean(s3)}}
    out["H2"] = gap(s1b, s4)
    out["H2"]["holds"] = above(out["H2"])
    h3 = compare(by["s4_nochal"], s4)
    out["H3"] = {"nochal_minus_s4": h3, "holds": above(h3)}
    h4 = compare(s4, s1b, "decoy_pages")
    out["H4"] = {"s4_minus_s1b": h4, "holds": below(h4)}
    noengine = by["s4_noengine"]
    h5 = compare(noengine, s4, "walk_away_error")
    ratio = mean(noengine, "walk_away_error") / mean(s4, "walk_away_error") if mean(s4, "walk_away_error") else None
    out["H5"] = {"noengine": mean(noengine, "walk_away_error"), "s4": mean(s4, "walk_away_error"), "ratio": ratio,
                 "noengine_minus_s4": h5, "holds": ratio is not None and ratio >= H5_FACTOR and above(h5)}
    missed = sorted(d for d in by["s4_nosweep"] if d in s4 and real[d] - first_plan[d])
    h6 = compare(by["s4_nosweep"], s4, deals=missed)
    out["H6"] = {"deals": missed, "nosweep_minus_s4": h6,
                 "holds": "too few to test" if len(missed) < H6_MIN else above(h6)}
    out["also"] = {"s4_minus_s1b_matched": compare(s4, by["s1b_matched"]),
                   "llmdecides_minus_s4": compare(by["s4_llmdecides"], s4)}
    return out


def load(data: Path) -> tuple[dict, dict, dict, list]:
    """(by, real, first_plan, rows) from a finished campaign's test-split runs."""
    rows = [json.loads(p.read_text()) for s in pilot.ALL for p in sorted((data / "runs" / s).glob("test-*.json"))]
    by = {s: {r["deal"]: r for r in rows if r["system"] == s and r.get("rep", 0) == 0} for s in pilot.ALL}
    by["s3"] = pilot.s3_rows(rows, 2)
    by["s1b_matched"] = pilot.s1b_matched(by["s1b"], by["s4"])
    real, first_plan = {}, {}
    for deal in by["s4"]:
        key = AnswerKey.model_validate_json((data / "truth" / f"{deal}.json").read_text())
        real[deal] = {f.trap for f in key.truth.facts if f.amount > 0}
        trace = [json.loads(x) for x in (data / "runs" / "s4" / f"{deal}.trace.jsonl").read_text().splitlines()]
        plan = next((r for r in trace if r["tool"] == "propose" and not r["refused"]), None)
        first_plan[deal] = {i["type"] for i in plan["args"]["issues"]} if plan else set()
    return by, real, first_plan, rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--repo", type=Path, default=Path("."))
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    if args.out.exists():  # the verdicts are one-shot: never overwrite a result already written
        print(f"Refusing to analyse: {args.out} already exists")
        return 1
    if not campaign.complete(args.data):
        print(f"Refusing to analyse: the campaign is not complete ({campaign.progress(args.data)})")
        return 1
    problem = campaign.preflight(args.data, args.repo)
    if problem:
        print(f"Refusing to analyse: {problem}")
        return 1
    by, real, first_plan, rows = load(args.data)
    result = analyse(by, real, first_plan) | {"systems": pilot.summarize(rows, s3_n=2)}
    args.out.write_text(json.dumps(result, indent=2))
    for h in ("H1", "H2", "H3", "H4", "H5", "H6"):
        print(f"{h}: {result[h]['holds']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
