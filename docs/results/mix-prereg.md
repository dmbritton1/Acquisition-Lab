# Mixed models: pre-registration

**Frozen:** 2026-10-12, before any model has run on the fresh deals. **Spec:**
`docs/superpowers/specs/2026-10-11-mixed-models-design.md`. **Practice record:** `docs/results/mix-tuning-log.md`
(round 0 only: no tuning rounds, since one rerun costs $2–11 and $9.30 of the approved $66 was left). **CLI:** Claude
Code 2.1.291.

## The four frozen mixes (`acqlab/bench/mix.py` `FINAL`)

Chosen by the spec §1 rule from the frontier of 6 systems and 176 cascades, all scored on the same 90 practice deals.

| # | Mix | Why it is picked | Practice regret | Practice right | $ per deal |
|---|---|---|---|---|---|
| 1 | `cascade:mix_h_haiku3>s1b@flag\|close:0.05` | lowest regret cheaper than `s1b` | 0.0096 | 80.0% | 0.092 |
| 2 | `cascade:mix_h_opus1>mix_opus_low@close:0.02` | lowest regret cheaper than `s4` | 0.0077 | 85.6% | 0.145 |
| 3 | `mix_haiku_solo` | cheapest frontier point | 0.0309 | 57.8% | 0.007 |
| 4 | `cascade:mix_haiku_solo>mix_sonnet_solo@close:0.02` | next cheapest frontier point | 0.0237 | 61.1% | 0.018 |

On practice, `s1b` scored 0.0132 at $0.132 and `s4` 0.0112 at $0.530.

**In words:**
1. The Haiku team decides; when the teaser discloses a seller exposure, or its walk-away is within 5% of the asking
   price, single Opus decides instead.
2. A Haiku reader and one Opus second opinion decide; when the walk-away is within 2% of the asking price, single Opus
   at low effort decides instead.
3. Single Haiku.
4. Single Haiku; when its walk-away is within 2% of the asking price, single Sonnet decides instead.

A run that never answered always escalates. A cascade's cost is the cheap system's plus the strong system's on
escalated deals.

## The frozen parts

Pinned by `tests/bench/test_mix.py::test_the_frozen_mixes_and_their_prompts_are_unchanged`, and checked in every row by
`scripts/mix_final.py`.

| Part | What it is | Fingerprint |
|---|---|---|
| `mix_haiku_solo` | single Claude's prompt and tools, on Haiku | `30366a33…` |
| `mix_sonnet_solo` | the same, on Sonnet | `26d3fb60…` |
| `mix_opus_low` | the same, on Opus at `--effort low` | `b9a9ba94…` |
| `mix_h_haiku3` | Haiku reader, 3 Haiku pricers (zero rule), engine on base-rate notes (`w` = 0), majority vote | `3a683445…` |
| `mix_h_opus1` | Haiku reader, 1 Opus pricer (zero rule), engine on base-rate notes (`w` = 0) | `25759ccd…` |
| `s1b` | single Opus, frozen at tag `s4-frozen-plan5` | (the Opus baseline) |

`mix_haiku_solo` and `mix_h_haiku3` use exactly the prompts and steps of the Haiku track's `haiku_solo` and frozen
`haiku_lean_zero_w0`, whose practice rows they were scored from. Base rates: `acqlab/bench/base_rates.json`
(sha `88a261b3…`).

## The final test

- **Deals:** `data/mix-test-r2` (80, profile `r2`, seed 650000) and `data/mix-test-r2u` (20, profile `r2u`, seed
  670000), test split, one run per deal per system.
- **Runs:** `s1b` and `s4` by `acqlab.bench.pilot --split test`; `mix_haiku_solo`, `mix_sonnet_solo`, `mix_opus_low`,
  `mix_h_haiku3` and `mix_h_opus1` by `acqlab.bench.mix --final --split test`. Estimate about $96 at list prices.
- **Analysis, once:** `.venv/bin/python scripts/mix_final.py --out docs/results/mix.json`. It refuses missing deals or
  traces, rows on the wrong models and rows whose fingerprint is not frozen.

**Verdicts (spec §1, unchanged):** each frozen mix against `s1b` and against `s4`, as a paired regret difference with
a 95% paired-bootstrap range, plus deals better, worse and tied. A range wholly below zero reads "better", wholly above
"worse", and otherwise "no clear difference: at most X worse", with X the range's upper end. Each is stated with its
cost ratio, on the 80, the 20 and all 100.

**The two named readings:**
- **"beats single Opus for less":** a frozen mix cheaper than `s1b` and not "worse" than it;
- **"matches the Opus team for less":** a frozen mix cheaper than `s4` and not "worse" than it.

## Notes fixed before the test

- **Practice selection:** the picks are the best of 182 candidates on the same 90 deals, so their practice scores are
  flattered. The Haiku team's practice gain vanished on fresh deals; the fresh test decides.
- **`data/mix-test-r2` carries one generator warning:** "add-back item/claimed differs by role" (trap quartiles
  0.37/0.78/0.86 against clean 0.35/0.54/0.67). It was kept, not regenerated, since its seed was fixed in advance; every
  system sees the same deals, so any hint it gives helps all of them.
- **`acqlab.bench.pilot` has no held-out refusal:** `s1b` and `s4` touch the fresh sets only after this file is
  committed.
- **Unanswered runs** are scored at face value, as everywhere in this project; `mix_h_opus1`'s Opus pricer ended
  without a call on 5 of 90 practice deals, and `mix_opus_low` on 3.
- **Costs** are list prices from each step's tokens; a timed-out step costs $0 because its tokens are unknown.
