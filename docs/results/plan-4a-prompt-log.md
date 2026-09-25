# Plan 4a prompt and tool log

Every change to the solver prompts or tools after the smoke run, per the Plan 4a spec. The S1b prompt is unchanged
throughout. Only the router system's paragraph and tools change, so S1b runs are reused.

## 2026-09-24: router v2, a gated and pushed router (after the 30-deal pilot)

**Why.** In the pilot, the router system called the optional `rank_issues` in only 2 of 30 runs. That checkpoint
therefore measured "offering a tool Opus ignores", not the router. Pilot verdict: **mixed**. The two systems had
identical regret on all 14 flip deals.

In two of S1b's five mistakes (dev-020 and dev-025), a debt-like flipper sat in the 14-page audited financials. The
model noted debt-like items at 40%, then spent its budget on the QoE first and could no longer afford the audited
financials. This is the case the router is meant to catch.

**Change (router system only; user decision "Gate reading"):**
- `open_document` is refused until the agent has at least one open note (chance below 1). The refusal is free.
- Every `note_issue` result carries the router's current ranking under `"router"`. Every opened document's text is
  followed by `Router ranking now: {...}`.
- The router is still router 6 over the agent's own notes. `rank_issues` stays available.
- The prompt's router paragraph now says to note a suspicion before reading, and that the ranking arrives with every
  note and document.

**Runs.**
- The v1 router runs are archived in `data/v3/runs-router-v1/`.
- The router arm is rerun on the same 30 dev deals.
- The S1b runs are unchanged.

### Router v2 result (30 dev deals, $4.07)

| | regret ÷ ask | on flip deals | correct | opened a relevant doc (flip deals) | pages | $/run |
|---|---|---|---|---|---|---|
| S1b | 0.0090 | 0.0169 | 25/30 | 10/14 | 20.3 | 0.114 |
| router v1 (optional) | 0.0112 | 0.0169 | 24/30 | 11/14 | 19.2 | 0.106 |
| router v2 (gated, pushed) | 0.0099 | 0.0169 | 24/30 | 12/14 | 17.8 | 0.136 |

**Verdict under the pre-registered rule: mixed again.** Regret on the 14 flip deals is identical to S1b's, and the
router opens a relevant document on 2 more flip deals.

**Where each system went wrong:**
- **All three systems miss the same four flip deals** (dev-019, 020, 025, 026). All three also miss dev-021.
- **Router v2 adds one miss:** dev-014, an unresolvable non-flip deal.
- **Router v2 fixes v1's one extra miss:** dev-007.

**Why the router doesn't help on dev-020 and dev-025:**
- **The router followed the agent's own map, and the map was wrong.** The agent pointed its debt-like note at the
  2-page legal document. The router ranked that note first, and the agent read it. The flipper was in the 14-page
  audited financials.
- **The agent pointed at the less likely document.** On data/v3, debt-like evidence is in the audited financials in
  about 66% of trap deals, in legal in about 22%, and in the QoE in about 11%.
- **The budget then ran out.** By the time the agent redirected the note to the audited financials, it could no longer
  afford them.
- **The agent also sized the debt at $3–15M.** The true amount was $22.4M.

**What this means:** the router prices the agent's beliefs faithfully, and the misses come from those beliefs (where
the evidence is, how big an item could be), not from the order of reading. This matches Track A: routing pays only
once the reader supplies good clues.

## 2026-09-24: router v3, the router prices reading from a fixed diligence map (after router v2)

**Why.** Router v2 faithfully priced the agent's own guesses about where evidence lives, and those guesses caused the
misses. For example, the agent looked for debt-like items in the legal letter. This change tests whether code-side
diligence knowledge, combined with the router, fixes them. User decision: "Test the belief fix cheaply."

**Change (router system only; S1b is unchanged and its runs are reused):**
- Each open note's page cost is the next unread document on a fixed `DILIGENCE_MAP` in `acqlab/agents/server.py`,
  the same for every deal. The map lists where an analyst looks first:

  | Issue | Documents, in order |
  |---|---|
  | add-backs | QoE, audited, CIM |
  | debt-like items | audited, legal, QoE |
  | concentration | contracts in id order, CIM, audited |
  | NWC | QoE, audited |
  | capex | assets, CIM, audited |

  It used to be the pages of the documents listed in the agent's note.
- The ranking names that document as `next_doc`.
- The prompt's router paragraph mentions `next_doc`. The v2 gate and the pushed ranking are unchanged.

**Caveats:**
- **The map is general practice, written without looking at any deal.** It agrees with where the generator usually
  places evidence. On data/v3 trap deals, the first document on the map holds the evidence for:
  - debt-like items in about 66% of deals
  - add-backs in about 60%
  - capex in about 90%
- **A fair control would give S1b the same map in its prompt.** Run that control only if v3 shows an effect, so any
  gain can be credited to the router rather than just the map.

**Runs.** The v2 router runs are archived in `data/v3/runs-router-v2/`.

### Router v3 result (30 dev deals, $4.09)

| | regret ÷ ask | on flip deals | correct | opened a relevant doc (flip deals) | pages | $/run |
|---|---|---|---|---|---|---|
| S1b | 0.0090 | 0.0169 | 25/30 | 10/14 | 20.3 | 0.114 |
| router v3 (diligence map) | 0.0099 | 0.0169 | 24/30 | 12/14 | 18.1 | 0.136 |

