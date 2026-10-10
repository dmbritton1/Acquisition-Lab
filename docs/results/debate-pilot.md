# Debate pilot: results (exploratory)

**Fixed rules:** `docs/results/debate-pilot-prereg.md`. **Spec:** `docs/superpowers/specs/2026-10-09-debate-pilot-design.md`. **Numbers:** `debate-pilot.json`, written once by `scripts/debate_pilot.py`.

## Result under the fixed rule: "debate doesn't help"

Neither debate system had a lower mean regret than single Claude over the 40 deals:

| System | Mean regret | Difference from single Claude | 95% range | Deals better / worse / tied |
|---|---|---|---|---|
| Single Claude (`s1b`) | **0.0084** | | | |
| Debate, extra pages (`debate_x`) | 0.0089 | +0.0004 | [0.0000, +0.0013] | 0 / 1 / 39 |
| Debate, same budget (`debate_s`) | 0.0109 | +0.0024 | [+0.0001, +0.0056] | 0 / 4 / 36 |
| The team (`s4`) | 0.0135 | | | |

- **The mechanics passed** for both systems. The referee gave a call on all 40 deals, no deal went over its page limit, no step timed out, and no step failed to give a call.
- **The safety check passed.** On the 8 confirmed deals, all four systems passed correctly, with no false GOs.
- **Under the fixed rules, this stops the debate track.**

## Setup

- **Deals:** the same 40 `r2u` deals as the hidden-upside pilot: 16 relief, 8 confirmed and 16 ordinary.
- **The steps.** The reader is single Claude. Then:
  - a bull argues for buying and may read more;
  - a bear argues for passing and reads nothing new;
  - a referee who read nothing makes the call.
- **The two systems:**
  - **`debate_x` (extra pages):** reuses each deal's existing single-Claude run as the reader. The bull reads up to 0.2 of the budget on top.
  - **`debate_s` (same budget):** runs a new reader at 0.8 of the budget, and the bull gets what is left.
- **Model and CLI:** `claude-opus-5-5` on every row; CLI 2.1.291.
- **Dates:** the runs took place on 2026-10-09, with two usage-limit pauses. The prompts were frozen after a smoke test that changed nothing.
- **Cost of the new runs:** $36.53, of which $16.17 was `debate_x` and $20.35 was `debate_s`; the smoke test cost $2.12 more. That is about $0.40 to $0.51 per deal, against single Claude's $0.13. It is above the estimate of $20 to $28 made before the run.

## The other measures

| Group | System | Regret | Correct | False GO / false NO-GO | Pages |
|---|---|---|---|---|---|
| Relief (16) | Single Claude | 0.0148 | 56% | 0 / 7 | 19.6 |
| Relief (16) | Debate, extra pages | 0.0158 | 50% | 0 / 8 | 21.2 |
| Relief (16) | Debate, same budget | 0.0209 | 31% | 0 / 11 | 19.5 |
| Relief (16) | The team | 0.0215 | 25% | 0 / 12 | 22.9 |
| Confirmed (8) | All four | 0.0000 | 100% | 0 / 0 | |
| Ordinary (16) | Single Claude and both debates | 0.0064 | 81% | 1 / 2 | |
| All 40 | Single Claude | 0.0084 | 75% | 1 / 9 | 18.3 |
| All 40 | Debate, extra pages | 0.0089 | 72.5% | 1 / 10 | 20.3 |
| All 40 | Debate, same budget | 0.0109 | 65% | 1 / 13 | 17.4 |

- **Overturned calls.** The referee changed the reader's call on 1 deal in `debate_x` and on 4 deals in `debate_s`.
  - In `debate_x`, the one change was a relief deal turned from a correct GO into a wrong NO-GO.
  - In `debate_s`, three of the four changes were right, all on ordinary deals: one NO-GO turned to GO and two GOs turned to NO-GO. The fourth was a relief deal turned from GO to a wrong NO-GO.
