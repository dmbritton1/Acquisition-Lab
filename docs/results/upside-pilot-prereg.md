# Hidden-upside pilot, stage 1: fixed rules (pre-registration)

Written on 2026-10-08 at commit d8e3d28, before any paid run. The spec is
`docs/superpowers/specs/2026-10-08-upside-pilot-design.md` (§2.3–2.4 restated here). The analysis is
`scripts/upside_pilot.py`, which writes `docs/results/upside-pilot.json` once.

## Deals

- 40 template-prose deals, split `test`, profile `r2u`, generator 4.1.0, base seed 11,250,000, in `data/pilot-r2u`.
- The seeds were clash-checked against `data/cal-r2`, `data/heldout-r2`, `data/test-r2`, `data/sim-r2` and
  `data/pilot-r2`: none.
- 16 relief, 8 confirmed, 16 ordinary.

```text
test-000 confirmed addback 11260000
test-001 decoy - 11260001
test-002 interaction - 11260002
test-003 unresolvable - 11260003
test-004 clean - 11260004
test-005 confirmed debt_like 11260005
test-006 relief debt_like 11260006
test-007 relief debt_like 11260007
test-008 decoy - 11260008
test-009 relief addback 11260009
test-010 relief concentration 11260010
test-011 decoy - 11260011
test-012 relief capex 11260012
test-013 confirmed capex 11260013
test-014 unresolvable - 11260014
test-015 interaction - 11260015
test-016 relief debt_like 11260016
test-017 decoy - 11260017
test-018 relief concentration 11260018
test-019 relief concentration 11260019
test-020 clean - 11260020
test-021 confirmed addback 11260021
test-022 confirmed capex 11260022
test-023 unresolvable - 11260023
test-024 relief debt_like 11260024
test-025 unresolvable - 11260025
test-026 relief debt_like 11260026
test-027 flip - 11260027
test-028 confirmed concentration 11260028
test-029 interaction - 11260029
test-030 relief debt_like 11260030
test-031 relief capex 11260031
test-032 confirmed concentration 11260032
test-033 confirmed concentration 11260033
test-034 relief capex 11260034
test-035 relief concentration 11260035
test-036 relief capex 11260036
test-037 relief debt_like 11260037
test-038 unresolvable - 11260038
test-039 decoy - 11260039
```

## Free checks (spec §2.2), all passed

```json
{
  "counts": {
    "relief": 16,
    "confirmed": 8,
    "ordinary": 16
  },
  "engine_right": 40,
  "half_right": {
    "relief": 0,
    "confirmed": 8
  },
  "ignore_right": {
    "relief": 16,
    "confirmed": 0
  },
  "ok": true
}
```

## Runs

- `s1b` (single Claude) and `s4` (the frozen team, tag `s4-frozen-plan5`), one run per deal.
- Model `claude-opus-5-5`, on Claude Code CLI 2.1.291 or newer.
- Runner: `.venv/bin/python -m acqlab.bench.pilot --data data/pilot-r2u --split test --n 40 --systems s1b,s4
  --confirm-claude`.
- Started only after the user's OK.

## Measures (fixed)

1. **Relief deals (16), the main measure:** false NO-GOs per system; mean regret and the paired `s4 − s1b`
   difference, with a 95% paired-bootstrap range.
2. **Confirmed deals (8):** false GOs and mean regret.
3. **Ordinary deals (16):** regret and share correct.
4. **All 40:** regret, share correct, false GO / NO-GO, pages, cost and sessions per deal, and results by deal type.
5. **Looked or not.** For each flagged deal, whether each system opened the settling document (the last document of
   the flagged issue's evidence). Each relief miss is "never looked" or "looked but didn't believe it".
6. **Took the warning.** For `s4`, the Deal Lead's first chance on the flagged issue (and the median). For `s1b`,
   whether it ever noted the flagged issue.
7. **Caution control.** `pilot.s1b_matched` over all 40, reported on the relief deals.

## How the result is read (fixed)

On the 16 relief deals:

| Result | Rule |
|---|---|
| **Team leans on caution** | `s4` has at least 3 more false NO-GOs than `s1b`, and a higher mean regret. |
| **Team weighs evidence fine** | `s4` has no more false NO-GOs than `s1b`. |
| **Unclear** | Anything else. |

The write-up also says:
- whether the team's median opening chance on the flagged issue was below 0.5 ("warning mostly not priced");
- which failure class holds most relief misses.

This is a pilot of 16 relief deals: a direction, not proof.
