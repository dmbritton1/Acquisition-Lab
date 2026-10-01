# Acquisition Lab: Session Handoff

*Last updated 2026-09-27, after Plan 5's checks and the Plan 6 design. Read this first, then the reframe spec. The
specs are the binding authority on design; this file is the source of truth for status and next steps.*

## Resume here (2026-09-27)

A new session (possibly on the user's other Claude account) continues from this point.
- **Where to work:** worktree `.claude/worktrees/plan-4b-freeze-preregistration-0908fa`, branch
  `claude/plan-4b-freeze-preregistration-0908fa`; `plan-5` (worktree `plan-4b-calibration-round-1-5f0549`) is
  fast-forwarded to it after each finished step (`git -C <that worktree> merge --ff-only <branch>`). The data
  (`data/cal-r2`, `data/heldout-r2`) is in this worktree, git-ignored.
- **Plan 5 is done:** S4 frozen (tag `s4-frozen-plan5`); the results are in `docs/results/plan-5-dev-checks.md` and
  the Next steps below.
- **Plan 6 (the main run): Tasks 1–7 are done** (plan `docs/superpowers/plans/2026-09-27-plan-6-main-run.md`,
  spec `docs/superpowers/specs/2026-09-27-plan-6-main-run-design.md`). Built subagent-driven with a review per task
  and a final whole-branch review; 335 tests pass. The addendum (`docs/results/plan-6-preregistration-addendum.md`)
  is committed; the free rehearsal passed (every phase, no regret in the log). Changes beyond the plan: the campaign
  refuses to start unless `CLAUDE_BIN` is Claude Code 2.1.280; a reset time that just passed waits 30 minutes, not a
  day; only real usage-limit wording is waited out (the message is logged); waits follow the wall clock (Mac sleep);
  the analysis refuses an existing `--out` and re-checks the S4 freeze.
- **Done since:** Task 8, the valuer on real Claude (2 `cal-r2` deals, all 4 turns answered, $0.22; in
  `docs/results/plan-6-prompt-log.md`). Task 9, the test set `data/test-r2` generated once (160 deals, 0 problems),
  fingerprint committed in `docs/results/plan-6-test-set.json`/`.md`; no system has run on it. The user chose three
  retries (10, 30, 90 minutes) on non-usage-limit errors; the spec says so. 337 tests pass.
- **Task 10 done:** recoverability on 20 test deals found 8 problems, all zero-amount facts stated in awkward
  template wording ("$0.0M below normal levels"); understood, reported in `docs/results/plan-6-test-set.md`, and the
  user decided to proceed without regenerating (2026-09-28).
- **Plan 6 is done (2026-10-01).** The campaign ran 2026-09-28 10:51 to 2026-10-01 00:34 with no errors; the
  analysis ran once. Results: `docs/results/plan-6-main-run.md` (numbers in `plan-6-main-run.json`). Headline: the
  Team's regret is 30% below Solo's and below best-of-2 Solo, but the CI includes zero, so **H1 fails as
  pre-registered**; **H2 holds** (the gain is on interaction and flip deals); H3 not shown; H4 fails (S4 reads more
  decoy pages); H5 fails on the ratio (1.54×, not 2×, though the engine clearly helps); H6 too few to test (0 deals).
- **Next:** Plan 7, the demo and slides (the showcase deal moved there), reporting Plan 6 as it came out. Still
  open: the "hidden upside" note (Plan 5 dev checks), and the deferred minors in the Plan 6 ledger.
- **Working conventions:** the user prefers plain explanations (they have asked for "explain like I'm 12"); ask
  before any real Claude or Codex call; commits end with the Co-Authored-By trailer the session's attribution names.
- **Codex:** the dacuber01 account, out of usage on 2026-09-26.
- **Two accounts:** development can move between the user's accounts through this file. The runner's `claude -p`
  calls use whichever account the Claude app is signed in to; switching accounts to get past usage limits may conflict
  with Anthropic's terms (the user checks); the runner does no account switching.

## Start here

**Where things stand:**
- Plans 1–4 are merged to `main`. Calibration passed on round 2: profile `r2` is frozen and the test size is 160 deals
  (`docs/results/plan-4b-preregistration.md`).
- **Plan 5 (S4, the multi-agent panel): Tasks 1–5 are built** on branch `plan-5` (worktree
  `.claude/worktrees/plan-4b-calibration-round-1-5f0549`). 277 tests pass. The work was subagent-driven, with a review
  per task and a final Opus review of the whole branch.
  - The reviews found and fixed real bugs the pre-verification missed. The plan's "Post-review changes (after
    execution)" section lists each fix.
  - The SDD ledger, with every ruling and every deferred minor, is at
    `.superpowers/sdd/2026-09-25-plan-5-s4-panel/progress.md` (git-ignored).
- **Task 6 (real runs) is in progress.** Results are in `docs/results/plan-5-dev-checks.md`.
  - Smoke run on 3 deals (`ef8f418`): the machinery works. It fed two code fixes (`c989fb1`): an objection nobody could
    afford to check changes nothing, and the sweep reads only documents on the diligence map. The smoke runs are kept in
    `data/cal-r2/s4-smoke-ef8f418`.
  - `s4` on `cal-r2` dev-000..009 (`c989fb1`):
    - 7/10 correct, the same as S1b; paired regret difference −0.0037, 95% CI [−0.024, 0.018].
    - $0.49 and 9.4 sessions per deal; `s3_n` = 2. The Committer refused 0 of 37 reports.
  - **S4's two wrong NO-GOs (dev-000, dev-006) come from two causes, both diagnosed offline:**
    1. **The router is myopic.** The Deal Lead starts every issue at chance 0.35–0.5 over wide ranges. At those chances,
       no single check can change the engine's call, so router 6 scores every issue 0 and `panel.pick()` stops. dev-006
       did no directed reading at all.
    2. **The Lead barely lowers a chance after reading without settling it.** For example, concentration went
       0.4 → 0.4 → 0.35 across three documents.

**Suggested first message for the next session:** see "Next steps" below.

### Next steps

1. **Done: D1 (router fallback), then D2 (the document router)**, which supersedes it. Spec
   `docs/superpowers/specs/2026-09-25-doc-router-design.md`, plan `docs/superpowers/plans/2026-09-25-plan-5-d2-doc-router.md`.
   Offline checks and the audit are in `plan-5-dev-checks.md`.
   D1 and D2 are on branch `claude/plan-4b-freeze-preregistration-0908fa` (worktree
   `.claude/worktrees/plan-4b-freeze-preregistration-0908fa`, which also holds a copy of `data/cal-r2`); `plan-5` is
   behind it and fast-forwards to it.
2. **Withdrawn: the Lead prompt fix.** "Not found" is no evidence against an issue, because a clean fact states
   $0.0M; the Lead holding its chance was correct. The map's order (off for `r2`) and the board minutes (off the map)
   are a later fairness question for the shared guide, which S1b also gets.
3. **Done: the D2 re-run on all 30 `cal-r2` dev deals** (`plan-5-dev-checks.md`): S4 26/30 correct vs S1b 22/30; mean
   regret 0.0107 vs 0.0195 (45% lower), paired difference −0.0088, 95% CI [−0.0228, +0.0055]; $0.49 and 10.8 sessions
   per deal; `s3_n` = 2. S4's losses: dev-022 (the Challenger named the QoE but had no budget left), dev-006 and dev-017
   (caution from unsettled issues), and dev-003 with S1b (CIM claims committed as fact).
