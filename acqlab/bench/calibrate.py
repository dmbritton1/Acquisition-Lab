"""Calibration check (reframe design §4): does one round's hard benchmark meet every target? No Claude calls: it reads
the round's finished S1b and S0 runs (pilot) and the round's 500-deal audit batch.

  uv run python -m acqlab.bench.calibrate --data data/cal-r1 --audit /tmp/acqlab-audit-r1

Writes <data>/calibration.json. Exit codes: 0 every target met; 1 a target missed (printed).
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np

from acqlab.bench.pilot import floors, summarize
from acqlab.generator.batch import AnswerKey
from acqlab.generator.validate import _auc

FLIP_WRONG_MIN = 0.30  # S1b gets at least 30% of flip deals wrong
S0_FLIP_RIGHT_MIN = 0.80  # S0 (reading everything) gets at least 80% of flip deals right
TEST_DEALS = 100  # the planned test size (main spec §4)
EFFECT = 0.25  # H1's noticeable difference
Z = 1.959964 + 0.841621  # paired test at two-sided 5%, 80% power
AUDIT_DEALS = 500
MARGIN_AUC_MAX = 0.72  # generator 3.0.0's margin shortcut


def deals_needed(regrets: list[float], effect: float = EFFECT) -> float:
    """Test deals needed to detect an `effect` cut in mean regret, modelling S4 as removing all of S1b's regret on a
    random `effect` share of deals (which cuts the mean by exactly `effect`). With S1b's per-deal regret r:
    n = Z² (E[r²] / (effect E[r]²) - 1). ponytail: a model of the unknown S4; use the paired variance once S4 has
    dev runs."""
    r = np.asarray(regrets, dtype=float)
    m1, m2 = r.mean(), (r ** 2).mean()
    return math.inf if m1 == 0 else float(math.ceil(Z ** 2 * (m2 / (effect * m1 ** 2) - 1)))


def margin_auc(keys: list[AnswerKey]) -> float:
    """How well a thin face-value margin picks out decision-flip deals (0.5 = not at all; NaN if one group is empty)."""
    h = np.array([abs(k.truth.face_walk_away / k.truth.deal.asking_price - 1) for k in keys])
    flip = np.array([k.truth.go != k.truth.face_go for k in keys])
    return 1 - _auc(h[flip], h[~flip]) if flip.any() and not flip.all() else math.nan


def _keys(data: Path) -> list[AnswerKey]:
    return [AnswerKey.model_validate_json(p.read_text()) for p in sorted((data / "truth").glob("*.json"))]


def check(data: Path, audit: Path) -> dict:
    """Every target with its measured value; `passed` only if all are met."""
    rows = [json.loads(p.read_text()) for s in ("s1b", "s0") for p in sorted((data / "runs" / s).glob("*.json"))]
    for r in rows:
        r["floors"] = floors(AnswerKey.model_validate_json((data / "truth" / f"{r['deal']}.json").read_text()))
    s1b = [r for r in rows if r["system"] == "s1b" and r.get("rep", 0) == 0]
    s0 = [r for r in rows if r["system"] == "s0" and r.get("rep", 0) == 0 and r["flip"]]
    flip = [r for r in s1b if r["flip"]]
    summary = summarize(rows) if s1b else {"floors": {}}
    regret = float(np.mean([r["regret"] for r in s1b])) if s1b else math.nan
    keys = _keys(audit)
    problems = json.loads((audit / "problems.json").read_text()) if (audit / "problems.json").exists() else None
    targets = [
        ("S1b wrong on flip deals", 1 - np.mean([r["correct"] for r in flip]) if flip else math.nan,
         ">=", FLIP_WRONG_MIN),
        ("test deals needed to detect a 25% cut", deals_needed([r["regret"] for r in s1b]) if s1b else math.inf,
         "<=", TEST_DEALS),
        ("S0 right on flip deals", np.mean([r["correct"] for r in s0]) if s0 else math.nan, ">=", S0_FLIP_RIGHT_MIN),
        ("S1b regret minus B0's", regret - summary["floors"].get("b0", math.nan), "<", 0.0),
        ("S1b regret minus the margin rule's", regret - summary["floors"].get("margin_rule", math.nan), "<", 0.0),
        ("audit deals", float(len(keys)), ">=", AUDIT_DEALS),
        ("audit batch problems (incl. word leaks)", math.inf if problems is None else float(len(problems)), "<=", 0.0),
        ("margin shortcut AUC (audit)", margin_auc(keys) if keys else math.nan, "<=", MARGIN_AUC_MAX),
    ]
    ops = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b, "<": lambda a, b: a < b}
    out = [{"target": name, "value": float(v), "need": f"{op} {want}", "met": bool(ops[op](float(v), want))}
           for name, v, op, want in targets]  # a NaN (no runs) never meets its target
    return {"targets": out, "passed": all(t["met"] for t in out), "n_s1b": len(s1b), "n_s1b_flip": len(flip),
            "n_s0": len(s0)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True, help="the round's deals, with S1b and S0 runs")
    ap.add_argument("--audit", type=Path, required=True, help="the round's 500-deal audit batch")
    args = ap.parse_args(argv)
    result = check(args.data, args.audit)
    (args.data / "calibration.json").write_text(json.dumps(result, indent=2))
    for t in result["targets"]:
        print(f"{'ok  ' if t['met'] else 'MISS'} {t['target']}: {t['value']:.3f} (need {t['need']})")
    print("PASSED: every target met" if result["passed"] else "FAILED: a target was missed")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
