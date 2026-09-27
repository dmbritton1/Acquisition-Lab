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
