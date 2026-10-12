# Mixing Opus, Sonnet and Haiku: the cost and quality frontier (design)

**Status:** design, approved section by section on 2026-10-11. It starts after the Haiku team's final test and
write-up are done.

**Goal:** find the mixes of Claude Opus 5.5, Sonnet 5.5 and Haiku 5.5 that give the best buy/pass decisions per
dollar, and test the best few once on fresh held-out deals. The user wants all three readings:
- **the frontier:** every frozen mix's quality against its cost;
- **"beats single Opus for less":** the best mix cheaper than single Opus;
- **"matches the Opus team for less":** the best mix cheaper than the Opus team.

**Why:**
- **The Haiku track.** On held-out deals, Haiku systems were somewhat worse than single Opus at about a sixth to a
  twentieth of the cost (interim, 2026-10-11). On new deals the Haiku teams added little over single Haiku.
- **A free check on 60 practice deals** (found after the fact, so it is a lead, not a result): "single Haiku decides;
  if it says pass, ask the Opus team" scored regret 0.0083 at $0.445 per deal. The Opus team alone scored 0.0090 at
  $0.535.
- **Haiku says pass on 82% of deals,** so a cascade is cheap only with a sharper signal for when to escalate.
- **The subagent-driven-development pattern:** use the cheapest model for each role, and escalate only when it is
  stuck.
- **The API guide's advice:** before building a cascade, try the strong model at lower effort.

## 1. What is compared, and on what

**Fresh held-out deals:**
- 100 deals: 80 in `data/mix-test-r2` (profile `r2`) and 20 in `data/mix-test-r2u` (profile `r2u`). That is the same
  4:1 mix as the Haiku test's 160 and 40.
- Their seeds are checked against every seed under `data/` (`testset.clashes`).
- No model touches them until the mixes are frozen.

**Baselines on the fresh deals:**
- `s1b` (single Opus) and `s4` (the Opus team, frozen at tag `s4-frozen-plan5`), run by `acqlab.bench.pilot` as before;
- `mix_haiku_solo` (single Haiku), the cheap reference.

**Practice deals:** the same 90 as the Haiku track: `data/cal-r2`, `data/heldout-r2` and `data/practice-r2u`, all on
the dev split. All design choices come from these deals only.

**Prices:** each step is priced from its token counts at list prices, in $ per million tokens.

| Model | Input | Output | Cache read | Cache write (1 hour) |
|---|---|---|---|---|
| `claude-opus-5-5` | 4 | 20 | 0.20 | 8 |
| `claude-sonnet-5-5` | 2 | 10 | 0.20 | 4 |
| `claude-haiku-5-5` | 0.10 | 0.50 | 0.01 | 0.20 |

**The frontier rule:**
- Each candidate has a practice regret and a practice cost per deal.
- The frontier is the set of candidates that no other candidate beats on both at once.
- Up to 4 frontier candidates are frozen. The four always include:
  - the lowest-regret candidate cheaper than `s1b` on practice;
  - the lowest-regret candidate cheaper than `s4` on practice;
  - after those, the cheapest frontier points first.

**Verdicts on the fresh deals:**
- Each frozen mix is compared with `s1b` and with `s4`: a paired regret difference with a 95% paired-bootstrap range
  (`analysis.compare`), plus deals better, worse and tied.
- The wording is fixed, as in the Haiku track:

  | Paired 95% range | Verdict |
  |---|---|
  | Wholly below zero | "better" |
  | Wholly above zero | "worse" |
  | Includes zero | "no clear difference: at most X worse", where X is the range's upper end |

- Each verdict is stated with its cost ratio.
- The two named readings come from these verdicts and costs:
  - **"beats single Opus for less":** a mix that is cheaper than `s1b` and not "worse" than it;
  - **"matches the Opus team for less":** a mix that is cheaper than `s4` and not "worse" than it.
- Results are given on the 80, the 20 and all 100.
- A quality-against-cost table covers every system.

## 2. Screening and tuning on the practice deals

**Fixed first:**
- `s1b` on the 30 `practice-r2u` deals, so that every practice deal has an Opus answer to escalate to. About $4.
- A one-deal check that CLI 2.1.291 accepts `--model claude-sonnet-5-5` and `--effort low`. It costs pennies, on a
  practice deal.

**Round 0, the building blocks:** each runs on all 90 practice deals.

| Candidate | What it is | Estimated cost per deal |
|---|---|---|
| `mix_sonnet_solo` | Single Claude's prompt and tools, on Sonnet | ~$0.07 |
| `mix_opus_low` | Single Claude on Opus at `--effort low` | ~$0.09 |
| `mix_h_opus1` | Haiku reader at the full budget, then 1 Opus pricer (zero rule), then the engine on base-rate-calibrated notes (`w` = 0) | ~$0.08 |
| `mix_h_sonnet3` | Haiku reader, then 3 Sonnet pricers (zero rule, `w` = 0), then the majority of the engine calls | ~$0.12 |

