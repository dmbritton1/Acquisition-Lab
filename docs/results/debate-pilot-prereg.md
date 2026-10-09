# Debate pilot: pre-registration

**Committed before any pilot run.**

| | |
|---|---|
| Spec | `docs/superpowers/specs/2026-10-09-debate-pilot-design.md` |
| Plan | `docs/superpowers/plans/2026-10-09-debate-pilot.md` |
| Runner | `acqlab/bench/debate.py` |
| Analysis | `scripts/debate_pilot.py`, run once into `docs/results/debate-pilot.json` |

The pilot is exploratory. 40 deals give a direction, not proof.

## What runs

| System | Reader | Bull's reading budget | Most pages |
|---|---|---|---|
| `debate_x` | the deal's existing `s1b` run, reused unchanged | 0.2·B on top | 1.2·B |
| `debate_s` | a new single-Claude run at 0.8·B | B minus what the reader spent | B |

- **Steps after the reader:**
  - the bull, who argues for buying and may read;
  - the bear, who argues for passing and reads nothing;
  - the referee, who reads nothing and makes the final call.
- **Deals:** the 40 `r2u` deals in `data/pilot-r2u`: 16 relief, 8 confirmed and 16 ordinary.
- **Baselines:** the finished `s1b` and `s4` runs.
- **Model:** `claude-opus-5-5`.
- **CLI:** `"${CLAUDE_BIN:-claude}" --version` gives 2.1.291 (Claude Code), with `CLAUDE_BIN` unset.

## Measures, fixed now (spec §3)

1. **Main measure: mean regret over all 40 deals.** Each debate system is compared with `s1b` and with `s4`, as a paired difference with a 95% paired-bootstrap range, plus deals won, lost and tied.
2. **Relief deals (16):** false NO-GOs and regret.
3. **Confirmed deals (8):** false GOs. This is the safety check.
4. **Overturned calls:** how often the referee's call differs from the reader's, split four ways:
   - NO-GO→GO right;
   - NO-GO→GO wrong;
   - GO→NO-GO right;
   - GO→NO-GO wrong.

   These are counted overall and by deal group. Deals where the reader or the referee gave no call are counted apart.
5. **The bull's finds:** relief deals where the bull opened the settling document and the reader had not.
6. **Effort per deal:** cost, sessions, pages and decoy pages. Each step's mean cost and pages, and its counts of missing calls and timeouts.
7. **Extra pages:** `debate_x` against `debate_s`, paired.
8. **Failures:** unanswered and timed-out steps and runs.

**Mechanics check, for each debate system:**
- The referee gives a call on at least 38 of the 40 deals.
- No deal's paid units (reads plus searches) exceed B for `debate_s`, or 1.2·B for `debate_x`.

**How the result is read:**

| Result | Rule |
|---|---|
| **Debate helps at the same budget** | `debate_s` has lower mean regret than `s1b` over all 40 deals, **and** at most one more false GO than `s1b` on the confirmed deals, **and** it passes the mechanics check. |
| **Debate helps only with extra pages** | `debate_x` meets those three conditions and `debate_s` does not. |
| **Debate doesn't help** | Neither meets them. |

**What each result leads to:**
- **A "helps" result** earns a larger confirmation test on fresh deals. You decide whether to run it.
- **"Doesn't help"** stops the debate track.

## The frozen prompts

These are the SHA-256 values of `debate.PROMPT_SHA`, one per template:

| Template | SHA-256 |
|---|---|
| `shared` | `5a90675be76cfd91e3e0a64cf09e402d905c83d47d8148e1b88362f91201f601` |
| `bull` | `87b139f56a22be4a9440f84aa28eee87db08bc1c8506ff0cb0d2f7f2baee9824` |
| `bear` | `5e0ed69d1f33616a646a020f1c3bcdd24a73a08913cdfb04bff0993b321c238e` |
| `referee` | `b61b9ea729dc1506358b84b908f85690ac29733f22e0cce18d0b04bba9ebd270` |

**The rest of each step's prompt** (the documents, the summaries, their order and the instructions) is pinned too. The fingerprints below are each step's rendered prompts on a fixed test room:

| Step | Fingerprint |
|---|---|
| Bull | `df9b47eb98b6da4ab8f70734e42e38f85248b86ecbff7c8463a3b3cf0568e19d` |
| Bear | `0b8017de1888aee165981dc7663eff4b720575ccaf4960e58fd6604f77644f28` |
| Referee | `9a218e0291a466d7e2e3b3995d08bb9c7ad4352289e1622fa744a6f089461ac9` |

**How the freeze is enforced:**
- `tests/bench/test_debate.py::test_the_frozen_prompts_are_unchanged` holds all seven values.
- The summaries come from `referee.solo_view`, which `tests/bench/test_referee.py` pins.
- Every run row records `PROMPT_SHA`, and the analysis refuses rows made with any other prompts.

## Smoke test (2026-10-09)

**Setup:** both systems on the practice deals `data/cal-r2` dev-000 and dev-001. Both deals have existing `s1b` runs. The results don't count.

**Mechanics:**
- All 16 steps submitted a call: 4 steps on each of 2 deals for each of 2 systems.
- There were no timeouts and no refused tool calls.
- The units paid stayed within the limits:

  | Run | Paid | Limit |
  |---|---|---|
  | `debate_x` dev-000 | 26 | 26.4 |
  | `debate_x` dev-001 | 24 | 25.2 |
  | `debate_s` dev-000 | 22 | 22 |
  | `debate_s` dev-001 | 20 | 21 |

- Every row is on `claude-opus-5-5` and carries the frozen prompt fingerprints.
- I rebuilt the referee's prompt from the step traces. It held every document read and all three summaries.

**Behaviour:**
- On `debate_x`, the bear twice said the documents favoured buying and declined to bluff, as the prompt asks.
- On `debate_s` dev-000, the referee overturned the reader's GO to a wrong NO-GO:
  - the reader, held to 0.8·B, did not reach the audited notes;
  - the bull said it could not afford them (11 pages against 6 units left);
  - the referee priced the unchecked debt-like risk and passed.

  This is a budget effect, not a prompt fault.

**Outcome:** no prompt was changed. The smoke test cost $2.12.

## Known features of the design (stated now, so they are not read as findings later)

- **The bull's finds in `debate_x` will be near zero.**
  - `s1b` left the settling document unopened on only 3 of the 16 relief deals:

    | Deal | Settling document | Pages | Bull's budget |
    |---|---|---|---|
    | test-006 | `audited` | 14 | 4.6 |
    | test-007 | `board_minutes` | 6 | 4.6 |
    | test-009 | `board_minutes` | 5 | 5.0 |

  - The bull can afford it on test-009 at most.
  - So any gain from `debate_x` has to come from the argument, not from new reading. That matches the upside pilot, where single Claude's misses were mostly "read the good news and still passed".
- **The summary order is seeded by deal id, not balanced.** On the 40 deal ids:
  - the analyst comes first 17 times, the bear 13 and the bull 10;
  - the bear comes last 17 times, the bull 14 and the analyst 9.

  If the referee weighs the last summary more, this could lean slightly toward NO-GO.
- **A missing advocate case is labelled "the analyst's run".** It is shown under the advocate's own heading, with the text "the analyst's run ended without submitting one". That wording is shared with the earlier pilots, which pin it.
