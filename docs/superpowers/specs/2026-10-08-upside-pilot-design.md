# Hidden-upside pilot, stage 1: a flagged worry that turns out smaller (design)

**Status:** design, approved section by section on 2026-10-08. Exploratory: a pilot, not a confirmatory test.

**Goal:** find out whether the team's main strength, buying fewer bad deals, is skill or a lean towards NO-GO.

**Why now:**
- Every surprise in today's deals (`r2`) is bad news, so a system that leans NO-GO is rewarded by construction (the
  Plan 5 dev checks, the Plan 6 post-hoc look and the reading simulator all note this).
- Reading S4's code shows that everything it adds can only push its call towards NO-GO:
  - the Challenger asks whether an issue "could be bigger";
  - open issues and pending objections are priced as losses;
  - the seller's documents can't settle an issue.
- The research note `docs/research/agent-teams-research-2026-10-07.md` (Part 3) explains why that matters.

**The two stages (decided by the user):**
- **Stage 1 (this spec): "the feared risk is smaller".**
  - The teaser flags a worry with an upper bound.
  - Independent documents show whether the worry is small ("relief") or large ("confirmed").
  - The frozen team's tools can express this, because every amount stays at zero or above. So this stage tests the
    real frozen team.
- **Stage 2 (later, with the debate design): "genuine extra value".**
  - Documents reveal value the teaser doesn't show.
  - This needs tools that accept negative amounts, which only the new system will have.

**What the pilot is for:**
- Show whether the team turns down good deals when a flagged worry turns out small.
- Show whether that comes from not reading the evidence or from not believing it.
- Give the debate design a test bed of 40 deals with finished baseline runs.
- It cannot prove anything. 16 relief deals is a direction, not a result.

## 1. The new deals

### 1.1 The flagged worry

A **flagged deal** has one flagged issue type, `flag.trap`, and a stated bound `flag.bound` in $M.

- **The bound** is that issue's worst case at severity 1 (`worst_amount`): the top of the range the generator
  already uses.
- **Which issue is flagged:**
  - Chosen from the issue types that can play the role on this deal (§1.2), weighted by `trap_weight`, as flippers
    are chosen today.
  - In practice, add-backs, debt-like items and customer loss qualify most often. Working capital and capex rarely
    do, because their flip points are usually out of range.
  - Add-backs are never flagged, because the CIM's add-back table states the item's size and would reveal the real
    amount (final review, 2026-10-08).
- **The teaser** gains one line, after the capex/NWC line:
  - The line is `Seller discloses: <label>; <bound phrase> up to <money(bound)>.`
  - `<label>` comes from the fact's variant (`render.LABELS`).
  - `<bound phrase>` depends on the issue type:

    | Issue | Bound phrase |
    |---|---|
    | addback | "add-backs that may not be one-time" |
    | debt_like | "estimated exposure" |
    | concentration | "annual revenue at risk" |
    | nwc | "possible shortfall in working capital at closing" |
    | capex | "possible extra capital expenditure per year" |

  - Example: *"Seller discloses: pending customer lawsuit; estimated exposure up to $38.0M."*
  - The exact wording is fixed in the plan. It never states the real amount.
- **Unflagged deals** (all `r2` deals, and the ordinary third of `r2u`) have no such line. Their teaser text is
  unchanged.

### 1.2 Roles and placement

All values are in severity units, as in `roles.py`:
- **0** is face value and **1** is the worst case.
- **`t`** is the flagged issue's flip point, with the other issues at face value (`flip_severity`).

- **"Looks bad" (both new roles):**
  - Pricing the flagged issue at half its bound must give NO-GO, by at least `PULL_BACK` (0.10).
  - In symbols: `t ≤ LOOK − PULL_BACK`, where `LOOK = 0.5`.
  - This uses the smaller margin because the full `MARGIN` (0.20) leaves only about 5% of deals per issue type
    eligible (measured on 400 face-GO bases).
  - Both roles use one flip-point window, `RELIEF_FLOOR + MARGIN ≤ t < LOOK − PULL_BACK` (0.25 to 0.40), so a deal's
    fragility says nothing about its type (final review, 2026-10-08).
