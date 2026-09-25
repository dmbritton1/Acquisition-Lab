# Plan 4b calibration (hard benchmark, Task 6)

Targets are from the reframe spec §4 (`docs/superpowers/specs/2026-09-24-reframe-design.md`). Each round is checked by
`uv run python -m acqlab.bench.calibrate --data data/cal-rN --audit /tmp/acqlab-audit-rN`, which also writes
`data/cal-rN/calibration.json`.

## Round 1 (2026-09-24, profile `r1`, generator 4.0.0): FAILED

- **Deals:** 30 dev deals, `--seed 610000`: unresolvable 10, decoy 7, interaction 5, flip 4, clean 4. 14 of them are
  decision flips (`go != face_go`).
- **Audit:** 500 deals (250 dev + 250 test), `--seed 710000`, 0 batch problems, 0 word leaks.
- **Runs:** S1b on all 30 deals, and S0 on the 14 flip deals, both on Opus 5.5 (`claude-opus-5-5`, CLI 2.1.280).

| Target | Value | Need | Met |
|---|---|---|---|
| S1b wrong on flip deals | 0.214 (3 of 14) | ≥ 0.30 | **MISS** |
| Test deals needed to detect a 25% cut | 308 | ≤ 100 | **MISS** |
| S0 right on flip deals | 1.000 (14 of 14) | ≥ 0.80 | ok |
| S1b regret minus B0's | −0.019 | < 0 | ok |
| S1b regret minus the margin rule's | −0.006 | < 0 | ok |
| Audit deals | 500 | ≥ 500 | ok |
| Audit batch problems (including word leaks) | 0 | 0 | ok |
| Margin shortcut AUC (audit) | 0.595 | ≤ 0.72 | ok |

**Per system** (from `pilot --report`):

| | S1b (30 deals) | S0 (14 flip deals) |
|---|---|---|
| Mean regret | 0.0120 | 0.0000 |
| Regret on flip deals | 0.0163 | 0.0000 |
| Correct decision | 0.867 | 1.000 |
| Walk-away error | 0.044 | 0.0004 |
| Pages opened | 19.1 | 39.7 |
| Decoy pages opened | 1.33 | 0.29 |
| Opened the relevant evidence on flip deals | 0.93 | 1.00 |
| No answer | 1 (`dev-016`) | 0 |
| Cost per run | $0.133 | $0.155 |
| Output tokens per run | 2,575 | 2,154 |
| Cache-read tokens per run | 62,489 | 63,942 |
| Cache-write tokens per run | 8,562 | 12,328 |

- **S1b's regret by case type:** clean 0, flip 0, unresolvable 0, decoy 0.019, interaction 0.046.
- **Floors:** B0 (always go) 0.031, always no 0.060, margin rule 0.018.
- **Total cost:** $3.98 (S1b) + $2.16 (S0) = $6.14.

### Reading

- **Regret is too sparse.** Only 4 of S1b's 30 deals had any regret (0.018, 0.133, 0.147 and 0.063), so the power model
  needs 308 test deals.
- **S1b finds the evidence but still errs on some flips.** It opened the relevant evidence on 13 of 14 flip deals and
  scored zero regret on every "flip" case-type deal. Its errors came from interactions and decoys.
- **`dev-016` had no answer.** S1b stopped without a decision. The default `go=True` happened to be right, so its
  regret is 0, but its walk-away error is 0.27.
- **The misses are the ones round 2 targets.** Both are about difficulty, not about leaks or floors. Profile `r2`
  keeps r1's case mix and adds more buried evidence, including the board minutes. That is the placement lever, the
  second in the spec's fixed order (case mix → placement → budget).

## Round 2 (2026-09-25, profile `r2`, generator 4.0.0): only "test deals needed" missed

- **Deals:** 30 dev deals, `--seed 620000`: decoy 8, interaction 8, unresolvable 8, clean 3, flip 3. 17 of them are
  decision flips.
- **Audit:** 500 deals (250 dev + 250 test), `--seed 720000`, 0 batch problems, 0 word leaks.
- **Runs:** S1b on all 30 deals, and S0 on the 17 flip deals, both on Opus 5.5 (`claude-opus-5-5`, CLI 2.1.280).

| Target | Value | Need | Met |
|---|---|---|---|
| S1b wrong on flip deals | 0.353 (6 of 17) | ≥ 0.30 | ok |
| Test deals needed to detect a 25% cut | 160 | ≤ 100 | **MISS** |
| S0 right on flip deals | 1.000 (17 of 17) | ≥ 0.80 | ok |
| S1b regret minus B0's | −0.028 | < 0 | ok |
| S1b regret minus the margin rule's | −0.003 | < 0 | ok |
| Audit deals | 500 | ≥ 500 | ok |
| Audit batch problems (including word leaks) | 0 | 0 | ok |
| Margin shortcut AUC (audit) | 0.611 | ≤ 0.72 | ok |

**Per system** (from `pilot --report`):

| | S1b (30 deals) | S0 (17 flip deals) |
|---|---|---|
| Mean regret | 0.0195 | 0.0000 |
| Regret on flip deals | 0.0243 | 0.0000 |
| Correct decision | 0.733 | 1.000 |
| Walk-away error | 0.054 | 0.0002 |
| Pages opened | 20.3 | 44.1 |
| Decoy pages opened | 2.63 | 1.94 |
| Opened the relevant evidence on flip deals | 0.76 | 1.00 |
| No answer | 0 | 0 |
| Cost per run | $0.133 | $0.168 |
| Output tokens per run | 2,512 | 2,286 |
| Cache-read tokens per run | 60,558 | 71,024 |
| Cache-write tokens per run | 8,787 | 13,532 |

- **S1b's regret by case type:** clean 0.037, decoy 0.008, flip 0.027, interaction 0.033, unresolvable 0.008.
- **Floors:** B0 (always go) 0.047, always no 0.052, margin rule 0.023.
- **Total cost:** $3.98 (S1b) + $2.86 (S0) = $6.84.

### Reading

- **Burying the evidence worked.** S1b opened the relevant evidence on 13 of 17 flip deals (0.76, down from 0.93), and
  8 of its 30 deals had regret (up from 4). Its flip error rate cleared the target.
- **Regret is still too uneven for 100 test deals.** The power model needs 160. That estimate rests on 8 deals with
  nonzero regret, so it is noisy.
- **S1b's lead over the margin rule is thin.** It beats the rule by only 0.003.
- **Per the handoff, this goes to the user.** When the only miss is "test deals needed", raising the test size is the
  user's call.
