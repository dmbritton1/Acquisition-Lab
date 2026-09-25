"""Generate the benchmark's deals: data rooms under data/deals/<id>/room, answer keys under data/truth/<id>.json.

  uv run python -m acqlab.generator.batch --out data --dev 50 --test 120 --hand 10 [--profile r1]

Exit codes: 0 all deals generated, no batch problems; 1 batch-level problems (printed); 2 Codex stopped (rerun to
resume from the cache); 3 a deal could not be generated or kept failing validation (printed).
"""
import argparse
import json
from functools import partial
from pathlib import Path

import numpy as np
from pydantic import BaseModel

from acqlab.dataroom.tools import write_room
from acqlab.generator.documents import Doc
from acqlab.generator.padding import pad
from acqlab.generator.render import Evidence, render, teaser_text
from acqlab.generator.truth import PROFILES, DealTruth, generate
from acqlab.generator.validate import (check_batch, check_consistency, check_engine, check_leaks, doc_words,
                                      word_leaks)
from acqlab.llm import LLMUnavailable

SEED_OFFSET = {"dev": 0, "test": 10_000, "hand": 20_000, "showcase": 30_000}
RETRY_SEED = 1_000_000
MAX_RETRIES = 5


class AnswerKey(BaseModel):
    truth: DealTruth
    evidence: list[Evidence]
    budget: float
    retrieval_cost: dict[str, float]  # trap -> pages to open its evidence documents
    llm_tokens: int = 0
    prose_fallbacks: int = 0  # paragraphs left as template prose after the LLM's attempts


def build(deal_id: str, split: str, seed: int, *, mc: int, llm=None,
          profile: str = "base") -> tuple[AnswerKey, list[Doc], str]:
    """One validated deal. Failed checks regenerate from a new seed. The cheap checks run on the template render
    first, so Codex is only paid for deals that pass them."""
    for k in range(MAX_RETRIES):
        t = generate(deal_id, split, seed + k * RETRY_SEED, mc=mc, force_case="flip" if split == "showcase" else None,
                     profile=profile)
        docs, evidence = render(t)
        teaser = teaser_text(t)
        if check_engine(t) + check_leaks(t, docs, teaser):
            continue
        tokens = fallbacks = 0
        if llm is not None:
            from acqlab.generator.prose import fill
            tz = t.base.teaser
            docs, tokens, fallbacks = fill(docs, llm, context=f"{tz.name}, a {tz.industry.lower()} business "
                                                               f"(deal {deal_id})")
        docs = pad(docs, t.base, t.style, t.seed)  # after the prose pass, so every document lands on its target length
        if not check_consistency(t, docs, evidence):
            pages = {d.id: d.pages for d in docs}
            key = AnswerKey(truth=t, evidence=evidence, budget=0.0, llm_tokens=tokens, prose_fallbacks=fallbacks,
                            retrieval_cost={e.trap: float(sum(pages[d] for d in e.docs)) for e in evidence})
            return key, docs, teaser
    raise RuntimeError(f"{deal_id}: failed validation {MAX_RETRIES} times")


