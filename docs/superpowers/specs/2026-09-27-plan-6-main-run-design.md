# Acquisition Lab: The Main Run (Plan 6)

Status: approved in brainstorming on 2026-09-27.
Parent documents: the reframe design (`2026-09-24-reframe-design.md`, §3 hypotheses, §5 ablations, §6 schedule), the
pre-registration (`docs/results/plan-4b-preregistration.md`), and the Plan 5 results (`docs/results/plan-5-dev-checks.md`).
The pre-registration stays binding; this spec adds only what it leaves open, and every addition is committed before the
test set exists (§1).

## Goal

Run the pre-registered experiment once: 160 fresh `r2` test deals, S1b, S3 (N = 2), S4 (frozen) and S0, and the four
ablations; then compute H1–H6 exactly as locked. The result must survive a sceptical judge: rules fixed before the data,
a provably fixed test set, a provably frozen S4, no early stopping and no peeking.

## Decisions (user, 2026-09-27)

- **Where runs happen:** the user's Claude subscription, over several usage windows, restarted automatically (§4).
- **Scope:** the pre-registration's needs only. Dropped from the main spec's older list: the budget sweep, 3 seeds on a
  subset, and the 10 hand-reviewed deals. The showcase deal moves to Plan 7 (the demo).
- **H2's "belief-error deals" are the `flip` case type** (one fact large enough, or placed unexpectedly enough, to flip
  the call alone: the design doc's "wrong beliefs about where evidence lives or how big it is").
- **The engine ablations change only the final step** and are replayed from S4's runs, on all 160 deals (§3).
- **Recoverability on a seeded sample of 20 test deals, with Codex** (decided 2026-09-26; `docs/HANDOFF.md`).

## Constraints

- **S4 is frozen.** `acqlab/agents` and `acqlab/routers` stay byte-identical to tag `s4-frozen-plan5`. New code lives
  outside them (`acqlab/bench`). The runner checks this before every phase and refuses to run otherwise.
- **Parity:** S1b's prompt is unchanged. The valuer's prompt (§3) is new S4-ablation text and is logged in the prompt
  log.
- **No answer-key information** in any system or ablation code; answer keys are read only for scoring and analysis.
- **No early stopping, no peeking:** the run completes whatever interim numbers show; the analysis runs once, after
  every phase. The runner logs progress counts, not regret.
- **Never a real Claude or Codex call without the user's OK.** The valuer's real rehearsal step (§6), the
  recoverability check and the campaign each start only on the user's explicit go; once started, the campaign's OK
  covers all its phases and restarts.

## 1. The pre-registration addendum (before any test deal)

`docs/results/plan-6-preregistration-addendum.md`, committed before the test set is generated. It records:
- the scope decisions and the H2 definition above;
- the ablation definitions (§3) and which deals each runs on;
- the pass/fail rules (§5);
- the pessimism control (`pilot.s1b_matched`) reported beside H1, not part of its rule;
- the test-set seed and the recoverability sample rule (§2);
- no early stopping.

## 2. The test set and the recoverability gate

**Generation, once:**

```bash
uv run python -m acqlab.generator.batch --out data/test-r2 --dev 0 --test 160 --hand 0 --showcase 0 \
  --seed 3500000 --profile r2
```

Test deal `test-NNN` gets seed 3,510,000 + NNN (`SEED_OFFSET["test"]`), and retries add multiples of 1,000,000. A
seed checker scans every answer key on disk (all worktrees and scratch batches: 2,257 distinct seeds on 2026-09-27) and
the seeds the docs record, and fails if any test seed or retry seed matches one, modulo 1,000,000. It passed for
3,500,000 on 2026-09-27; it runs again, as a gate, immediately before generation. The batch must report 0 problems
(the word-leak check runs, since 160 ≥ 100).

**The fingerprint:** the SHA-256 of every answer file, and one hash over them in order, go into
`docs/results/plan-6-test-set.md` and are committed at once. The analysis recomputes them and refuses to run on a
changed test set.

