# Debate pilot: a bull, a bear and a referee on top of single Claude (design)

**Status:** design, approved section by section on 2026-10-09. Exploratory: a pilot, not a confirmatory test.

**Goal:** find out whether a two-sided debate before a referee who did not read makes better buy/pass calls than
single Claude, at the same page budget and with a little extra.

**Why this design:**
- **The research note** (`docs/research/agent-teams-research-2026-10-07.md`, Parts 2 and 4) found that two-sided
  debate, judged by someone with less information than the debaters and backed by checkable quotes, is the
  multi-agent design with the strongest evidence for our kind of problem. A one-sided critic, like the team's
  Challenger, does worse.
- **The hidden-upside pilot** (`docs/results/upside-pilot.md`) found two kinds of miss on deals where a feared problem
  turned out small:
  - **The team mostly never opened the document holding the good news** (9 of its 12 misses). A bull advocate with a
    small reading budget targets this.
  - **Single Claude mostly read the good news and still passed** (5 of its 7 misses). A two-sided argument before a
    referee targets this.

**Scope:** this spec is the debate only. Stage 2 of the hidden-upside track ("genuine extra value", negative amounts)
is a separate spec, decided after this pilot (§6).

## 1. What is compared

- **Deals:** the 40 `r2u` deals in `data/pilot-r2u` (16 relief, 8 confirmed, 16 ordinary; spec
  `2026-10-08-upside-pilot-design.md`).
- **Baselines:** the finished `s1b` (single Claude) and `s4` (the frozen team) runs on those deals. They cost nothing
  more. Every comparison is paired, deal by deal.
- **Two new systems.** `B` is the deal's page budget (`default_budget` in the room's index).

  | System | Reader | Bull's reading budget | Most pages possible |
  |---|---|---|---|
  | `debate_x` ("extra pages") | the deal's existing `s1b` run, reused unchanged | 0.2·B | 1.2·B |
  | `debate_s` ("same budget") | a new single-Claude run at 0.8·B | B minus what the reader spent (at least 0.2·B) | B |

- **Model:** every step uses `claude-opus-5-5`, on Claude Code CLI 2.1.291 or newer.

## 2. The steps

Each step is one sandboxed `claude -p` session on our tool server, which enforces its budget and writes its trace
(`solver.run_session`). No step reads an answer key.

1. **Reader.**
   - Single Claude, unchanged: `solver.solve`, with the same prompt and tools.
   - In `debate_x`, the reader is the deal's `s1b` row and trace in `runs/s1b`. If either is missing, the deal stops
     with an error rather than running a new reader.
