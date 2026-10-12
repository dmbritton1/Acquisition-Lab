# Mixed models: tuning log

**Spec:** `docs/superpowers/specs/2026-10-11-mixed-models-design.md` §2. **Scorecard:** `.venv/bin/python scripts/mix_practice.py`.

Practice deals only (`data/cal-r2`, `data/heldout-r2`, `data/practice-r2u`; 90). The fresh held-out sets
(`data/mix-test-r2`, 80 deals, seed 650000; `data/mix-test-r2u`, 20 deals, seed 670000) are never run before the
freeze; `acqlab/bench/mix.py` refuses them.

**Rules:** round 0 runs the four building blocks (`mix_sonnet_solo`, `mix_opus_low`, `mix_h_opus1`,
`mix_h_sonnet3`) and `s1b` on `practice-r2u`; cascades are scored from the rows. At most 3 more rounds, one change each,
kept only if `scripts/mix_practice.py --keep <new> --over <parent>` says True. Cap: $50 for the practice phase, under
one OK from the user.

## Round 0

Not run yet: awaits the user's OK for the practice phase.