4. **Done: D3 (the Challenger at the midpoint, CIM claims)** and its 30-deal re-run (`plan-5-dev-checks.md`): 26/30,
   mean regret 0.0076 vs S1b 0.0195 (61% lower), paired difference −0.0119, 95% CI [−0.0243, −0.0016]; D3 − D2
   −0.0032, CI [−0.0118, +0.0015] (dev-022 won, dev-010 lost). The Challenger now gets 10–14 pages, but only 32% of
   its objections get a named document read; both changed calls turn on late objections that no budget remains to
   settle. The CIM rule never fired (no run opened the CIM). Then the D3 addendum (D3 spec §8): with the router,
   reading always runs in two passes, so the −Challenger ablation reads in S4's order and H3 compares only the
   objections.
5. **Done: the held-out check** (`plan-5-dev-checks.md`, criteria committed before the run): 30 fresh `r2` deals
   (`data/heldout-r2`, `--seed 630000`). **Fails:** S4 regret 0.0105 vs S1b 0.0078 (all 30), 23/30 vs 27/30
   correct; all 7 of S4's wrong calls are NO-GO on good deals. Replaying the 59
   final records: the Lead's chance for issues S4 never settles averages 0.38 against 22% real, and that lean, not the
   Challenger, decides these calls. The batch was a GO-heavy draw (19 of 29; `r2` is 45% GO, 53% flips, all flips
   toward NO-GO); reweighted to `r2`'s mix S4 is 42% below S1b (90%: −73% to −5%). Decided 2026-09-26: don't tune
   the Lead's chances (parity); next, a pessimism control (below).
6. **Next: a pessimism control.** Every `r2` surprise points to NO-GO, so a system that leans NO-GO is rewarded by
   design. **Done** (`plan-5-dev-checks.md`, `pilot.s1b_matched` in the report): S1b made just as pessimistic as S4
   barely improves on `cal-r2` (0.0195 → 0.0182) and gets worse on the held-out batch (0.0078 → 0.0168); S4 beats it
   on both (−0.0106, CI [−0.0222, −0.0018]; −0.0064, CI [−0.0165, +0.0010]). S4's edge is in which deals it
   rejects, not only how many. Report it beside H1 in the main run.
   **Note to explore later (user, 2026-09-26):** `r2` has no hidden upside (deals that look NO-GO but are GO). Adding
   it would be fairer to systems that don't lean NO-GO, but changes the frozen profile and the pre-registration.
7. **Done (2026-09-26): S4 frozen** at `b728999`'s S4 code (tag `s4-frozen-plan5`); prompt tuning skipped (fitting
   risk); `s3_n` = 2 on both batches; main-run budget about $230 notional and 17 h of runs, about 14 usage windows
   (`plan-5-dev-checks.md`). The user decides subscription or API.
8. **Done: build-step checks** (`plan-5-dev-checks.md`), 10 `cal-r2` deals, $11.65: regret S1b 0.0280, `s4_1`
   0.0263, `s4_2` 0.0080, `s4_3` 0.0134, `s4` 0.0183. The gain appears with the Deal Lead's issue-by-issue
   investigation (`s4_2`); the Challenger and the router show no regret gain over it on 10 deals (the router cuts cost
   from $0.80 to $0.50). Their tests are the ablations (H3); S4 stays frozen.
   **Decided (user, 2026-09-26): recoverability on a sample.** A seeded random sample of 20 test deals (about 200
   Codex calls, about 4 Plus usage windows), not every test deal: the documents are template prose and the generator
   has had 0 batch problems on over 500 `r2` deals, so a sample catches a generator bug. Codex stays the extractor
   (main spec §2: a non-solver family). Any failure stops the main run until it is understood. Before it gates scored
   deals, close Codex's read access (see "Codex can read files" below).
9. **Then Plan 6:** the test set generated once (seeds clear of 610000–640499 and the audits), the four ablations,
   the run schedule, and the analysis (H1–H6, with the pessimism control beside H1).

### Other outstanding items
- **Codex recoverability check (waiting on Codex quota, 2026-09-26).** The user OK'd it on the dacuber01 Codex account
  (Plus; the CLI in `/Applications/ChatGPT.app` is signed in to it), which was out of usage on 2026-09-26. A dry run
  with Codex stubbed found the old `data/poc` cache (in worktree `acqlab-handoff-review-677fc2`) no longer matches: the
  generator changed since Plan 2, so the old `--llm --recover 3` command is a fresh ~180-call run (120 prose calls,
  ~200k tokens per deal), and it tests Codex prose, which the benchmark does not use (`cal-r2` is template prose).
  Recommended instead, 40 extraction calls on template-prose `r2` deals, no test deals:
  ```bash
  uv run python -m acqlab.generator.batch --out data/recover-r2 --dev 3 --test 0 --hand 0 --showcase 1 --recover 3
  ```
  Before the main run: a sample of 20 test deals (decided 2026-09-26, item 8 above), not all 160.
- **The Plan 1 Task 9 spreadsheet check** is still deferred by the user.

## The claim and the hypotheses (reframe design, 2026-09-24)

**Headline to prove:** "On deals where a strong single Opus agent makes costly mistakes, a panel that uses a
deterministic LBO engine to challenge its own beliefs cuts decision regret by at least 25%, at the same diligence
budget."

**User decisions:**
- **The goal** is to win the competition *and* have a number that survives a sceptical judge.
- **The headline must beat a single Opus.** A tie or an efficiency claim is not acceptable.
- **Approach 1:** a hard benchmark, calibrated on S1b alone.

**Why the claim changed.** At the Plan 4a checkpoint, four router versions (120 runs, the last on 30 fresh,
pre-registered deals) never improved a decision over S1b:
- **The router reliably changes reading:** 8–12% fewer pages and 68% fewer decoy pages.
- **S1b's misses come from beliefs:**
  - two-issue interactions
  - evidence it thinks is somewhere else, or smaller than it is
  - caution on good deals
- **H1 was untestable on the old benchmark.** S1b's regret was 0.006–0.009 per asking price.

**The contribution is now engine-grounded challenge of beliefs.** Code and the engine test "what would have to be true
to flip this deal":
- pairwise interactions
- "could it be bigger?"
- "is the evidence elsewhere?"

The Challenger and the Deal Lead must answer those tests. The router stays as a component. The fallback claim, "the
router is what matters even for one agent", is retired.

**Hypotheses** (to be pre-registered at the freeze, before any test deal exists; spec §3):
- **H1 (headline).** S4's regret is ≥ 25% lower than S1b's on the frozen hard test set, with a paired bootstrap 95% CI
  excluding zero. S4 must also beat S3 (best-of-N S1b at matched tokens), so "more tokens" can't explain the win.
- **H2.** The gain concentrates on interaction and belief-error deals.
- **H3.** Removing the Challenger increases regret.
- **H4.** S4 spends less budget on decoys than S1b.
- **H5.** Removing the engine sharply increases walk-away error.
- **H6.** The residual sweep helps when a trap isn't on the Deal Lead's initial list.

**Fairness.** S1b, S3 and every single-agent system get the same diligence knowledge that S4 has in code,
`knowledge.GUIDE`, in their prompt: where each issue is usually settled, and its typical size. The only difference
between systems is then architecture.

