# Mixed models: the full benchmark on 300 deals (pre-registration)

**Frozen:** 2026-10-15, before `mix_opus_low` or `mix_sonnet_solo` has run on any held-out deal. **Follows:**
`docs/results/mix.md` (100 fresh deals) and `docs/results/mix-confirm.md` (the two leads on the 200 held-out deals).

Some systems had 300 deals and some only the 100 fresh ones. This puts every system and every frozen mix on the same
300: the 200 held-out deals (`data/test-r2`, 160 `r2`; `data/pilot-r2u`, 40 `r2u`) and the 100 fresh deals
(`data/mix-test-r2`, `data/mix-test-r2u`). Nothing is chosen from it; it is a benchmark table, not a new pick.

## The runs

Only the two parts still missing on the held-out sets: `mix_opus_low` (single Opus at `--effort low`, fingerprint
`b9a9ba94…`) and `mix_sonnet_solo` (single Sonnet, `26d3fb60…`), one run per deal, by `acqlab.bench.mix --final
--split test --systems mix_sonnet_solo,mix_opus_low` on each set. The runner allows only `mix.CONFIRM` on these sets.
Estimate about $30 at list prices (their averages on 190 earlier deals: $0.097 and $0.051).

Every other run already exists: `s1b`, `s4`, `mix_h_opus1` on all four sets; single Haiku and the Haiku team as the
Haiku track's `haiku_solo` and `haiku_lean_zero_w0` on the held-out sets and as `mix_haiku_solo` and `mix_h_haiku3`
(the same prompts) on the fresh sets.

## The table

The 10 systems: `s4`, `s1b`, `mix_h_opus1`, `mix_opus_low`, `mix_sonnet_solo`, single Haiku (mix 3), the Haiku team,
and the three frozen cascades (mixes 1, 2 and 4). For each, on all 300, the 200 held-out and the 100 fresh: regret,
share right, false GOs and NO-GOs, list-price cost per deal, the share escalated (cascades), and the median and
90th-percentile minutes per deal (Claude's reported session time, summed over a run's sessions; a cascade adds its
strong system's time only on escalated deals). Each system other than the baselines is compared with `s1b` and `s4`
by the verdict rule of `docs/results/mix-prereg.md` (paired 95% bootstrap range: "better", "worse", or "no clear
difference: at most X worse"), with its cost ratio.

**Analysis, once:** `.venv/bin/python scripts/mix_benchmark.py --out docs/results/mix-benchmark.json`. It refuses a
set where any system misses a deal, and any row this benchmark or the mix test made that lacks a trace, ran on the
wrong models or was not made with the frozen mixes. It never overwrites its output.

## Notes fixed before the test

- **The pre-registered verdicts stand where they were made.** The four mixes' tested result is the 100 fresh deals
  (`mix.md`); Lead 1's is the 200 held-out deals (`mix-confirm.md`). The 300-deal table is the fuller description, and
  it includes the deals each lead and pick came from.
- **Run dates differ:** `s1b` and `s4` ran on the held-out sets on 2026-09-28 and 2026-10-08, the Haiku systems
  around 2026-10-11/12, `mix_h_opus1` on 2026-10-14/15, and these two parts now, on Claude Code 2.1.291. Times and
  results can drift with the CLI and the service.
- **Times are not a controlled measure:** they depend on server load at the time of the run and exclude waits for
  usage limits.
- **One run per deal.**
