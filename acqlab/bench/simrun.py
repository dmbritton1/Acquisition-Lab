"""The reading simulator's runner (spec 2026-10-01-reading-simulator-design.md §3): template deals, simulated runs
in a process pool, the greedy combination, and the report. Offline: no Claude or Codex call anywhere.

  uv run python -m acqlab.bench.simrun deals --out data/sim-r2 --n 300 --base 7000000
  uv run python -m acqlab.bench.simrun run --data data/cal-r2 --strategies baseline --opening logged
  uv run python -m acqlab.bench.simrun run --data data/sim-r2 --strategies baseline,regret,... --opening model
  uv run python -m acqlab.bench.simrun combine --data data/sim-r2
  uv run python -m acqlab.bench.simrun report --json docs/results/reading-simulator.json

Runs go to <runs>/<data dir name>/<strategy>/<deal>.json (default runs: data/sim-r2/runs); finished runs are skipped.
Exit codes: 0 done; 1 refused (a seed clash, or a missing input)."""
import argparse
import json
import math
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from statistics import NormalDist

import numpy as np

from acqlab.agents.record import load_face
from acqlab.bench import sim, testset
from acqlab.generator import batch
from acqlab.generator.batch import AnswerKey
from acqlab.routers.track_a import bootstrap_ci

RUNS = Path("data/sim-r2/runs")
PRACTICE = (Path("data/cal-r2"), Path("data/heldout-r2"))
TEST = Path("data/test-r2")
SINGLES = list(sim.STRATEGIES)
FAMILIES = {"regret": ["regret"], "pages": ["pages_0.5", "pages_0"], "base_rate": ["base_rate"],
            "cut": ["cut_0.25", "cut_0.5"], "no_sweep": ["no_sweep"]}  # spec §3: a family enters at its best value
AGREE, REGRET_GAP = 0.85, 0.003  # spec §2's pass bars
SD, H1_GAP = 0.0368, -0.0038  # Plan 6: per-deal SD of S4 − S1b regret, and its mean


# --- deals -------------------------------------------------------------------------------------------------------

def make_deals(out: Path, n: int, base: int, roots: list[Path], mc: int = 400) -> list[int]:
    """Template-prose r2 deals as split dev (seeds base..base+n-1). Returns the clashing used seeds; generates
    nothing if there are any."""
    bad = testset.clashes(base, n, testset.used_seeds(roots), split="dev")
    if not bad:
        batch.run(out, {"dev": n}, seed=base, mc=mc, profile="r2")
        (out / "seed.json").write_text(json.dumps({"base": base, "n": n, "split": "dev"}))
    return bad


# --- runs --------------------------------------------------------------------------------------------------------

def deals_of(data: Path, opening: str) -> list[str]:
    """Logged openings need a real S4 trace; modelled ones take every deal."""
    deals = [d for ds in json.loads((data / "splits.json").read_text()).values() for d in ds]
    return [d for d in deals if opening == "model" or (data / "runs" / "s4" / f"{d}.trace.jsonl").exists()]


def fitted() -> dict:
    """The modelled Lead, fitted on the practice deals' logged opening plans (spec §2)."""
    plans = [(sim.logged_plan(t), load_face(p / "deals" / t.name.split(".")[0] / "room"))
             for p in PRACTICE for t in sorted((p / "runs" / "s4").glob("*.trace.jsonl"))]
    return sim.fit_lead(plans)


def _one(job: tuple) -> str:
    data, deal, name, opening, model, out = job
    room = data / "deals" / deal / "room"
    docs = [d["id"] for d in json.loads((room / "index.json").read_text())["documents"]]
    plan = (sim.logged_plan(data / "runs" / "s4" / f"{deal}.trace.jsonl") if opening == "logged"
            else sim.model_plan(model, load_face(room), docs))
    sim.simulate(data, deal, sim.strategy(name), name, plan, out)
    return deal


def run(data: Path, names: list[str], opening: str, runs: Path = RUNS, jobs: int | None = None,
        model: dict | None = None) -> int:
    """Every missing run of these strategies on this deal set; returns how many were made. A modelled opening uses
    `model`, or the Lead fitted on the practice deals."""
    if opening == "model" and model is None:
        model = fitted()
    todo = [(data, d, name, opening, model, runs / data.name / name / f"{d}.json")
            for name in names for d in deals_of(data, opening)]
    todo = [j for j in todo if not j[-1].exists()]
    with ProcessPoolExecutor(jobs or os.cpu_count()) as pool:
        for i, _ in enumerate(pool.map(_one, todo), 1):
            if i % 50 == 0 or i == len(todo):
                print(f"{i}/{len(todo)} runs")
    return len(todo)