**Schedule** (competition about mid/late November 2026; spec §6):

| When | Plan | Delivers |
|---|---|---|
| now to about 2026-10-02 | 4b | Calibration rounds, freeze, pre-registration |
| about 10-02 to 10-23 | 5 | S4, in the build order below, each step checked against S1b on dev and calibration deals |
| about 10-23 to 11-06 | 6 | Test set generated once; S1b, S3, S4, S0 and ablations; paired bootstrap for H1–H6 |
| about 11-06 to 11-20 | 7 | Demo (fork chart, the "these two together flip it" moment, the evidence trail) and slides |

**S4's build order** (spec §5):
1. Deal Record, Committer, and the engine making the go/no-go call
2. Investigator with intent briefs
3. Challenger with the pairwise screen
4. Router plus residual sweep

**Ablations:** −Challenger, −engine, −residual sweep, and "LLM decides".

**The main run** is funded by API credits (roughly $300–400) or spread over several days on the subscription. Decide in
Plan 5 from S4's measured tokens per deal.

## Plan 4b: the hard benchmark (2026-09-24)

Spec: `docs/superpowers/specs/2026-09-24-reframe-design.md` (§4, and the §8 revisions from pre-verification). Plan:
`docs/superpowers/plans/2026-09-24-plan-4b-hard-benchmark.md` (its "Findings" section matters). Commits `8c1dbd3` to
`94d8df3` on `plan-4`.

**What it built:**
- **Search-safe reveal wording** (generator **4.0.0**).
  - A real problem and a clean fact render the *same* sentences; only the numbers differ, and a clean fact states
    `$0.0M`.
  - An unresolvable fact writes its range where an amount would go, e.g. `$6.8–$19.2M`.
  - Word leaks on 500 deals went from 48 to 0.
- **Role-blind placement.** Placement no longer depends on a fact's role, so where a sentence sits says nothing either.
  Plan 2's "decoys loud, flippers buried" rule is gone, and so is the "range" placement.
- **Search is back** for every system.
  - It costs 1 unit and returns the ids of the documents holding the 5 best-matching paragraphs, often fewer than 5
    documents.
  - It never returns text, and it matches letters only.
- **`acqlab/agents/knowledge.py`** holds `DILIGENCE_MAP`, `typical_high` and `GUIDE`. `GUIDE` is in every system's
  prompt, and a test keeps it in step with the map and sizes.
- **Difficulty profiles** (`truth.PROFILES`, `batch --profile`):

  | Profile | Case mix | Placement | Budget share |
  |---|---|---|---|
  | `base` | today's | role-blind | 0.25 |
  | `r1` | clean 0.15, flip 0.10, interaction 0.25, none 0.50 | role-blind | 0.25 |
  | `r2` | as r1 | more buried, including `board_minutes` | 0.25 |
  | `r3` | as r2 | as r2 | 0.20 |

  `board_minutes` is now a core document (domain governance), with a neutral line per topic.
- **Batch checks:** word leaks count as batch problems, and every batch writes `problems.json`.
- **Pilot:**
  - **S0** gets the whole room plus `MAX_CALLS` as budget, so searches can't crowd out reading. Its prompt says its
    budget covers every document; S1b's prompt is unchanged.
  - Also new: `--reps`, `--flip-only`, and S3 (the majority of S1b runs, with a tie going to no-go; `--report --s3 N`).
- **`acqlab/bench/calibrate.py`:** the round check described above.

**Calibration (Task 6, 2026-09-24 to 25).** Each round ran S1b on 30 dev deals and S0 on their flip deals, all on Opus
5.5 through `CLAUDE_BIN` (CLI 2.1.280). Full numbers are in `docs/results/plan-4b-calibration.md`.

| Round | Profile | S1b wrong on flips | Test deals needed | S0 right on flips | Beats B0 / the margin rule | Margin AUC | Cost |
|---|---|---|---|---|---|---|---|
| 1 | `r1` | 0.214 **miss** | 308 **miss** | 1.000 | −0.019 / −0.006 | 0.595 | $6.14 |
| 2 | `r2` | 0.353 | 160 **miss** | 1.000 | −0.028 / −0.003 | 0.611 | $6.84 |

- **Both audits:** 500 deals, 0 batch problems, 0 word leaks.
- **The ruling.** Round 2's only miss was "test deals needed", which the plan leaves to the user. The user chose to accept
  160 test deals and freeze `r2`, rather than run round 3 (`r3`, budget share 0.20).
- **Caveats:**
  - 160 rests on only 8 of 30 deals with nonzero regret, so it is a rough estimate.
  - S1b beats the margin rule by only 0.003.
- **Per-run cost:** S1b about $0.13, S0 about $0.15–0.17.
- **The pilot's log is buffered.** Its per-deal lines appear only when the pilot exits. To watch progress, count the
  `runs/<system>/*.json` files.

**Review and audits:**
- **Reviews.** Every task passed its per-task review. The Opus final review found 1 Important issue (S0's budget and
  prompt) and minors; all were fixed in `94d8df3` and re-reviewed.
- **Final-review leak audit** (500 deals each):
  - `base` at seed 910000 and `r2` at 920000: 0 batch problems and 0 word leaks.
  - A wider scan of about 4,700 word, page, position and document-count features found a largest |z| of 3.7. Noise alone
    would give about 3.9.
- **Margin shortcut AUC:**
  - `r1`/`r2` measure 0.59–0.67 across seeds.
  - `base` measures 0.70–0.75, right at the limit. The plan's 0.66 for `base` didn't reproduce. `base` isn't a
    calibration profile, so this doesn't block anything, but don't cite 0.66.

**Controller rulings made during execution** (all in the ledger):
- **Final-review scope.** It covered only Plan 4b's commits; Plan 4a had its own Opus review.
- **S0's prompt** swaps one sentence ("You cannot read everything…"). S0 is a ceiling, not a competitor, so §3's parity
  rule is untouched. It's logged in `docs/results/plan-4a-prompt-log.md`.
- **Search** kept its leak-audited top-5-paragraph behaviour; only its description was corrected.
- **S3's `correct`** is derived from the floors rather than from the key's `go`. The two differ only on an exact tie.

**Deferred cosmetic minors:**
- one render sentence says "annual purchases" twice (changing it would change the audited wording)
- the pilot reads each room's `index.json` even without S0
- a redundant NaN guard in `calibrate.check`

## Plan 4a: router checkpoint tooling (2026-09-24)

Spec: `docs/superpowers/specs/2026-09-24-plan-4a-checkpoint-design.md` (its "Revisions from pre-verification" matter). Plan: `docs/superpowers/plans/2026-09-24-plan-4a-checkpoint.md`. Code: `acqlab/generator/padding.py`, `acqlab/agents/` (`server.py`, `prompts.py`, `solver.py`), `acqlab/bench/pilot.py`.

