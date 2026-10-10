# Haiku team: tuning log

**Spec:** `docs/superpowers/specs/2026-10-10-haiku-team-design.md` §3. **Scorecard:**
`.venv/bin/python scripts/haiku_practice.py`.

Practice deals only (`data/cal-r2`, `data/heldout-r2`, `data/practice-r2u`; 90 in all). The held-out sets
(`data/test-r2`, `data/pilot-r2u`) are never run before the freeze.

**Base rates** (`acqlab/bench/base_rates.json`, from the 90 practice answer keys): addback 0.23, debt_like 0.41,
concentration 0.36, nwc 0.19, capex 0.24.

**Rules:** one change per round, as a new registry entry in `acqlab/bench/haiku.py`; kept only if
`scripts/haiku_practice.py --keep <new> --over <best>` says True. Cap: 8 rounds or $15, round 0 included.

Each round records: the change and why (the commonest cause of the best candidate's misses), the scorecard before and
after, the cost, and kept or reverted.

## Round 0

Not run yet: awaits the user's OK for the practice phase.