**Verdict: mixed, a third time.** The decisions are the same as router v2's on every deal.

**Why dev-020 and dev-025 are still missed:**
- **The map worked.** The router now names the audited financials as the next document for the debt-like note.
- **The router ranked that note last, and correctly so given the agent's belief.** The agent sized the debt at $2–10M
  (dev-020) and $1–8M (dev-025). Items that small can't flip deals whose face-value headroom is $14.8M and $11.4M, so
  14 pages to check them is poor value. The true amounts were $22.4M and $16.6M.
- **The bottleneck is now the agent's size belief, not where it looks.**

**Caution:**
- **Three router versions have now been tried on the same 30 dev deals,** and the last two were each designed after
  looking at dev-020 and dev-025.
- **Any further change aimed at those deals must be confirmed on fresh deals** before it counts as evidence.

## 2026-09-24: router v4, typical size ranges, tested on fresh deals (after router v3)

**Why.** In router v3 the diligence map found the right document, but the agent's size guesses were too small ($2–10M
against a true $22.4M). The router therefore correctly judged the check not worth its pages. User decision: "option 1
on fresh deals."

**Change (router system only; the S1b prompt and tools are unchanged):**
- Each open note is priced at the agent's chance, but over at least the usual size range for its issue type. The top of
  that range is `typical_high` in `acqlab/agents/server.py`, computed from teaser numbers only:

  | Issue | Top of the usual range |
  |---|---|
  | add-backs | min(claimed add-backs, 25% of adjusted EBITDA) |
  | debt-like items | 20% of asking price |
  | concentration | 25% of revenue |
  | NWC | 20% × NWC% × revenue |
  | capex | 3% of revenue |

- The ranking shows `size_high_used`, and the router paragraph says the router widens ranges.
- The v3 diligence map, the gate and the pushed ranking all stay.

**Caveat.** These ranges are the generator's own worst-case ranges, re-expressed in visible numbers. They are not
sourced industry ranges. A win therefore shows that correct size priors plus the router help. The real-world version
needs sourced ranges, which were already on the handoff's "later additions" list.

**Pre-registered before any run:**
- **Data.** 30 fresh dev deals in `data/v3-fresh` (`--seed 500000`, no overlap with data/v3; 14 flip deals).
- **Systems.** S1b and router v4, both run fresh on those deals.
- **Verdict.** The same checkpoint rule as the pilot.
- **Frozen.** No change to the prompts or the router after seeing these results. Any further idea is tested on another
  fresh batch.

### Router v4 result on fresh deals (data/v3-fresh, 30 deals, 60 runs, $7.83)

| | regret ÷ ask | on flip deals | correct | opened a relevant doc (flip deals) | pages | decoy pages | $/run |
|---|---|---|---|---|---|---|---|
| S1b | 0.0056 | 0.0069 | 24/30 | 10/14 | 18.4 | 2.2 | 0.124 |
| router v4 | 0.0123 | 0.0212 | 23/30 | 10/14 | 16.8 | 0.7 | 0.137 |

B0 scores 0.0500 and the margin rule 0.0114. There are no `b0_warning` or `margin_warning` flags.

**Pre-registered verdict: reframe.**
- **Regret:** the router is worse on flip deals by +0.0143, with 95% CI [0.000, 0.043].
- **Evidence:** it opens a relevant document no more often than S1b does.

**All of the regret difference comes from one deal, dev-001:**
- **Both systems read the same documents** (the QoE, then the audited financials), and both missed the debt-like
  flipper in the 2-page legal letter. The v4 map sends debt-like checks to the audited financials first.
- **S1b said no-go and was right.** With face-value headroom of only $1.8M, it declined out of caution.
- **The router system said go and was wrong.**
- **So the gap isn't caused by the router's advice.** Every other deal ended with the same decision.

**The router's consistent effect is on reading, not decisions.** Across v2–v4 it reads 8–12% fewer pages. On fresh deals
it reads 68% fewer decoy pages (0.7 vs 2.2).

**Conclusion after four router versions:**
- **The router changes what gets read, not what gets decided.** The flip-deal misses come from the agent's beliefs and
  judgement, not from the order it reads in.
- **Per spec §4, the claim should be reframed before S4 is built in full.** The spec says: "if the router doesn't help,
  reframe the claim".

## 2026-09-24: S0 (Plan 4b) gets a one-sentence prompt change and search-slack budget

**Why.** S0 is the reading ceiling, not a competitor, so the parity rule that keeps S1b and S1b + router's prompts
frozen doesn't apply to it (main spec §4). Two things were wrong for a system meant to read everything:
- Its system prompt was the shared `_BASE`, which says "You cannot read everything, so choose what to read." — false
  for S0, whose budget is the whole room.
- Its budget was exactly the room's page total, but `search` also costs 1 unit each. An S0 that searches even once
  could no longer afford to open every document, so it wasn't actually unbudgeted.

**Fix.** `system_prompt` takes a keyword-only `unbudgeted` flag (default `False`, so S1b and S1b + router are
byte-for-byte unchanged); for S0 it swaps that one sentence for "Your budget covers every document, so you can read
them all." S0's budget is now the whole room's pages plus `acqlab.agents.server.MAX_CALLS`, so a run that spends its
full call budget on `search` still has every page available to it.
