# Mixed models: tuning log

**Spec:** `docs/superpowers/specs/2026-10-11-mixed-models-design.md` §2. **Scorecard:** `.venv/bin/python scripts/mix_practice.py`.

Practice deals only (`data/cal-r2`, `data/heldout-r2`, `data/practice-r2u`; 90). The fresh held-out sets
(`data/mix-test-r2`, 80 deals, seed 650000; `data/mix-test-r2u`, 20 deals, seed 670000) are never run before the
freeze; `acqlab/bench/mix.py` refuses them.

**Rules:** round 0 runs the four building blocks (`mix_sonnet_solo`, `mix_opus_low`, `mix_h_opus1`,
`mix_h_sonnet3`) and `s1b` on `practice-r2u`; cascades are scored from the rows. At most 3 more rounds, one change each,
kept only if `scripts/mix_practice.py --keep <new> --over <parent>` says True. Cap: $50 for the practice phase, under
one OK from the user. A rejected variant is added to `REJECTED` in `scripts/mix_practice.py` (shown, never
picked); a kept pipeline variant is added to `CHEAP`.

## Round 0 (2026-10-11 to 2026-10-12)

**Run:** the user's OK on 2026-10-11 for $66 (the $50 cap plus $16 for `s4` on `practice-r2u`). A one-deal CLI check
on `cal-r2/dev-000` (Sonnet and `--effort low` accepted; each row recorded its model and steps), then `s1b` and `s4` on
`practice-r2u`, then the four building blocks on all 90 practice deals. **Spend:** $56.70 at list prices.

**Plain systems** (90 deals each):

| System | Regret | Right | False GOs | False NO-GOs | $ per deal | Unanswered |
|---|---|---|---|---|---|---|
| `s4` (Opus team) | 0.0112 | 71.1% | 4 | 22 | 0.530 | 0 |
| `mix_h_opus1` (Haiku reader, 1 Opus pricer) | 0.0114 | 78.9% | 9 | 10 | 0.126 | 5 |
| `mix_opus_low` (single Opus, effort low) | 0.0128 | 78.9% | 11 | 8 | 0.096 | 3 |
| `s1b` (single Opus) | 0.0132 | 80.0% | 9 | 9 | 0.132 | 0 |
| `mix_h_haiku3` (the Haiku winner) | 0.0164 | 63.3% | 6 | 27 | 0.023 | 0 |
| `mix_sonnet_solo` | 0.0165 | 75.6% | 9 | 13 | 0.051 | 0 |
| `mix_h_sonnet3` (Haiku reader, 3 Sonnet pricers) | 0.0208 | 60.0% | 11 | 25 | 0.125 | 0 |
| `mix_haiku_solo` | 0.0309 | 57.8% | 2 | 36 | 0.007 | 0 |

**Unanswered runs:** `mix_h_opus1`'s 5 are all its Opus pricer ending without a call (the Haiku reader answered every
time); `mix_opus_low`'s 3 are single Opus at low effort stopping without a submit. Both are scored at face value, like
every unanswered run.

**Cascades:** 176 scored from these rows, all on the full 90 deals. The frontier, cheapest first:

| Candidate | Regret | $ per deal |
|---|---|---|
| `mix_haiku_solo` | 0.0309 | 0.007 |
| `cascade:mix_haiku_solo>mix_sonnet_solo@close:0.02` | 0.0237 | 0.018 |
| `mix_h_haiku3` | 0.0164 | 0.023 |
| `cascade:mix_h_haiku3>mix_sonnet_solo@split` | 0.0162 | 0.026 |
| `cascade:mix_h_haiku3>mix_sonnet_solo@close:0.02` | 0.0144 | 0.032 |
| `cascade:mix_h_haiku3>mix_sonnet_solo@flag` | 0.0144 | 0.034 |
| `cascade:mix_h_haiku3>mix_opus_low@close:0.02` | 0.0121 | 0.041 |
| `cascade:mix_h_haiku3>mix_opus_low@close:0.05` | 0.0108 | 0.066 |
| `cascade:mix_h_haiku3>mix_opus_low@flag|close:0.05` | 0.0104 | 0.073 |
| `cascade:mix_h_haiku3>s1b@close:0.05` | 0.0099 | 0.082 |
| `cascade:mix_h_haiku3>s1b@flag|close:0.05` | 0.0096 | 0.092 |
| `cascade:mix_h_opus1>s1b@split` | 0.0092 | 0.132 |
| `cascade:mix_h_opus1>mix_opus_low@close:0.02` | 0.0077 | 0.145 |

**The §1 picks:** `cascade:mix_h_haiku3>s1b@flag|close:0.05` (lowest regret cheaper than `s1b`),
`cascade:mix_h_opus1>mix_opus_low@close:0.02` (lowest regret cheaper than `s4`), then the two cheapest frontier points,
`mix_haiku_solo` and `cascade:mix_haiku_solo>mix_sonnet_solo@close:0.02`.

**Caution:** 176 cascades were searched on the same 90 deals, so the best ones are flattered; the fresh test is the
guard.

**Tuning rounds:** none yet. One rerun of a pipeline on the 90 deals costs $2 to $11, and $9.30 of the approved $66 is
left.
