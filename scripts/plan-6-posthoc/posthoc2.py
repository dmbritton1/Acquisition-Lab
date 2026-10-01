"""Part 2: calibration of the open-issue prices, and base-rate counterfactuals. No Claude calls."""
import copy, json
from collections import defaultdict
from pathlib import Path
import numpy as np
from acqlab.agents.knowledge import typical_high
from acqlab.bench import valuer
from acqlab.generator.batch import AnswerKey
from acqlab.generator.traps import TRAPS
from acqlab.routers.track_a import bootstrap_ci, regret

D = Path("data/test-r2")
deals = json.loads((D / "splits.json").read_text())["test"][:160]
keys = {d: AnswerKey.model_validate_json((D / "truth" / f"{d}.json").read_text()) for d in deals}
tr = lambda s, d: [json.loads(x) for x in (D / "runs" / s / f"{d}.trace.jsonl").read_text().splitlines()]
s4 = {d: json.loads((D / "runs/s4" / f"{d}.json").read_text()) for d in deals}
s1b = {d: json.loads((D / "runs/s1b" / f"{d}.json").read_text()) for d in deals}
recs = {d: valuer.replay(D / "deals" / d / "room", tr("s4", d)) for d in deals}

print("=== A. Deal Lead's first-plan chance vs how often the issue is real (amount > 0) ===")
pairs = []
for d in deals:
    t = tr("s4", d); plan = next(r for r in t if r["tool"] == "propose" and not r["refused"])
    facts = {f.trap: f for f in keys[d].truth.facts}
    for i in plan["args"]["issues"]:
        pairs.append((i["type"], float(i["chance"]), facts[i["type"]].amount > 0))
for trap in TRAPS:
    p = [(c, r) for tt, c, r in pairs if tt == trap]
    print(f"{trap:13s} n={len(p):3d} mean chance {np.mean([c for c,_ in p]):.2f}  actually real {np.mean([r for _,r in p]):.2f}")
print(f"{'all':13s} n={len(pairs)} mean chance {np.mean([c for _,c,_ in pairs]):.2f}  actually real {np.mean([r for *_,r in pairs]):.2f}")

print("\n=== B. Issues still open at the end: chance vs real, and was it searched? ===")
op = []
for d in deals:
    facts = {f.trap: f for f in keys[d].truth.facts}
    for tname, e in recs[d].entries.items():
        if e.known is None and e.proposed and e.chance > 0:
            op.append((tname, e.chance, facts[tname].amount > 0, bool(e.searched), facts[tname].amount, max(e.high, typical_high(tname, recs[d].face.teaser))))
print(f"open at end: {len(op)} issues on {sum(any(e.known is None and e.proposed and e.chance>0 for e in recs[d].entries.values()) for d in deals)} deals; "
      f"mean chance {np.mean([o[1] for o in op]):.2f}; actually real {np.mean([o[2] for o in op]):.2f}")
for s in (True, False):
    sub = [o for o in op if o[3] == s]
    print(f"  searched-and-not-found={s}: n={len(sub)} mean chance {np.mean([o[1] for o in sub]):.2f} real {np.mean([o[2] for o in sub]):.2f}")
real_open = [o for o in op if o[2]]
print(f"  when real, true size / priced top: mean {np.mean([o[4]/o[5] for o in real_open]):.2f} (engine assumes uniform 0..top: mean 0.50)")
print(f"  expected $ priced per open issue (chance x top/2) {np.mean([o[1]*o[5]/2 for o in op]):.1f}M vs true mean amount {np.mean([o[4] for o in op]):.1f}M")

print("\n=== C. Base rates in the non-test sets (cal-r2, heldout-r2) ===")
base = defaultdict(list); size = defaultdict(list)
for s in ("cal-r2", "heldout-r2"):
    for p in sorted((Path("data") / s / "truth").glob("*.json")):
        k = AnswerKey.model_validate_json(p.read_text())
        for f in k.truth.facts:
            base[f.trap].append(f.amount > 0)
            if f.amount > 0:
                size[f.trap].append(f.amount / typical_high(f.trap, k.truth.base.teaser))
print("deals:", len(base["addback"]))
for trap in TRAPS:
    print(f"{trap:13s} P(real) {np.mean(base[trap]):.2f}  size/top when real: mean {np.mean(size[trap]):.2f}")

print("\n=== D. Counterfactual engine calls on S4's record with open-issue beliefs replaced (in-sample, exploratory) ===")
def run(name, mod):
    reg, cor = [], []
    for d in deals:
        r = copy.deepcopy(recs[d])
        for tname, e in r.entries.items():
            if e.known is None and e.proposed and e.chance > 0:
                mod(tname, e, r)
        go = r.decide()[0]
        reg.append(regret(keys[d], go) / keys[d].truth.deal.asking_price); cor.append(go == keys[d].truth.go)
    dd = np.array(reg) - np.array([s1b[d]["regret"] for d in deals])
    fn = sum((not g) and keys[d].truth.go for g, d in zip([c for c in cor], deals))
    print(f"{name:58s} regret {np.mean(reg):.4f} correct {np.mean(cor):.1%} vs S1b {dd.mean():+.4f} CI {np.round(bootstrap_ci(dd),4)}")
run("as run", lambda t, e, r: None)
pr = {t: float(np.mean(base[t])) for t in TRAPS}
run("chance = cal/heldout base rate", lambda t, e, r: setattr(e, "chance", pr[t]))
def searched_down(t, e, r):
    if e.searched: e.chance *= 0.5
run("chance halved only if searched and not found", searched_down)
run("chance = base rate, halved if searched", lambda t, e, r: setattr(e, "chance", pr[t] * (0.5 if e.searched else 1)))
