"""The midpoint and named-source check (docs/results/midpoint-check-prereg.md). Reads finished simulator runs; never
calls a model. Run from the repository root after the runs: .venv/bin/python scripts/midpoint_check.py > out.json"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from acqlab.bench import sim, simrun

RUNS = simrun.RUNS
LOGGED = [*simrun.PRACTICE, simrun.TEST]


def pooled(sets, name):
    return {f"{d.name}/{k}": r for d in sets for k, r in simrun.load(RUNS, d, name).items()}


def arm(rows, base):
    rs = list(rows.values())
    reached = [r["real_reached"] for r in rs if r["real_reached"] is not None]
    ds = sorted(set(rows) & set(base))
    diff = [rows[d]["regret"] - base[d]["regret"] for d in ds]
    return {"n": len(rs), "regret": float(np.mean([r["regret"] for r in rs])),
            "correct": float(np.mean([r["correct"] for r in rs])),
            "false_go": sum(r["go"] and not r["correct"] for r in rs),
            "false_nogo": sum(not r["go"] and not r["correct"] for r in rs),
            "pages": float(np.mean([r["pages"] for r in rs])),
            "real_reached": float(np.mean(reached)) if reached else None,
            "nofact_share": float(sum(r["nofact_pages"] for r in rs) / sum(r["pages"] for r in rs)),
            "minus_base": simrun.paired(rows, base),
            "won_lost_tied": [sum(x < -1e-12 for x in diff), sum(x > 1e-12 for x in diff),
                              sum(abs(x) <= 1e-12 for x in diff)]}


def interaction(by):
    """(combo − no_mid) − (named_x2 − baseline), deal by deal, with a paired CI."""
    ds = sorted(set.intersection(*(set(r) for r in by.values())))
    x = {d: {"regret": by["no_mid+named_x2"][d]["regret"] - by["no_mid"][d]["regret"]
             - by["named_x2"][d]["regret"] + by["baseline"][d]["regret"]} for d in ds}
    return simrun.paired(x, {d: {"regret": 0.0} for d in ds})


def named_counts():
    """Documents the real Lead's opening plan names per issue, and their share of the deal's documents."""
    n, share = [], []
    for data in LOGGED:
        for t in sorted((data / "runs" / "s4").glob("*.trace.jsonl")):
            docs = json.loads((data / "deals" / t.name.split(".")[0] / "room" / "index.json").read_text())["documents"]
            for i in sim.logged_plan(t):
                n.append(len(set(i["docs"])))
                share.append(len(set(i["docs"])) / len(docs))
    return {"mean_named": float(np.mean(n)), "mean_share_of_documents": float(np.mean(share)),
            "issues_naming_none": int(sum(x == 0 for x in n)), "issues": len(n)}


def main():
    out = {}
    sim_data = Path("data/sim-r2")
    t1 = {n: simrun.load(RUNS, sim_data, n) for n in ("baseline", "no_mid")}
    out["test1_template"] = {n: arm(r, t1["baseline"]) for n, r in t1.items()}
    ci = out["test1_template"]["no_mid"]["minus_base"]["ci95"]
    out["test1_wins"] = ci[1] < 0
    fresh = Path("data/sim2-r2")
    if (RUNS / fresh.name / "no_mid").exists():
        t1c = {n: simrun.load(RUNS, fresh, n) for n in ("baseline", "no_mid")}
        m = simrun.paired(t1c["no_mid"], t1c["baseline"])
        out["test1_confirmation"] = {"arms": {n: arm(r, t1c["baseline"]) for n, r in t1c.items()},
                                     "confirmed": m["diff"] < 0}
    names = ("baseline", "no_mid", "named_x2", "no_mid+named_x2")
    t2 = {n: pooled(LOGGED, n) for n in names}
    out["test2_logged"] = {n: arm(r, t2["baseline"]) for n, r in t2.items()}
    out["test2_interaction"] = interaction(t2)
    out["test2_named"] = named_counts()
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
