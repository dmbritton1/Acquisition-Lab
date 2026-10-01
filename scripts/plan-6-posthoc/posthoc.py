"""Post-hoc, exploratory look at the Plan 6 runs. No Claude calls. Reads data/test-r2 only."""
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from acqlab.bench import pilot, valuer
from acqlab.generator.batch import AnswerKey
from acqlab.routers.track_a import bootstrap_ci

D = Path("data/test-r2")
deals = json.loads((D / "splits.json").read_text())["test"][:160]
keys = {d: AnswerKey.model_validate_json((D / "truth" / f"{d}.json").read_text()) for d in deals}
rows = [json.loads(p.read_text()) for s in pilot.ALL for p in sorted((D / "runs" / s).glob("test-*.json"))]
by = {s: {r["deal"]: r for r in rows if r["system"] == s and r.get("rep", 0) == 0} for s in pilot.ALL}
s1b_r1 = {r["deal"]: r for r in rows if r["system"] == "s1b" and r.get("rep") == 1}
by["s3"] = pilot.s3_rows(rows, 2)
by["s1b_matched"] = pilot.s1b_matched(by["s1b"], by["s4"])
s1b, s4 = by["s1b"], by["s4"]
trace = lambda s, d: [json.loads(x) for x in (D / "runs" / s / f"{d}.trace.jsonl").read_text().splitlines()]
ask = lambda d: keys[d].truth.deal.asking_price
P = print


def hdr(t):
    P(f"\n=== {t} ===")


hdr("1. Error direction (false NO-GO = passed on a good deal; false GO = bought a bad one)")
for s in ("s1b", "s3", "s4", "s1b_matched", "s4_llmdecides", "s4_noengine", "s0"):
    rs = by[s]
    fn = [d for d in deals if d in rs and not rs[d]["go"] and keys[d].truth.go]
    fg = [d for d in deals if d in rs and rs[d]["go"] and not keys[d].truth.go]
    P(f"{s:14s} falseNOGO {len(fn):3d} (regret {sum(rs[d]['regret'] for d in fn)/160:.4f})  "
      f"falseGO {len(fg):3d} (regret {sum(rs[d]['regret'] for d in fg)/160:.4f})  NO-GO rate {np.mean([not rs[d]['go'] for d in rs]):.2f}")
P(f"truth NO-GO rate {np.mean([not keys[d].truth.go for d in deals]):.2f}; face NO-GO rate {np.mean([not keys[d].truth.face_go for d in deals]):.2f}")

hdr("1b. Errors by case type and direction, S1b vs S4")
for c in ("clean", "decoy", "flip", "interaction", "unresolvable"):
    ds = [d for d in deals if keys[d].truth.case_type == c]
    out = []
    for s in ("s1b", "s4"):
        fn = sum(not by[s][d]["go"] and keys[d].truth.go for d in ds)
        fg = sum(by[s][d]["go"] and not keys[d].truth.go for d in ds)
        out.append(f"{s}: falseNO {fn:2d} falseGO {fg:2d}")
    tg = sum(keys[d].truth.go for d in ds)
    P(f"{c:13s} n={len(ds):3d} truthGO={tg:3d} faceGO={sum(keys[d].truth.face_go for d in ds):3d} | " + " | ".join(out))

hdr("2. Win/loss S4 vs S1b (per-deal regret)")
diff = {d: s4[d]["regret"] - s1b[d]["regret"] for d in deals}
w = [d for d in deals if diff[d] < -1e-12]; l = [d for d in deals if diff[d] > 1e-12]
P(f"S4 better on {len(w)}, worse on {len(l)}, same on {160-len(w)-len(l)}")
P(f"sum of S4 gains {-sum(diff[d] for d in w):.3f}, sum of S4 losses {sum(diff[d] for d in l):.3f} (per-deal units)")
top = sorted(deals, key=lambda d: abs(diff[d]), reverse=True)[:12]
for d in top:
    t = keys[d].truth
    P(f"  {d} {t.case_type:12s} truthGO={t.go!s:5s} S1b={s1b[d]['go']!s:5s} S4={s4[d]['go']!s:5s} diff={diff[d]:+.4f}")
gains = np.sort([-diff[d] for d in w])[::-1]
P(f"share of S4's total gain from its top 5 wins: {gains[:5].sum()/gains.sum():.0%}")

hdr("3. Signed walk-away bias ((estimate − truth)/ask; negative = too low = pessimistic)")
for s in ("s1b", "s4", "s4_noengine", "s0"):
    b = {c: np.mean([(by[s][d]["walk_away"] - keys[d].truth.walk_away) / ask(d) for d in deals
                     if keys[d].truth.case_type == c]) for c in ("clean", "decoy", "flip", "interaction", "unresolvable")}
    allb = np.mean([(by[s][d]["walk_away"] - keys[d].truth.walk_away) / ask(d) for d in deals])
    P(f"{s:12s} all {allb:+.4f} | " + " ".join(f"{c} {v:+.4f}" for c, v in b.items()))