**What it built:**
- **Bigger rooms.** Neutral padding brings every document to a seeded target length, with 3–6 contracts and 6–9 filler documents. Page counts reveal nothing. Generator version 3.0.0.
- **A tighter budget.** `BUDGET_SHARE = 0.25`. Every room also carries `engine.json`, holding the face-value teaser and deal.
- **Two leak checks.** A page-length Welch check that is a batch problem, and a word-level AUC report (`word_leaks.json`) that is only a report.
- **The tool server.** A stdlib MCP stdio server that offers the room, the engine, issue notes and, for the router system, router 6 over the agent's notes. It has a budget, a JSONL trace and an 80-call cap. It never reads an answer key and has **no search tool**.
- **The solver.** A sandboxed `claude -p` adapter. The child process gets only an allowlisted environment: PATH, HOME, USER, LOGNAME, SHELL, TMPDIR, LANG, TERM and `LC_*`. No `CLAUDE*`, `ANTHROPIC*` or `MCP_*` setting from the launching session reaches scored runs. Each run row records `env_keys` and the `models` the CLI reports. The pre-verification sandbox call ran before this scrub existed, so the smoke run's first call is also the check that auth still works without those variables.
- **The pilot runner.** It covers scoring, the no-AI floors, and the pre-registered checkpoint:
  - The checkpoint looks at flip deals only. On those, if the router has lower regret *and* opens decision-relevant documents more often, the verdict is **keep**.
  - If neither holds, it is **reframe**. Otherwise it is **mixed**.

**Numbers on `data/v3` (181 deals):**
- **Room size.** 68–106 pages, 87.7 on average, with an average budget of 22.3 pages.
- **Budget coverage.** The budget covers all evidence in 14% of deals, and the decision-relevant documents in 89% of the 89 deals that have them.
- **Word-level leaks.** `data/v3` has 17.
- **500-deal audit.** 0 batch problems and 48 word-level leaks, the same as pre-verification.

**Search was off for agents in Plan 4a** (one search for "confirmed" identified concentration traps). Plan 4b fixed the wording and brought it back.

**Running it** needs Claude Code CLI 2.1.280 or newer; the `claude` on PATH (2.1.266) can't run Opus 5.5. Every real run needs the user's OK first, and costs their Claude subscription usage.
```bash
export CLAUDE_BIN="$HOME/Library/Application Support/Claude/claude-code/2.1.280/claude.app/Contents/MacOS/claude"
uv run python -m acqlab.bench.pilot --data data/v3 --n 3 --confirm-claude     # smoke: 6 runs
uv run python -m acqlab.bench.pilot --data data/v3 --n 30 --confirm-claude    # pilot: 60 runs
uv run python -m acqlab.bench.pilot --data data/v3 --report
```
- **Exit codes.** 0 means done. 2 means Claude stopped, for example at a usage limit; rerun later and finished runs are skipped. 3 means the run was refused without `--confirm-claude`.
- **After the smoke run,** report tokens per run before asking about the pilot.
- **Log any prompt edit** made after the smoke run in `docs/results/plan-4a-prompt-log.md`.

### Plan 4a pilot results (2026-09-24, 30 dev deals × 2 systems, $6.61, about 26 s and $0.11 per run)

Raw: `data/v3/runs/` (git-ignored); summary with `uv run python -m acqlab.bench.pilot --data data/v3 --report`.

| | regret ÷ ask | on flip deals | correct | opened a relevant doc (flip deals) | pages |
|---|---|---|---|---|---|
| S1b | 0.0090 | 0.0169 | 25/30 | 10/14 | 20.3 |
| S1b + router | 0.0112 | 0.0169 | 24/30 | 11/14 | 19.2 |
| B0 (face value) | 0.0490 | | | | |
| margin rule (best hindsight threshold, 13.5%) | 0.0148 | | | | |

**Pre-registered verdict: mixed.** The two systems had identical regret on all 14 flip deals, and the router opened a relevant doc on one more deal. No `b0_warning`, and S1b beats the margin shortcut.

**What the verdict means:**
- **The router was barely tested.** The router system called `rank_issues` in only 2 of 30 runs; Opus treats an optional adviser as ignorable. Its one extra error, dev-007 (a decoy deal, wrong no-go), came from a run that never called the router.
- **S1b is not at ceiling.** It got 5 of 30 wrong, and both systems made the same 5 mistakes:
  - **dev-020 and dev-025 are routing failures, exactly the case the router targets.** In each, a debt-like flipper sat in the 14-page audited financials. S1b even noted debt-like items at 40%, but opened the 10–11-page QoE first and could no longer afford the audited financials.
  - **dev-019 and dev-026:** interaction deals.
  - **dev-021:** an unresolvable, non-flip deal where the model was too cautious.

**Router v2** (done 2026-09-24): reading is gated on an open note, and the ranking is shown with every note and document. The router arm was rerun ($4.07).
- **Verdict: mixed again.** Flip-deal regret is identical, the router system opens more relevant documents (12 vs 10 of 14), and it reads 12% fewer pages.
- **The same hard deals are missed.** The router faithfully prices the agent's beliefs, and the misses come from wrong beliefs: which document holds the evidence, and how big an item could be.

**Router v3** (done 2026-09-24, $4.09): page costs come from a fixed diligence map, and the ranking names `next_doc`.
- **Verdict: mixed again.** The decisions are identical to v2's.
- **The map sent the agent to the right document** (the audited financials).
- **The router still ranked that check last, correctly given the agent's belief.** The agent believed the debt was at most $8–10M, too small to flip the deal. It was really $16–22M.
- **The bottleneck is now the agent's size beliefs.** Three router versions tried on the same 30 deals leave flip-deal decisions unchanged.

**Router v4 on 30 fresh deals** (`data/v3-fresh`, `--seed 500000`, pre-registered, $7.83): open notes are priced over at least the usual size range.
- **Pre-registered verdict: reframe.** On flip deals the router's regret is higher by +0.014 (CI [0, 0.043]).
- **All of the difference is one deal (dev-001).** Both systems read the same documents and missed the flipper; S1b said no-go on a thin margin and was right, the router system said go.
- **The router's consistent effect is on reading, not decisions.** It reads 8–12% fewer pages, and on fresh deals 68% fewer decoy pages.

**Checkpoint outcome: reframe.** Decided with the user on 2026-09-24; see `docs/superpowers/specs/2026-09-24-reframe-design.md`.
- **The headline still has to beat Opus**, but on a hard benchmark calibrated on S1b alone.
- **The contribution becomes engine-grounded challenge of beliefs.**
- **Next is Plan 4b:** the hard benchmark, the wording fix, S0 and S3, S1b's fairness prompt, and calibration.

The full results and diagnosis are in `docs/results/plan-4a-prompt-log.md`. Earlier router runs are archived in `data/v3/runs-router-v1/`, `data/v3/runs-router-v2/` and `data/v3/runs-router-v3/`.

## Codex status (Plan 2 proof of concept)

- **Smoke call (2026-09-23):** returned `('ok', 19648)`. Token parsing works, but nearly all of those tokens are the Codex CLI's own built-in instructions: every call carries about 20k tokens of overhead. Plan 4 needs this number (spec §4: token overhead must be comparable across systems, or scored runs use the API).
- **Prose run (2026-09-23):** 4 deals, 0 batch problems, 0 prose fallbacks, 31 calls, about 200k tokens per deal (184k–225k). Codex mostly splits the template sentences, so it adds little realism; loosening the prose prompt is a cheap later improvement.
- **Recoverability (`--recover 3`), half done:** Codex hit the usage limit after 21 of 40 calls; 20 of the 21 passed. The one failure was a question problem (it asked about "the largest customer", which the contract never says) and is fixed. Finish it with step 2 above.

## Plan 3 results: Track A (2026-09-24)