**Recoverability (the gate):** a seeded random sample of 20 of the 160 (numpy seed 0, fixed in the addendum), with
Codex as the extractor (main spec §2: a non-solver family), about 200 calls. **New guard:** Codex's `--json` event
stream is checked for any event reporting a command, file read or tool call; any such event fails that call (the
extractor must use only the text in its prompt). This closes the "Codex can read files" gap in `docs/HANDOFF.md`.
The main run starts only after the check passes. A failure stops everything until it is understood (reported, not
regenerated). If Codex is out of usage when everything else is ready, ask the user.

## 3. The ablations

| Ablation | What changes | How it runs | Deals |
|---|---|---|---|
| −Challenger | `Config(challenger=False)`; the two-pass reading order is kept (D3 §8) | a full panel run | `test-000`–`test-039` |
| −residual sweep | `Config(sweep=False)` | a full panel run | `test-000`–`test-039` |
| −engine | the final walk-away and go/no-go come from an LLM "valuer" that sees no engine output | a replay of S4's final record + one valuer turn | all 160 |
| LLM decides | the engine's walk-away is shown to the valuer, which makes only the go/no-go | a replay + one valuer turn | all 160 |

The first 40 test deals are a random subset (deals are independent draws), fixed now.

**The replay:** S4's final Deal Record is rebuilt from its trace exactly as in Plan 5's diagnostic
(`docs/results/scripts/plan-5-caution-replay.py`: `plan`, `apply`, `challenge` in trace order, objections cleared). A
replay that does not reproduce S4's recorded call stops the phase (it reproduced all 59 dev runs).

**The valuer:** one sandboxed `claude -p` session (the solver sandbox: no built-in tools, our tool server only) whose
only tool is the submit call. Its prompt holds the teaser, the deal terms and the Deal Record's committed values and
open beliefs; for −engine nothing the engine computed (no walk-away, flip amounts or evaluations), for LLM decides also
the engine's median walk-away and its 10–90% range. −engine submits a walk-away and a go/no-go; LLM decides submits a
go/no-go and keeps the engine's walk-away. The ablation configs, replay and valuer live in `acqlab/bench`.

## 4. The campaign runner

`acqlab/bench/campaign.py`, started once as its own process:

```bash
nohup caffeinate -i uv run python -m acqlab.bench.campaign --data data/test-r2 --confirm-claude \
  > data/test-r2/campaign.out 2>&1 &
```

**Phases, in order** (finished runs are skipped, so a restart resumes):
1. **H1 core:** S1b, S4 and S3's second S1b run (`rep` 1), deal by deal over the 160 so results stay paired.
2. **Ablations:** −Challenger and −sweep on the first 40; −engine and LLM decides on the 160.
3. **S0** on the 160.

**Before each phase:** the freeze check (`git diff --quiet s4-frozen-plan5 -- acqlab/agents acqlab/routers`) and the
fingerprint check. Either failing stops the runner with the reason.

**At a usage limit** (`LLMUnavailable` whose message says "resets <time> (<zone>)"): wait until 5 minutes after the
reset, then continue. Times such as "9:20pm", "4am" or "12:05am", later today or tomorrow, are read in the named time
zone; a message with no readable time waits 30 minutes and tries again. A long wait (a weekly limit) is logged, not
treated as an error.

**Any other error:** one retry after 10 minutes, then stop with the error in the log.

**Visibility:** `data/test-r2/campaign.log` gets one line per phase change, wait and finished run, with counts only
("s4 83/160"), never regret. `--status` prints the counts per phase and system and, when waiting, the resume time.
`--stop` ends the process (its pid is in `data/test-r2/campaign.pid`); starting it again resumes.

## 5. The analysis and the pass/fail rules

`acqlab/bench/analysis.py`, run once after every phase is complete (it refuses otherwise and checks the fingerprint),
writes `docs/results/plan-6-main-run.md`'s numbers and a JSON summary. Every comparison is a paired per-deal difference
with a paired bootstrap 95% CI (`bootstrap_ci`, fixed seed), also reported by case type.

