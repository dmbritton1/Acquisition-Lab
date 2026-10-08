# Hidden-upside pilot, stage 1: fixed rules (pre-registration)

Written on 2026-10-08 at commit 9f56edb, before any paid run. Revised the same day, before any paid run, after the
final review (add-backs no longer flagged; one flip-point window; unanswered runs and the model check). The spec is
`docs/superpowers/specs/2026-10-08-upside-pilot-design.md` (§2.3–2.4 restated here). The analysis is
`scripts/upside_pilot.py`, which writes `docs/results/upside-pilot.json` once.

## Deals

- 40 template-prose deals, split `test`, profile `r2u`, generator 4.1.1, base seed 11,250,000, in `data/pilot-r2u`.
- Seeds are the base plus the test split's offset of 10,000, so the deals use 11,260,000 to 11,260,039.
- An earlier draw of these deals, made before this revision, is kept in `data/pilot-r2u-v1` and is not used.
- The seeds were clash-checked against `data/cal-r2`, `data/heldout-r2`, `data/test-r2`, `data/sim-r2` and
  `data/pilot-r2`: none.
- 16 relief, 8 confirmed, 16 ordinary.

```text
test-000 confirmed debt_like 11260000
test-001 decoy - 11260001
test-002 interaction - 11260002
test-003 unresolvable - 11260003
test-004 clean - 11260004
test-005 confirmed nwc 11260005
test-006 relief debt_like 11260006
test-007 relief debt_like 11260007
test-008 decoy - 11260008
test-009 relief concentration 11260009
test-010 relief concentration 11260010
test-011 decoy - 11260011
test-012 relief capex 11260012
test-013 confirmed debt_like 11260013
test-014 unresolvable - 11260014
test-015 interaction - 11260015
test-016 relief debt_like 11260016
test-017 decoy - 11260017
test-018 relief concentration 11260018
test-019 relief concentration 11260019
test-020 clean - 11260020
test-021 confirmed concentration 11260021
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
test-033 confirmed nwc 11260033
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
- Before the runs start, the CLI version (`claude --version`, 2.1.291 or newer) is recorded here.
- Recorded on 2026-10-08, before the runs started: `claude --version` gives `2.1.291 (Claude Code)`, at
  `/Users/dwightbritton/.nvm/versions/node/v22.22.3/bin/claude` (`CLAUDE_BIN` unset, so the runner uses `claude`).
- Runner: `.venv/bin/python -m acqlab.bench.pilot --data data/pilot-r2u --split test --n 40 --systems s1b,s4
  --confirm-claude`.
- Started only after the user's OK.

## Measures (fixed)

1. **Relief deals (16), the main measure:** false NO-GOs per system, paired on the same deals; mean regret and the
   paired `s4 − s1b` difference, with a 95% paired-bootstrap range.
2. **Confirmed deals (8):** false GOs and mean regret.
3. **Ordinary deals (16):** regret and share correct.
4. **All 40:** regret, share correct, false GO / NO-GO, pages, cost and sessions per deal, and results by deal type.
5. **Looked or not.** For each flagged deal, whether each system opened the settling document (the last document of
   the flagged issue's evidence). Each relief miss is "never looked" or "looked but didn't believe it", reported per system.
6. **Took the warning.** For `s4`, the chance the Deal Lead's first `propose` gave the flagged issue type (and the median). For `s1b`,
   whether it ever noted the flagged issue.
7. **Caution control.** `pilot.s1b_matched` over all 40, reported on the relief deals beside both systems.
8. **Unanswered runs:** scored at face value (GO on every flagged deal) by the runner. Each group reports unanswered
   runs and timeouts, and missing traces are listed. Any unanswered relief run in either system marks the reading
   provisional. Every row must show model `claude-opus-5-5`, or the analysis refuses.

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

## Limits

- On every flagged deal, the CIM's standard sentence denies the issue the seller discloses. This is the same for relief
  and confirmed deals and for both systems.
- Where the settling document sits (board minutes are not in the shared reading guide) may drive "never looked". Report
  the settling document's kind beside that measure (`settling_docs` in the analysis output).
