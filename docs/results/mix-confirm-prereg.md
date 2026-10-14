# Mixed models: confirming the final test's two leads (pre-registration)

**Frozen:** 2026-10-14, before `mix_h_opus1` has run on any deal named here. **Leads from:** `docs/results/mix.md`,
"Observations outside the pre-registered comparisons". **CLI:** Claude Code 2.1.291.

The final test's four frozen mixes are unchanged (`mix.FINAL`, `docs/results/mix-prereg.md`). Two of their parts,
on their own, looked better than the mixes on the 100 fresh deals. Those deals suggested the leads, so they cannot
confirm them; this test uses deals the leads did not come from.

## Lead 1: the Haiku reader and one Opus pricer, nothing else (`mix_h_opus1`)

On the 100 fresh deals: regret 0.0096 at $0.128 per deal, against the Opus team's 0.0092 at $0.537.

- **Deals:** `data/test-r2` (160, profile `r2`, Plan 6's test set) and `data/pilot-r2u` (40, profile `r2u`), test
  split, 200 deals. The frozen `s1b` and `s4` have already run on every one (first runs only; `test-r2`'s repeats
  `*.r1.json` are not read). `mix_h_opus1` has never run on them, and nothing in its design came from them: its
  prompts, the base rates (`acqlab/bench/base_rates.json`, from the practice sets) and its settings are pinned by
  `test_the_frozen_mixes_and_their_prompts_are_unchanged` (fingerprint `25759ccd…`).
- **Run:** `mix_h_opus1` only, one run per deal: `acqlab.bench.mix --final --split test --systems mix_h_opus1` on each
  set. The runner refuses any other system on these sets (`mix.CONFIRM`, `mix.CONFIRM_SETS`). Estimate about $26 at
  list prices (its average on 190 earlier deals was $0.123–0.128).
- **The claim:** "matches the Opus team for less": on all 200, `mix_h_opus1` costs less than `s4` and is not "worse"
  than it. Reported with the range's upper end ("at most X worse"), which says how close the match is.
- **Also reported:** against `s1b`; on the 160 and the 40 apart; and on all 300 deals including the 100 it came from
  (labelled as such: those 100 favour it by selection).

## Lead 2: the Haiku team on its own (`mix_h_haiku3`, the Haiku track's `haiku_lean_zero_w0`)

On the 100 fresh deals: regret 0.0133 at $0.024, lower than single Opus's 0.0154. **No new runs:** the same system
(the same prompts, pinned by the freeze test) already ran as the Haiku track's frozen winner on the same 200 held-out
deals, before this lead existed (`docs/results/haiku-team.md`: no clear difference from `s1b`, at most 0.0092 worse,
0.0157 against 0.0118). Reported against `s1b` and `s4` on those 200 (the test), on the 100 fresh deals, and on all
300.

## Verdicts and analysis

Unchanged from `docs/results/mix-prereg.md`: a paired regret difference with a 95% paired-bootstrap range, plus deals
won, lost and tied. A range wholly below zero reads "better", wholly above "worse", otherwise "no clear difference: at
most X worse". Costs are list prices from each step's tokens.

**Analysis, once:** `.venv/bin/python scripts/mix_confirm.py --out docs/results/mix-confirm.json`. It refuses a
missing deal or trace, a `mix_h_opus1` row on the wrong models or not made with the frozen mix, and a Haiku-team or
baseline set that does not cover the test split; it never overwrites its output.

## Notes fixed before the test

- **Not brand-new deals:** the 200 held-out deals were scored in Plan 6 and the Haiku track. They are new to
  `mix_h_opus1`, and no choice about it was made on them. Brand-new deals would need both Opus baselines rerun
  (about $82 for 100 deals) and give a wider range.
- **The baselines ran earlier:** `s1b` and `s4` ran on `test-r2` on 2026-09-28 and on `pilot-r2u` on 2026-10-08, on
  an older Claude Code; `mix_h_opus1` runs now on 2.1.291. In the final test every system ran in the same days. If
  the CLI or the models' service changed in between, it would show up here as a difference between systems.
- **Unanswered runs** are scored at face value, as everywhere in this project.
- **One run per deal.**
