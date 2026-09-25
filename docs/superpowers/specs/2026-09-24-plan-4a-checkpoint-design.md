# Acquisition Lab: Router Checkpoint Design (Plan 4a)

Status: approved in brainstorming on 2026-09-24.
Parent spec: `2026-09-22-acquisition-lab-design.md`, §4 (Systems, Checkpoint, Scale). The parent remains the binding authority, and every deviation is listed at the end.
Inputs: the engine (Plan 1), the generator and data room (Plan 2), and the router 6 math (Plan 3). All money is in $M.

## Goal

Run the parent spec's week-4 checkpoint: **S1b vs S1b + router** on real Claude runs. Track A (Plan 3) showed the router math works, but it did not settle whether router 6 beats router 3. That makes this checkpoint the real test of the router idea. It answers one question before S4 is built: when one Opus agent does real diligence, does a dollar-priced router make its decisions better?

## Scope

| In Plan 4a | Not in Plan 4a (Plan 4b or later) |
|---|---|
| Bigger data rooms (about 55–125 pages, typically about 85), generator 3.0.0 | S0 (reading ceiling), S1a (no engine), S3 (best-of-N) |
| An MCP tool server for data-room tools, the engine, issue notes and the router | Router 2 (LLM judgment) |
| A `claude -p` solver adapter on the user's Claude subscription | The API path and a second model family |
| S1b and S1b + router, plus no-AI floors (trivial baselines and B0) | S4, ablations, the budget sweep |
| A staged pilot: 3 deals, then 30 dev deals | The ~100-deal test run |
| A pre-registered two-signal checkpoint rule | |

## 1. Bigger data rooms

Plan 2's rooms are small enough that the budget covers most of the evidence, which leaves nothing to route. Plan 4a makes the rooms bigger without changing what the documents say about any trap.

- **Neutral content, written by code, in every deal.** It is drawn from the deal's seed and sized as follows:

  | Document | Pages |
  |---|---|
  | Audited financials | 10–14 |
  | CIM | 10–15 |
  | QoE | 8–12 |
  | Credit agreement | 4–6 |
  | Contracts | 3–6 contracts × 2–3 pages each |
  | Asset/lease schedule | 3–5 |
  | Legal letter | about 2 |
  | Filler | 6–9 documents × 2–6 pages each |

  This gives rooms of about 55–125 pages, typically about 85 (the sum of the ranges above).

  The content is sections like segment tables, accounting-policy notes, covenant definitions, contract boilerplate, asset lists and minutes. Each is built from the deal's own numbers and the existing `heading`/`table` helpers, so it reads like the rest of the document.
- **Rules for the new content:**
  - Reveal and hint sentences are unchanged.
  - The new content never states or implies a trap quantity, such as an add-back amount, a customer loss, a debt-like amount, an NWC gap or a capex shortfall.
  - The presence rule still holds: the new content mentions trap topics equally often in trap deals and clean deals.
- **The leak audit is re-run statistically** over a generated batch of at least 500 deals, per the standing rule. It covers:
  - the existing `check_batch` presence ratios
  - a new check that no page-count or document-size feature separates trap deals from clean deals by more than the presence tolerance, since bigger rooms must not make a trap's document fatter
- ~~`search(query)` returns documents and hit counts only.~~ **Revised: agents get no search tool in Plan 4a** (see "Revisions from pre-verification", item 1).
- **`BUDGET_SHARE` is re-tuned** so that the default budget covers the pages of all evidence documents in under 30% of deals. The chosen value and the measured share go in the spec revision note after pre-verification.
- **`GENERATOR_VERSION` becomes 3.0.0.** The 181-deal benchmark set and the Track A deals are regenerated into new directories and never overwritten. Track A results stay valid for the rooms they ran on.
- **Pilot rooms use template prose (no Codex).** Both systems see the same rooms, so the paired comparison doesn't need the prose pass. The Codex prose pass stays available.

## 2. Agent harness

### Solver call

Each run is one `claude -p` subprocess, started from an empty temp directory:

```
claude -p --output-format json --model claude-opus-5-5 --tools "" \
  --mcp-config <tmp>/mcp.json --strict-mcp-config --allowedTools <our tools only> \
  --setting-sources "" --system-prompt <ours> --no-session-persistence
```

- It runs on the user's Claude subscription. `--bare` needs an API key, so it isn't used.
- A hard timeout of 20 minutes applies to every run.
- On a non-zero exit, a timeout, or a usage-limit message, the adapter raises `LLMUnavailable`, the same class as the Codex adapter.
- The answer key's path is never inside the temp directory or reachable by any tool.

### Tool server: `acqlab/agents/server.py`

A stdio MCP server, hand-written as JSON-RPC over stdlib (`initialize`, `tools/list`, `tools/call`). If the hand-written version fails against the real CLI, it falls back to the `mcp` package. It is started with a room path, a budget, a trace path and a `--router` flag. It reads only the room directory.

