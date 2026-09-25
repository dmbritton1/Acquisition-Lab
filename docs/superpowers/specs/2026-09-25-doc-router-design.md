# Acquisition Lab: Document Router Design (Plan 5, change D2)

Status: approved in brainstorming on 2026-09-25; §2 revised after pre-verification the same day (§8).
Parent specs: `2026-09-24-reframe-design.md` (§3 fairness, §5 S4) and the Plan 5 plan
(`docs/superpowers/plans/2026-09-25-plan-5-s4-panel.md`, Decision 4 and change D1). The reframe spec stays the binding
authority on design; this spec changes only how S4's router chooses what to read.
Inputs: S4 as built at `d7bbc00` (Plan 5 Tasks 1–5, fixes S1–S2 and D1). All money is in $M.

## Goal

S4 must beat S1b by at least 25% on regret (H1). On the first 10 `cal-r2` dev deals it only tied. A page-spend audit of
those traces found why S4 misses the deals that matter: it reads the wrong documents.

**The audit (offline replay of the 10 S4 traces at `c989fb1`, no Claude calls):**
- **S4 never opened the audited notes: 0 of 10 runs. S1b opened them in 18 of 30.** The audited notes (11–14 pages, on
  budgets of 20–27) are on the diligence map for all five issue types. They held the hidden fact in 5 of the 10 deals
  (dev-002, 003, 005, 007, 008).
- **dev-003 (interaction, 28% of S1b's total regret on the 30 deals).** The answer needed contract_1 (3 pages, a $24.5M
  customer loss) and the audited notes (13 pages, a $2.8M add-back): 16 of 25 pages. S4 read contract_1 but not the
  audited notes, and said GO. S1b read the audited notes but not contract_1, and said GO. The Challenger's objection
  named the audited notes correctly, but 4.5 pages were left.
- **Why:** router 6 scores one issue at a time, divided by the pages of that issue's first document. A 2–3 page
  contract always beats a 13-page document that could settle every issue at once. The map sends add-backs and NWC to
  the QoE first (8–12 pages), after which the audited notes no longer fit. The sweep reads untouched domains first,
  then the shortest documents.
- **The same short-sightedness caused dev-006** (fixed as D1): no single issue could flip the call, so every issue
  scored 0 and S4 did no directed reading.

**The fix:** the router prices **documents**, not issues. A document's value is how far what it may reveal is
expected to move the engine's walk-away, across every open issue it could settle, per page (router 3's sensitivity,
per document; §2, and §8 for why not regret).

**Success:**
- Offline, on the recorded Lead plans: the audited notes get credit for every issue they may settle, the first pick is
  stable over seeds, and the reading path reaches the evidence (§5).
- Then a paid re-run on 15 dev deals (§6) shows whether S4's calls improve against S1b.

## Constraints

- **No answer-key information in S4.** The router uses the diligence map's order, the Lead's and Challenger's named
  documents, page counts and the engine.
- **Parity (reframe spec §3).** S4 gets no diligence knowledge S1b lacks. S1b's prompt is unchanged, so the calibrated
  baseline (`r2`, 160 test deals) does not move.
- **The engine makes the go/no-go call,** unchanged.
- **Build steps and ablations keep working.** `s4_2` and `s4_3` (no router) keep issue briefs in the Lead's order, so
  the build order still isolates the router. −Challenger and −sweep are unaffected.

## Findings behind the design (from the 30 `cal-r2` answer keys; read-only, not used by S4)

1. **"Not found" says nothing about whether an issue is real.** A clean fact is still written into its documents,
   stating `$0.0M`. An Investigator who finds the topic settles it, at 0 if clean; one who doesn't has read the wrong
   document. So a read that misses moves *where* the evidence is likely to be, not *whether* the issue is real. The
   Lead holding its chance after "not found" was correct, and the Lead prompt fix deferred on 2026-09-25 is
   withdrawn.
2. **The map's order is off for `r2`.** Add-back evidence is in the audited notes in 43% of deals and in the QoE in
   30%, yet the map sends add-backs to the QoE first.
3. **The board minutes are not on the map,** but hold evidence for 13–30% of each issue type. S4's sweep reads only
   map documents (fix S2), while S1b can read them.