| | Deals | Holds if |
|---|---|---|
| **H1** | 160 | S4's mean regret is at least 25% below S1b's, the CI on S4 − S1b excludes zero (below it), and S4's mean regret is below S3's. |
| **H2** | 160 | The gain (S1b − S4) on `interaction` and `flip` deals exceeds the gain on the other case types, with a bootstrap CI on that gap (resampling within each group) excluding zero. |
| **H3** | 40 | −Challenger's regret exceeds S4's, CI on the difference excluding zero. |
| **H4** | 160 | S4's decoy pages are below S1b's, CI on the difference excluding zero. |
| **H5** | 160 | −engine's mean walk-away error is at least twice S4's, and the CI on the difference excludes zero. |
| **H6** | the 40 | On deals where a real trap (a fact with a nonzero amount) is not in S4's first Deal Lead plan: −sweep's regret exceeds S4's, CI excluding zero. Fewer than 5 such deals: "too few to test". |

**Also reported, no pass/fail:** the pessimism control beside H1 (S4 − `s1b_matched`, CI); LLM decides against S4;
for every system, correct calls, walk-away error, pages, decoy pages, sessions and cost; S0 and the no-AI floors
(always GO, always NO, B0, the margin rule). H3 and H6 have 40 deals and little power; a CI that includes zero is
reported as "not shown", not as evidence against.

## 6. Testing and the rehearsal

**Unit tests (no Claude or Codex calls):**
- runner: reset-time parsing (evening, early morning, after midnight, unreadable), waiting with a fake clock, phase
  order and resume, one retry then stop, the freeze and fingerprint checks refusing to run;
- replay and valuer: the replay reproduces a fake S4 run's call; the −engine prompt holds no engine numbers and no
  answer-key words; the LLM-decides prompt holds the engine's walk-away;
- the Codex guard: a fake event stream with a command event fails the call;
- the seed checker catches a planted collision; the fingerprint changes when an answer file changes;
- the analysis: each rule on synthetic rows with a known answer, including H6's "too few to test".

**Rehearsal before the real campaign:**
1. The whole campaign on 3 dev deals with a fake Claude (free), every phase.
2. The valuer for real on 2 `cal-r2` deals from their S4 runs (a few cents; needs the user's OK).

The plan is pre-verified in a scratch copy, as in Plan 5.

## 7. Cost and time

| Phase | Runs | Notional cost | Run time |
|---|---|---|---|
| 1 | 160 × (S1b + S4 + S1b rep 1) | about $123 | about 9.6 h |
| 2 | 40 × 2 panel ablations + 160 × 2 valuer turns | about $56 | about 5 h |
| 3 | 160 × S0 | about $27 | about 1.3 h |
| **Total** | | **about $210** | **about 16 h** |

At about $17 of runs per usage window (2026-09-26), about 12–13 windows: roughly 4–5 days if each resumes promptly.
Build 1–2 days first; Plan 6's slot runs to about 2026-11-06.

## 8. Records

- The addendum (§1), then the test-set fingerprint (§2), each committed before the next step.
- `docs/results/plan-6-main-run.md`: every number in §5, written from the analysis output.
- `docs/results/plan-6-prompt-log.md`: the valuer's prompt, with why and the parity note.
- `docs/HANDOFF.md`: progress and next steps (Plan 7).

## Risks

- **A weekly usage limit** stretches the run; the runner waits and logs it.
- **The Mac sleeping or shutting down pauses the run** (`caffeinate -i` stops idle sleep only; closing the lid on
  battery can still sleep it). Keep it plugged in; nothing is lost.
- **Codex usage delays the recoverability gate,** and with it the main run.
- **H1 may fail.** The pre-registered result is reported as it is (reframe §7); H2–H6 and the pessimism control still
  tell an honest story.
- **The valuer may answer badly** (malformed submits). The rehearsal's real step checks the format; an unanswered
  valuer turn is scored like any unanswered run (B0's call), and the count is reported.