| Tool | Cost | Does |
|---|---|---|
| `list_documents()` | free | Titles, domain tags and page counts |
| `open_document(doc_id)` | pages | Full text |
| `evaluate(adjustments)` | free | Walk-away and go/no-go for `{trap: $M}` adjustments on the face-value deal |
| `note_issue(name, type, chance, low, high, docs)` | free | Records or replaces the agent's belief about one issue. `type` is one of the five trap types, and the range is in $M |
| `rank_issues()` | free | **Router system only.** Router 6 ranks the agent's open notes |
| `submit(go, walk_away, reason)` | free | Ends the run |

- **Budget:** enforced by the existing `DataRoom` class. An over-budget call is refused with the remaining budget stated. After 80 tool calls, every tool except `submit` is refused. If a run never submits, it is scored with B0's decision and counted separately as "no answer".
- **$M conversion:** `write_room` also writes `engine.json`, the face-value `BaseDeal` built from the deal's visible numbers. `evaluate` and `rank_issues` convert $M to engine inputs with `params_for` on that base. It holds no facts, and it reveals nothing that `evaluate({})` doesn't already return.
- **`rank_issues`:**
  - **Mapping notes to beliefs.** A note with chance < 1 becomes an open `Issue(p_real=chance, hi=high)`. A note with chance = 1 becomes a known range (low, high). Trap types with no note are unproposed.
  - **Cost** is the pages of the note's `docs` not yet opened, with a minimum of 1.
  - **Output.** Router 6's `score_regret`, including pair screening, returns each note's regret reduction per page in $M, highest first, plus the current decision.
  - It is advice only: the agent chooses what to open.
- **Trace:** every call is written to the trace file with its tool, arguments, cost, remaining budget and whether it was refused.
- **Isolation:** the server never imports or reads `AnswerKey`, `DealTruth`, `data/truth/` or facts. A test enforces this, as in Plan 3.

### Prompts

- One system prompt, in `acqlab/agents/prompts.py`. The router system's prompt adds one paragraph on `rank_issues` and is otherwise identical, and a test checks this.
- The prompt asks for:
  - notes as issues are found
  - `evaluate` before deciding
  - a `submit` that states go/no-go and a walk-away
- Every prompt edit made after the smoke run is logged to `docs/results/plan-4a-prompt-log.md` with the reason and the runs it followed. The same edit always goes to both systems (tuning parity).

### No-AI floors

These are computed in code for every pilot deal:

- always go
- always no-go
- walk-away = asking price
- **B0:** the engine on the face-value deal with no adjustments, which is the generator's `face_go` and `face_walk_away`

B0 is wrong on every decision-flip deal by construction. That makes it a floor for overall regret, not for regret on flip deals.

### Runner: `acqlab/bench/pilot.py`