Findings 2 and 3 concern the shared guide, so they affect S1b too. They are a later fairness question and are **out of
scope** here: the map and `knowledge.GUIDE` are unchanged.

## 1. The chance a document settles an issue

For each open issue t and each document d in the room, `settle_weights(t, pages, read, named)` in `record.py` gives a
weight: the chance that d is where t is settled.

- **Map documents.** `DILIGENCE_MAP[t]` lists document kinds in order. They get weights `MAP_WEIGHTS = (0.45, 0.25,
  0.15)` for first, second and third place. A kind with several documents (the contracts) splits its weight evenly
  among them.
- **Every other document.** The leftover weight (1 − the map weights used: 0.15, or 0.30 for NWC, which has two map
  kinds) is spread evenly over the documents in `named` that are not on t's map. `named` is the Lead's documents for t
  plus those of any objection on t (the entry's `docs`, which `record.challenge` already extends). If no such document
  is named, the leftover is spread evenly over all other documents in the room.
- **After a read.** Every issue's evidence is somewhere in the room (clean facts included), so read documents get
  weight 0 and the rest are renormalized to sum to 1 over the unread documents.
- **A settled issue** (committed, no pending objection) is not a target and gets no weights.
- `MAP_WEIGHTS` carries a `ponytail:` comment: hand-set from the map's order, not measured; the knob to tune if the
  offline check (§5) shows the order dominating.

**Parity.** The weights use only the map's order, which S1b's guide states in words ("first …, then …, then …"), and
the documents the panel's own roles named.

**Worked example, dev-003 after contract_1 settles concentration, nothing else read.** Add-backs: QoE 0.45, audited
0.25, CIM 0.15. Debt-like: audited 0.45, legal 0.25, QoE 0.15. NWC: QoE 0.45, audited 0.25. Capex: assets 0.45, CIM
0.25, audited 0.15. The audited notes carry weight for four open issues.

## 2. A document's value

`score_docs(values, w, weights, pages, open_, u)` in `acqlab/routers/routers.py`, next to `score_sensitivity`, is a
pure numpy function. `Record.rank_docs(pages, read, docs, seed=0)` wraps it for S4 and replaces router 6's `rank` in
S4's router mode.

1. **Simulated deals.** The record's simulated deals (`worlds()`, the same 400 the engine's call uses): sampled values
   for every issue, and each deal's engine walk-away. Committed issues are fixed; open issues and issues with a pending
   objection vary, as today (`Record.issue`).
2. **What reading d would reveal.** For each simulated deal and each open issue t, d settles t if a uniform draw is
   below d's weight for t. One fixed table of uniform draws (seeded, one column per issue type) is shared by every
   document, so random noise cannot reorder documents.
3. **Group by what the reader would learn.** Each open issue gets a label per simulated deal: settled at 0, settled
   small, settled large (split at the median of its nonzero sampled sizes), or not here. Simulated deals with the
   same labels across all open issues form one group.
4. **Value.** The expected absolute move of the mean walk-away from learning the group: the sum over groups of (share
   of deals in the group) × |group mean walk-away − overall mean walk-away|. **Score = value ÷ d's pages.**

**What it captures:**
- **Everything a document may settle.** A document that may settle four open issues moves the walk-away through all
  of them, so the audited notes get credit for each.
- **No need for the call to flip.** At the Lead's first plan no single read changes the go/no-go call (§8), but reading
  still narrows the walk-away, which is what a sequence of reads needs. Sensitivity sees that; the regret score does
  not.
- **Nothing for noise.** A document with no weight on open issues forms one group and scores exactly 0; filler gets
  only the leftover's small share.

**Candidates.** Unread documents with weight above 0 for at least one open issue, whose pages fit the budget left
(including the sweep reserve; §3).

**Not guaranteed.** Cheap documents win per page: the 2-page legal letter is the first pick on 9 of the 10 recorded
first plans. On dev-003's replayed path (§5) the router reads legal, the QoE and then the audited notes (23 of 25
pages), which leaves too little for contract_1 unless an earlier find changes the plan.

## 3. The reading loop (router on)

`Panel.directed()` in router mode:

1. **Pick.** Score the candidates with `rank_docs`; take the best (ties: fewer pages, then id) if its score is above
   0. Otherwise directed reading ends: no unread document can move the walk-away, and the sweep takes over. This
   replaces D1's fallback, which existed only because the regret score was 0 at the start of most deals.
2. **Brief.** One Investigator, one document: `prompts.doc_brief`. It names the document and its pages, and for each
   open issue with weight above 0 in it, the existing brief lines (current belief or committed value, and the flip
   amount). It ends: "Report every issue type this document settles, including ones not listed."
3. **Budget.** The Investigator's reading budget is exactly the document's pages, so the tool server keeps it to that
   document (re-opening already-read documents stays free). This also ends the audit's "kept reading after finding
   it" waste.
4. **Re-plan only after a commit.** The Lead re-plans when the read committed a value or range for some issue. After a
   read that settles nothing, it does not: per finding 1 there is nothing for it to update, and this saves a session.

**The sweep reserve.** The router may spend into the sweep's reserve (`SWEEP_SHARE` of the budget) when its chosen
document needs it: candidates are documents that fit `budget − spent`, not `avail()`. The sweep then reads with
whatever is left. Rationale: unspent budget earns nothing, a document the engine ranks first is worth more than
coverage, and the audited notes are on the map for every issue, so they double as coverage. Cost: H6 (the sweep helps
when a trap is not on the Lead's list) gets less sweep budget; the −sweep ablation still measures it.

**Challenger objections:**
- An objection raises how its issue is priced and adds its documents to the issue's `named` list (`record.challenge`,
  unchanged). They get weight through §1, and directed reading resumes after each Challenger round.
- An objection **clears when a document it names is read**, or when its issue is settled by a new commit. A pair
  objection (from the pair screen) names no documents; it clears when any document with weight above 0 for its issue
  is read.
- If an objection names documents and all of them were already read (the claim is that the reader missed something),
  it gets **one free re-check**: the existing issue brief (`prompts.brief`) with the Challenger's reason, a reading
  budget of 0, and the named documents free to re-open.
- Objections still pending at the end change nothing (fix S1, unchanged).

**The `route` row.** Each pick appends a trace row `{"tool": "route", "args": {"doc", "issues", "scores" (top 5)},
"cost": 0.0, "refused": false, ...}`, written by the panel like its `submit` row. `spent()` sums it as 0 and `read()`
ignores it. Audits read the router's choices from it instead of replaying runs, and the demo's evidence trail can show
why each document was read.

**Unchanged:** the non-router build steps (`s4_2`, `s4_3`: issue briefs in the Lead's order, `MAX_TRIES`), the
Challenger's rounds and pair screen, the sweep's own rule, the engine's call, and S1b.

## 4. Unit tests (TDD, fake sessions, no Claude calls)

- **`settle_weights`:** map places get 0.45/0.25/0.15; contracts split their share; the leftover goes to named off-map
  documents, or to all other documents when none is named; read documents get 0; the weights sum to 1 over unread
  documents.
- **`score_docs`:**
  - a document with weight 0 for every open issue scores 0;
  - a document that may settle two issues scores the walk-away move of both: more than one that may settle either
    alone, and exactly its hand-computed value on synthetic simulated deals;
  - dividing by pages: the same document at twice the pages scores half;
  - the same inputs give the same scores.
- **Panel:**
  - the router briefs one document, with a reading budget of exactly its pages;
  - the Lead re-plans only after a commit;
  - an objection clears when a document it names is read;
  - the free re-check runs when every named document was already read;
  - the router may pick a document that fits only with the sweep reserve;
  - `route` rows cost 0 and don't count as reads;
  - when no candidate scores above 0, directed reading ends.
- **Unchanged behaviour:** the existing `s4_2`/`s4_3` tests pass untouched. The D1 test (`test_panel.py`) is replaced by
  the router tests above.

## 5. Offline checks before any paid run (no Claude calls)

Run during pre-verification on the scratch build, from each of the 10 deals' recorded first Lead plan (and dev-003's
record after contract_1); the plan repeats them on the real code:
1. **What ranks first, and stability.** Top 3 documents per deal, the audited notes' rank, and the first pick over 5
   seeds. Pre-verification: first pick agrees in 80–100% of seeds on every deal (100% on 10 of 11 states); the audited
   notes rank 2–7 everywhere.
