"""A free sample deal for the analyst board, made from a benchmark room with no Claude call: the room's teaser and
CIM are ingested, the company numbers come from its engine.json (saved as the analyst's own), the settings too (if
the home has none), and the five worries sit at their starting guesses. Prints the deal id. From the repository root:

  .venv/bin/python scripts/board_sample.py --room <generated deals/dev-000/room> --home <folder outside the repo>"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from acqlab.agents.knowledge import typical_high
from acqlab.app.ingest import ingest
from acqlab.app.store import checkouts, load, write
from acqlab.generator.sample import Teaser
from acqlab.generator.traps import TRAPS

REPO = Path(__file__).resolve().parents[1]
RATES = json.loads((REPO / "acqlab" / "bench" / "base_rates.json").read_text())["rates"]
TEASER_FIELDS = ("revenue_ltm", "reported_ebitda", "claimed_addbacks", "adj_ebitda", "growth", "capex_pct", "nwc_pct")
COMPANY_FIELDS = ("da_pct", "tax_rate")


def main(argv=None) -> str:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--room", type=Path, required=True)
    p.add_argument("--home", type=Path, required=True)
    args = p.parse_args(argv)
    home = args.home.expanduser().resolve()
    if inside := [c for c in checkouts() if home.is_relative_to(c)]:  # covers every data/ folder: deals stay outside
        p.error(f"--home must be outside the repository ({inside[0]}), not {home}")
    engine = load(args.room / "engine.json")
    teaser, company = engine["teaser"], engine["deal"]["company"]
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp) / "teaser.md"
        t.write_text(load(args.room / "index.json")["teaser"])
        deal = ingest(home, teaser["name"], engine["deal"]["asking_price"], {"teaser": t, "cim": args.room / "cim.md"})
    values = {k: teaser[k] for k in TEASER_FIELDS} | {k: company[k] for k in COMPANY_FIELDS}
    write(deal / "numbers.json", {
        "name": teaser["name"], "industry": teaser["industry"], "hints": [], "cost": 0.0,
        "numbers": {k: {"value": v, "status": "you", "quotes": [], "calc": "none", "inputs": [], "why": ""}
                    for k, v in values.items()}})
    if not load(home / "settings.json"):
        write(home / "settings.json", {g: engine["deal"][g] for g in ("financing", "policy")})
    shown = Teaser(**teaser)
    write(deal / "worries.json", {"cost": 0.0, "worries": {
        k: {"chance": RATES[k], "low": 0.0, "high": typical_high(k, shown), "reason": "starting guess, not read",
            "quotes": [], "dropped_quotes": 0} for k in TRAPS}})
    print(deal.name)
    return deal.name


if __name__ == "__main__":
    main()