**Cascades:**
- A cascade is a cheap system, a strong system and an escalation signal.
- **Its call:** the strong system's call on escalated deals, and the cheap system's call otherwise.
- **Its cost:** the cheap system's cost, plus the strong system's cost on escalated deals only.
- **Scoring is free:** cascades are scored from rows that already exist, with no new runs.
- **The cheap systems:** `haiku_solo`, `haiku_lean_zero_w0` and the round-0 candidates.
- **The strong systems:** `s1b`, `s4`, `mix_opus_low` and `mix_sonnet_solo`.
  - `s4` has no runs on `practice-r2u`, and running it there would cost about $16, which breaks the cap. So cascades
    that escalate to `s4` are scored on the 60 practice deals that have `s4` runs, and the scorecard flags them.
- **The signals use public information only:**
  - **the cheap call is a pass;**
  - **the pricers disagree** (for pipelines with three pricers);
  - **the call is close to the line:** the walk-away is within a margin `m` of the asking price, which is read from the
    teaser;
  - **the teaser flags a seller exposure;**
  - an OR of any of these.
- Each margin `m` is a candidate setting, taken from {2%, 5%, 10%}.

**Tuning rounds:**
- At most 3 after round 0, under the Haiku track's rules:
  - one change per round, rerun on the 90 deals;
  - kept only if practice regret falls and neither relief false NO-GOs nor confirmed false GOs rise;
  - each round logged in `docs/results/mix-tuning-log.md`.
- **Practice cap:** $50 for everything in §2, under one OK from the user.

**Freeze:**
- the up to 4 frontier mixes are chosen by the §1 rule;
- their prompts, models, effort levels, settings and cascade signals are pinned by a fingerprint test;
- `docs/results/mix-prereg.md` is committed before any fresh deal runs.

## 3. Build

`acqlab/agents`, `acqlab/routers` and the Haiku track's `acqlab/bench/haiku.py` stay unchanged. The frozen Haiku
track's tests must still pass.

| File | What it does |
|---|---|
| `acqlab/bench/mix.py` (new) | Described below the table. |
| `scripts/mix_practice.py` (new) | The practice scorecard: each system's regret, correct, false GOs and NO-GOs by set and type, cost and health. Every cascade is scored from existing rows, and the frontier is picked by the §1 rule. It writes nothing. |
| `scripts/mix_final.py` (new) | The one-shot final analysis into `docs/results/mix.json`. It refuses to overwrite, and it refuses wrong models, missing deals, missing traces or unfrozen fingerprints. |
| `data/mix-test-r2`, `data/mix-test-r2u` | The fresh deals. Git-ignored. |

**What `mix.py` holds:**
- **`on_model(model, effort)`:** the run-time model switch, swapping `solver.command`. It applies per step, so one
  pipeline can mix models.
- **Pipelines:**
  - `single(model, effort)`;
  - `pipeline(reader=(model, effort), pricers=(model, effort, n), w, zero)`. This reuses `haiku.second_zero`,
    `haiku.calibrated_call`, `haiku.vote`, `recon.step` and `recon.combine`.
- **Per-step pricing:** each row stores every step's model and tokens (`steps`), and its cost is the sum of the steps'
  list prices. A row's summed tokens cannot price a mixed-model run.
- **Cascades:** `cascade(cheap_row, strong_row, signal)` gives the call and the cost. The signals read only the rows
  and the room's teaser, never `truth/`.
- **The registry:** candidates with their fingerprints, covering prompts, models, effort, settings and signal.
- **The runner:** it skips finished deals, pauses and resumes at usage limits, and retries. It refuses `mix-test-*`
  before the freeze (`MIX_FINAL` set).

**Tests use the fake Claude:**
- each step's command line gets its own `--model` and `--effort`, and Opus is restored afterwards;
- per-step pricing adds up across mixed steps;
- each cascade signal fires as specified and reads no answer key;
- the frontier rule, including the two named picks;
- the runner's refusals;
- each branch and refusal of the analysis;
- the frozen files are unchanged.

## 4. Order of work and cost

1. **Build and test,** subagent-driven (free).
2. **Generate the fresh deals,** then the one-deal CLI check (pennies).
3. **The user's OK, then the practice phase** (cap $50).
4. **Freeze** and pre-register.
5. **The user's OK, then the final test.**
   - It runs `s1b`, `s4`, `mix_haiku_solo` and the frozen mixes on the 100 fresh deals.
   - Estimate: about $67 for the Opus baselines, $1 for single Haiku and about $40 for the mixes, so about $110 in all.
   - It takes about a day, with usage-limit pauses.
6. **Run the analysis once.** Then a plain-language write-up (`docs/results/mix.md`, with the quality-against-cost
   table) and a `docs/HANDOFF.md` update.

## Out of scope

- Fable 5.1; fast mode; the Batch API (this project runs through the Claude Code CLI).
- Changes to the frozen team or to single Claude's prompt.
- More than one run per deal in the final test.

## Limits (stated in the write-up)

- **Practice selection:** the candidates and cascades are picked on the same 90 practice deals, so their practice
  scores are flattered. The fresh test is the guard.
- **100 fresh deals:** paired ranges of about ±0.007 regret, so small differences will read as "no clear difference".
- **Running every system on every deal:** cascades are evaluated with the strong system's existing run on every deal,
  but charged only on escalated deals. A live cascade would run the strong system only when escalating, and its calls
  would be the same.
- **Prices are list prices from token counts.** They are not what a subscription or the CLI charges.