2. **The reading path.** Under the D2 loop the record changes only on a commit, so the path up to the first find can be
   replayed exactly by assuming reads find nothing. Pre-verification: on the 8 deals with real evidence, the path
   reaches it on 6 (dev-000, 003, 004, 007, 008, 009); it misses dev-002 and dev-005, where the audited notes held
   only decoys, which don't change the call.

These are diagnostics, not gates: tuning to answer keys past a diagnostic would fit S4 to the generator.

**The audit becomes a tool:** `acqlab/bench/audit.py`, reading `route` rows. It reports pages by kind (on-map,
off-map, already-settled, evidence hits), the audited-notes read rate, and reads the router wanted but could not
afford.

## 6. The paid re-run (needs the user's OK)

- Archive `data/cal-r2/runs/s4` to `data/cal-r2/s4-c989fb1`, because the pilot skips finished runs.
- Run `s4` on dev-000..009 plus S1b's other misses: dev-012, 013, 016, 025, 029 (15 deals; about $8–10 with more
  sessions, about 35 minutes). S1b is unchanged, so its runs stand. CLI 2.1.280 through `CLAUDE_BIN`, for parity.
- Report: the paired regret difference against S1b with a 95% CI, results by case type, the audited-notes read rate,
  and sessions and cost per deal. S3's N is measured again from these tokens.

## 7. Records

- `docs/results/plan-5-prompt-log.md` (new; format of `plan-4a-prompt-log.md`): the document brief, logged as an S4
  architecture change. Parity note: it adds no knowledge beyond the guide's order.
- The Plan 5 plan's "Post-review changes" gets **D2**, which supersedes Decision 4's issue-by-issue router in S4 and D1's fallback.
- `docs/HANDOFF.md`: the deferred Lead prompt fix is withdrawn (finding 1); findings 2 and 3 are recorded as a later
  fairness question.

## Risks

- **dev-003 may still read the QoE first** (§2, "Not guaranteed").
- **Cost per deal rises:** one document per Investigator session. Skipping the re-plan after an unproductive read
  offsets part of it. S3's N rises with S4's tokens.
- **H6 gets less sweep budget** (§3).
- **Sensitivity is not regret.** The router ranks by walk-away movement, not by decision value, so it may read a
  document that moves the walk-away far from the asking price. Track A found the two tie on regret (router 3 vs 6),
  and the call itself stays with the engine; the Challenger's pair screen keeps the "these two flip it together"
  test.
- **Cheap documents first** (§2, "Not guaranteed").
- **The weights are hand-set.** Findings 2 and 3 say the map's order is imperfect for `r2`; the weights inherit that,
  on purpose, for parity.

## 8. Revision from pre-verification (2026-09-25)

The approved §2 scored a document by the decision regret it would remove (router 6's measure, grouped jointly). Built
and run in a scratch copy on the 10 recorded first Lead plans, it failed the stability check (§5) and picked badly:
- **At the Lead's first plan no single read of any document changes the call.** The Lead starts with 3–5 issues at
  35–50% over wide ranges; ruling out one or two leaves the rest. So the audited notes scored about 0 on most deals
  (rank 15–22), and first-pick agreement over seeds was 20–100%, mostly 40–60%, against the 80% check.
- **Noise won.** On dev-006 the router read the HR policy, insurance, marketing, whistleblowing, environmental and IT
  policy documents before D1's fallback took over.
- **Not a thin-groups problem.** 8,000 simulated deals (instead of 2,000), and grouping on one predicted-walk-away
  number (a least-squares fit), left it as broken. The short-sightedness is across time: reading pays off as a
  sequence, and one-read value of information can't see that.

Sensitivity (router 3's measure, per document) was stable at 400 simulated deals and reached the evidence as often on
the replayed paths, without reading filler. Changes from the approved design:
- §2 scores by sensitivity; `ROUTE_WORLDS` is dropped (the router uses the record's 400 simulated deals).
- §3's D1 fallback is dropped: sensitivity is 0 only when no document can move the walk-away.
- The `route` row loses its `fallback` field.
- Non-myopic planning (scoring whole reading plans) was the alternative; it was not chosen, being riskier and needing
  its own design round.