- **`relief`:**
  - The real severity is drawn uniformly from `[RELIEF_FLOOR, t − MARGIN]`, with `RELIEF_FLOOR = 0.05`.
  - Combined with the "looks bad" rule, this needs `0.25 ≤ t ≤ 0.40`.
  - The severity is never 0. A zero amount renders as "no such issue", which would contradict the teaser.
- **`confirmed`:**
  - The real severity is drawn uniformly from `[t + MARGIN, 1]`, as for a flipper today.
- **The other four issue types** get today's ordinary roles (`OTHER_ROLES`: clean, decoy or unresolvable), placed by
  today's rules.
- **Where the evidence goes:**
  - The flagged issue's evidence uses `r2`'s placement weights (`_BURIED`) and today's renderers.
  - Its settling document is never the CIM on its own. The renderers already settle every issue in an independent
    document.
- **Whole-deal rules** (otherwise the deal is regenerated):
  - The deal is GO at face value. Every flagged deal is face-value GO, and "looks bad" comes only from the flag.
  - A relief deal is truly GO.
  - A confirmed deal is truly NO-GO.
  - Today's margin rule and "explained flip" rule still apply. For a confirmed deal, the flip is explained by the
    `confirmed` fact.
- **Deal types:** `case_type` returns `relief` or `confirmed` for these deals. Those roles take priority over every
  other role.

### 1.3 The `r2u` profile and the batch

- **`PROFILES["r2u"]`:** `r2`'s placement and budget share (0.25), plus a fixed quota of 16 `relief` and 8
  `confirmed` deals in a 40-deal split.
- **Exact counts:**
  - A seeded shuffle of the split's deal indices assigns the quota cases.
  - The remaining 16 draw their case from `r2`'s case mix as today.
  - Each deal's case is fixed before generation and kept on retry, as `force_case` does today.
- **Deals generated:** 40 template-prose deals, split `test`, base seed 11,250,000. The first choice, 11,000,000,
  clashed with `data/pilot-r2`: seeds clash modulo 1,000,000.
  - The seeds are clash-checked (`testset.clashes`) against `data/cal-r2`, `data/heldout-r2`, `data/test-r2`,
    `data/sim-r2` and `data/pilot-r2`.
  - They go to `data/pilot-r2u`, which git ignores.
  - No Codex calls.
- **Versions:** `GENERATOR_VERSION` becomes 4.1.0, and 4.1.1 after the final review (final review, 2026-10-08).
  - `DealTruth` gains `flag: Flag | None = None`, where `Flag` holds `trap` and `bound`. Older answer keys load with
    no flag.
  - Any seeded `r2` deal must generate exactly as before, apart from the `generator_version` label.

### 1.4 Checks on every new deal

These are added to `validate.py`:
- **`check_engine`:**
  - The deal is NO-GO with the flagged issue at half its bound, by the margin.
  - The relief or confirmed amount is on the right side of `t` by `MARGIN`.
  - The relief amount is greater than 0.
  - The stored GO / NO-GO matches the type.
- **`check_leaks`:**
  - A flagged deal's teaser may contain the words of its own flagged issue. `LEAK_WORDS` matching that issue's label
    are allowed for that deal only.
  - The teaser must not contain `money(amount)` for any fact.
  - Unflagged teasers are checked as today.

## 2. The paid pilot

### 2.1 What runs

- **Systems:** `s1b` (single Claude) and `s4` (the frozen team, tag `s4-frozen-plan5`).
- **Runs:** one run per deal, with the existing runner (`acqlab.bench.pilot --split test --n 40`), which resumes after
  a stop.
