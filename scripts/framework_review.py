"""Read-only, exploratory audit of saved runs. Never invokes an LLM.

Run from the repository root: .venv/bin/python scripts/framework_review.py DATA_ROOT
where DATA_ROOT contains cal-r2, heldout-r2 and test-r2. Prints JSON to stdout.
"""
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from acqlab.agents.committer import check
from acqlab.agents.record import Record, load_face, settle_weights
from acqlab.bench import analysis, valuer


def audit(root):
    data = root / "test-r2"
    by, real, plans, rows = analysis.load(data)
    ds = sorted(by["s4"])
    a, b = by["s1b"], by["s4"]
    out = {"scope": "Exploratory audit, no new model runs; test data must not select a new policy",
           "main_comparison": analysis.compare(b, a), "systems": {}}
    for s in ("s1b", "s3", "s4", "s0"):
        rs = list(by[s].values())
        out["systems"][s] = {"n": len(rs), "regret": float(np.mean([r["regret"] for r in rs])),
                              "accuracy": float(np.mean([r["correct"] for r in rs])),
                              "cost": float(np.mean([r["cost_usd"] for r in rs])),
                              "tokens": {k: float(np.mean([r["tokens"][k] for r in rs]))
                                         for k in rs[0]["tokens"]}}
    wins = [d for d in ds if b[d]["regret"] < a[d]["regret"] - 1e-12]
    losses = [d for d in ds if b[d]["regret"] > a[d]["regret"] + 1e-12]
    shared = [d for d in ds if not a[d]["correct"] and not b[d]["correct"]]
    out["complementarity"] = {"team_wins": len(wins), "team_losses": len(losses),
        "ties": len(ds) - len(wins) - len(losses), "both_wrong": len(shared),
        "oracle_selector_accuracy": 1 - len(shared) / len(ds),
        "oracle_selector_regret": float(np.mean([min(a[d]["regret"], b[d]["regret"]) for d in ds])),
        "warning": "Oracle selection uses truth: a ceiling, not a runnable system; separate reading budgets."}
    counters, obligations, records, barriers, endpoint_mismatches = Counter(), [], [], [], []
    for d in ds:
        room = data / "deals" / d / "room"
        trace = [json.loads(x) for x in (data / "runs" / "s4" / f"{d}.trace.jsonl").read_text().splitlines()]
        rec = valuer.replay(room, trace)
        records.append(rec)
        counters["final_open"] += sum(e.known is None and e.chance > 0 for e in rec.entries.values())
        counters["final_committed"] += sum(e.known is not None for e in rec.entries.values())
        counters["final_open_positive_low"] += sum(e.known is None and e.chance > 0 and e.low > 0
                                                    for e in rec.entries.values())
        pages = {x["id"]: x["pages"] for x in json.loads((room / "index.json").read_text())["documents"]}
        budget = json.loads((room / "index.json").read_text())["default_budget"]
        key = json.loads((data / "truth" / f"{d}.json").read_text())
        for fact in key["truth"]["facts"]:
            entry = rec.entries[fact["trap"]]
            if entry.known is not None:
                wanted = fact["documented"] or (fact["amount"], fact["amount"])
                if any(abs(x-y) > .051 for x, y in zip(entry.known, wanted)):
                    endpoint_mismatches.append({"deal": d, "type": fact["trap"], "committed": entry.known,
                                               "documented": wanted, "team_correct": b[d]["correct"]})
        first_challenge = next((i for i, r in enumerate(trace)
                                if r["tool"] == "challenge" and not r.get("refused")), len(trace))
        midpoint_spent = sum(r["cost"] for r in trace[:first_challenge])
        for doc, cost in pages.items():
            if cost > budget / 2 and cost <= budget:
                ev = [e["trap"] for e in key["evidence"] if e["docs"][-1] == doc]
                barriers.append({"deal": d, "doc": doc, "pages": cost, "budget": budget,
                                 "remaining_at_first_challenge": budget - midpoint_spent,
                                 "now_unaffordable": cost > budget - midpoint_spent,
                                 "settles": ev,
                                 "still_open": [t for t in ev if rec.entries[t].known is None],
                                 "team_wrong": not b[d]["correct"]})
        spent, reads = 0, set()
        for i, r in enumerate(trace):
            spent += r["cost"]
            if r.get("refused"):
                continue
            if r["tool"] == "open_document":
                reads.add(r["args"]["doc_id"])
            if r["tool"] == "propose":
                counters["lead_turns"] += 1
            if r["tool"] != "challenge":
                continue
            counters["challenge_turns"] += 1
            counters["flagged_pair_answers"] += len(r["args"]["pairs"])
            for o in r["args"]["objections"]:
                counters["objections"] += 1
                counters["objection_" + o["kind"]] += 1
                unread = [x for x in o["docs"] if x not in reads and x in pages]
                after = {rr["args"]["doc_id"] for rr in trace[i+1:]
                         if rr["tool"] == "open_document" and not rr.get("refused")}
                obligations.append({"deal": d, "type": o["type"], "unread": unread,
                                    "budget_left": budget - spent,
                                    "any_affordable": any(pages[x] <= budget - spent for x in unread),
                                    "any_read_after": bool(set(unread) & after)})
    unread = [o for o in obligations if o["unread"]]
    out["trace_counts"] = dict(counters)
    out["committed_endpoint_mismatches"] = endpoint_mismatches
    out["challenger_unread_obligations"] = {"n": len(unread),
        "any_named_doc_read_later": sum(o["any_read_after"] for o in unread),
        "affordable_at_objection": sum(o["any_affordable"] for o in unread),
        "affordable_but_no_named_doc_read_later": sum(o["any_affordable"] and not o["any_read_after"] for o in unread),
        "note": "Counts objections, not unique issues; not all objections merit investigation."}
    out["midpoint_barriers"] = {"long_document_candidates": len(barriers),
        "unaffordable_after_first_pass": sum(x["now_unaffordable"] for x in barriers),
        "documents_with_still_open_evidence_now_unaffordable": sum(x["now_unaffordable"] and bool(x["still_open"])
                                                                  for x in barriers),
        "deals_with_such_open_evidence": len({x["deal"] for x in barriers if x["now_unaffordable"] and x["still_open"]}),
        "wrong_deals_with_such_open_evidence": len({x["deal"] for x in barriers if x["now_unaffordable"]
                                                    and x["still_open"] and x["team_wrong"]}),
        "by_document": {doc: {"candidates": sum(x["doc"] == doc for x in barriers),
                             "unaffordable": sum(x["doc"] == doc and x["now_unaffordable"] for x in barriers)}
                        for doc in sorted({x["doc"] for x in barriers})},
        "note": "Structural opportunity only. A long document need not be optimal; no counterfactual run."}
    locations, weights, hinted, counts = {}, {}, {}, Counter()
    for batch in ("cal-r2", "heldout-r2"):
        practice = root / batch
        deals = json.loads((practice / "splits.json").read_text())["dev"]
        for deal in deals:
            key = json.loads((practice / "truth" / f"{deal}.json").read_text())
            room = practice / "deals" / deal / "room"
            pp = {x["id"]: x["pages"] for x in json.loads((room / "index.json").read_text())["documents"]}
            tr = [json.loads(x) for x in (practice / "runs" / "s4" / f"{deal}.trace.jsonl").read_text().splitlines()]
            first = next(r for r in tr if r["tool"] == "propose" and not r.get("refused"))
            named = {i["type"]: i["docs"] for i in first["args"]["issues"]}
            for ev in key["evidence"]:
                t, dest = ev["trap"], ev["docs"][-1]
                dest = "contract" if dest.startswith("contract_") else dest
                locations.setdefault(t, Counter())[dest] += 1
                counts[t] += 1
                for doc, weight in settle_weights(t, pp, set(), []).items():
                    kind = "contract" if doc.startswith("contract_") else doc
                    weights.setdefault(t, Counter())[kind] += weight
                hinted.setdefault(t, []).append(settle_weights(t, pp, set(), named.get(t, [])).get("board_minutes", 0))
    out["practice_source_locations"] = {t: {"n": counts[t], "observed": dict(locations[t]),
        "router_mean_weight_without_named_hints": {k: v / counts[t] for k, v in weights[t].items()},
        "router_board_minutes_weight_with_logged_opening_hints": float(np.mean(hinted[t]))}
        for t in locations}
    # Three minimal interface probes, without changing production code.
    pages = {"qoe": 8, "audited": 14, "cim": 11, "board_minutes": 2, "legal": 2}
    w0 = settle_weights("addback", pages, set(), [])
    w1 = settle_weights("addback", pages, set(), ["audited"])
    rec = Record(records[0].face)
    rec.plan([{"type": "debt_like", "chance": .5, "low": 1, "high": 10, "docs": []}])
    issue1 = rec.issue("debt_like")
    rec.entries["debt_like"].low = 9
    issue2 = rec.issue("debt_like")
    text = "The company has a debt-like obligation of $9.0M payable at closing."
    commit, errors = check({"type": "debt_like", "status": "value", "value": 0,
                           "quotes": [{"doc_id": "audited", "text": text}]}, {"audited": text})
    out["interface_probes"] = {"naming_audited_changes_addback_weights": w0 != w1,
        "before_weights": w0, "after_weights": w1,
        "changing_open_low_1_to_9_changes_priced_issue": issue1 != issue2,
        "zero_claim_against_positive_quote_accepted": commit is not None and not errors,
        "zero_claim_commit": commit}
    # Compare industry slices; descriptive only, all within the same acquisition domain.
    out["industry_slices"] = {}
    inds = {}
    for d in ds:
        key = json.loads((data / "truth" / f"{d}.json").read_text())
        industry = key["truth"]["base"].get("industry", key["truth"]["base"].get("kind", "unknown"))
        if isinstance(industry, dict):
            industry = json.dumps(industry, sort_keys=True)
        inds.setdefault(industry, []).append(d)
    for ind, sub in inds.items():
        out["industry_slices"][ind] = analysis.compare(b, a, deals=sub)
    return out


if __name__ == "__main__":
    print(json.dumps(audit(Path(sys.argv[1])), indent=2))
