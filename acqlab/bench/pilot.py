"""Pilot runner: single-agent systems on dev deals, scored against the answer keys (Plan 4a design §3; Plan 4b adds
S0 and S3, reframe design §4; Plan 5 adds S4 and its build steps, s4_1 to s4_3, reframe design §5).

  uv run python -m acqlab.bench.pilot --data data/v3 --n 3 --confirm-claude     # runs (uses the Claude subscription)
  uv run python -m acqlab.bench.pilot --data D --n 30 --systems s0 --flip-only --confirm-claude   # S0 on flip deals
  uv run python -m acqlab.bench.pilot --data D --n 30 --reps 3 --systems s1b --confirm-claude     # runs for S3
  uv run python -m acqlab.bench.pilot --data D --n 3 --systems s4 --confirm-claude   # S4 (a panel: many sessions)
  uv run python -m acqlab.bench.pilot --data data/v3 --report [--s3 3]           # summary, no Claude

Each run goes to <data>/runs/<system>/<deal>.json (repeat k>0: <deal>.r<k>.json; its tool trace beside it); reruns
skip finished runs.
Exit codes: 0 done; 2 Claude stopped (usage limit or a failed call: rerun later to resume); 3 refused (no
--confirm-claude).
"""
import argparse
import json
from collections.abc import Callable
from pathlib import Path

import numpy as np

from acqlab.agents import panel
from acqlab.agents.panel import STAGES
from acqlab.agents.server import MAX_CALLS
from acqlab.agents.solver import RunTimeout, solve
from acqlab.generator.batch import AnswerKey
from acqlab.llm import LLMUnavailable
from acqlab.routers.track_a import bootstrap_ci, regret

SYSTEMS = {"s1b": False, "s1b_router": True, "s0": False}  # name -> offered the router
UNBUDGETED = {"s0"}  # the reading ceiling: its budget is the whole room (main spec §4)
ALL = [*SYSTEMS, *STAGES]  # S4's build steps and S4 itself run as panels (acqlab.agents.panel)


def relevant_docs(key: AnswerKey) -> set[str]:
    """Documents holding a decision-relevant fact: a flipper, an interaction, or an unresolvable fact that flips the
    decision alone."""
    facts = {f.trap: f for f in key.truth.facts}
    return {d for e in key.evidence for d in e.docs
            if facts[e.trap].role in ("flipper", "interaction")
            or (facts[e.trap].role == "unresolvable" and facts[e.trap].alone_flips)}


def decoy_docs(key: AnswerKey) -> set[str]:
    facts = {f.trap: f for f in key.truth.facts}
    return {d for e in key.evidence for d in e.docs if facts[e.trap].role == "decoy"} - relevant_docs(key)


def floors(key: AnswerKey) -> dict:
    """No-AI reference points: normalised regret and walk-away error."""
    t, ask = key.truth, key.truth.deal.asking_price
    return {"always_go": regret(key, True) / ask, "always_no": regret(key, False) / ask,
            "b0": regret(key, t.face_go) / ask, "b0_walk_away_error": abs(t.face_walk_away - t.walk_away) / ask,
            "ask_walk_away_error": abs(ask - t.walk_away) / ask,
            "headroom": t.face_walk_away / ask - 1,  # face-value margin, visible to any agent via the free engine
            "ask": ask, "true_walk_away": t.walk_away}  # reference numbers, for combining runs (S3)


def margin_rule(floors: list[dict]) -> tuple[float, float]:
    """Best "go iff headroom >= c" rule, c picked in hindsight on these same deals: (threshold, mean regret).
    ponytail: in-sample threshold, so it overstates the shortcut; that makes it a harder floor to beat, not easier."""
    h = np.array([f["headroom"] for f in floors])
    go, no = np.array([f["always_go"] for f in floors]), np.array([f["always_no"] for f in floors])
    return min(((float(c), float(np.where(h >= c, go, no).mean())) for c in np.append(np.unique(h), 0.0)),
               key=lambda x: (x[1], x[0]))


