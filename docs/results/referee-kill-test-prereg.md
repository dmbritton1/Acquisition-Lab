# Referee kill test: rules fixed before any run (exploratory)

This was written and committed before any referee run. It is the first step of the "independent analyses that
reconcile" track (designs A and C, discussed 2026-10-04). It makes real Claude calls, with the user's OK
(2026-10-04).

## The question

On deals where the team (S4) and single Claude (S1b) reached opposite calls, can a referee who sees both analysts' work
and every document either of them read pick the right call?

**If it can't, even with this much evidence, reconciling cannot work here and designs A and C stop.**

## Setup

- **Deals:** the 48 `test-r2` deals where S4's and S1b's calls differ.
- **The referee:** one sandboxed Claude turn on the same model as every system (`claude-opus-5-5`).
  - Its only tools are `evaluate` and `submit`; it cannot read further.
  - It sees the teaser.
  - It sees the full text of every document either analyst opened: 33.5 pages on average, against a budget of about
    22.
  - It sees the general diligence guide every system gets.
  - It sees both analysts' work, labelled Analyst 1 and Analyst 2 in an order fixed per deal from its id:
    - **The team:** its final Deal Record (committed amounts with quotes, open issues, and the engine's call and
      walk-away).
    - **Single Claude:** its last note per issue, its last `evaluate` adjustments and result, and its call,
      walk-away and reason.
- **Runs:** one per deal. A run that never submits is scored as it is elsewhere: the deal's face decision,
  `answered=False`.
- **Code:** `acqlab/bench/referee.py`. It reads the room and the two traces, never an answer key.

## Baselines on these 48 deals (already known)

| Rule | Correct | Mean regret |
|---|---|---|
| The team's call | 25 / 48 | 0.0188 |
| Single Claude's call | 23 / 48 | 0.0315 |
| Always the NO-GO side | 24 / 48 | 0.0191 |
| The right side every time (uses the answer key) | 48 / 48 | 0 |

## The bar

- **Pass (keep exploring A and C):** the referee is correct on **at least 32 of 48** deals **and** its mean regret is
  **below 0.0188**, the team's on these deals.
  - At a coin flip's 50%, reaching 32 has about a 1% chance.
- **Kill:** anything else. The referee designs stop, and the track moves to hidden-upside deals or the Challenger
  replay.

## What a pass would not show

- **It is not a result.** The referee pools about 1.5 times the reading budget. These deals were already examined, and
  each gets one run.
- **A pass only earns the same-budget pilot of C and A** on fresh deals, which would get its own spec and need the
  user's OK.

Estimated cost: 48 sessions, about $5–10.
