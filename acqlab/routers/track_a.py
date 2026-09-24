"""Track A (Plan 3 design): routers against a simulated investigator, no LLM.

  uv run python -m acqlab.routers.track_a --deals data/track_a --grid headline --workers 8

Results go to <deals>/results.jsonl (one line per run; reruns skip finished runs) and <deals>/summary_<grid>.json.
"""
import argparse
import itertools
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import NamedTuple

import numpy as np

from acqlab.engine import is_go, walk_away
from acqlab.generator.batch import AnswerKey
from acqlab.generator.traps import TRAPS, params_for
from acqlab.generator.truth import Fact
from acqlab.routers.beliefs import HAIRCUT_CAP, Beliefs, Issue, draw, walk_aways
from acqlab.routers.routers import ROUTERS, decide

LEVELS = {"low": (0.2, 0.0), "medium": (0.4, 0.10), "high": (0.7, 0.25)}  # prior noise s, forget probability f
INVESTIGATORS = ("perfect", "failure", "noisy")
SHARES = (0.25, 0.5, 1.0)  # budget as a share of the deal's default budget
ALL_ROUTERS = ("checklist", "random", "sensitivity", "flip", "regret", "regret+veto", "oracle")
N_WORLDS = 400
BASE_P_REAL = 0.30
SWEEP_SHARE = 0.10
FAIL_P = 0.25
NOISE = 0.25
VETO = 0.0025  # "regret+veto" stops when the best score is below this share of the asking price per page
FULL_DEALS = 500  # the full and hints grids use the first 500 deals
CLUES = (0.7, 0.9)  # hints grid: chance each hint is right (0.5 = a coin flip = no hint)
FINAL = 10_000  # world-draw seed slot for the final decision (steps use 0, 1, 2, ...)


class Setting(NamedTuple):
    router: str
    investigator: str
    level: str
    share: float
    truth: str = "generator"  # generator: the answer key; self: true values drawn from the router's own priors
    clue: float = 0.5  # chance each prior hint is right; 0.5 = no information


def grid(name: str) -> list[Setting]:
    """headline: both truths at medium priors; full: every investigator and prior level; hints: the clue study."""
    if name == "headline":
        axes = (ALL_ROUTERS, ("perfect",), ("medium",), SHARES, ("generator", "self"), (0.5,))
    elif name == "full":
        axes = (ALL_ROUTERS, INVESTIGATORS, tuple(LEVELS), SHARES, ("generator",), (0.5,))
    else:
        axes = (ALL_ROUTERS, ("perfect",), ("medium",), SHARES, ("generator",), CLUES)
    return [Setting(*s) for s in itertools.product(*axes)]


def _idx(s: Setting) -> tuple[int, int, int]:
    return INVESTIGATORS.index(s.investigator), list(LEVELS).index(s.level), SHARES.index(s.share)


def priors(key: AnswerKey, level: str, clue: float = 0.5) -> Beliefs:
    """Noisy versions of each trap's range (0, worst), never the generator's own prior. The same for every router.
    With clue > 0.5, each issue also gets a hint ("real problem" or "clean") that is right with probability `clue`,
    and p_real is scaled by the hint's likelihood ratio. Hints come from the answer key: a "what if" study only."""
    s, forget = LEVELS[level]
    rng = np.random.default_rng([key.truth.seed, list(LEVELS).index(level)])
    hints = np.random.default_rng([key.truth.seed, list(LEVELS).index(level), 7])  # base priors ignore the clue
    out = {}
    for f in key.truth.facts:
        p = BASE_P_REAL * float(np.exp(rng.normal(0, s)))
        hi = f.worst * float(np.exp(rng.normal(0, s)))
        proposed = bool(rng.random() >= forget)
        says_real = (f.role != "clean") == (hints.random() < clue)
        ratio = clue / (1 - clue)
        p = float(np.clip(p * (ratio if says_real else 1 / ratio), 0.02, 0.95))
        out[f.trap] = Issue(p_real=p, hi=hi, proposed=proposed)
    return out


def self_consistent(key: AnswerKey, level: str) -> AnswerKey:
    """The fair game: the same deal, with true values drawn from the medium-noise priors themselves (forgotten
    issues included), so the routers' beliefs are exactly right. Roles become "problem" or "clean"."""
    t = key.truth
    b = {trap: issue._replace(proposed=True) for trap, issue in priors(key, level).items()}
    values = draw(b, 1, np.random.default_rng([t.seed, list(LEVELS).index(level), 777]))[0]
    # Cap concentration at HAIRCUT_CAP * revenue per spec §3
    conc_idx = TRAPS.index("concentration")
    values[conc_idx] = min(values[conc_idx], HAIRCUT_CAP * t.base.teaser.revenue_ltm)
    facts = [f.model_copy(update={"amount": float(v), "realized": float(v), "documented": None,
                                  "role": "clean" if v == 0 else "problem"}) for f, v in zip(t.facts, values)]
    p = params_for({f.trap: f.amount for f in facts}, t.base)
    return key.model_copy(update={"truth": t.model_copy(update={
        "facts": facts, "walk_away": walk_away(t.deal, p), "go": is_go(t.deal, p),
        "case_type": "clean" if all(f.role == "clean" for f in facts) else "problem"})})