- **Did the bull find the good news?** It opened the settling document where the reader had not on 0 relief deals in `debate_x` and 1 in `debate_s`. The pre-registration predicted close to zero for `debate_x`, because its bull's budget can rarely cover that document.
- **Extra pages compared with the same budget:** `debate_x` minus `debate_s` is −0.0020, with a range of [−0.0052, +0.0006]. `debate_x` did better on 4 deals and worse on 1.
- **Against the team:** both debates have lower regret than the team, with ranges that include zero:
  - `debate_x`: −0.0046, with a range of [−0.0122, +0.0015];
  - `debate_s`: −0.0026, with a range of [−0.0106, +0.0037].
- **Cost per deal, by step:**

  | Step | `debate_x` | `debate_s` |
  |---|---|---|
  | Reader | $0.13 | $0.12 |
  | Bull | $0.16 | $0.16 |
  | Bear | $0.15 | $0.14 |
  | Referee | $0.09 | $0.09 |

  - The bull read 2.0 new pages per deal in `debate_x` and 3.7 in `debate_s`.

## Why it didn't help (exploratory, read from the runs after the fixed analysis)

1. **The referee almost always sided with the reader.**
   - It agreed with the reader on 39 of 40 deals in `debate_x` and on 36 of 40 in `debate_s`.
   - It did so even though the bull and the bear disagreed on 18 and 15 deals respectively.
2. **On the deals that mattered, the bull mostly did not argue to buy.**
   - The deals that mattered are the relief deals where the reader wrongly passed: 7 in `debate_x` and 10 in `debate_s`.
   - The bull argued GO on 3 of the 7 in `debate_x` and on 1 of the 10 in `debate_s`. On the rest it agreed the deal should be passed. It had been told to make an honest case and not to bluff.
   - The referee turned none of these deals to GO.
   - The upside pilot found that single Claude's misses were mostly "read the good news and still passed". Two more readings of the same documents, by the bull and the referee, mostly weighed them the same way.
3. **At the same budget, the debate cannot make up for the reading it gives away.**
   - `debate_s`'s reader alone, at 0.8 of the budget, would have scored 0.0144.
   - The debate improved that to 0.0109: the referee's changes were 3 right and 1 wrong.
   - That is still worse than single Claude reading with the full budget (0.0084).
   - So the 20% of budget handed to the bull was worth more as the reader's own reading.
4. **The design did avoid one failure.** It never turned a confirmed deal into a GO, though the bull argued GO on 1 of the 8 in `debate_x` and 2 of the 8 in `debate_s`.

## What this means

- **On these deals, a bull-and-bear debate before a referee does not correct single Claude's weighing errors.** All three roles share the model's reading of the documents. The "honest advocate" mostly agrees with the reader rather than arguing the other side.
- **The debate track stops here**, as the fixed rules say.
- **The team's caution and single Claude's caution are different problems:**
  - the team mostly doesn't read the good news;
  - single Claude reads it and still passes, and a debate doesn't change that.
- **For stage 2 of the hidden-upside track** ("genuine extra value"), the spec said it would come first if the debate helped. It didn't, so stage 2 comes after Plan 7 (the demo and slides), as planned.

## Limits

- **Small sample:** 40 deals and one run each, so the paired ranges are wide. The same-budget loss to single Claude (+0.0024, with a range just above zero) is the only difference whose range excludes zero.
- **Same deals as before:** these are the 40 deals that showed the "never looked" finding, and the design was shaped by them.
- **The prompts are one design choice.** The "say so rather than bluff" instruction may have made the advocates too agreeable. A bull told to always argue GO might move the referee more, but it would also risk false GOs on confirmed deals. That variant was not tested.
- **Unbalanced reading and order:**
  - Only the bull reads beyond the reader.
  - The summary order is seeded by deal id, and the bear came last on 17 of the 40 deals.
- **The deals:** template prose only, and only one kind of flagged deal (a worry that turns out smaller).