- **Model:** `claude-opus-5-5` on Claude Code CLI 2.1.291 or newer, checked in every row.
  - The CLI version is recorded before the runs start (final review, 2026-10-08).
  - Every row must show model `claude-opus-5-5` (a timed-out row may show none), or the analysis refuses (final review, 2026-10-08).
- **Cost:** about $28 (`s4` about $22, `s1b` about $6, from the recon pilot's per-deal costs).
- **The paid runs wait for the user's OK.** That OK is asked for after the code is built and tested, the deals are
  made, the free checks pass and the fixed rules are committed.

### 2.2 Free checks before any paid run

Run with `scripts/upside_pilot.py --check`. Each one must hold, or the deals are fixed before anything is paid for.

1. **Engine on the true amounts:** 40 of 40 correct.
2. **"Price the warning at half"** (flagged issue at `0.5·bound`, nothing else): wrong on all 16 relief deals and
   right on all 8 confirmed deals.
3. **"Ignore warnings"** (face value): right on all 16 relief deals and wrong on all 8 confirmed deals.
4. **Counts:** exactly 16 relief, 8 confirmed and 16 ordinary deals.

### 2.3 Measures (fixed before the paid runs)

Every measure is reported per system, paired on the same deals. Each confidence range is a paired bootstrap with 95%
coverage, as in Plan 6 (`analysis.compare`).

1. **Main measure: relief deals (16).**
   - False NO-GOs per system.
   - Mean regret, and the paired difference `s4 − s1b` with its confidence range.
2. **Confirmed deals (8):** false GOs per system, and mean regret.
3. **Ordinary deals (16):** regret and share correct, to see whether the old pattern repeats.
4. **All 40:**
   - regret, share correct, false GO / NO-GO;
   - pages, cost and sessions per deal;
   - results by deal type.
5. **Looked or not.** The *settling document* is the last document of the flagged issue's evidence, `docs[-1]` (as
   `recon_pilot.reached`). For each flagged deal and system, record whether it was opened. Each relief deal a system
   gets wrong is classed as one of two:
   - **"never looked":** the settling document was not opened;
   - **"looked but didn't believe it":** it was opened, and the system still said NO-GO.
6. **Took the warning.**
   - For `s4`: the chance the Deal Lead's first `propose` gave the flagged issue type.
   - For `s1b`: whether it ever noted the flagged issue type (`note_issue`).
   - Reported per deal and as a median, so a result where the team never priced the warning reads as "warning
     ignored", not "evidence weighed well".
7. **Caution control.** `pilot.s1b_matched` is computed over all 40 deals: single Claude made exactly as cautious as
   the team. Its false NO-GOs and regret on the 16 relief deals are reported beside both systems.
8. **Unanswered runs and missing traces** (final review, 2026-10-08):
   - unanswered runs are scored at face value (GO on flagged deals);
   - each group reports unanswered runs and timeouts;
   - any unanswered relief run in either system marks the reading provisional;
   - missing traces are listed per system;
   - the cost mean leaves out runs with no cost.

### 2.4 How the result is read (fixed before the paid runs)

On the 16 relief deals:

| Result | Rule |
|---|---|
| **Team leans on caution** | `s4` has at least 3 more false NO-GOs than `s1b`, **and** a higher mean regret. |
| **Team weighs evidence fine** | `s4` has no more false NO-GOs than `s1b`. |
| **Unclear** | Anything else. |

**Two notes the write-up adds, with no change to the reading:**
- If the team's median opening chance on the flagged issue is below 0.5, it says the warning was mostly not priced.
- It says which failure class (§2.3 item 5) holds most of each system's relief misses.

**What the result decides:**
- What the pitch may say about the team.
- What the debate design targets:
  - mostly "looked but didn't believe it" points to weighing, so a debate over documents already read is enough;
  - mostly "never looked" points to reading, so the bull advocate needs a small reading budget.

It does not decide whether the debate design goes ahead; the user has already chosen it.