def score(key: AnswerKey, system: str, trace: list[dict], cli: dict | None, status: str) -> dict:
    """One run's row. A run that never submitted is scored with B0's decision and marked answered=False."""
    t, ask = key.truth, key.truth.deal.asking_price
    submit = next((r for r in trace if r["tool"] == "submit" and not r["refused"]), None)
    go = submit["args"]["go"] if submit else t.face_go
    wa = float(submit["args"]["walk_away"]) if submit else t.face_walk_away
    reads = [(r["args"]["doc_id"], r["cost"]) for r in trace if r["tool"] == "open_document" and not r["refused"]]
    relevant, decoys = relevant_docs(key), decoy_docs(key)
    notes = {r["args"]["type"]: r["args"] for r in trace if r["tool"] == "note_issue" and not r["refused"]}
    first_plan = next((r for r in trace if r["tool"] == "propose" and not r["refused"]), None)
    for i in first_plan["args"]["issues"] if first_plan else []:  # S4: the Deal Lead's first proposal is its prior
        notes.setdefault(i["type"], i)
    facts = {f.trap: f for f in t.facts}
    # non-clean facts only, matching Track A's prior_inside (routers/track_a.py): a clean fact is never "in" a note
    inside = [n["low"] <= facts[k].realized <= n["high"] for k, n in notes.items() if facts[k].role != "clean"]
    usage = (cli or {}).get("usage", {})
    return {
        "deal": t.id, "system": system, "status": status, "answered": submit is not None, "go": go, "walk_away": wa,
        "regret": regret(key, go) / ask, "correct": go == t.go, "walk_away_error": abs(wa - t.walk_away) / ask,
        "flip": t.go != t.face_go, "case_type": t.case_type,
        "pages": sum(c for _, c in reads), "decoy_pages": sum(c for d, c in reads if d in decoys),
        "opened_relevant": bool(relevant & {d for d, _ in reads}) if relevant else None,
        "tool_calls": sum(r["tool"] != "initialize" for r in trace),  # the initialize row (F7) is not a tool call
        "rank_calls": sum(r["tool"] == "rank_issues" for r in trace),
        "prior_inside": float(np.mean(inside)) if inside else None,
        "tokens": {k: int(usage.get(k, 0)) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens",
                                                       "cache_creation_input_tokens")},
        "num_turns": (cli or {}).get("num_turns"), "duration_ms": (cli or {}).get("duration_ms"),
        "sessions": (cli or {}).get("sessions", 1 if cli else 0),
        "cost_usd": (cli or {}).get("total_cost_usd"), "models": sorted((cli or {}).get("modelUsage", {})),
        "env_keys": (cli or {}).get("env_keys"), "timeouts": (cli or {}).get("timeouts", 0),
        "floors": floors(key),
    }


def run(data: Path, n: int, systems: list[str], solver: Callable = solve, reps: int = 1,
        flip_only: bool = False, panel_solver: Callable = panel.solve) -> list[dict]:
    """Run each system `reps` times on the first n dev deals (only the decision-flip ones if flip_only), skipping
    finished runs. Raises LLMUnavailable to stop the batch."""
    deals = json.loads((data / "splits.json").read_text())["dev"][:n]
    rows = []
    for deal in deals:
        key = AnswerKey.model_validate_json((data / "truth" / f"{deal}.json").read_text())
        if flip_only and key.truth.go == key.truth.face_go:
            continue
        room = data / "deals" / deal / "room"
        whole = float(sum(d["pages"] for d in json.loads((room / "index.json").read_text())["documents"]))
        for system in systems:
            for rep in range(reps):
                out = data / "runs" / system / (f"{deal}.json" if rep == 0 else f"{deal}.r{rep}.json")
                if out.exists():
                    continue
                out.parent.mkdir(parents=True, exist_ok=True)
                trace_path = out.with_suffix(".trace.jsonl")
                trace_path.unlink(missing_ok=True)
                unbudgeted = system in UNBUDGETED
                # +MAX_CALLS so a search (1 unit each) never costs S0 a document it could otherwise open: its budget
                # is meant to be the whole room, not the whole room minus whatever it spends finding its way around
                budget = whole + MAX_CALLS if unbudgeted else key.budget
                kwargs = {"unbudgeted": True} if unbudgeted else {}
                try:
                    cli = (panel_solver(room, budget, trace_path, STAGES[system]) if system in STAGES else
                           solver(room, budget, trace_path, SYSTEMS[system], **kwargs))
                    status = "ok"
                except RunTimeout:
                    cli, status = None, "timeout"
                trace = [json.loads(x) for x in trace_path.read_text().splitlines()] if trace_path.exists() else []
                if status == "ok" and not trace:
                    raise LLMUnavailable(f"{system}/{deal}: the tool server never ran (no trace)")
                row = score(key, system, trace, cli, status) | {"rep": rep}
                out.write_text(json.dumps(row, indent=2))
                rows.append(row)
                print(f"{system:10s} {deal} r{rep}: regret {row['regret']:.3f} answered={row['answered']} "
                      f"pages={row['pages']}")
    return rows