hdr("4. S4's final record vs the truth (replayed offline, per issue)")
status = Counter(); per_deal = {}
for d in deals:
    rec = valuer.replay(D / "deals" / d / "room", trace("s4", d))
    facts = {f.trap: f for f in keys[d].truth.facts}
    st = {}
    for t, e in rec.entries.items():
        f = facts[t]
        real = f.amount > 0
        if e.known is not None:
            lo, hi = e.known
            truthv = f.realized
            ok = lo - 0.05 <= truthv <= hi + 0.05 and (hi - lo) <= max(0.1, 0.05 * max(truthv, 1))
            kind = "committed-right" if ok else ("committed-range" if lo - 0.05 <= truthv <= hi + 0.05 else "committed-wrong")
        elif e.proposed and e.chance > 0:
            kind = "open"
        else:
            kind = "dropped"
        st[t] = (kind, f.role, e)
        status[(f.role, kind)] += 1
    per_deal[d] = (rec, st)
for role in ("flipper", "interaction", "unresolvable", "decoy", "clean"):
    P(f"{role:13s} " + "  ".join(f"{k} {status[(role, k)]}" for k in
                                  ("committed-right", "committed-range", "committed-wrong", "open", "dropped")))

hdr("4b. S4's wrong calls: what in the record drove them")
for d in deals:
    if s4[d]["correct"]:
        continue
    rec, st = per_deal[d]
    t = keys[d].truth
    opn = [(k, round(e.chance, 2), round(e.high, 1), role) for k, (kind, role, e) in st.items() if kind == "open"]
    wrong = [(k, e.known, round(next(f.realized for f in t.facts if f.trap == k), 2), role)
             for k, (kind, role, e) in st.items() if kind in ("committed-wrong",)]
    pt = rec.point()
    from acqlab.agents.record import Record  # noqa
    P(f"{d} {t.case_type:12s} truth={'GO' if t.go else 'NO'} S4={'GO' if s4[d]['go'] else 'NO'} "
      f"trueWA/ask={t.walk_away/ask(d):.3f} S4WA/ask={s4[d]['walk_away']/ask(d):.3f} pointGO={rec._go(pt)} "
      f"open={opn} wrong={wrong} decoy_pages={s4[d]['decoy_pages']}")

hdr("5. Counterfactual engine calls on S4's own record (in-sample, exploratory)")


def score_go(d, go):
    k = keys[d]
    return pilot.regret(k, go) / ask(d) if hasattr(pilot, "regret") else None


from acqlab.routers.track_a import regret  # noqa


def cf(name, fn):
    reg, cor = [], []
    for d in deals:
        rec, st = per_deal[d]
        go = fn(d, rec, st)
        reg.append(regret(keys[d], go) / ask(d)); cor.append(go == keys[d].truth.go)
    dd = np.array(reg) - np.array([s1b[d]["regret"] for d in deals])
    P(f"{name:52s} regret {np.mean(reg):.4f} correct {np.mean(cor):.1%}  vs S1b {dd.mean():+.4f} CI {np.round(bootstrap_ci(dd), 4)}")
    return reg


cf("as run (engine, open issues priced)", lambda d, r, st: r.decide()[0])
cf("point: committed values only, open issues = 0", lambda d, r, st: r._go(r.point()))


def no_open(d, r, st):
    import copy
    r2 = copy.deepcopy(r)
    for e in r2.entries.values():
        if e.known is None:
            e.chance = 0.0
    return r2.decide()[0]


cf("engine with open issues dropped", no_open)


def halved(d, r, st):
    import copy
    r2 = copy.deepcopy(r)
    for e in r2.entries.values():
        if e.known is None:
            e.chance *= 0.5
    return r2.decide()[0]


cf("engine with open-issue chances halved", halved)


def truth_reads(d, r, st):
    a = r.point()
    for f in keys[d].truth.facts:
        if st[f.trap][0].startswith("committed"):
            a[f.trap] = f.realized
    return r._go(a)


cf("point, committed values replaced by truth", truth_reads)

hdr("6. Noise: S1b run 1 vs run 2 on the same deals")
same = np.mean([s1b[d]["go"] == s1b_r1[d]["go"] for d in deals])
rd = np.array([s1b[d]["regret"] - s1b_r1[d]["regret"] for d in deals])
P(f"S1b agrees with itself on {same:.1%} of calls; mean regret r0 {np.mean([s1b[d]['regret'] for d in deals]):.4f} "
  f"r1 {np.mean([s1b_r1[d]['regret'] for d in deals]):.4f}; r0−r1 CI {np.round(bootstrap_ci(rd), 4)}")
P(f"S4 vs S1b call agreement {np.mean([s4[d]['go'] == s1b[d]['go'] for d in deals]):.1%}")
dd = np.array([diff[d] for d in deals])
sd = dd.std(ddof=1)
for eff in (0.0038, 0.0050):
    n80 = ((1.96 + 0.84) * sd / eff) ** 2
    P(f"sd of per-deal S4−S1b {sd:.4f}: deals for 80% power at effect {eff}: {n80:.0f}")