def investigate(f: Fact, kind: str, rng: np.random.Generator) -> tuple[float, float] | None:
    """The simulated investigator's reply: a (low, high) range, or None if the read failed."""
    if kind == "failure" and rng.random() < FAIL_P:
        return None
    if f.documented:
        return tuple(f.documented)
    if kind == "noisy" and f.amount > 0:
        r = f.amount * rng.uniform(1 - NOISE, 1 + NOISE)
        return r / (1 + NOISE), r / (1 - NOISE)
    return f.amount, f.amount


def regret(key: AnswerKey, go: bool) -> float:
    """$M regret against the answer key's knowable truth."""
    t = key.truth
    ask = t.deal.asking_price
    if go and not t.go:
        return max(0.0, ask - t.walk_away)
    if not go and t.go:
        return max(0.0, t.walk_away - ask)
    return 0.0


def _simulate(key: AnswerKey, beliefs: Beliefs, level: str, slot: int, cache: dict) -> tuple[np.ndarray, np.ndarray]:
    """(values, walk-aways) of N_WORLDS worlds. Seeded by deal, level and slot (step number or FINAL) only, so every
    router at the same step with the same beliefs gets the same worlds, which are therefore computed once per deal."""
    k = (level, slot, tuple(beliefs[t] for t in TRAPS))
    if k not in cache:
        rng = np.random.default_rng([key.truth.seed, list(LEVELS).index(level), slot])
        values = draw(beliefs, N_WORLDS, rng)
        cache[k] = values, walk_aways(key.truth.base, values)
    return cache[k]


def _record(key: AnswerKey, s: Setting, beliefs0: Beliefs, reads: list[str], go: bool, est: float,
            found: bool) -> dict:
    t = key.truth
    ask, facts = t.deal.asking_price, {f.trap: f for f in t.facts}
    nonclean = [f for f in t.facts if f.role != "clean"]
    return {
        "deal": t.id, **s._asdict(), "regret": regret(key, go) / ask, "correct": go == t.go,
        "wa_error": abs(est - t.walk_away) / ask, "pages": sum(key.retrieval_cost[r] for r in reads),
        "pages_on_decoys": sum(key.retrieval_cost[r] for r in reads if facts[r].role == "decoy"),
        "found_by_sweep": found, "reads": reads, "flip": t.go != t.face_go,
        "has_decoy": any(f.role == "decoy" for f in t.facts),
        "has_interaction": any(f.role == "interaction" for f in t.facts), "case_type": t.case_type,
        "prior_inside": (sum(f.realized <= beliefs0[f.trap].hi for f in nonclean) / len(nonclean)) if nonclean
        else None,
    }


def run(key: AnswerKey, s: Setting, cache: dict | None = None) -> dict:
    """One run: route, sweep, decide. `cache` shares simulated worlds between runs on the same deal."""
    cache = {} if cache is None else cache
    t = key.truth
    ask, costs, facts = t.deal.asking_price, key.retrieval_cost, {f.trap: f for f in t.facts}
    beliefs0 = priors(key, s.level, s.clue)
    beliefs = dict(beliefs0)
    budget = key.budget * s.share
    spent, reads, attempts = 0.0, [], {trap: 0 for trap in TRAPS}
    inv, lvl, shr = _idx(s)
    order_rng = np.random.default_rng([t.seed, lvl, shr, 99])

    def read(trap: str) -> tuple[float, float] | None:
        nonlocal spent
        spent += costs[trap]
        reads.append(trap)
        attempts[trap] += 1
        rng = np.random.default_rng([t.seed, inv, lvl, TRAPS.index(trap), attempts[trap]])
        return investigate(facts[trap], s.investigator, rng)

    name = s.router.removesuffix("+veto")
    fn, needs_worlds = ROUTERS[name]
    reserve = SWEEP_SHARE * budget
    for step in itertools.count():
        open_ = [x for x in TRAPS if beliefs[x].open and costs[x] <= budget - spent - reserve + 1e-9]
        if not open_:
            break
        values = w = None
        if needs_worlds:
            values, w = _simulate(key, beliefs, s.level, step, cache)
        scores = fn(values, w, ask, costs, open_, order_rng)
        best = max(open_, key=lambda x: (scores[x], -TRAPS.index(x)))
        if s.router.endswith("+veto") and scores[best] < VETO * ask:
            break
        reply = read(best)
        if reply is not None:
            beliefs[best] = beliefs[best]._replace(known=reply)
    found = False
    while cand := [x for x in TRAPS if x not in reads and costs[x] <= budget - spent + 1e-9]:
        trap = min(cand, key=lambda x: (costs[x], TRAPS.index(x)))
        reply = read(trap)
        if reply is not None:
            found |= not beliefs[trap].proposed and facts[trap].role != "clean"
            beliefs[trap] = beliefs[trap]._replace(known=reply, proposed=True)
    go, est = decide(_simulate(key, beliefs, s.level, FINAL, cache)[1], ask)
    return _record(key, s, beliefs0, reads, go, est, found)