Spec: `docs/superpowers/specs/2026-09-23-plan-3-track-a-design.md` (§7 has the pre-verification revisions). Plan: `docs/superpowers/plans/2026-09-23-plan-3-track-a.md`. Code: `acqlab/routers/` (`beliefs.py`, `routers.py`, `track_a.py`).

**What was run:** 2,000 separate Track A deals (`--seed 200000`, never the benchmark splits), 189,000 runs, no skipped deals, 2 h 23 min on this laptop:
- **headline:** 7 routers × perfect investigator × medium priors × budgets 25/50/100% of default × truth {generator, self}, on 2,000 deals.
- **full:** × investigators {perfect, failure, noisy} × prior levels {low, medium, high}, on the first 500 answer keys sorted by filename (dev-000 … dev-1362). Its perfect/medium cells reuse the headline rows for those 500 deals.
- **hints:** clue 0.7 and 0.9 (a "what if" study that uses the answer key), on the same 500.

**Every cell, with CIs: `docs/results/2026-09-24-track-a.md`** (all four slices; means for routers 3, 5, 6, checklist, random and oracle; 6−3, 6−5, 6−random and 6−checklist with 95% CIs and win/loss flags; generated from the summaries by `uv run python docs/results/track_a_table.py`). Raw data (git-ignored): `data/track_a/{headline,full,hints}.txt`, `summary_<grid>.json`, `read_rates.txt`, `results.jsonl`. Rerun a grid with `uv run python -m acqlab.routers.track_a --deals data/track_a --grid <grid> --workers 8`; it resumes, so on the existing rows it only re-summarises (a few seconds).

**Headline, mean regret ÷ asking price (lower is better), generator truth, 2,000 deals:**

| Budget | random | checklist | 5 flip | 3 sensitivity | 6 regret/page | 6 + veto | oracle |
|---|---|---|---|---|---|---|---|
| 25% | 0.0234 | 0.0224 | 0.0224 | 0.0222 | 0.0223 | 0.0221 | 0.0137 |
| 50% | 0.0179 | 0.0147 | 0.0147 | 0.0141 | 0.0136 | 0.0144 | 0.0026 |
| 100% | 0.0064 | 0.0038 | 0.0042 | 0.0033 | 0.0034 | 0.0048 | 0.0001 |

