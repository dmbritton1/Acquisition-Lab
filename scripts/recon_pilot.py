"""The reconciliation pilot's analysis (spec docs/superpowers/specs/2026-10-06-recon-pilot-design.md §5): the fixed
pick, each design against single Claude and the team, and the C and A measures. Reads finished runs and answer keys;
never calls a model. From the repository root:

  .venv/bin/python scripts/recon_pilot.py --data data/pilot-r2 --out docs/results/recon-pilot.json"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from acqlab.bench import analysis, recon, simrun
from acqlab.bench.referee import opened, rows as trace_rows
from acqlab.generator.batch import AnswerKey

SYSTEMS = ("s1b", "s4", *recon.DESIGNS)


def load(data: Path, system: str) -> dict[str, dict]:
    """deal -> row, first runs only (a repeat is <deal>.r<k>.json)."""
    return {p.stem: json.loads(p.read_text()) for p in sorted((data / "runs" / system).glob("*.json"))
            if "." not in p.stem}


def real_docs(key: AnswerKey) -> set[str]:
    """The documents that settle a real fact (amount > 0): the last of its evidence."""
    facts = {f.trap: f for f in key.truth.facts}
    return {e.docs[-1] for e in key.evidence if facts[e.trap].amount > 0}


def reached(key: AnswerKey, docs: list[str]) -> float | None:
    """Share of the real facts settled by these documents; None if the deal has none."""
    facts = {f.trap: f for f in key.truth.facts}
    real = [e for e in key.evidence if facts[e.trap].amount > 0]
    return float(np.mean([e.docs[-1] in set(docs) for e in real])) if real else None


def summary(rows: dict, traces: dict, keys: dict) -> dict:
    rs = list(rows.values())
    reach = [x for d in rows if (x := reached(keys[d], opened(traces[d]))) is not None]
    by_case = {}
    for case_type in sorted(set(r.get("case_type") for r in rs if "case_type" in r)):
        case_rows = [r for r in rs if r.get("case_type") == case_type]
        by_case[case_type] = {"n": len(case_rows), "regret": float(np.mean([r["regret"] for r in case_rows])),
                              "correct": float(np.mean([r["correct"] for r in case_rows]))}
    return {"n": len(rs), "regret": float(np.mean([r["regret"] for r in rs])),
            "correct": float(np.mean([r["correct"] for r in rs])),
            "false_go": sum(r["go"] and not r["correct"] for r in rs),
            "false_nogo": sum(not r["go"] and not r["correct"] for r in rs),
            "pages": float(np.mean([r["pages"] for r in rs])), "decoy_pages": float(np.mean([r["decoy_pages"] for r in rs])),
            "real_reached": float(np.mean(reach)) if reach else None,
            "cost": float(np.mean([r["cost_usd"] or 0 for r in rs])),
            "sessions": float(np.mean([r["sessions"] for r in rs])), "by_case": by_case}


def won_lost_tied(a: dict, b: dict) -> list[int]:
    diff = [a[d]["regret"] - b[d]["regret"] for d in sorted(set(a) & set(b))]
    return [sum(x < -1e-12 for x in diff), sum(x > 1e-12 for x in diff), sum(abs(x) <= 1e-12 for x in diff)]


def design_stats(rows: dict, traces: dict, keys: dict, pages: dict) -> dict:
    """Disputes, overrules, the referee's own reads; for A, the scouts' overlap and reach."""
    disputed = [d for d, r in rows.items() if r["disputed"]]
    over, ref_pages, ref_found = [0, 0], [], 0
    for d in disputed:
        r = rows[d]
        for i, call in enumerate(r["analysts"]):
            over[i] += bool(r["answered"] and call is not None and call["go"] != r["go"])
        paid = [x for x in traces[d] if x.get("step") == "referee" and x["tool"] == "open_document"
                and not x["refused"] and x["cost"] > 0]
        ref_pages.append(sum(x["cost"] for x in paid))
        ref_found += bool({x["args"]["doc_id"] for x in paid} & real_docs(keys[d]))
    out = {"disputes": len(disputed), "dispute_rate": len(disputed) / len(rows),
           "overruled_analyst_1": over[0], "overruled_analyst_2": over[1],
           "referee_new_pages_mean": float(np.mean(ref_pages)) if ref_pages else 0.0,
           "referee_reads_reached_a_real_fact": ref_found}
    if any(x.get("step") == "scout1" for t in traces.values() for x in t):
        scouts = {d: [opened([x for x in traces[d] if x.get("step") == s]) for s in ("scout1", "scout2")]
                  for d in rows}
        out["overlap_pages_mean"] = float(np.mean([sum(pages[d][x] for x in set(a) & set(b))
                                                   for d, (a, b) in scouts.items()]))
        for i, label in enumerate(("scout1", "scout2")):
            r = [x for d, s in scouts.items() if (x := reached(keys[d], s[i])) is not None]
            out[f"{label}_real_reached"] = float(np.mean(r)) if r else None
        r = [x for d, s in scouts.items() if (x := reached(keys[d], s[0] + s[1])) is not None]
        out["scouts_together_real_reached"] = float(np.mean(r)) if r else None
    return out


def sizing(chosen: dict, s1b: dict) -> dict:
    """Spec §5.5: deals for 80% and 90% power against single Claude, at the pilot's gap and at half of it."""
    ds = sorted(set(chosen) & set(s1b))
    diff = np.array([chosen[d]["regret"] - s1b[d]["regret"] for d in ds])
    gap, sd = float(diff.mean()), float(diff.std(ddof=1))
    if gap >= 0 or sd == 0:
        return {"gap": gap, "sd": sd, "note": "no gain over single Claude, so nothing to size"}
    return {"gap": gap, "sd": sd} | {label: {"power_80": simrun.deals_needed(g, sd, 0.8),
                                             "power_90": simrun.deals_needed(g, sd, 0.9)}
                                     for label, g in (("full", -gap), ("half", -gap / 2))}


def analyse(data: Path) -> dict:
    by = {s: load(data, s) for s in SYSTEMS}
    deals = sorted(set().union(*by.values()))
    keys = {d: AnswerKey.model_validate_json((data / "truth" / f"{d}.json").read_text()) for d in deals}
    pages = {d: {x["id"]: x["pages"] for x in json.loads((data / "deals" / d / "room" / "index.json").read_text())
                 ["documents"]} for d in deals}
    traces = {s: {d: trace_rows(data / "runs" / s / f"{d}.trace.jsonl") for d in by[s]} for s in SYSTEMS}
    out = {"deals": len(deals), "pick": recon.pick(by),
           "systems": {s: summary(by[s], traces[s], keys) for s in SYSTEMS},
           "versus": {d: {b: analysis.compare(by[d], by[b]) | {"won_lost_tied": won_lost_tied(by[d], by[b])}
                          for b in ("s1b", "s4")} for d in recon.DESIGNS},
           "designs": {d: design_stats(by[d], traces[d], keys, pages) for d in recon.DESIGNS}}
    out["sizing"] = sizing(by[out["pick"]["chosen"]], by["s1b"])
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    if args.out.exists():  # one-shot, like the Plan 6 analysis: never overwrite a result already written
        print(f"Refusing: {args.out} already exists")
        return 1
    out = analyse(args.data)
    args.out.write_text(json.dumps(out, indent=2))
    print(json.dumps(out["pick"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