2. **Bull.**
   - **It sees:** the teaser; the full text of every document the reader opened, passed as already paid for (the
     server's `--paid` option); and the reader's view (`referee.solo_view`: its last note per issue type, its last
     priced adjustments, and its call and reason).
   - **Its tools:** `list_documents`, `search`, `open_document`, `evaluate`, `note_issue` and `submit`, within its
     reading budget.
   - **Its task:** make the strongest honest case that the sponsor should buy. Look for evidence that feared problems
     are smaller or absent, especially in documents the reader didn't open. Note each issue type at the bull's
     evidence-based view, and price it with `evaluate`. Submit `go`, `walk_away` and a `reason` that states the case
     with verbatim quotes and document ids. Where the evidence is clearly against buying, say so rather than bluff.
3. **Bear.**
   - **It sees:** the teaser; the full text of every document the reader or the bull opened; the reader's view; and
     the bull's case (its last note per issue type plus its submitted reason).
   - **Its tools:** `evaluate`, `note_issue` and `submit`, with budget 0. It reads nothing new.
   - **Its task:** make the strongest honest case that the sponsor should pass, answering the bull point by point,
     with quotes. Same submit format as the bull.
4. **Referee.**
   - **It sees:** the teaser; the full text of every document anyone opened; and three summaries (the reader's view,
     the bull's case and the bear's case). The order of the summaries is set by a seeded shuffle on the deal id, so it
     changes from deal to deal and no side is always first.
   - **Its tools:** `evaluate` and `submit`, with budget 0.
   - **Its task:** find what the disagreement turns on, settle it from the documents, price with `evaluate`, and
     submit the final `go`, `walk_away` and a one-line reason. The referee's call is the system's call.

**Shared rules for all three new prompts:**
- **The seller's memo:** the CIM is the seller's marketing. Its claims are what diligence checks, never evidence on
  their own.
- **Amounts:** in $M, with the same issue definitions and general diligence guide (`GUIDE`) as the existing prompts.
- **Scoring:** buying a deal worth less than its price, or passing on one worth more, costs the difference.

**Unchecked quotes:** the referee has the full text of every cited document and can check quotes itself, as the
kill-test referee did. No code checks the quotes.

**Missing calls:**
- A step that times out or never submits still lets the next steps run.
- The referee's prompt says when an advocate gave no case.
- If the referee gives no call, the deal is unanswered: `pilot.score` scores it at face value (GO on flagged deals),
  and it is reported.

**Pages and cost:**
- Each system's row counts every step: in `debate_x` that includes the reused reader's pages, tokens and cost.
- Its trace is the merged trace of all steps (`recon.combine`). The reader's submit is renamed `step_submit`, and the
  final submit is the referee's.

## 3. Measures (fixed before the pilot runs)

1. **Main measure: mean regret over all 40 deals.** For each debate system, against `s1b` and against `s4`: the
   paired difference with a 95% paired-bootstrap range (`analysis.compare`), and deals won, lost and tied.
2. **Relief deals (16):** false NO-GOs and regret per system.
3. **Confirmed deals (8), the safety check:** false GOs per system.
4. **Overturned calls.** For each debate system, how often the referee's call differs from its reader's. These are
   split four ways: NO-GO→GO right, NO-GO→GO wrong, GO→NO-GO right and GO→NO-GO wrong. Results are also given by deal
   type.
5. **Did the bull find the good news?** On relief deals, count the deals where the bull opened the settling document
   (the last document of the flagged issue's evidence, as in the upside pilot) and the reader had not.
6. **Cost, sessions, pages and decoy pages per deal,** for every system. Each step's share is reported too.
7. **What the extra pages are worth:** `debate_x` against `debate_s`, paired.
8. **Unanswered or timed-out steps and runs,** per system.

**Mechanics check (each debate system):**
- the referee gives a call on at least 38 of 40 deals;
- no deal exceeds its page limit: B for `debate_s`, 1.2·B for `debate_x`.

**How the result is read:**

| Result | Rule |
|---|---|
| **Debate helps at the same budget** | `debate_s` has a lower mean regret than `s1b` over all 40 deals, **and** at most one more false GO than `s1b` on the confirmed deals, **and** it passes the mechanics check. |
| **Debate helps only with extra pages** | `debate_x` meets those three conditions and `debate_s` does not. |
| **Debate doesn't help** | Neither meets them. |

**What the result decides:**
- A "helps" result earns a larger confirmation test on fresh deals, sized from this pilot's per-deal spread. The user
  decides whether to run it.
- "Doesn't help" stops the debate track, as the reconciliation pilot's rule did.
- 40 deals give a direction, not proof.

## 4. Build and tests

**Unchanged:** `acqlab/agents` and `acqlab/routers` stay byte-identical to tag `s4-frozen-plan5`. No tool changes.

| File | Change |
|---|---|
| `acqlab/bench/debate.py` (new) | The three system prompts (`BULL`, `BEAR`, `REFEREE`); the steps `bull`, `bear` and `judge`; `run_x` and `run_s`; `RUN`; `run(data, systems, split="test", deals=None)`, which skips finished deals and raises `LLMUnavailable` to stop; and `main` (`--data`, `--systems`, `--split`, `--deals`, `--confirm-claude`; exit codes 0 done, 1 unknown system, 2 Claude stopped, 3 refused). It reuses `recon.step`, `recon.combine`, `recon.call_of`, `recon.spent`, `referee.opened`, `referee.rows`, `referee.note_lines` and `referee.solo_view`. |
| `acqlab/bench/referee.py` | `documents(room, read) -> str` is extracted: the full text of the documents read, in index order, as `build` writes them today. `build` and `recon.second_prompts` use it. The existing kill-test prompt fingerprint test must still pass unchanged. |
| `acqlab/bench/recon.py` | `second_prompts` uses `referee.documents`; its output is unchanged. |
| `scripts/debate_pilot.py` (new) | The §3 analysis into `--out`. It refuses to overwrite. It refuses if any system's deals differ from the split's, or if any row's models aren't `["claude-opus-5-5"]` (a timed-out row may have none). |
| `docs/results/debate-pilot-prereg.md` (new) | §3 restated, the SHA-256 of each of the three system prompts, and the smoke-test outcome. Committed before any pilot run. |

**Tests** (fake Claude, as `tests/bench/test_recon.py` does):
- `run_x` reuses the `s1b` row and trace: its pages, tokens and cost include the reader's, and a missing `s1b` run
  raises a clear error.
- `run_s` gives the reader 0.8·B and the bull B minus what the reader spent; total pages never exceed B.
- The bull's session gets the reader's documents as paid and has the reading tools; the bear's and referee's sessions
  have budget 0 and no reading tools.
- The referee's prompt holds every opened document's text and the three summaries in a deal-seeded order that varies
  across deals.
- No step reads the answer key.
- A missing bull or bear case is stated to the referee; a referee without a call leaves the deal unanswered.
- The analysis script:
  - each branch of the reading rule and the mechanics check;
  - the overturned-call counts and the "bull found the good news" count;
  - the refusal to overwrite, the deal-set check and the model check.
- The kill-test prompt fingerprint is unchanged.

## 5. Order of work and cost

1. **Build and test** (free).
2. **Smoke test** on `data/cal-r2` deals `dev-000` and `dev-001` (practice deals with existing `s1b` runs). It runs
   both systems and costs about $1–2. It checks that each step answers and budgets hold, and that the referee gets
   every document and summary. The results are not counted. Prompts may be fixed here, and only here.
3. **Freeze:** commit the pre-registration with the prompt fingerprints.
4. **The user's OK, then the pilot:** both systems on the 40 deals. Estimated cost: `debate_x` about $8–12,
   `debate_s` about $12–16. On the Pro plan, expect usage-limit pauses; reruns resume.
5. **Analysis** (run once) **and a plain-language write-up** in `docs/results/debate-pilot.md`, plus a
   `docs/HANDOFF.md` bullet.

## 6. Out of scope

- **Stage 2 of the hidden-upside track:** documents that reveal value the teaser doesn't show, with negative amounts.
  It gets its own spec after this pilot: first if the debate helps (only a system with a bull could act on good news),
  otherwise after Plan 7.
- **Debating with the team as the reader;** several debate rounds; code that checks quotes.
- **Any change to the frozen team, to single Claude's prompt or to the tools.**

## Limits (stated in the write-up)

- **The same 40 deals** that showed the "never looked" finding. The design was shaped by them, so a "helps" result
  needs fresh deals before any claim.
- **Small sample:** 40 deals, one run each. The paired ranges will be wide.
- **Unbalanced reading:** only the bull reads beyond the reader. That is deliberate, since it targets the observed
  miss, and the confirmed-deal safety check watches for the optimism it could cause.
- **The deals:** template prose only, and flagged deals of one kind (a worry that turns out smaller).