def load(runs: Path, data: Path, name: str) -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text()) for p in sorted((runs / data.name / name).glob("*.json"))}


# --- analysis ----------------------------------------------------------------------------------------------------

def paired(a: dict, b: dict, field: str = "regret") -> dict:
    """a − b on the deals both have: n, mean, paired bootstrap CI."""
    ds = sorted(set(a) & set(b))
    d = np.array([a[x][field] - b[x][field] for x in ds], dtype=float)
    return {"n": len(ds), "diff": float(d.mean()), "ci95": [float(x) for x in bootstrap_ci(d)]}


def opened(trace: Path) -> list[str]:
    rows = [json.loads(x) for x in trace.read_text().splitlines()]
    return [r["args"]["doc_id"] for r in rows if r["tool"] == "open_document" and not r["refused"]]


def faithfulness(sim_rows: dict, real_rows: dict, sim_docs: dict, real_docs: dict) -> dict:
    """Simulated baseline against the real system, deal by deal (spec §2)."""
    ds = sorted(set(sim_rows) & set(real_rows))
    jac = [len(set(sim_docs[d]) & set(real_docs[d])) / max(1, len(set(sim_docs[d]) | set(real_docs[d]))) for d in ds]
    diverge = [next((i for i, (a, b) in enumerate(zip(sim_docs[d], real_docs[d])) if a != b),
                    min(len(sim_docs[d]), len(real_docs[d]))) for d in ds]
    out = {"n": len(ds), "agree": float(np.mean([sim_rows[d]["go"] == real_rows[d]["go"] for d in ds])),
           "regret_sim": float(np.mean([sim_rows[d]["regret"] for d in ds])),
           "regret_real": float(np.mean([real_rows[d]["regret"] for d in ds])),
           "sim_minus_real": paired(sim_rows, real_rows),
           "pages_sim": float(np.mean([sim_rows[d]["pages"] for d in ds])),
           "pages_real": float(np.mean([real_rows[d]["pages"] for d in ds])),
           "jaccard": float(np.mean(jac)), "same_reads": float(np.mean([sim_docs[d] == real_docs[d] for d in ds])),
           "first_divergence_median": float(np.median(diverge))}
    ci = out["sim_minus_real"]["ci95"]
    out["passes"] = (out["agree"] >= AGREE and abs(out["sim_minus_real"]["diff"]) < REGRET_GAP
                     and ci[0] <= 0 <= ci[1])
    return out


def table(by: dict[str, dict], base: str = "baseline") -> dict:
    """Per strategy: means, and the paired difference from the baseline."""
    out = {}
    for name, rows in by.items():
        rs = list(rows.values())
        reached = [r["real_reached"] for r in rs if r["real_reached"] is not None]
        out[name] = {"n": len(rs), "regret": float(np.mean([r["regret"] for r in rs])),
                     "correct": float(np.mean([r["correct"] for r in rs])),
                     "nofact_share": float(sum(r["nofact_pages"] for r in rs) / max(1e-9, sum(r["pages"] for r in rs))),
                     "real_reached": float(np.mean(reached)) if reached else None,
                     "minus_base": paired(rows, by[base]) if name != base else None}
    return out


def best_of(tab: dict, names: list[str]) -> str:
    return min(names, key=lambda n: tab[n]["regret"])


def greedy(tab: dict, by: dict[str, dict], run_combo) -> dict:
    """Spec §3's combination: start from the best single strategy whose CI against the baseline lies below zero; add
    each other family at its best value, in order of regret, keeping it only if (with) − (without) has a CI below
    zero. run_combo(name) -> deal -> row runs a combination ("a+b") on the template deals."""
    reps = {f: best_of(tab, ms) for f, ms in FAMILIES.items()}
    good = sorted((n for n in reps.values() if tab[n]["minus_base"]["ci95"][1] < 0), key=lambda n: tab[n]["regret"])
    if not good:
        return {"combo": "baseline", "steps": []}
    combo, rows, steps = good[0], by[good[0]], []
    for n in sorted((n for n in reps.values() if n != good[0]), key=lambda n: tab[n]["regret"]):
        trial = f"{combo}+{n}"
        new = run_combo(trial)
        c = paired(new, rows)
        keep = c["ci95"][1] < 0
        steps.append({"tried": trial, "with_minus_without": c, "kept": keep})
        if keep:
            combo, rows = trial, new
    return {"combo": combo, "steps": steps}


