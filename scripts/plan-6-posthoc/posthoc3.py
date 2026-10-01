"""Part 3: reading efficiency, and Solo's own notes priced by the team's engine. No Claude calls."""
import json
from pathlib import Path
import numpy as np
from acqlab.agents.record import Record, load_face
from acqlab.bench import pilot
from acqlab.generator.batch import AnswerKey
from acqlab.generator.traps import TRAPS
from acqlab.routers.track_a import bootstrap_ci, regret

D = Path("data/test-r2")
deals = json.loads((D / "splits.json").read_text())["test"][:160]
keys = {d: AnswerKey.model_validate_json((D / "truth" / f"{d}.json").read_text()) for d in deals}
tr = lambda s, d, suf="": [json.loads(x) for x in (D / "runs" / s / f"{d}{suf}.trace.jsonl").read_text().splitlines()]
row = lambda s, d: json.loads((D / "runs" / s / f"{d}.json").read_text())
s1b = {d: row("s1b", d) for d in deals}; s4 = {d: row("s4", d) for d in deals}

print("=== E. Where the pages went (share of pages read) ===")
for s in ("s1b", "s4", "s0"):
    cats = {"decision-relevant": 0, "decoy": 0, "only $0 facts": 0, "no facts": 0}; tot = 0; found = []
    for d in deals:
        k = keys[d]; facts = {f.trap: f for f in k.truth.facts}
        rel, dec = pilot.relevant_docs(k), pilot.decoy_docs(k)
        any_ev = {doc for e in k.evidence for doc in e.docs}
        reads = [(r["args"]["doc_id"], r["cost"]) for r in tr(s, d) if r["tool"] == "open_document" and not r["refused"]]
        opened = {doc for doc, _ in reads}
        for doc, c in reads:
            tot += c
            cats["decision-relevant" if doc in rel else "decoy" if doc in dec else "only $0 facts" if doc in any_ev else "no facts"] += c
        real = [e for e in k.evidence if facts[e.trap].amount > 0]
        found.append(np.mean([bool(set(e.docs) & opened) for e in real]) if real else np.nan)
    print(f"{s:4s} " + "  ".join(f"{c} {v/tot:.0%}" for c, v in cats.items()) + f" | opened a doc holding each real fact: {np.nanmean(found):.0%}")

print("\n=== F. Solo's own notes, priced and decided by the team's engine (in-sample, exploratory) ===")
def solo_engine(d, unnoted_chance):
    rec = Record(load_face(D / "deals" / d / "room"))
    notes = {}
    for r in tr("s1b", d):
        if r["tool"] == "note_issue" and not r["refused"]:
            notes[r["args"]["type"]] = r["args"]
    issues = []
    for t in TRAPS:
        e = rec.entries[t]
        if t in notes:
            n = notes[t]
            if float(n["chance"]) >= 1:
                e.proposed, e.known = True, (float(n["low"]), float(n["high"]))
            else:
                e.proposed, e.chance, e.low, e.high = True, float(n["chance"]), float(n["low"]), float(n["high"])
        elif unnoted_chance:
            e.proposed, e.chance = True, unnoted_chance
    return rec.decide()[0]
for name, uc in (("unnoted issues = no problem", 0.0), ("unnoted issues open at chance 0.39 (team's average)", 0.39)):
    reg = np.array([regret(keys[d], solo_engine(d, uc)) / keys[d].truth.deal.asking_price for d in deals])
    cor = np.mean([solo_engine(d, uc) == keys[d].truth.go for d in deals])
    base = np.array([s1b[d]["regret"] for d in deals]); t4 = np.array([s4[d]["regret"] for d in deals])
    print(f"{name:55s} regret {reg.mean():.4f} correct {cor:.1%}; minus S1b {np.mean(reg-base):+.4f} CI {np.round(bootstrap_ci(reg-base),4)}; "
          f"minus S4 {np.mean(reg-t4):+.4f} CI {np.round(bootstrap_ci(reg-t4),4)}")
print("S1b noted types per deal:", np.mean([len({r['args']['type'] for r in tr('s1b', d) if r['tool']=='note_issue'}) for d in deals]))