def run(out: Path, counts: dict[str, int], *, seed: int = 0, mc: int = 400, llm=None, recover: int = 0,
        extract=None, profile: str = "base") -> list[str]:
    """Generate every split; returns batch-level problems (also printed)."""
    splits: dict[str, list[str]] = {s: [] for s in counts}
    keys, texts, pages, words = [], {}, {}, {}
    for split, n in counts.items():
        for i in range(n):
            deal_id = f"{split}-{i:03d}"
            key, docs, teaser = build(deal_id, split, seed + SEED_OFFSET[split] + i, mc=mc, llm=llm, profile=profile)
            face = {"teaser": key.truth.base.teaser.model_dump(), "deal": key.truth.deal.model_dump()}
            key.budget = write_room(out / "deals" / deal_id / "room", teaser, docs,
                                    budget_share=PROFILES[profile]["budget_share"], engine=face)
            (out / "truth").mkdir(parents=True, exist_ok=True)
            (out / "truth" / f"{deal_id}.json").write_text(key.model_dump_json(indent=2))
            splits[split].append(deal_id)
            keys.append(key)
            texts[deal_id] = " ".join(d.render() for d in docs)
            pages[deal_id] = {d.id: d.pages for d in docs}
            words[deal_id] = doc_words(docs)
    (out / "splits.json").write_text(json.dumps(splits, indent=2))
    problems = check_batch([k.truth for k in keys], texts, pages)
    if len(keys) >= 100:  # smaller batches are too noisy to judge
        leaks = word_leaks([k.truth for k in keys], words)
        (out / "word_leaks.json").write_text(json.dumps(leaks, indent=2))
        # agents can search since Plan 4b, so a word that separates trap deals from clean ones is a real leak
        problems += [f"word leak: {r['word']!r} in {r['doc']} (AUC {r['auc']}) for {r['trap']}" for r in leaks]
    if extract is not None:
        problems += _recoverability(out, keys, splits, recover, extract)
    (out / "problems.json").write_text(json.dumps(problems, indent=2))  # the calibration check reads it
    for p in problems:
        print("PROBLEM:", p)
    return problems


def _recoverability(out: Path, keys: list[AnswerKey], splits: dict, n_dev: int, extract) -> list[str]:
    """Phase-in (design §7): hand-reviewed, showcase and a random sample of dev deals."""
    from acqlab.generator.recover import check
    rng = np.random.default_rng(0)
    dev = splits.get("dev", [])
    chosen = set(splits.get("hand", []) + splits.get("showcase", [])) | set(
        rng.choice(dev, min(n_dev, len(dev)), replace=False).tolist() if dev else [])
    problems = []
    for key in keys:
        if key.truth.id not in chosen:
            continue
        room = out / "deals" / key.truth.id / "room"
        texts = {p.stem: p.read_text() for p in room.glob("*.md")}
        filler = next(d["id"] for d in json.loads((room / "index.json").read_text())["documents"]
                      if d["domain"] == "filler")
        found, _ = check(key.truth, key.evidence, texts, extract, filler)
        problems += [f"{key.truth.id}: {p}" for p in found]
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("data"))
    ap.add_argument("--dev", type=int, default=50)
    ap.add_argument("--test", type=int, default=120)
    ap.add_argument("--hand", type=int, default=10)
    ap.add_argument("--showcase", type=int, default=1)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--profile", choices=list(PROFILES), default="r2", help="difficulty profile (reframe design §4; "
                    "frozen by calibration round 2)")
    ap.add_argument("--mc", type=int, default=400, help="Monte Carlo draws for per-fact decision value")
    ap.add_argument("--llm", action="store_true", help="write prose with Codex (default: template prose)")
    ap.add_argument("--recover", type=int, default=-1,
                    help="run the recoverability check on hand/showcase plus this many dev deals (needs Codex)")
    args = ap.parse_args(argv)
    llm = extract = None
    if args.llm or args.recover >= 0:
        from acqlab.llm import complete
        complete = partial(complete, cache_dir=args.out / "llm_cache")  # the cache lives beside the batch
        llm = complete if args.llm else None
        extract = complete if args.recover >= 0 else None
    counts = {"dev": args.dev, "test": args.test, "hand": args.hand, "showcase": args.showcase}
    try:
        problems = run(args.out, counts, seed=args.seed, mc=args.mc, llm=llm, recover=max(args.recover, 0),
                       extract=extract, profile=args.profile)
    except LLMUnavailable as e:
        print(f"Codex stopped: {e}\nEvery completed call is cached. Run the same command again (after any usage "
              "limit resets) to continue where it left off.")
        return 2
    except RuntimeError as e:  # after LLMUnavailable, which is a RuntimeError too
        print(f"Generation stopped: {e}")
        return 3
    print(f"generated {sum(counts.values())} deals into {args.out}; {len(problems)} batch problems")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