def s3_rows(rows: list[dict], n: int) -> dict[str, dict]:
    """S3 (main spec §4), deal -> row: the majority go/no-go of the first n S1b runs (a tie is no-go, the cautious
    call) and their median walk-away. Pages, tokens and cost add up over the n runs. Deals with fewer runs are left
    out."""
    reps: dict[str, list[dict]] = {}
    for r in rows:
        if r["system"] == "s1b" and r.get("rep", 0) < n:
            reps.setdefault(r["deal"], []).append(r)
    out = {}
    for deal, rs in reps.items():
        if len(rs) < n:
            continue
        f, go = rs[0]["floors"], 2 * sum(r["go"] for r in rs) > n
        wa = float(np.median([r["walk_away"] for r in rs]))
        out[deal] = {
            "deal": deal, "system": "s3", "status": "timeout" if any(r["status"] == "timeout" for r in rs) else "ok",
            "answered": all(r["answered"] for r in rs), "go": go, "walk_away": wa,
            "regret": f["always_go"] if go else f["always_no"], "correct": go == (f["always_go"] <= f["always_no"]),
            "walk_away_error": abs(wa - f["true_walk_away"]) / f["ask"], "flip": rs[0]["flip"],
            "case_type": rs[0]["case_type"], "pages": sum(r["pages"] for r in rs),
            "decoy_pages": sum(r["decoy_pages"] for r in rs),
            "opened_relevant": None if rs[0]["opened_relevant"] is None else any(r["opened_relevant"] for r in rs),
            "rank_calls": 0, "prior_inside": None, "floors": f,
            "tokens": {k: sum(r["tokens"][k] for r in rs) for k in rs[0]["tokens"]},
            "cost_usd": sum(r["cost_usd"] or 0 for r in rs)}
    return out


def _mean(rows: list[dict], field: str) -> float | None:
    vals = [r[field] for r in rows if r[field] is not None]
    return float(np.mean(vals)) if vals else None