### 2.5 Write-up

- `docs/results/upside-pilot.md` and `upside-pilot.json`.
- The json is written once by `scripts/upside_pilot.py`, which refuses to overwrite an existing file.
- The analysis fails with an error if the two systems' deal lists differ from the split's 40 deals.
- `docs/HANDOFF.md` gets a research-track bullet.

## 3. Build and tests

**Unchanged:**
- `acqlab/agents` and `acqlab/routers` stay byte-identical to tag `s4-frozen-plan5`. The existing test checks this.
- The tools are unchanged, and so is single Claude's prompt.

| File | Change |
|---|---|
| `acqlab/generator/roles.py` | Places `relief` and `confirmed` (§1.2). New constants `LOOK = 0.5` and `RELIEF_FLOOR = 0.05`. |
| `acqlab/generator/truth.py` | `Flag`; `DealTruth.flag`; the `r2u` profile with its quota; `_plan` for the two new cases; `case_type` priority; version 4.1.0. |
| `acqlab/generator/render.py` | `teaser_text` adds the disclosure line on flagged deals (§1.1). |
| `acqlab/generator/validate.py` | The §1.4 checks. |
| `acqlab/generator/batch.py` | Quota assignment by seeded shuffle (§1.3). |
| `acqlab/bench/analysis.py` | `CASES` gains `relief` and `confirmed`. |
| `scripts/upside_pilot.py` (new) | `--check`: the free checks (§2.2). Default: the analysis (§2.3) into `--out`, refusing to overwrite. |
| `docs/results/upside-pilot-prereg.md` (new) | §2.3–2.4 restated, with the deal seeds and the `--check` output. Committed before the paid runs. |

**Tests (in `tests/generator` and `tests/bench`):**
- **`relief`:**
  - the deal is NO-GO at half the bound by the margin, and truly GO;
  - the amount is at least `RELIEF_FLOOR · worst` and at most `(t − MARGIN) · worst`, and never 0.
- **`confirmed`:** NO-GO at half the bound, truly NO-GO, and the amount is at least `(t + MARGIN) · worst`.
- **The teaser:**
  - the disclosure line appears only on flagged deals, names the flagged issue's label and shows the bound;
  - it never shows any fact's real amount.
- **Nothing old changes:**
  - five seeded `r2` deals' answer keys (apart from `generator_version`), documents, evidence and teasers hash to the
    value pinned from the old code;
  - old answer keys load with `flag` set to `None`.
- **The quota:** a 40-deal `r2u` split has exactly 16 relief, 8 confirmed and 16 others, and the same seed gives the
  same assignment.
- **The free checks:** on a small `r2u` batch, `--check` produces the §2.2 pattern.
- **The analysis:**
  - on a fake finished pilot, it reports the §2.3 measures, including the "looked or not" classes and the caution
    control;
  - it refuses to overwrite;
  - it fails when a system's deals differ from the split.

**Order of work:**
1. Generator.
2. Generate the deals and run `--check`.
3. Commit the fixed rules.
4. The user's OK.
5. Paid runs.
6. Analysis and write-up.

## Out of scope

- **Stage 2** ("genuine extra value", negative amounts) and the **debate design**: separate specs, which reuse these
  40 deals.
- **A confirmatory test:** a 160-deal or larger run only if this pilot gives a clear direction and the user asks for
  it.
- **Any change to S4, single Claude's prompt or the tools.**
- **Codex-written prose.**

## Limits (stated in the write-up)

- **A flagged issue is always at least a little real.** That's true to life, and it's the same for both systems.
- **Flagged deals are a particular kind of deal:** ones where the flagged issue decides the call at 25–40% of its
  range. They are not a random draw.
- **The 2:1 relief-to-confirmed ratio is chosen, not a real-world base rate.** The all-40 averages depend on it, so
  the per-type results come first.
- **16 relief deals, one run each.** A direction only.
- **Template prose only.**
