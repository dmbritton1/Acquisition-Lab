"""PAID (about $2 for 10 deals; make no run without the user's OK). Paid check 1 of the analyst board: on generated
deals whose true numbers are known, how often Haiku fills each number right, wrong or not at all, and how often the
board's call at Opus's worries (priced at the true numbers) matches the true call. Without --yes it prints the
estimate and stops. From the repository root:

  .venv/bin/python scripts/board_reading_check.py --data <set folder> --n 10 --out <new .json> [--yes]"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from board_sample import COMPANY_FIELDS, TEASER_FIELDS, checkouts  # the same checkout rule and field lists

from acqlab.app import steps
from acqlab.app.board import compute, face
from acqlab.app.ingest import ingest
from acqlab.app.store import load
from acqlab.app.verify import FIELDS

REFUSED = ("test-r2", "pilot-r2u")  # held-out sets, and mix-test-*


def score(field_value, truth) -> str:
    if field_value is None:
        return "blank"
    close = abs(field_value - truth) <= (1e-9 if truth == 0 else 0.01 * abs(truth))
    return "right" if close else "wrong"


def main(argv=None) -> dict | None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--n", type=int, default=10)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--home", type=Path)
    p.add_argument("--claude", help="the claude program (default: the real one; tests pass a fake)")
    p.add_argument("--yes", action="store_true", help="spend the money")
    args = p.parse_args(argv)
    data = args.data.expanduser().resolve()
    if data.name in REFUSED or data.name.startswith("mix-test-"):
        p.error(f"{data.name} is held out")
    if args.out.exists():
        p.error(f"{args.out} exists")
    home = (args.home or Path(tempfile.mkdtemp())).expanduser().resolve()
    if inside := [c for c in checkouts() if home.is_relative_to(c)]:
        p.error(f"--home must be outside the repository ({inside[0]}), not {home}")

    ids = sorted(d.name for d in (data / "deals").iterdir())[:args.n]
    todo = []  # (deal id, deal folder, engine.json)
    for d in ids:
        room = data / "deals" / d / "room"
        engine = load(room / "engine.json")
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp) / "teaser.md"
            t.write_text(load(room / "index.json")["teaser"])
            todo.append((d, ingest(home, engine["teaser"]["name"], engine["deal"]["asking_price"],
                                   {"teaser": t, "cim": room / "cim.md"}), engine))
    total = sum(steps.estimate(deal, s) for _, deal, _ in todo for s in ("read", "price"))
    print(f"{len(todo)} deals, estimated ${total:.2f}")
    if not args.yes:
        print("Nothing run. Add --yes to spend it.")
        return None

    fields = {f: {"right": 0, "wrong": 0, "blank": 0} for f in FIELDS}
    calls, cost, deals = {"right": 0, "wrong": 0}, 0.0, []
    for d, deal, engine in todo:
        truth = {k: engine["teaser"][k] for k in TEASER_FIELDS} | {k: engine["deal"]["company"][k] for k in COMPANY_FIELDS}
        read = steps.read(deal, claude=args.claude)
        verdicts = {f: score(read["numbers"][f]["value"], truth[f]) for f in FIELDS}
        for f, v in verdicts.items():
            fields[f][v] += 1
        settings = {g: engine["deal"][g] for g in ("financing", "policy")}
        mine = {f: {"value": v, "status": "you"} for f, v in truth.items()}
        worries = steps.price(deal, settings, claude=args.claude, numbers=mine)
        go = compute(face(truth, settings, engine["deal"]["asking_price"], engine["teaser"]["name"], ""),
                     worries["worries"], set())["go"]
        true_go = load(data / "truth" / f"{d}.json")["truth"]["go"]
        calls["right" if go == true_go else "wrong"] += 1
        cost += read["cost"] + worries["cost"]
        deals.append({"deal": d, "fields": verdicts, "go": go, "true_go": true_go, "cost": read["cost"] + worries["cost"]})
    out = {"fields": fields, "calls": calls, "cost": cost, "deals": deals}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2))
    for f, c in fields.items():
        print(f"{f:18} right {c['right']:3}  wrong {c['wrong']:3}  blank {c['blank']:3}")
    print(f"calls right {calls['right']}, wrong {calls['wrong']}; spent ${cost:.2f}; wrote {args.out}")
    return out


if __name__ == "__main__":
    main()