hdr("7. Close calls: error rate by |true walk-away − ask| / ask")
bins = [0, 0.05, 0.10, 0.20, 1.0]
for lo, hi in zip(bins, bins[1:]):
    ds = [d for d in deals if lo <= abs(keys[d].truth.walk_away / ask(d) - 1) < hi]
    P(f"margin {lo:.2f}-{hi:.2f}: n={len(ds):3d} " + "  ".join(
        f"{s} wrong {sum(not by[s][d]['correct'] for d in ds):2d} regret {np.mean([by[s][d]['regret'] for d in ds]):.4f}"
        for s in ("s1b", "s4")))

hdr("8. Decoy deals in detail")
for d in [d for d in deals if keys[d].truth.case_type == "decoy"]:
    rec, st = per_deal[d]
    t = keys[d].truth
    dec = [(k, round(f.realized, 1), st[k][0], (round(st[k][2].known[0], 1), round(st[k][2].known[1], 1)) if st[k][2].known else
            (round(st[k][2].chance, 2), round(st[k][2].high, 1))) for k in st for f in t.facts if f.trap == k and f.role == "decoy"]
    if s4[d]["correct"] and s1b[d]["correct"]:
        continue
    P(f"{d} truth={'GO' if t.go else 'NO'} S1b={'GO' if s1b[d]['go'] else 'NO'} S4={'GO' if s4[d]['go'] else 'NO'} "
      f"trueWA/ask={t.walk_away/ask(d):.3f} S4WA/ask={s4[d]['walk_away']/ask(d):.3f} S1bWA/ask={s1b[d]['walk_away']/ask(d):.3f} "
      f"decoy={dec} S4 open={[(k, round(e.chance,2), round(e.high,1)) for k,(kind,_,e) in st.items() if kind=='open']}")

hdr("9. Ablations on the first 40 (call disagreements with S4)")
first40 = deals[:40]
for s in ("s4_nochal", "s4_nosweep"):
    dis = [d for d in first40 if by[s][d]["go"] != s4[d]["go"]]
    P(f"{s}: disagrees with S4 on {len(dis)} of 40: " + ", ".join(
        f"{d}({keys[d].truth.case_type},{'S4 right' if s4[d]['correct'] else 'abl right'})" for d in dis))
    P(f"   S4 on these 40: regret {np.mean([s4[d]['regret'] for d in first40]):.4f} correct {np.mean([s4[d]['correct'] for d in first40]):.1%}; "
      f"S1b {np.mean([s1b[d]['regret'] for d in first40]):.4f} {np.mean([s1b[d]['correct'] for d in first40]):.1%}; "
      f"cost {np.mean([by[s][d]['cost_usd'] for d in first40]):.2f} vs S4 {np.mean([s4[d]['cost_usd'] for d in first40]):.2f}")
for s in ("s4_llmdecides", "s4_noengine"):
    dis = [d for d in deals if by[s][d]["go"] != s4[d]["go"]]
    P(f"{s}: disagrees with S4 on {len(dis)}; S4 right on {sum(s4[d]['correct'] for d in dis)}, ablation right on {sum(by[s][d]['correct'] for d in dis)}")

hdr("10. Reading: budget use and decoy reading")
for s in ("s1b", "s4", "s0"):
    used = np.mean([by[s][d]["pages"] / keys[d].budget for d in deals])
    P(f"{s:4s} pages/budget {used:.2f}  opened a decision-relevant doc on flip deals "
      f"{np.mean([by[s][d]['opened_relevant'] for d in deals if by[s][d]['flip'] and by[s][d]['opened_relevant'] is not None]):.1%}")
dp = [d for d in deals if keys[d].truth.case_type == "decoy"]
P(f"decoy deals: S4 decoy pages {np.mean([s4[d]['decoy_pages'] for d in dp]):.2f} vs S1b {np.mean([s1b[d]['decoy_pages'] for d in dp]):.2f}")
P(f"wrong decoy-deal calls when the decoy doc was read: S4 {sum((not s4[d]['correct']) and s4[d]['decoy_pages']>0 for d in dp)}"
  f"/{sum(s4[d]['decoy_pages']>0 for d in dp)}, unread {sum((not s4[d]['correct']) and s4[d]['decoy_pages']==0 for d in dp)}"
  f"/{sum(s4[d]['decoy_pages']==0 for d in dp)}; S1b read {sum((not s1b[d]['correct']) and s1b[d]['decoy_pages']>0 for d in dp)}"
  f"/{sum(s1b[d]['decoy_pages']>0 for d in dp)}, unread {sum((not s1b[d]['correct']) and s1b[d]['decoy_pages']==0 for d in dp)}"
  f"/{sum(s1b[d]['decoy_pages']==0 for d in dp)}")

hdr("11. Cost (see the write-up; the ratio below is cost per 0.001 of regret below B0)")
for s in ("s1b", "s3", "s4"):
    P(f"{s}: ${np.mean([by[s][d]['cost_usd'] for d in deals]):.3f}/deal, "
      f"$ per 0.001 regret below B0: {np.mean([by[s][d]['cost_usd'] for d in deals]) / ((np.mean([keys[d].truth.go != keys[d].truth.face_go for d in deals]) and 0.0356 - np.mean([by[s][d]['regret'] for d in deals])) * 1000):.3f}")
