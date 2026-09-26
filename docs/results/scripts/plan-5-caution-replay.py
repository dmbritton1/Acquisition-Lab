"""Where S4's NO-GO lean comes from (Plan 5 held-out check): replay each run's final Deal Record from its trace,
check it reproduces the recorded call, then re-decide under what-ifs. Diagnostic only (answer keys used for
scoring, never in S4). Run from the repo root: uv run python docs/results/scripts/plan-5-caution-replay.py"""
import json
from pathlib import Path

import numpy as np

import acqlab.agents.record as R
from acqlab.agents.record import Record, load_face
from acqlab.generator.batch import AnswerKey
from acqlab.routers.routers import decide
from acqlab.routers.track_a import regret

BATCHES = {"cal-r2": Path("data/cal-r2"), "heldout": Path("data/heldout-r2")}
TYPICAL = R.typical_high


def replay(data: Path, deal: str):
    face = load_face(data / "deals" / deal / "room")
    rows = [json.loads(x) for x in (data / "runs" / "s4" / f"{deal}.trace.jsonl").read_text().splitlines()]
    rec, first = Record(face), None
    for r in rows:
        if r.get("refused"):
            continue
        if r["tool"] == "propose":
            rec.plan(r["args"]["issues"])
        elif r["tool"] == "report":
            rec.apply((r.get("result") or {}).get("commits", []))
        elif r["tool"] == "challenge":
            if first is None:  # the Lead's beliefs just before the Challenger first spoke
                first = {t: (e.proposed, e.chance, e.low, e.high) for t, e in rec.entries.items()}
            rec.challenge(r["args"]["objections"])
    for e in rec.entries.values():
        e.objections = []
    sub = next(r for r in rows if r["tool"] == "submit")["args"]
    return rec, first, sub


def call(rec: Record, **what_if) -> bool:
    saved = {t: (e.proposed, e.chance, e.low, e.high) for t, e in rec.entries.items()}
    try:
        R.typical_high = (lambda t, teaser: 0.0) if what_if.get("lead_range") else TYPICAL
        for t, e in rec.entries.items():
            if not e.open:
                continue
            if what_if.get("first") and what_if["first"].get(t):
                e.proposed, e.chance, e.low, e.high = what_if["first"][t]
            if "scale" in what_if:
                e.chance *= what_if["scale"]
            if what_if.get("open_zero"):
                e.proposed = False
        w = rec.worlds()[1]
        ask = rec.face.deal.asking_price
        return bool(np.median(w) >= ask) if what_if.get("median") else decide(w, ask)[0]
    finally:
        R.typical_high = TYPICAL
        for t, e in rec.entries.items():
            e.proposed, e.chance, e.low, e.high = saved[t]


WHAT_IFS = {
    "as run": {},
    "Lead's beliefs before the Challenger": "first",
    "open issues over the Lead's range only": {"lead_range": True},
    "open chances halved": {"scale": 0.5},
    "open issues ignored (face value)": {"open_zero": True},
    "median walk-away vs ask": {"median": True},
}

calib = []  # (assigned chance, real?) for issues still open at the end
for name, data in BATCHES.items():
    res = {k: [] for k in WHAT_IFS}
    mism, s1 = 0, []
    for i in range(30):
        deal = f"dev-{i:03d}"
        if not (data / "runs" / "s4" / f"{deal}.json").exists():
            continue
        key = AnswerKey.model_validate_json((data / "truth" / f"{deal}.json").read_text())
        ask = key.truth.deal.asking_price
        rec, first, sub = replay(data, deal)
        go0, _ = rec.decide()
        mism += go0 != sub["go"]
        s1.append(json.loads((data / "runs" / "s1b" / f"{deal}.json").read_text())["regret"])
        real = {f.trap: f.amount > 0 for f in key.truth.facts}
        for t, e in rec.entries.items():
            if e.open:
                calib.append((e.chance, real.get(t, False), name))
        for k, v in WHAT_IFS.items():
            go = call(rec, first=first) if v == "first" else call(rec, **v)
            res[k].append((go, key.truth.go, regret(key, go) / ask))
    print(f"\n== {name}: {len(s1)} deals, replay mismatches {mism}, S1b regret {np.mean(s1):.4f}")
    for k, rs in res.items():
        print(f"  {k:40} regret {np.mean([r[2] for r in rs]):.4f}  correct {sum(g == t for g, t, _ in rs):2d}"
              f"  wrong NO-GO {sum(t and not g for g, t, _ in rs)}  wrong GO {sum(g and not t for g, t, _ in rs)}")

ch = np.array([c for c, _, _ in calib]); re = np.array([r for _, r, _ in calib])
print(f"\nissues still open at the end: {len(calib)}, mean chance the Lead gave {ch.mean():.2f}, share actually real "
      f"{re.mean():.2f}")
for lo, hi in ((0, 0.25), (0.25, 0.4), (0.4, 1.01)):
    m = (ch >= lo) & (ch < hi)
    if m.any():
        print(f"  chance {lo:.2f}-{hi:.2f}: n={m.sum():3d}, real {re[m].mean():.2f}")
