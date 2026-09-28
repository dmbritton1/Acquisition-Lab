# The Plan 6 test set

Generated once on 2026-09-27, after the pre-registration addendum was committed (`f511004`).

```bash
uv run python -m acqlab.bench.testset seeds --base 3500000 --n 160 --roots /Users/dwightbritton/Developer/acquisition-lab /private/tmp/claude-501
uv run python -m acqlab.generator.batch --out data/test-r2 --dev 0 --test 160 --hand 0 --showcase 0 --seed 3500000 --profile r2
uv run python -m acqlab.bench.testset fingerprint --data data/test-r2 > docs/results/plan-6-test-set.json
```

- **Seed check:** 4,200 seeds used on disk; clashes with base 3,500,000 (test seeds 3,510,000–3,510,159, modulo the
  1,000,000 retry offset): none.
- **Generator:** version 4.0.0, profile `r2`; 160 deals, 0 batch problems (the word-leak check ran).
- **Case mix:** interaction 43, decoy 37, flip 12, clean 26, unresolvable 42. Decision flips (the true call differs
  from the face call): 79. GO: 77 of 160.
- **Fingerprint:** SHA-256 of each answer file in `plan-6-test-set.json`; over all of them in order:
  `54acaa91232832352dfa94ec839360aadaf8c5b5bf3d2193e78d3e8bbe3289e8`.

No system has been run on these deals. (Counts only: no deal was opened or read.)

## Recoverability (2026-09-27 to 2026-09-28)

```bash
uv run python -m acqlab.bench.testset recover --data data/test-r2 --n 20 --confirm-codex
```

20 test deals drawn with numpy seed 0: test-002, 005, 011, 026, 038, 044, 073, 077, 085, 089, 090, 093, 098, 099,
113, 119, 121, 138, 149 and 150. 200 Codex calls (CLI 0.158, the ChatGPT app's copy), over three usage windows and two
of the user's ChatGPT accounts; every call was cached, so each rerun resumed. No call used a tool.

**Result: 8 problems (exit 1), so the gate did not pass as written.**

- Every fact with a nonzero amount was recovered (27 of 27), and every unrelated-document check correctly found no
  answer.
- Facts whose amount is zero: 65 of 73 recovered. In all 8 failures Codex answered null ("the documents do not
  say") where the answer key is 0:
  - 5 working-capital facts (test-002, 005, 011, 073, 121), whose evidence reads "At year end, net working capital
    was $0.0M below normal levels; the review covered customer collections pulled forward."
  - 2 litigation facts (test-011, 119): "We expect it to settle for $0.0M, payable by the Company."
  - 1 restructuring add-back (test-085): restructuring costs of $0.0M, $0.0M and $2.0M over three years, so none
    recurs and nothing is disallowed; this one takes an inference.
- **Diagnosis.** The zero is stated in the evidence, in the generator's template wording; the checker's question
  says "Answer 0 only if the documents show it will not", and Codex did not read "$0.0M below normal levels" or "settle
  for $0.0M" as showing that. The information is recoverable; the wording is awkward. Every system reads the same
  documents, so the effect is the same for all of them.
- **Decision (the user, 2026-09-28):** the failures are understood and reported here; the test set is not
  regenerated (pre-registration addendum, "The test set"), and the main run proceeds.
