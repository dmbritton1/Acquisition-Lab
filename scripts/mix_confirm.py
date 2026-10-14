"""The confirmation test of the mixed-model final test's two leads (docs/results/mix-confirm-prereg.md), run once
after mix_h_opus1 has run on the held-out sets. Reads answer keys and runs; never calls a model. From the repository
root:

  .venv/bin/python scripts/mix_confirm.py --out docs/results/mix-confirm.json"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from acqlab.bench import mix
from debate_pilot import versus
from haiku_team import verdict
from mix_final import OPUS_BASELINES, check, results, summary
from upside_pilot import keys, load

ROOT = Path(__file__).resolve().parents[1] / "data"
LEAD = "mix_h_opus1"  # lead 1: the Haiku reader and one Opus pricer, nothing else
# lead 2, the Haiku team on its own: the Haiku track's frozen winner on its held-out sets, the same prompts under
# their mix name on the fresh sets (pinned by test_mix's freeze test); no new runs
TEAM = {"test-r2": "haiku_lean_zero_w0", "pilot-r2u": "haiku_lean_zero_w0",
        "mix-test-r2": "mix_h_haiku3", "mix-test-r2u": "mix_h_haiku3"}


def one(res: dict[str, dict[str, dict]], system: str) -> dict:
    """`system` against s1b and s4 on one deal set: every summary, the paired ranges, verdicts and cost ratios."""
    cards = {s: summary(r) for s, r in res.items()}
    out = {"n": cards["s1b"]["n"], "systems": cards, "versus": {}, "verdicts": {}, "cost_ratio": {}}
    for b in OPUS_BASELINES:
        c = versus(res[system], res[b])
        out["versus"][b], out["verdicts"][b] = c, verdict(c)
        out["cost_ratio"][b] = cards[b]["cost"] / cards[system]["cost"] if cards[system]["cost"] else None
    return out


def pooled(res: dict[str, dict], names: tuple[str, ...]) -> dict:
    return {s: {f"{n}/{d}": x for n in names for d, x in res[n][s].items()} for s in res[names[0]]}


def lead_sets(root: Path, names: tuple[str, ...]) -> dict:
    """Lead 1's runs with the two baselines on each set, refused unless every run is there, traced, on the right
    models and made with the frozen mix."""
    res = {}
    for name in names:
        by = {s: load(root / name, s) for s in (*OPUS_BASELINES, LEAD)}
        check(by, keys(root / name, "test"), root, name)
        res[name] = {s: results(by, {}, s) for s in by}
    return res


def team_sets(root: Path, names: tuple[str, ...]) -> dict:
    """Lead 2's runs, already checked by the analyses that first read them; refused only if a deal is missing."""
    res = {}
    for name in names:
        ks = keys(root / name, "test")
        by = {"s1b": load(root / name, "s1b"), "s4": load(root / name, "s4"), "team": load(root / name, TEAM[name])}
        if bad := [s for s, rows in by.items() if set(rows) != set(ks)]:
            raise ValueError(f"{name}: {bad} do not cover the test split")
        res[name] = {s: results(by, {}, s) for s in by}
    return res


def analyse(root: Path) -> dict:
    held, fresh = mix.CONFIRM_SETS, mix.TEST_SETS
    lead = lead_sets(root, (*held, *fresh))
    lead1 = {n: one(lead[n], LEAD) for n in held} | {"all": one(pooled(lead, held), LEAD),
                                                      "with_discovery": one(pooled(lead, (*held, *fresh)), LEAD)}
    team = team_sets(root, (*held, *fresh))
    lead2 = {"held_out": one(pooled(team, held), "team"), "fresh": one(pooled(team, fresh), "team"),
             "all": one(pooled(team, (*held, *fresh)), "team")}
    a = lead1["all"]
    confirmed = a["systems"][LEAD]["cost"] < a["systems"]["s4"]["cost"] and a["verdicts"]["s4"] != "worse"
    return {"lead1": lead1, "lead2": lead2, "lead1_matches_s4_for_less": confirmed}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=ROOT, help="the directory holding the deal sets")
    ap.add_argument("--out", type=Path, required=True, help="where the analysis goes (never overwritten)")
    args = ap.parse_args(argv)
    if args.out.exists():  # one-shot: never overwrite a result already written
        print(f"Refusing: {args.out} already exists")
        return 1
    try:
        out = analyse(args.root)
    except ValueError as e:
        print(f"Refusing: {e}")
        return 1
    args.out.write_text(json.dumps(out, indent=2))
    print(json.dumps({"lead1": {n: c["verdicts"] for n, c in out["lead1"].items()},
                      "lead2": {n: c["verdicts"] for n, c in out["lead2"].items()},
                      "lead1_matches_s4_for_less": out["lead1_matches_s4_for_less"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