def oracle_table(key: AnswerKey, level: str, clue: float = 0.5,
                 cache: dict | None = None) -> dict[tuple[str, ...], tuple[float, float, bool, float]]:
    """For every subset of traps learned perfectly: (true regret, cost, go, walk-away estimate)."""
    cache = {} if cache is None else cache
    beliefs0 = priors(key, level, clue)
    out = {}
    for k in range(len(TRAPS) + 1):
        for subset in itertools.combinations(TRAPS, k):
            beliefs = dict(beliefs0)
            for f in key.truth.facts:
                if f.trap in subset:
                    beliefs[f.trap] = beliefs[f.trap]._replace(known=tuple(f.documented or (f.amount, f.amount)),
                                                               proposed=True)
            go, est = decide(_simulate(key, beliefs, level, FINAL, cache)[1], key.truth.deal.asking_price)
            out[subset] = (regret(key, go), sum(key.retrieval_cost[x] for x in subset), go, est)
    return out


def run_oracle(key: AnswerKey, s: Setting, table: dict) -> dict:
    """Ceiling: the affordable subset of perfect reads with the lowest true regret (ties: cheaper)."""
    budget = key.budget * s.share
    subset = min((sub for sub, v in table.items() if v[1] <= budget + 1e-9), key=lambda sub: table[sub][:2])
    _, _, go, est = table[subset]
    return _record(key, s, priors(key, s.level, s.clue), list(subset), go, est, False)


def run_deal(path: Path, settings: list[Setting]) -> list[dict]:
    """Every pending setting for one deal. Errors come back as a single {"deal", "error"} row."""
    try:
        real = AnswerKey.model_validate_json(path.read_text())
        keys: dict[tuple[str, str] | str, AnswerKey] = {}
        tables: dict[tuple, dict] = {}
        caches: dict[tuple[str, str] | str, dict] = {}  # worlds depend on the truth mode and level
        rows = []
        for s in settings:
            key_k = (s.truth, s.level) if s.truth != "generator" else "generator"
            if key_k not in keys:
                keys[key_k] = self_consistent(real, s.level) if s.truth == "self" else real
            cache_k = (s.truth, s.level) if s.truth != "generator" else "generator"
            if cache_k not in caches:
                caches[cache_k] = {}
            key, cache = keys[key_k], caches[cache_k]
            if s.router == "oracle":
                tk = (s.truth, s.level, s.clue)
                if tk not in tables:
                    tables[tk] = oracle_table(key, s.level, s.clue, cache)
                rows.append(run_oracle(key, s, tables[tk]))
            else:
                rows.append(run(key, s, cache))
        return rows
    except Exception as e:  # logged and skipped by main(), never scored
        return [{"deal": path.stem, "error": f"{type(e).__name__}: {e}"}]


def _key(row: dict) -> tuple:
    return (row["deal"], *(row[f] for f in Setting._fields))


def bootstrap_ci(diff: np.ndarray, n: int = 2000, seed: int = 0) -> tuple[float, float]:
    """Paired bootstrap 95% CI of the mean of per-deal differences."""
    rng = np.random.default_rng(seed)
    means = diff[rng.integers(0, len(diff), (n, len(diff)))].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


COMPARED = ("sensitivity", "flip", "random", "checklist")  # router 6 minus each of these, per cell (H2, and the floor)
SLICES = {"all": lambda r: True, "flip": lambda r: r["flip"], "decoy": lambda r: r["has_decoy"],
          "interaction": lambda r: r["has_interaction"]}