**Fair game (true values drawn from the routers' own priors), 2,000 deals:** at 50%: random 0.0115, checklist 0.0090, 5 0.0083, 3 0.0067, 6 0.0068, oracle 0.0013. Router 6 beats random and checklist at every budget (at 50%: −0.0047 [−0.0065, −0.0032] and −0.0022 [−0.0034, −0.0012]). **The router math is confirmed: when beliefs are right, computed routing beats random and checklist reading.**

**H2 verdict (pre-registered rule: lower mean and paired bootstrap 95% CI excluding zero, per cell). Counts are over all four slices:**
- **Router 6 vs router 3: not supported.** Headline: no win in any cell on either truth (generator 50%: −0.0005 [−0.0013, +0.0003]; decoy −0.0003 [−0.0019, +0.0010]; interaction −0.0005 [−0.0023, +0.0011]). One cell goes the other way: in the fair game at 25%, router 3 is significantly better, +0.00014 [+0.00001, +0.00029], but only 11 of 2,000 deals differ, so it is fragile. Full grid: 13 wins of 108 cells (4 of 27 on the all slice), 12 of them at the 50% budget, and 3 losses: failure investigator, medium priors, 100% budget, on all (+0.0020 [+0.0007, +0.0036]), flip and decoy. Hints: no wins, no losses. **The full-grid wins do not replicate** because they come from one 500-deal subset: on those 500 deals, the headline 50% cell gives 6 − 3 = −0.0022 [−0.0041, −0.0006]; on the other 1,500 it gives +0.00006 [−0.0008, +0.0009]. The full grid reuses those same deals and priors in every cell, so one fluctuation repeats across correlated cells.
- **Router 6 vs router 5: partly supported.** Headline generator truth: wins at 100% on all, flip and decoy (all: −0.0008 [−0.0015, −0.0002]); not at 25% or 50%, not on interaction deals. Fair game: wins at 50% and 100% (all and flip), not at 25%. Full grid: 17 wins of 108 (6 of 27 on the all slice). Hints: 1 win of 24. No losses anywhere.
- **Router 6 vs checklist:** no win on generator truth at any budget (25%: −0.00003 [−0.0007, +0.0006]; 50%: −0.0011 [−0.0023, +0.00003]; 100%: −0.0004 [−0.0011, +0.0002]). Fair game: wins at every budget on the all slice (5 of 6 cells). Full grid: 6 wins and 3 losses of 108. Hints: at clue 0.9 and 50%, a win (−0.0016 [−0.0029, −0.0003]); losses on flip deals at 25% for both clues.
- **Router 6 vs random:** wins at every budget on generator truth (all slice; at 25% only just: −0.0010 [−0.0021, −0.00003]), 8 of 12 headline cells; all 6 fair-game cells. Full grid: 31 wins and 2 losses of 108; the losses are interaction deals at 50% (perfect and noisy investigators, medium priors: for perfect, +0.0067 [+0.0008, +0.0136]). Hints: 3 wins and 1 loss (interaction deals, clue 0.9, 50%: +0.0067 [+0.0013, +0.0139]). The matching 2,000-deal headline interaction cell is −0.0004 [−0.0060, +0.0051], so these losses sit on the same 500 deals.
- **Why 6 ties 3 (measured, not the flat costs):** at step 0 (50% budget, medium priors, first 300 deals), the two routers' first picks agree in only 62% of deals, and scoring router 6 with flat costs changes its pick in only 9%, so dividing by page cost is not what makes them alike. A fresh set of 400 worlds changes router 6's first pick in 15% of deals (13–18% over five fresh sets) and router 3's in 12% (10–13%): both scores are noisy at N_WORLDS = 400. In the headline results at 50%, the two read in a different order in 44.5% of deals but end with a different regret in only 4.8%: most differing reads don't change the final decision.
- **Why every router is close to random on generator truth at 25%:** that budget buys about one fact (router 6 reads 1.14 facts, 1.24 pages), and the priors carry no deal-specific clue about which issue is real; the clue lives in the documents (Track B).

**Other results:**
- **Hints study ("what if"):** with strong hints (0.9) at 50%, routers 3/5/6 reach 0.0061/0.0064/0.0066 against checklist 0.0082 and random 0.0117, so routing pays once the reader supplies clues. Router 6 still ties 3 and 5. At clue 0.7 router 6's only all-slice win is against random at 50%. The hint update overstates hints (see limitations).
- **"6 + veto"** (stop routing below 0.25% of asking price per page) is worse than router 6 at 50% and 100% (0.0144 vs 0.0136; 0.0048 vs 0.0034). It does not stop spending: after routing stops, the sweep spends the rest of the budget cheapest-first (spec §4, "the sweep still runs"). At 50% the veto row spends 3.01 pages against 3.21 for router 6 and reads more facts (2.21 vs 2.16). So the row measures "router 6, then cheapest-first", not budget stewardship. For the later veto work, turn the sweep off for vetoed budget, or report pages saved.
- **Prior calibration** (share of real problems inside the prior range, full grid): low 0.88, medium 0.83, high 0.74. **Sweep:** finds a forgotten problem in 4.4% (headline) to 4.5% (full, hints) of non-oracle runs.
- **Read rates** (generator truth, medium priors, 50% budget; 984 decision-flip deals): router 6 reads a decision-relevant fact in 595, router 3 in 618, checklist 581, random 494. The oracle reads one in only 283, because the prior decision is often already right and it prefers the cheapest set of reads on ties.

**Implication for the checkpoint:** on generator truth (headline), router 6 beats random reading, but not checklist and not router 3; it beats router 5 only at the 100% budget. It beats checklist consistently only in the fair game, where beliefs are right (and with strong hints at 50%). It does not beat router 3 robustly anywhere. So Track A supports "an engine-computed router beats random reading, and beats a checklist when beliefs are right", not "router 6 beats valuation sensitivity". If H2 matters to the pitch, the levers are more worlds per score (raise N_WORLDS, or average scores over seeds) alongside more varied costs (bigger data rooms). The cheapest test, not yet run: the fair-game 50% cell on 500 deals with N_WORLDS = 2000. Otherwise reframe around routers 3/6 jointly versus LLM judgement (router 2) and S1b.

**Known limitations of Track A:**
- **Retrieval cost reveals the role:** for addback, debt_like, nwc and capex, a cost of 3 pages or more always means a non-clean fact (219 of 2,000 deals), because only non-clean facts get the "contradicted" placement. No Track A router exploits it (router 6 divides by cost, so it leans away). Fix or control for it before giving any other router costs (for example router 2 in Plan 4).
- **Seed-stream collision (parked):** numpy seeds `[s, lvl]` and `[s, lvl, 0]` give the same stream, so the priors and the step-0 worlds share a stream; at "low" they also equal the generator's `default_rng(seed)`, at "medium" the renderer's `[seed, 1]`. Measured no leak. Fix with distinct nonzero seed tags before any re-run (it changes every result).
- **The hint update is not Bayes:** it multiplies p by the likelihood ratio instead of the odds, so a "real" hint at clue 0.9 on p = 0.30 gives 0.95 (the clip) instead of 0.79. This affects only how the hints study reads (spec §7).
- **"First 500 deals"** means the first 500 answer keys sorted by filename (dev-000 … dev-1362), not dev-000 to dev-499. Harmless.

**Deviations recorded in the spec:** router 2 moved to Plan 4; the veto is a single "6 + veto" row; budgets are 25/50/100% of default; a fair-game truth mode and a hints study were added (user decisions, spec §7).

## Findings from the handoff review still relevant (2026-09-23, 800-deal batch)

- **The default budget barely binds, and costs are flat.** The non-filler room is about 11 pages; the default budget (about 7) covers every evidence document in 86% of deals. The pilot must re-check room size for Track B.
- **Decision-flip cases are `go != face_go`, not `case_type == "flip"`.** 51% of deals flip versus face value, and 30% of those have `case_type == "unresolvable"`. Use `go != face_go` for every "decision-flip cases" metric; use per-fact roles for decoy and interaction metrics.
- **Regret normaliser:** "EV" in spec §4 means **asking price**, everywhere.
- **Leak audit: clean.** Neither the teaser, `list_documents` (titles, domains, page counts), nor any non-evidence text predicts a fact's role; the only cues are the realistic ones (the add-back gap, and a thin face-value margin predicting flips).
- **Answer keys and units:** load with `AnswerKey.model_validate_json(path.read_text())` (`acqlab/generator/batch.py`). Facts are in $M; always convert with `acqlab.generator.traps.params_for(amounts, truth.base)` (it takes the generator's `BaseDeal`, not the engine `Deal`).
- **Decision-value noise:** a fact's stored `decision_value` (at `--mc 400`) is noisy; raise `--mc` or average over seeds before comparing against it.

## The project in one paragraph

This is a solo competition entry, due about mid/late November 2026. The deliverable is a live demo plus a 5–10 minute pitch to finance-oriented judges.

A fictional PE sponsor considers buying a company. The seller's asking price is set from a teaser alone. Hidden facts buried in a synthetic data room decide whether the deal is actually good: fake EBITDA add-backs, debt-like items, customer concentration, a working-capital shortfall, deferred capex, litigation.

A multi-agent framework, with Opus in every role, investigates under a diligence budget:
- a Deal Lead
- an Investigator with intent briefs
- a Modeler
- a Challenger using Analysis of Competing Hypotheses
- a code Committer
- a code **Router** that prices every open question by its expected reduction in decision regret per unit cost

A deterministic LBO engine is the only source of financial numbers. The claim to prove is lower decision regret than a single Opus agent at equal cost; since the Plan 4a checkpoint it is sharpened to "engine-grounded challenge of beliefs" on a hard, calibrated benchmark (see "The claim and the hypotheses" above). The demo shows a "fork chart" of possible walk-away prices narrowing as evidence arrives.

## Decisions already made (don't re-litigate; the spec has the rationale)

| Topic | Decision |
|---|---|
| Deal type | **Pure LBO**: one target, one sponsor, one term loan, annual periods. The PE add-on variant is a later addition. |
| Output | Walk-away price (the max price with base-case IRR ≥ 20%, debt sized by sponsor rules) **and** go/no-go against the asking price |
| Primary metric | **Decision regret** in $, normalised by EV. Also reported on decision-flip cases separately. |
| Models | **Solver = Claude Opus 5.5** (`claude-opus-5-5`) in every agent and baseline. **Document renderer = Codex/GPT.** Dev runs on the user's subscriptions (`claude -p` / `codex exec`) behind one adapter. The 30-deal pilot's token use decides subscription vs API for scored runs. |
| Baselines | S1a (single Opus, tools + budget), **S1b (single Opus + engine as a tool: the fair fight)**, S0 (reads every document; the ceiling), S3 (best-of-N at equal tokens), trivial baselines, B0 (engine on the teaser only) |
| "Noticeable difference" | S4 regret ≥ 25% lower than S1b **and** a paired bootstrap 95% CI excluding zero, on ~100 test deals |
| Benchmark | Procedural generator (181 deals: dev 50 / test 120 / hand-reviewed 10 / showcase 1). Track B (real LLMs) is the headline; Track A (routers with a simulated investigator, **noisy priors**) is an internal diagnostic. |
| Scope tiers | Core vs Stretch tables in spec §3–4 |
| Checkpoint | Done 2026-09-24: verdict **reframe** (router changes reading, not decisions). The reframe spec (`2026-09-24-reframe-design.md`) now wins over the main spec where they conflict. |
| Demo | A recorded S4 trace replay is the primary path. Engine interactions are always live. |
| Stack | Python 3.12, uv, pydantic 2, numpy, pytest + hypothesis. JSON files, no database. Demo is FastAPI + Vite/React (Streamlit fallback). |
| Novelty stance | Closest prior art is **MAI-DxO / SDBench** (arXiv:2506.22405); also AUDITFLOW, arXiv:2605.13110 and arXiv:2603.22651. The claimed contribution is the *combination*; never claim "first". **Verify every citation before it goes on a slide.** |

User preferences:
- Ambitious scope is welcome ("don't get timid"), but always keep a guaranteed-to-work demo path.
- Wants a complex architecture diagram for credibility: a simple main slide plus a full backup slide.
- Finance judges, so lead with the financial decision.
- Likes plain explanations ("explain like I'm 12") when asked.
- Wants reviews held to a high standard.

## What's built

### Repo map

```
acquisition-lab/
  docs/
    HANDOFF.md                                             ← this file
    superpowers/specs/2026-09-22-acquisition-lab-design.md  ← THE spec (binding authority)
    superpowers/specs/2026-09-23-plan-2-generator-design.md ← Plan 2 design; read its "Revisions" section
    superpowers/plans/2026-09-23-plan-1-lbo-engine.md       ← Plan 1 (done except the Task 9 spreadsheet check)
    superpowers/plans/2026-09-23-plan-2-generator.md        ← Plan 2 (done)
    superpowers/specs/2026-09-23-plan-3-track-a-design.md   ← Plan 3 design; read §7
    superpowers/plans/2026-09-23-plan-3-track-a.md          ← Plan 3 (done; results above)
    superpowers/specs/2026-09-24-plan-4a-checkpoint-design.md, plans/2026-09-24-plan-4a-checkpoint.md ← Plan 4a (done)
    superpowers/specs/2026-09-24-reframe-design.md          ← the reframe: wins over the main spec where they conflict
    superpowers/plans/2026-09-24-plan-4b-hard-benchmark.md  ← Plan 4b (Tasks 1–5 done; Task 6 = calibration)
    results/plan-4a-prompt-log.md                           ← every prompt/router change and its result
  acqlab/engine/      model.py, lbo.py, walkaway.py, beliefs.py         (Plan 1)
  acqlab/generator/   industries.py, sample.py, traps.py, roles.py, truth.py, documents.py,
                      render.py, validate.py, prose.py, recover.py, batch.py   (Plan 2)
  acqlab/dataroom/tools.py                                              (Plan 2)
  acqlab/llm.py                                                         (Plan 2)
  acqlab/routers/     beliefs.py, routers.py, track_a.py                (Plan 3)
  acqlab/agents/      server.py, prompts.py, solver.py (Plan 4a), knowledge.py (Plan 4b)
  acqlab/bench/       pilot.py (Plan 4a/4b), calibrate.py (Plan 4b)
  tests/engine/, tests/generator/, tests/routers/, tests/test_llm.py, tests/conftest.py
  data/               git-ignored: deals/<id>/room/, truth/<id>.json, splits.json, llm_cache/, poc/, track_a/,
                      v3/ and v3-fresh/ (Plan 4a runs), cal-r1/ (calibration round 1)
```

### The engine (`acqlab.engine`, Plan 1)

All money is in **$M**; rates are decimals. There are no LLM calls, and this is the only code allowed to produce financial numbers.

**Public API:**
- `evaluate(deal, params, price=None)` returns a `Result`: uses, debt, equity, exit equity, IRR, MOIC, base and downside year paths, covenant headroom, `debt_caps`, `debt_limit` (which cap set the debt), and `bridge` (`EquityBridge`).
- `walk_away(deal, params)`: the max price with IRR ≥ hurdle, by bisection. `PRICE_FLOOR = 0.01` if nothing clears.
- `is_go(deal, params)`: exact, meaning IRR at the asking price ≥ hurdle.
- `flip_threshold(deal, params, name, lo, hi)`: the parameter value where go/no-go flips. Bounds may come in either order.
- `evaluate_under(deal, base, beliefs, n=200, seed=0)`: a Monte Carlo of walk-away prices. Keys are sampled in sorted order, so a seed gives the same result every time.

**Parameters** (`Params`, the only knobs):

| Parameter | Bounds |
|---|---|
| `ebitda_adjustment` | any sign |
| `debt_like` | ≥ 0 |
| `revenue_haircut` | [0, 1) |
| `nwc_adjustment` | ≥ 0 |
| `capex_adjustment_pct` | any sign |

Unknown fields, NaN/inf and out-of-range values all raise `ValidationError`.

**Definitions:**
- Debt = min(lender cap, covenant-safe debt in the −10% revenue / −2pt margin downside, (1 − min equity) × uses).
- Uses = price × (1 + fees) + debt-like items + NWC adjustment.
- IRR = MOIC^(1/5) − 1.
- Revolver draws pay interest; surplus cash earns none.

**Verified:**
- A hand-checked simple fixture, and a full fixture matched against independent reference scripts.
- Property tests over random deals, stress-run at 3,000 deals per property.
- **Never edit golden numbers to make a test pass.**
- Known exception: a bigger revenue haircut can raise walk-away in thin, cash-hungry deals. The generator's margin rule keeps deals out of that regime.

**Documented simplifications** (have judge answers ready):
- annual covenant testing
- one term loan
- no loss carryforward
- fees charged on price
- the year-1 working-capital release in the downside
- the exit multiple is fixed by policy and dominates the walk-away (prepare an exit-multiple sensitivity backup slide)

### The generator and data room (Plan 2)

**Sampling:**
- `industries.py`: 9 industries from Damodaran's January 2026 tables.
- `sample.py`: the teaser, financing and 3 years of history from cited ranges: GF Data (7.2x, 3.6x leverage), Lincoln (SOFR + 4.75–5.50%), Sidley (25–35% covenant cushion).
- Asking prices sit about 15% below the market average, because a 20% hurdle with no multiple expansion rarely clears at market prices.

**Traps and roles:**
- `traps.py`: 5 traps, one per engine parameter. Litigation is a debt-like variant. Some story variants are held out of dev and appear only in test.
- `roles.py`: flipper, decoy, interaction pair, unresolvable and clean, constructed with the engine.

**Answer keys** (`truth.py`):
- Every deal records all five traps as facts.
- Case mix: clean 15%, flip 25%, interaction 10%, other 50%. About 47% of deals are a true go.
- Unresolvable facts are scored at the midpoint of their documented range.
- Decision values are cross-fitted, with zero-severity draws in their own bin.

**Documents** (`documents.py`, `render.py`):
- Code writes every number.
- **Presence rule:** every trap topic appears in every deal.
- Trust ranking: contracts and audited accounts > QoE > CIM.
- The CIM always makes the seller's claims, and default sentences are neutral, so neither reveals a fact's role.

**Checks** (`validate.py`):
- engine roles, leaks, consistency
- batch go rate
- topic presence
- the add-back line-item distribution, clean vs trap

**Codex layer:**
- `prose.py`: Codex writes prose one call per document. It may write no digits or number words, and a broken paragraph is retried on its own.
- `recover.py`: a positive and a negative probe per fact. Each question says "answer 0 only if the documents show…", so an unrelated document gets null, not 0. The handoff review fixed this: "answer 0 if none" contradicted the "null if not found" rule.

**The command** (`batch.py`):
```bash
uv run python -m acqlab.generator.batch [--out data] [--dev 50] [--test 120] [--hand 10] [--showcase 1] [--seed 0] [--mc 400] [--llm] [--recover N]
```
Exit codes: 0 clean, 1 batch problems, 2 Codex stopped (rerun to resume), 3 generation failed.

**Data room** (`dataroom/tools.py`): `DataRoom(room, budget)`.
- `teaser()` and `list_documents()` are free.
- `search(query)` costs 1 unit and returns the top 5 paragraph hits (letters-only tokens). The agents' tool server exposes only the hits' document ids (Plan 4b), never text.
- `open_document(id)` costs 1 unit per 120-word page.
- The default budget is `BUDGET_SHARE` = 25% of the room (profile `r3`: 20%).
- Every call is logged, over-budget calls are refused, and only indexed ids can be opened.

**Codex adapter** (`llm.py`): `complete(prompt, *, schema=None, run=..., cache_dir=...)`.
- Codex is the CLI bundled with the ChatGPT app, at `/Applications/ChatGPT.app/Contents/Resources/codex`. It is not on PATH; set `CODEX_BIN` to override.
- Each call runs with `--ephemeral` (so calls stay out of the user's Codex history), a read-only sandbox, and an empty temp working directory.
- A failed call raises `LLMUnavailable` and is never cached. Cache writes are atomic.
- Plan 4 adds `claude -p`, the solver sandbox and an API backend behind the same signature.

**Known limitations (parked, with reasons):**
- **Codex can read files.** Its `--sandbox read-only` blocks writes, not reads, so the recoverability extractor could in principle read other files. That's acceptable for the proof of concept, but it must be closed (Plan 4 sandbox) before recoverability gates scored test deals.
- **Decision values are noisy at `--mc 400`** (see the findings list above).
- **Weak, realistic cues remain:**
  - Flippers' add-back line items run larger than clean ones when compared by role (the overall distributions match).
  - Placement weights make "the QoE defers to the notes" mildly predictive.
  - `search()` snippets can surface a fact's amount cheaply; watch this in the pilot.
- **Wording nits:**
  - The CIM's "renewed on a long-term basis" reads against every contract's "renews annually".
  - The number-word guard rejects "third-party"; drop "third" if Codex fallbacks pile up.
  - One capex claim is ungrammatical for plural labels.
  - Company-name suffixes ignore the industry (the showcase deal is "Marlow Mill Manufacturing", an information services business). Fix this before polishing the showcase deal. Note that it changes every prose prompt, so the cached prose would be paid for again.
- **Recoverability failures are reported, not regenerated.** A seeded sample of 20 test deals must pass recoverability before the main benchmark (the user changed "every test deal" to a sample on 2026-09-26).
- **Plan 1's Task 9 spreadsheet check is still deferred by the user.** The spec lists it as required.
- **Negative `debt_like` / `nwc_adjustment` values are rejected, not modelled.** A favourable surprise can only enter through `ebitda_adjustment`.

## Later plans

The reframe spec's §5–6 replace the old Plan 4–7 outline. In short:
- **Plan 4b (done, 2026-09-25):** calibration passed on round 2; `r2` frozen, H1–H6 pre-registered with 160 test deals.
- **Plan 5 (planned, 2026-09-25):** `docs/superpowers/plans/2026-09-25-plan-5-s4-panel.md`.
- **Plan 5:** S4 in the build order above (Deal Record + Committer + engine decides → Investigator with intent briefs → Challenger with the pairwise screen → router + residual sweep); each step checked on dev/calibration deals against S1b; prompt tuning logged equally for S1b. Measure S4 tokens per deal early (sets S3's N and the main-run budget).
- **Plan 6:** generate the test set once; S1b, S3, S4, S0 and ablations (−Challenger, −engine, −residual sweep, LLM decides); paired bootstrap for H1–H6.
- **Plan 7:** demo UI (FastAPI + React: fork chart, pairwise "these two together flip it", evidence viewer, agent timeline), recorded-trace replay as the primary path, slides and judge answers.
- **Parked:** Track A's seed-stream fix (only if Track A is rerun); router 2 is now Stretch.
- **Anytime before slides:** read arXiv:2605.13110 and arXiv:2603.22651 in full and verify every citation.

**Later additions** (from the Plan 2 design):
- a dice-rolled realism batch
- favorable surprises
- sourced trap size ranges
- aggressive-seller archetypes
- messy documents (mixed units, fiscal year ends)
- pinning the Damodaran values against his .xls files

## How this project is worked (conventions and lessons)

**Workflow:**
1. superpowers:brainstorming for anything new.
2. superpowers:writing-plans: one plan per subsystem, in `docs/superpowers/plans/`.
3. superpowers:subagent-driven-development, with a ledger in the git-ignored `.superpowers/sdd/<plan>/`. The workspace is deleted when the plan finishes; git history is the record.
4. superpowers:finishing-a-development-branch. So far: squash-merge to `main` with the Opus trailer, keeping the feature branch for its full history.

**Plan style:** complete code in every step, TDD, and exact expected test counts. **Pre-verify every plan by running its code in a scratch copy, then rebuild the plan from its own text on a fresh `main` and run the suite.** For Plan 2, that caught:
- an engine bug (`flip_threshold` with reversed bounds)
- a biased case mix
- an all-zero decision-value prior
- digits in prose templates

**Lessons from Plan 2:**
- **Per-task reviews can't see cross-document leaks.** The Opus final review found two answer leaks that pre-verification and nine task reviews missed:
  - a clean add-back's CIM line item was always 40% of the total
  - the seller's claim appeared mostly for clean facts

  It found them by **measuring role-dependence statistically** over a generated batch. For any plan that generates or scores data, include that measurement as a step, and run the final review on Opus.
- **Controller fidelity check:** after each transcription task, diff the committed files against the verified scratch copy. It's cheap, and it confirms the implementer copied exactly.
- **Plan-mandated review findings were worth fixing.** Reviewers flagged duplicated evidence code, missing negative tests for validators, a Codex timeout that escaped as a crash, and a non-numeric JSON crash. All four were real.

**Commits and subagents:**
- **Commits** end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Tell subagents this explicitly, because Haiku subagents default to their own name.
- **Model choice:** Haiku for transcription tasks when the plan has complete code; Sonnet for task reviews; Opus for final reviews and judgment-heavy fix waves. Always set the model explicitly.
- **Tell every subagent:**
  - never modify settings or permissions files
  - if a git operation is blocked, stop and report
  - never make a real LLM/Codex call unless the user approved it

**Other rules:**
- **Ponytail mode** is active: minimal code, stdlib first, no speculative abstractions.
- **Never put ground-truth files anywhere a solver sandbox could read them.**
- **Real Codex calls use the user's ChatGPT subscription quota.** Ask before running any, and size runs to fit a usage window. Batches are resumable (exit code 2, then rerun).

## Git state

```
main               4a113ba spec → 6b34612 Plan 1 (squash) → eb6a3ee Plan 2 (squash) → handoff review, Codex PoC, Plan 3 spec and plan (7e965f0); 130 tests
                   → a796026 Plan 3 (squash); 159 tests
                   → 382bf35 Plan 4 (squash: 4a checkpoint + 4b hard benchmark, r2 frozen, pre-registration); 223 tests
plan-5             main + the Plan 5 plan, Tasks 1–5 (S4), review fixes, smoke fixes, dev-check results; 277 tests;
                   worktree .claude/worktrees/plan-4b-calibration-round-1-5f0549
plan-4             full Plan 4 history (0d5db70)
claude/plan-4b-calibration-round-1-5f0549  Plan 4b calibration commits, contained in plan-4 (kept)
plan-3-track-a     full Plan 3 history
plan-1-lbo-engine  full Plan 1 history
plan-2-generator   full Plan 2 history
claude/plan-1-implementation-review-727227  finished review branch (kept)
```

The Plan 2 worktree (`.claude/worktrees/plan-1-implementation-review-727227`) is managed by the Claude app and can be removed from there. No git remote is configured.