def deals_needed(gap: float, sd: float = SD, power: float = 0.8, alpha: float = 0.05) -> int:
    """Paired deals for a two-sided test at level alpha to detect a mean difference `gap` with this power."""
    z = NormalDist().inv_cdf
    return math.ceil(((z(1 - alpha / 2) + z(power)) * sd / gap) ** 2)


def sizing(sim_gain: float) -> dict:
    """Spec §3: a real test of the winner against S1b, at the full and at half the simulated gain (gain < 0 is
    better)."""
    out = {}
    for label, g in (("full", sim_gain), ("half", sim_gain / 2)):
        gap = H1_GAP + min(0.0, g)
        out[label] = {"gap": gap, "power_80": deals_needed(abs(gap), power=0.8),
                      "power_90": deals_needed(abs(gap), power=0.9)}
    return out


# --- commands ----------------------------------------------------------------------------------------------------

def combine(data: Path, runs: Path = RUNS) -> dict:
    by = {n: load(runs, data, n) for n in SINGLES}
    tab = table(by)

    def run_combo(name: str) -> dict:
        run(data, [name], "model", runs)
        return load(runs, data, name)

    result = greedy(tab, by, run_combo)
    (runs / data.name / "combination.json").write_text(json.dumps(result, indent=2))
    return result


def report(runs: Path = RUNS, sim_data: Path = Path("data/sim-r2")) -> dict:
    out: dict = {"seed": json.loads((sim_data / "seed.json").read_text())}
    faith = {}
    for label, sets, real in (("practice", PRACTICE, "s4"), ("test", (TEST,), "s4"),
                              ("test_nochal", (TEST,), "s4_nochal")):
        srows, rrows, sdocs, rdocs = {}, {}, {}, {}
        for data in sets:
            s = load(runs, data, "baseline")
            for d, row in s.items():
                rp = data / "runs" / real / f"{d}.json"
                if not rp.exists():
                    continue
                key = f"{data.name}/{d}"
                srows[key], rrows[key] = row, json.loads(rp.read_text())
                sdocs[key], rdocs[key] = row["opened"], opened(rp.with_suffix(".trace.jsonl"))
        faith[label] = faithfulness(srows, rrows, sdocs, rdocs)
    out["faithfulness"] = faith
    out["passes"] = all(f["passes"] for f in faith.values())
    by = {n: load(runs, sim_data, n) for n in SINGLES}
    if not all(by.values()):  # spec §2: the strategies are compared only after the faithfulness check
        return out
    out["strategies"] = table(by)
    comb = runs / sim_data.name / "combination.json"
    if comb.exists():
        c = json.loads(comb.read_text())
        out["combination"] = c
        out["combination_minus_base"] = paired(load(runs, sim_data, c["combo"]), by["baseline"])
        conf = {n: {f"{p.name}/{d}": r for p in PRACTICE for d, r in load(runs, p, n).items()}
                for n in ("baseline", c["combo"])}
        if conf[c["combo"]]:
            m = paired(conf[c["combo"]], conf["baseline"])
            out["confirmation"] = {"minus_base": m, "passes": m["diff"] <= 0}
        out["sizing"] = sizing(out["combination_minus_base"]["diff"])
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("deals")
    d.add_argument("--out", type=Path, default=Path("data/sim-r2"))
    d.add_argument("--n", type=int, default=300)
    d.add_argument("--base", type=int, required=True)
    r = sub.add_parser("run")
    r.add_argument("--data", type=Path, required=True)
    r.add_argument("--strategies", default="baseline")
    r.add_argument("--opening", choices=("logged", "model"), required=True)
    r.add_argument("--jobs", type=int)
    c = sub.add_parser("combine")
    c.add_argument("--data", type=Path, default=Path("data/sim-r2"))
    p = sub.add_parser("report")
    p.add_argument("--json", type=Path, required=True)
    args = ap.parse_args(argv)
    if args.cmd == "deals":
        bad = make_deals(args.out, args.n, args.base, [*PRACTICE, TEST])
        if bad:
            print(f"Refusing: base {args.base} clashes with used seeds {bad[:10]}")
            return 1
        return 0
    if args.cmd == "run":
        print(f"{run(args.data, args.strategies.split(','), args.opening, jobs=args.jobs)} runs made")
        return 0
    if args.cmd == "combine":
        print(json.dumps(combine(args.data), indent=2))
        return 0
    result = report()
    args.json.write_text(json.dumps(result, indent=2))
    print(json.dumps({k: result[k] for k in ("passes", "faithfulness")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