def summarize(rows: list[dict]) -> dict:
    """Mean normalised regret per router and cell, and paired CIs for router 6 minus routers 3, 5, random, checklist."""
    cells: dict[tuple, dict[str, dict[str, float]]] = {}
    for r in rows:
        cell_key = (r["truth"], r["clue"], r["investigator"], r["level"], r["share"])
        cells.setdefault(cell_key, {}).setdefault(r["router"], {})[r["deal"]] = r
    out = []
    for (truth, clue, inv, level, share), by_router in sorted(cells.items()):
        for name, keep in SLICES.items():
            cell = {"truth": truth, "clue": clue, "investigator": inv, "level": level, "share": share, "slice": name,
                    "mean_regret": {}}
            for router, by_deal in by_router.items():
                vals = [r["regret"] for r in by_deal.values() if keep(r)]
                cell["mean_regret"][router] = float(np.mean(vals)) if vals else None
            six = by_router.get("regret", {})
            for other in COMPARED:
                deals = [d for d, r in six.items() if keep(r) and d in by_router.get(other, {})]
                if len(deals) >= 2:
                    diff = np.array([six[d]["regret"] - by_router[other][d]["regret"] for d in deals])
                    lo, hi = bootstrap_ci(diff)
                    cell[f"regret_minus_{other}"] = {"mean": float(diff.mean()), "ci95": [lo, hi], "n": len(deals),
                                                     "router6_wins": bool(diff.mean() < 0 and hi < 0)}
            cell["n"] = sum(keep(r) for r in six.values())
            out.append(cell)
    calib = {}
    for level in LEVELS:
        vals = [r["prior_inside"] for r in rows if r["level"] == level and r["router"] == "checklist"
                and r["truth"] == "generator" and r["clue"] == 0.5 and r["prior_inside"] is not None]
        if vals:
            calib[level] = float(np.mean(vals))
    swept = [r["found_by_sweep"] for r in rows if r["router"] != "oracle"]  # the oracle never sweeps
    sweep = float(np.mean(swept)) if swept else 0.0
    return {"cells": out, "prior_calibration": calib, "sweep_find_rate": sweep}


def _print(summary: dict) -> None:
    for c in summary["cells"]:
        if c["slice"] != "all" and c["n"] == 0:
            continue
        regrets = " ".join(f"{k}={v:.4f}" for k, v in c["mean_regret"].items() if v is not None)
        wins = " ".join(f"6<{k.removeprefix('regret_minus_')}:{'yes' if v['router6_wins'] else 'no'}"
                        f"({v['mean']:+.4f} [{v['ci95'][0]:+.4f},{v['ci95'][1]:+.4f}])"
                        for k, v in c.items() if k.startswith("regret_minus_"))
        print(f"{c['truth']:9s} clue={c['clue']:.1f} {c['investigator']:7s} {c['level']:6s} {c['share']:.2f} "
              f"{c['slice']:11s} n={c['n']:4d} {regrets} {wins}")
    print("prior calibration (share of problems inside the prior range):", summary["prior_calibration"])
    print("share of runs where the sweep found a forgotten problem:", round(summary["sweep_find_rate"], 4))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--deals", type=Path, default=Path("data/track_a"))
    ap.add_argument("--grid", choices=("headline", "full", "hints"), default="headline")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=None, help="use only the first N deals")
    args = ap.parse_args(argv)
    paths = sorted((args.deals / "truth").glob("*.json"))
    limit = None if args.grid == "headline" else FULL_DEALS
    if args.limit is not None:
        limit = args.limit if limit is None else min(limit, args.limit)
    paths = paths[:limit]
    settings = grid(args.grid)
    out = args.deals / "results.jsonl"
    rows = [json.loads(line) for line in out.read_text().splitlines()] if out.exists() else []
    done = {_key(r) for r in rows}
    todo = [(p, [s for s in settings if (p.stem, *s) not in done]) for p in paths]
    todo = [(p, pending) for p, pending in todo if pending]
    errors = 0
    with out.open("a") as fh, ProcessPoolExecutor(args.workers) as pool:
        mapper = map if args.workers == 1 else pool.map  # 1 = in-process (tests, debugging)
        for got in mapper(run_deal, [p for p, _ in todo], [pending for _, pending in todo]):
            for r in got:
                if "error" in r:
                    errors += 1
                    print(f"SKIPPED {r['deal']}: {r['error']}", file=sys.stderr)
                else:
                    fh.write(json.dumps(r) + "\n")
                    rows.append(r)
            fh.flush()
    wanted = {(p.stem, *s) for p in paths for s in settings}
    summary = summarize([r for r in rows if _key(r) in wanted])
    (args.deals / f"summary_{args.grid}.json").write_text(json.dumps(summary, indent=2))
    _print(summary)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
