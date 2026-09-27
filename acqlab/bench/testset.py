"""The Plan 6 test set (spec §2): the seed check before it is generated, its fingerprint, and the recoverability check
on a seeded sample of it.

  uv run python -m acqlab.bench.testset seeds --base 3500000 --n 160 --roots DIR [DIR ...]
  uv run python -m acqlab.bench.testset fingerprint --data data/test-r2 > docs/results/plan-6-test-set.json
  uv run python -m acqlab.bench.testset recover --data data/test-r2 --n 20 --confirm-codex

Exit codes: 0 clean; 1 a clash or a recoverability problem; 2 Codex stopped (rerun later: calls are cached); 3
refused (no --confirm-codex)."""
import argparse
import hashlib
import json
from collections.abc import Callable
from functools import partial
from pathlib import Path

import numpy as np

from acqlab.generator.batch import RETRY_SEED, SEED_OFFSET, AnswerKey, recover_deal
from acqlab.llm import LLMUnavailable


def used_seeds(roots: list[Path]) -> set[int]:
    """Every seed recorded in an answer key under these directories (any depth)."""
    seeds = set()
    for root in roots:
        for p in Path(root).rglob("truth/*.json"):
            try:
                seed = json.loads(p.read_text())["truth"]["seed"]
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if isinstance(seed, int):
                seeds.add(seed)
    return seeds


def clashes(base: int, n: int, used: set[int]) -> list[int]:
    """Used seeds equal to one of the n test deals' seeds or to one of its retries (retries add multiples of
    RETRY_SEED, so a clash is a match modulo RETRY_SEED)."""
    mine = {(base + SEED_OFFSET["test"] + i) % RETRY_SEED for i in range(n)}
    return sorted(s for s in used if s % RETRY_SEED in mine)


def fingerprint(data: Path) -> dict:
    """SHA-256 of every answer key, and one hash over them in name order."""
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((data / "truth").glob("*.json"))}
    return {"files": files, "all": hashlib.sha256("".join(f"{k} {v}\n" for k, v in files.items()).encode()).hexdigest()}


def recover_sample(data: Path, n: int = 20, seed: int = 0, extract: Callable | None = None) -> tuple[list[str], list]:
    """The recoverability gate (spec §2): a seeded random sample of n test deals. Returns (chosen, problems)."""
    if extract is None:
        from acqlab.llm import complete
        extract = partial(complete, cache_dir=data / "llm_cache")
    deals = json.loads((data / "splits.json").read_text())["test"]
    chosen = sorted(np.random.default_rng(seed).choice(deals, min(n, len(deals)), replace=False).tolist())
    problems = []
    for deal in chosen:
        key = AnswerKey.model_validate_json((data / "truth" / f"{deal}.json").read_text())
        problems += recover_deal(data, key, extract)
    return chosen, problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seeds", help="fail if a test seed clashes with any seed already used")
    s.add_argument("--base", type=int, required=True)
    s.add_argument("--n", type=int, required=True)
    s.add_argument("--roots", type=Path, nargs="+", required=True)
    f = sub.add_parser("fingerprint", help="print the answer keys' fingerprint as JSON")
    f.add_argument("--data", type=Path, required=True)
    r = sub.add_parser("recover", help="the recoverability check on a seeded sample (uses Codex)")
    r.add_argument("--data", type=Path, required=True)
    r.add_argument("--n", type=int, default=20)
    r.add_argument("--confirm-codex", action="store_true", help="required to make real Codex calls")
    args = ap.parse_args(argv)
    if args.cmd == "seeds":
        used = used_seeds(args.roots)
        found = clashes(args.base, args.n, used)
        print(f"{len(used)} seeds used; clashes with base {args.base}: {found or 'none'}")
        return 1 if found else 0
    if args.cmd == "fingerprint":
        print(json.dumps(fingerprint(args.data), indent=2))
        return 0
    if not args.confirm_codex:
        print("Refusing to run: this uses your Codex quota. Add --confirm-codex to proceed.")
        return 3
    try:
        chosen, problems = recover_sample(args.data, args.n)
    except LLMUnavailable as e:
        print(f"Codex stopped: {e}\nEvery completed call is cached. Run the same command again to continue.")
        return 2
    print(f"checked {len(chosen)} deals: {', '.join(chosen)}")
    for p in problems:
        print("PROBLEM:", p)
    print(f"{len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
