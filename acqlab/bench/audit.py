"""Page-spend audit (document router design §5): where each run's pages went, against the answer keys. No Claude
calls: it reads a system's finished runs (pilot) and the answer keys.

  uv run python -m acqlab.bench.audit --data data/cal-r2 --system s4 --system s1b
"""
import argparse
import json
from pathlib import Path

from acqlab.generator.batch import AnswerKey


def audit(data: Path, system: str) -> list[dict]:
    """Per run: pages read, pages on documents holding a real (nonzero) fact's evidence, whether the audited notes
    were read, and the real facts whose evidence was never read."""
    rows = []
    for path in sorted((data / "runs" / system).glob("*.json")):
        run = json.loads(path.read_text())
        key = AnswerKey.model_validate_json((data / "truth" / f"{run['deal']}.json").read_text())
        trace = [json.loads(x) for x in path.with_suffix(".trace.jsonl").read_text().splitlines()]
        reads = [(r["args"]["doc_id"], r["cost"]) for r in trace if r["tool"] == "open_document" and not r["refused"]]
        real = {f.trap for f in key.truth.facts if f.amount > 0}
        where = {e.trap: set(e.docs) for e in key.evidence if e.trap in real}
        read = {d for d, _ in reads}
        rows.append({"deal": run["deal"], "case_type": run["case_type"], "correct": run["correct"],
                     "regret": run["regret"], "pages": sum(c for _, c in reads),
                     "evidence_pages": sum(c for d, c in reads if any(d in docs for docs in where.values())),
                     "audited": "audited" in read, "missed": sorted(t for t, docs in where.items() if not docs & read)})
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--system", action="append", required=True)
    args = ap.parse_args(argv)
    for system in args.system:
        rows = audit(args.data, system)
        print(f"== {system}: {len(rows)} runs, audited notes read in {sum(r['audited'] for r in rows)}, "
              f"{sum(bool(r['missed']) for r in rows)} with a real fact never read")
        for r in rows:
            print(f"{r['deal']} {r['case_type']:12} {'✓' if r['correct'] else '✗'} regret {r['regret']:.3f} "
                  f"pages {r['pages']:g} (evidence {r['evidence_pages']:g}) audited {'yes' if r['audited'] else 'no'}"
                  + (f" missed {', '.join(r['missed'])}" if r["missed"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
