"""The r2 profile's case mix, from a throwaway batch (no Claude calls):
  uv run python -m acqlab.generator.batch --out <dir> --dev 500 --test 0 --hand 0 --showcase 0 --seed 640000 --profile r2
  uv run python docs/results/scripts/plan-5-r2-mix.py <dir>"""
import collections
import json
import sys
from pathlib import Path

import numpy as np

t = [json.loads(p.read_text())["truth"] for p in sorted((Path(sys.argv[1]) / "truth").glob("*.json"))]
n = len(t)
go = np.array([x["go"] for x in t])
flip = np.array([x["go"] != x["face_go"] for x in t])
print(n, "deals | GO right:", go.sum(), f"({go.mean():.2f}) | decision flips: {flip.sum()} ({flip.mean():.2f})")
print("flips toward NO-GO:", sum(x["face_go"] and not x["go"] for x in t),
      "| toward GO:", sum((not x["face_go"]) and x["go"] for x in t))
print("case types:", dict(collections.Counter(x["case_type"] for x in t)))
print(f"share of issue facts that are real: {np.mean([f['amount'] > 0 for x in t for f in x['facts']]):.2f}")
rng = np.random.default_rng(0)
print("GO-right count in a random 30, 5/50/95%:",
      np.percentile([go[rng.choice(n, 30, replace=False)].sum() for _ in range(10000)], [5, 50, 95]))
