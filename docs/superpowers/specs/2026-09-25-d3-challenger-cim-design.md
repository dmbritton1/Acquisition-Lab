# Acquisition Lab: The Challenger at the Midpoint, and CIM Claims (Plan 5, change D3)

Status: approved in brainstorming on 2026-09-25.
Parent specs: `2026-09-24-reframe-design.md` (§3 fairness, §5 S4) and `2026-09-25-doc-router-design.md` (D2). The
reframe spec stays the binding authority on design; this spec changes when S4's Challenger speaks and what the Committer
accepts from the seller's CIM.
Inputs: S4 as built at `6c2e000` (D2: the document router). All money is in $M.

## Goal

The D2 re-run on all 30 `cal-r2` dev deals (`docs/results/plan-5-dev-checks.md`): S4 26/30 correct against S1b's
22/30, mean regret 45% lower, but the paired CI includes zero. Two of S4's four wrong calls come from failure modes this
change fixes:

- **The Challenger is starved.** Directed reading spends nearly the whole budget before the Challenger speaks: when it
  first objected, 0–1 pages were left on 25 of the 30 deals. On 12 of the 30 it pointed at an unread document that held
  a real fact. On **dev-022** (flip, regret 0.118) it named the QoE, which holds the $45.8M debt-like flipper, in both
  rounds, and nothing was left to read it. H3 (removing the Challenger increases regret) is pre-registered and cannot
  show an effect while the Challenger can't act.
- **The seller's CIM claims are committed as fact.** On **dev-003** (interaction, both systems miss) an Investigator
  read the CIM and committed $0 for all five issues from the seller's claims, including concentration, whose $24.5M loss
  sits in contract_1. Under D2 the CIM ranks high (second or third on the map for most issues). 5 commits across the 30
  runs quote the CIM.

**Success:** objection documents get read when the engine rates them worth their pages; CIM-only commits stop; a
re-run on the 30 deals keeps or improves on 26/30 and regret 0.0107.

## Constraints

- **No answer-key information in S4 code.** **Parity:** no diligence knowledge S1b lacks; S1b's prompt is unchanged.
- **The engine makes the go/no-go call,** unchanged.
- **No prompt change.** Both changes are code: when a role runs, and what the Committer accepts.
- **Build steps and ablations keep their meaning.** The non-router steps (`s4_2`, `s4_3`) are unchanged. With the
  Challenger off (the −Challenger ablation), directed reading runs to the end as under D2, so H3 compares exactly "with
  vs without the Challenger".

## 1. The Challenger at the midpoint

**The rule (router mode, Challenger on).** The first directed pass keeps picking documents while less than half the
budget is spent (`MID_SHARE = 0.5`). The document that crosses the midpoint is allowed, so a big document (the audited
notes, 10–14 pages) can still be read early, as under D2. Then the existing `challenge()` loop runs unchanged:
- round 1 objects at the midpoint; its objections raise how their issue is priced and add weight to the documents they
  name (`Record.challenge`, D2 §1), and directed reading continues with the full remaining budget, so the router weighs
  objection documents against its own picks by the same engine score;
- round 2 objects at the end, followed by directed reading (whatever is left, and the free re-checks) and the sweep.

**Code.** `Panel.directed(until: float | None = None)`: with the router, `route()` keeps picking only while
`spent() < until` (when given). `Panel.run()` calls `self.directed(MID_SHARE * self.budget if self.cfg.challenger else
None)` for the first pass. `route()`'s candidates are unchanged (documents that fit `budget − spent`).

**Why no separate budget for objections.** A fixed reserve is an arbitrary size (40% of a 22-page budget buys the QoE
but not the audited notes) and takes reading away from the router's first pass. At the midpoint the engine decides
whether an objection is worth its pages, which is the project's claim ("code prices every objection").

**Trade-off.** The Challenger's first round sees only about half the evidence, and when a big document crosses the
midpoint it may have 6–9 pages to work with. The offline check (§4) measures the budget it gets.

## 2. CIM claims never settle an issue alone

**Why.** the CIM only ever carries the seller's
claims ("There is no …", "at normal levels", "cash-free and debt-free"). This is also ordinary diligence practice: a
seller's marketing document is a claim to verify, never evidence on its own. The project's trust ranking already puts
it last (contracts and audited accounts > QoE > CIM).

In `committer.check`, a value, range or computed finding whose quotes all come from the seller's documents
(`SELLER_DOCS = ("cim",)`) becomes a `not_found` commit with `docs: ["cim"]`: no error, no retry. The record then shows
the CIM as read without settling the issue (`Entry.searched`), and the issue's weight moves to other documents (D2 §1).
A finding that quotes the CIM alongside any other document is accepted as today: the "calculation" placements need it
(a customer's share of revenue from the CIM, the amount from a contract).

**Parity.** A trust rule in the Committer's code is S4's architecture, like the engine. S1b reads the same CIM and
weighs it however it likes.

## 3. Unit tests (TDD, no Claude calls)

- **Committer:** a CIM-only quoted value becomes `not_found` with `docs == ["cim"]`; a CIM-only range becomes
  `not_found`; a value quoting the CIM and a contract is accepted.
- **Panel:**
  - with the Challenger on (router), the first Challenger turn comes once at least half the budget is spent, and a
    document its objection names is read afterwards when it fits;
  - a document may cross the midpoint;
  - with the Challenger off, directed reading runs to the end with no pause.

## 4. Offline checks before the paid run (no Claude calls)

- **The Challenger's budget.** Replay the first directed pass of the 30 D2 runs under the midpoint rule (the path is
  exact until the first commit, D2 §5), and report the pages left when the Challenger first speaks. Under D2: 0–1 pages
  on 25 of 30.
- **CIM conversions.** Count the D2 commits the new rule would convert (those quoting only the CIM; 5 quote it at
  all) and list their deals.

These are diagnostics, not gates.

## 5. The paid re-run (needs the user's OK)

Archive `data/cal-r2/runs/s4` to `data/cal-r2/s4-d2-059a3b4`; run `s4` on all 30 `cal-r2` dev deals (about $15, 70
minutes). Report against S1b and against the D2 run: correct calls, the paired regret difference with its 95% CI, by
case type, how often an objection's document was read, the budget left at each Challenger round, and cost per deal.

## 6. Records

- The Plan 5 plan's "Post-review changes" gets **D3**.
- `docs/results/plan-5-dev-checks.md` gets the offline checks and the re-run.
- `docs/HANDOFF.md` next steps.

## Risks

- **The Challenger may still get little budget** on deals where a big document crosses the midpoint (§1, trade-off).
- **Reading may get worse.** Half the first pass's budget goes to the router's picks before the Challenger speaks; the
  objection documents it then asks for may displace documents the router would have read. The re-run compares with D2.
- **A CIM-only commit sometimes helped.** Where the seller's claim happens to be true (a clean fact), the issue now
  stays open, so the Lead's starting chance stands, which can push the call toward NO-GO on good deals (the caution seen
  on dev-006 and dev-017). The re-run shows the net effect.
- **The rule is tied to one document id** (`cim`). Generated rooms have exactly one CIM; real data rooms may label the
  seller's material differently.