def summarize(rows: list[dict], s3_n: int | None = None) -> dict:
    """Each system over its own finished deals (first runs only; S3 from S1b's repeats), the no-AI floors over S1b's
    deals, and the Plan 4a checkpoint on deals both S1b and S1b + router finished. Regret is normalised by asking
    price."""
    first = [r for r in rows if r.get("rep", 0) == 0]
    by = {s: {r["deal"]: r for r in first if r["system"] == s} for s in ALL}
    if s3_n:
        by["s3"] = s3_rows(rows, s3_n)
    out: dict = {"n_deals": len(by["s1b"]), "systems": {}}
    for s in [s for s in by if by[s]]:
        rs = [by[s][d] for d in sorted(by[s])]
        flip = [r for r in rs if r["flip"]]
        # timed-out runs (and any run with no usage at all) would drag the token/cost means toward zero, so leave
        # them out of those two fields only; everything else still scores over every finished run (F5)
        scored = [r for r in rs if r.get("status") != "timeout" and any(r["tokens"].values())]
        out["systems"][s] = {
            "regret": _mean(rs, "regret"), "regret_flip": _mean(flip, "regret"), "correct": _mean(rs, "correct"),
            "walk_away_error": _mean(rs, "walk_away_error"), "opened_relevant_flip": _mean(flip, "opened_relevant"),
            "pages": _mean(rs, "pages"), "decoy_pages": _mean(rs, "decoy_pages"),
            "prior_inside": _mean(rs, "prior_inside"), "rank_calls": _mean(rs, "rank_calls"),
            "no_answer": sum(not r["answered"] for r in rs), "cost_usd": _mean(scored, "cost_usd"),
            "tokens": {k: float(np.mean([r["tokens"][k] for r in scored])) if scored else 0.0
                       for k in ("input_tokens", "output_tokens", "cache_read_input_tokens",
                                 "cache_creation_input_tokens")},
            "by_case": {c: _mean([r for r in rs if r["case_type"] == c], "regret")
                        for c in sorted({r["case_type"] for r in rs})},
            "sessions": _mean([{"sessions": r.get("sessions")} for r in rs], "sessions"),
            "timeouts": sum(r.get("timeouts", 0) for r in rs),  # S4's skipped turns
        }
        paired = sorted(set(by[s]) & set(by["s1b"])) if s != "s1b" else []
        if paired:  # S4's build-step check (reframe design §5): the same deals, against S1b
            diff = np.array([by[s][d]["regret"] - by["s1b"][d]["regret"] for d in paired])
            flip = [by[s][d]["regret"] - by["s1b"][d]["regret"] for d in paired if by["s1b"][d]["flip"]]
            ci = bootstrap_ci(diff) if len(diff) > 1 else (float(diff[0]), float(diff[0]))
            out["systems"][s]["vs_s1b"] = {"n": len(paired), "regret_diff": float(diff.mean()), "ci95": list(ci),
                                           "n_flip": len(flip), "regret_diff_flip": float(np.mean(flip)) if flip
                                           else None}
    base = [by["s1b"][d] for d in sorted(by["s1b"])]
    out["floors"] = {k: float(np.mean([r["floors"][k] for r in base])) if base else None
                     for k in ("always_go", "always_no", "b0", "b0_walk_away_error", "ask_walk_away_error")}
    if base:
        out["floors"]["margin_threshold"], out["floors"]["margin_rule"] = margin_rule([r["floors"] for r in base])
    flip = [d for d in sorted(set(by["s1b"]) & set(by["s1b_router"])) if by["s1b"][d]["flip"]]
    if flip:
        diff = np.array([by["s1b_router"][d]["regret"] - by["s1b"][d]["regret"] for d in flip])
        lo, hi = bootstrap_ci(diff) if len(diff) > 1 else (float(diff[0]), float(diff[0]))
        a, b = out["systems"]["s1b_router"], out["systems"]["s1b"]
        regret_lower = bool(diff.mean() < 0)
        evidence_more = (a["opened_relevant_flip"] or 0) > (b["opened_relevant_flip"] or 0)
        out["checkpoint"] = {
            "n_flip": len(flip), "regret_diff": float(diff.mean()), "ci95": [lo, hi],
            "regret_lower": regret_lower, "evidence_more": evidence_more,
            "verdict": "keep" if regret_lower and evidence_more else
                       "reframe" if not (regret_lower or evidence_more) else "mixed"}
    if "s4" in out["systems"]:  # S3's N (pre-registration): S4's tokens per deal over S1b's, all four kinds, on the
        # deals both answered with usage (paired, like vs_s1b)
        paired = [d for d in sorted(set(by["s4"]) & set(by["s1b"]))
                  if any(by["s4"][d]["tokens"].values()) and any(by["s1b"][d]["tokens"].values())]
        total = {s: sum(sum(by[s][d]["tokens"].values()) for d in paired) for s in ("s4", "s1b")}
        out["s3_n"] = max(1, round(total["s4"] / total["s1b"])) if total["s1b"] else None
    s1b = out["systems"]["s1b"]["regret"] if base else None
    out["b0_warning"] = s1b is not None and out["floors"]["b0"] is not None and s1b >= out["floors"]["b0"]
    out["margin_warning"] = s1b is not None and base != [] and s1b >= out["floors"]["margin_rule"]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--n", type=int, default=3, help="first n dev deals")
    ap.add_argument("--systems", default="s1b,s1b_router", help=f"comma-separated, from {', '.join(ALL)}")
    ap.add_argument("--reps", type=int, default=1, help="runs per system and deal (S3 combines S1b's)")
    ap.add_argument("--flip-only", action="store_true", help="only the decision-flip deals (S0's calibration use)")
    ap.add_argument("--s3", type=int, default=0, help="with --report: add S3 over this many S1b runs per deal")
    ap.add_argument("--confirm-claude", action="store_true", help="required to make real Claude calls")
    ap.add_argument("--report", action="store_true", help="summarise finished runs; no Claude calls")
    args = ap.parse_args(argv)
    if args.report:
        rows = [json.loads(p.read_text()) for s in ALL for p in sorted((args.data / "runs" / s).glob("*.json"))]
        for r in rows:  # floors depend only on the answer key: recompute so older run files get new floors too
            r["floors"] = floors(AnswerKey.model_validate_json((args.data / "truth" / f"{r['deal']}.json").read_text()))
        summary = summarize(rows, s3_n=args.s3 or None)
        (args.data / "runs").mkdir(parents=True, exist_ok=True)
        (args.data / "runs" / "summary.json").write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary, indent=2))
        return 0
    if not args.confirm_claude:
        print("Refusing to run: this uses your Claude subscription. Add --confirm-claude to proceed.")
        return 3
    try:
        run(args.data, args.n, [s for s in args.systems.split(",") if s], reps=args.reps, flip_only=args.flip_only)
    except LLMUnavailable as e:
        print(f"Claude stopped: {e}\nFinished runs are saved. Run the same command again (after any usage limit "
              "resets) to continue where it left off.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