- Invoked as `uv run python -m acqlab.bench.pilot --deals <dir> --n <k> --systems s1b,s1b_router --seed <s> --confirm-claude`. It refuses to run without `--confirm-claude`.
- For each (system, deal) it writes `data/runs/<system>/<deal>.json`. Each file holds:
  - the trace
  - the submitted decision
  - regret ÷ asking price
  - walk-away error ÷ asking price
  - tokens (input, output, cache read, cache write, from the CLI's JSON)
  - wall time and exit status
- It is resumable: existing run files are skipped.
- On a usage limit it stops the whole batch, exits 2, and keeps what finished.
- The solver command is injectable, so tests never call Claude.

## 3. Pilot, checkpoint rule, testing

### Staged pilot

I ask the user before each stage, since each one uses the subscription.

1. **Smoke run:** 3 dev deals × 2 systems = 6 runs. It checks the sandbox, the traces, the token counts and the real tokens per run.
2. **Pilot:** the first 30 dev deals × 2 systems × 1 seed = 60 runs.
3. **Optional second seed** on a subset, only if the regret differences between seeds on the same deals look too large to read the checkpoint.

### Recorded per run and reported

- Regret ÷ asking price, go/no-go correct, and walk-away error.
- Pages spent, pages spent on decoy-evidence documents, and whether the agent opened any **decision-relevant document**. That is a document holding a fact that is a flipper, an interaction, or an unresolvable fact that flips the decision alone (the generator's `explained` roles).
- Tokens, tool calls, `rank_issues` calls, and "no answer" runs.
- **Prior calibration:** for each noted issue whose type matches a trap, is the true value inside the agent's noted range?

Everything is reported overall, on decision-flip deals (`go != face_go`) and by case type, next to the no-AI floors.

### Checkpoint rule (fixed before any pilot run)

On decision-flip deals:

1. **Regret:** is the mean regret of S1b + router lower than that of S1b?
2. **Evidence:** does S1b + router open a decision-relevant document on more of those deals?

| Result | Action |
|---|---|
| Both yes | Keep the router-centred claim and go to Plan 4b |
| Both no | Reframe the claim before building S4 |
| Mixed | The user and I decide together |

- The paired bootstrap 95% CI on the regret difference is reported, but it isn't required to exclude zero at n ≈ 30.
- If S1b doesn't beat B0 on overall regret, this is flagged at the top of the results. It means the harness or the prompt is failing, not the router.

### Testing (no Claude calls in tests)

- **Tool server:** tests drive a real server subprocess with scripted JSON-RPC requests. They cover:
  - initialize and list
  - every tool
  - budget refusal and the tool-call cap
  - search not being offered (Revisions, item 1)
  - $M conversion matching `params_for`
  - trace contents
- **`rank_issues`:** matches `score_regret` on the same beliefs, and passes the isolation test.
- **Runner:** tests use a fake `claude` script that emits recorded JSON. They cover:
  - scoring
  - resume
  - the usage-limit stop (exit 2)
  - timeouts
  - "no answer" runs
  - refusal without `--confirm-claude`
- **Generator 3.0.0:**
  - Existing tests pass.
  - Golden numbers change only where the version bump makes that necessary, and the diff is reviewed rather than edited to pass.
  - New tests check page ranges, the no-quantity rule, and the statistical leak audit over at least 500 deals.

### Process

- `writing-plans`, pre-verified in a scratch copy and rebuilt from the plan's own text, as in Plans 1–3.
- **Pre-verification includes one tiny real `claude -p` call,** which needs the user's OK. It confirms that:
  - `--setting-sources ""` loads none of the user's hooks, plugins or CLAUDE.md
  - only our tools are visible
  - the token fields parse
- Subagent-driven execution, with the final whole-branch review on Opus.
- **The subagent rule still holds:** no subagent makes a real Claude or Codex call. Pilot stages are run by me, after the user's OK.

## Deviations from the parent spec

- **Agents have no search tool in Plan 4a.** The word-level audit showed that search gives traps away (Revisions, item 1). It returns in Plan 4b after the reveal wording is fixed.
- **The budget share is re-tuned** from about 30–40% of room cost to "covers all evidence in under 30% of deals". The 30–40% band was set for small rooms.
- **Documents per deal rise** from about 12–20 to about 15–21, with rooms of about 55–125 pages.
- **Regret is normalised by asking price,** not EV, as in Plan 3.
- **The checkpoint runs before S0, S1a and S3 exist.** The parent names only S1b vs S1b + router for the checkpoint, and the others follow in Plan 4b.
- **Generator version 3.0.0.** The benchmark set is regenerated.

## Revisions from pre-verification (2026-09-24)

All of the plan's code was run before the plan was written (197 tests), and one real `claude -p` call was made with the user's OK.

1. **Search is off for agents.** A word-level audit of 500 deals found 48 (trap, document, word) triples whose counts separate trap deals from clean ones. A 1-unit search for "confirmed" identifies concentration traps perfectly.

   The cause is Plan 2's reveal wording: trap and clean sentences use different words, and the range wording appears only for unresolvable facts. The user decided:
   - no search tool in 4a
   - the word-level check ships now as a report (`validate.word_leaks`, written to `word_leaks.json` by the batch)
   - the wording rewrite is Plan 4b's job

   `DataRoom.search` is unchanged and unused.
2. **`BUDGET_SHARE = 0.25`.** On 300 deals, the default budget (about 22 pages) covers every evidence document in 21% of deals, and the decision-relevant documents in 86% of the deals that have them.
3. **Rooms are 67–105 pages, 87 on average.** Every document lands exactly on its drawn target, whatever its reveal says. A new batch check flags any document that is longer on average when a trap is real (Welch gap > 4 standard errors). On 500 deals it found 0 problems.
4. **Solver.** The command adds `--disable-slash-commands` and runs with an empty stdin; the CLI otherwise waits 3 s.

   The `claude` on PATH (2.1.266) cannot run Opus 5.5, so runs set `CLAUDE_BIN` to the app-bundled CLI 2.1.280.

   The real check confirmed four things:
   - only our tools are visible
   - no hooks, skills or CLAUDE.md load; the CLI does add the account email, which is harmless
   - the server connects and logs the call
   - the usage fields parse

   Each run also records `total_cost_usd`.
5. **A timeout doesn't stop the batch.** The adapter raises `RunTimeout`, a subclass of `LLMUnavailable`, and the runner scores that run as "no answer". Any other failure stops the batch with exit 2.
6. **Padded contracts** state the contract term as plain text, since padding runs after the prose pass.
7. **Two Track A tests changed scenario budgets.** The retry test and the veto test assumed small rooms, so each now has the budget its premise needs. No expected number changed.

## Later (Plan 4b)

- S0, S1a and S3; router 2
- the budget sweep; the ~100-deal test run
- the API path, if tokens per run make the subscription impractical
- Codex prose for the benchmark rooms
- the seed-stream collision fix from Plan 3 (fix it before any Track A re-run)
- the reveal-wording rewrite, until `word_leaks` is empty at 500 deals; then search comes back, returning document ids and hit counts
