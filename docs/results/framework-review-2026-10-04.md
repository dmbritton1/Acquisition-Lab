# Framework review — 4 October 2026

There are credible, untested ways to improve this team. The highest-priority work is making evidence requests affect the reading schedule, preserving budget for important long documents, and testing independent solutions with a shared verifier. Adding more roles or increasing caution has much weaker support.

The current evidence supports a narrower claim: the team can avoid some costly acquisition mistakes under a restricted reading budget. It does not yet establish a consistent win over Solo, a benefit caused specifically by multiple agents, or an advantage across distinct task domains.

This review inspected the orchestration, prompts, record, committer, engine, routers, generator, simulator, evaluation and tests; reviewed the Track A, router, calibration, development, held-out, main-run and simulation reports; and audited the saved main-run traces and 60 practice deals. Main and the data-bearing worktree were both at `a131f0e`. Historical Track A findings below come from its committed results table, not a fresh replay of that entire campaign. New calculations are **exploratory**. Production code and the frozen results were not changed; no real Claude or Codex evaluation calls were made.

Reproduction: [audit script](../../scripts/framework_review.py), [audit numbers](framework-review-2026-10-04.json). From the repository root:

```sh
.venv/bin/python scripts/framework_review.py .claude/worktrees/plan-4b-freeze-preregistration-0908fa/data
```

**What the experiments actually establish**

| Experiment | Finding | Consequence for the next version |
|---|---|---|
| Track A: simulated investigators, 2,000-deal headline grid | Regret-based routing beat random routing in several settings; it did not consistently beat sensitivity routing. On generator truth at the 25% budget, regret was 223.4 versus 221.5 basis points for sensitivity. | A theoretically attractive router is not enough; observation and belief quality matter. |
| Plan 4a: four router versions | Reading changed without consistent decision improvement. The fresh 30-deal v4 check had regret 0.0123 versus Solo's 0.0056. | Avoid optimizing pages or decoy avoidance as substitutes for decision quality. |
| Plan 4b calibration | Harder evidence placement increased Solo's errors. The 160-deal sizing estimate rested on only eight nonzero-loss practice deals. | Difficulty calibration succeeded, but the power estimate was fragile. |
| Plan 5 development | D2 achieved 45% lower regret than Solo; D3 achieved 61% lower on the same 30 development deals. | Useful development progress, not independent confirmation. |
| Plan 5 held-out check | Team 0.0105 versus Solo 0.0078. All seven team mistakes rejected good deals. | The benefit depends on the task distribution. Keep the failed check visible. |
| Plan 5 build steps, ten deals | Lead plus issue investigations had regret 0.0080; full team 0.0183. | A smaller architecture deserves a proper comparison; ten deals cannot select a winner. |
| Plan 6, 160 fresh deals | Team 0.00878 versus Solo 0.01260; paired difference CI approximately [−0.0100, +0.0016]. Team also below two-Solo voting, but that difference is uncertain. | Promising average loss reduction; H1 did not pass. |
| Plan 6 component tests | Challenger benefit unproven on 40 deals; sweep hypothesis had no eligible deals; engine improved valuation error by 1.54× rather than the required 2×. | Preserve the engine; test whether each additional role earns its cost. |
| Reading simulator, 300 deals | None of seven tested changes beat baseline. Broad absence discounts were particularly harmful. | Do not repeat these changes under new names. The tests do not cover every scheduling or inference design. |

Sources: [Track A](2026-09-24-track-a.md), [router log](plan-4a-prompt-log.md), [calibration](plan-4b-calibration.md), [development checks](plan-5-dev-checks.md), [main run](plan-6-main-run.md), [simulator](reading-simulator.md).

The new audit adds an important definition of “consistently”: S4 beats Solo on **25 deals, loses on 23, and ties on 112**. Its advantage is the size of the losses avoided, not an overwhelming frequency of winning. Accuracy is 78.1% versus 76.9%; two-Solo voting achieves 78.75%. Keep decision loss as the primary objective if that is what matters, but report accuracy, catastrophic mistakes, cost and win/tie/loss counts alongside it.

**1. Give the Challenger an effective way to direct evidence gathering**

The current Challenger generates requests, but the router often discards their most specific information.

In [record.py](../../acqlab/agents/record.py), `settle_weights()` assigns fixed weights to document kinds. A named document receives extra weight only if it is **off** the diligence map. An objection specifically naming the audited accounts for an add-back gets exactly the same document weights as no document hint. The audit reproduces this directly. Naming one specific customer contract likewise cannot distinguish it from other contracts through this mechanism.

Across the main run:

- 318 Challenger turns produced 1,359 explicit objections; 1,144 were “elsewhere” objections.
- 1,354 objections named at least one unread document. Only 425 were followed by a read of any such document.
- In 281 cases, at least one named document was affordable when the objection was made, but none was subsequently read.

These are objection counts, not unique deals. They do not imply that every request deserved a read. They do show why “make the Challenger smarter” may not improve the system: its source selection can disappear at the handoff.

Test an explicit evidence-request object: issue, concrete source, reason, expected decision impact, cost, and resolution status. A source-specific request should update the source-location belief even when the source is already on the map. The scheduler should either allocate the read or record why another use of the remaining budget is preferable. Do not automatically obey every objection.

Also test a **symmetric Challenger**. `Record.issue()` takes maxima of chances and upper bounds for objections; a committed floor stands. The prompt asks primarily whether issues could be bigger or elsewhere. There is no comparable mechanism to challenge excessive pessimism or retire an unsupported risk. A symmetric role should request evidence that could overturn either GO or NO-GO, and explicitly distinguish evidence-based corrections from speculation.

This is not a recommendation to cut all probabilities. That already failed. It is a recommendation to make challenges specific, actionable and capable of correcting both directions of error.

**2. Replace the hard halfway reading boundary with a schedule that preserves useful options**

In [panel.py](../../acqlab/agents/panel.py), `MID_SHARE = 0.5` restricts the first pass to documents that fit in half the budget. The router then greedily spends that allowance before the Challenger intervenes. A document too long for the first pass can become unaffordable for the second pass.

For example, with 22 units total and a 14-page audited report, the report is excluded from the first pass. Spending nine units elsewhere makes it impossible to read later. Running the Challenger at the midpoint does not repair that lost option.

The trace audit found 221 document/deal combinations where a document exceeded half the budget but fit the total. After the first pass, 136 were unaffordable. Fifty-six of these documents held terminal evidence for issues still open at the end, covering **54 deals, including 22 of the team's 35 wrong decisions**. Audited accounts were excluded this way on 56 of the 91 deals where they were longer than half the budget.

This is evidence of a scheduling constraint, not proof that reading those documents would have improved regret: each read displaces other evidence. The correct test is a paired policy comparison at the same total budget.

Compare an uninterrupted reading pass, an early Challenger, and a scheduler that reserves the cost of a high-value long document before buying short reads. A two-step lookahead can compare bundles or sequences of documents rather than only the next document's score. Start with the simplest scheduling ablation to isolate the mechanism.

None of the seven simulator variants changed the fixed midpoint. Even `no_sweep` inherits it. This avenue remains open after the simulator's negative results.

**3. Learn where evidence is likely to be found, separately from how costly a problem might be**

The existing page-weight experiments changed the denominator of a score. They did not repair its source-location model.

The 60 practice deals already show a substantial mismatch:

| Issue | Practice facts settled in board minutes | Mean initial board-minutes weight using the real Lead's named sources |
|---|---:|---:|
| Add-backs | 11/60, 18.3% | 0.9% |
| Debt-like items | 12/60, 20.0% | 10.6% |
| Customer concentration | 9/60, 15.0% | 3.5% |
| Working capital | 15/60, 25.0% | 1.8% |
| Capital expenditure | 11/60, 18.3% | 1.4% |

These frequencies use the final document of each evidence chain, matching the simulator's settlement convention. They are diagnostics, not independent estimates of a real-world source distribution. Another mismatch is that the generic map allocates 15–25% to the CIM for several issues, while a CIM-only finding is deliberately not sufficient to commit an amount.

Test a regularized source-location model trained only on practice evidence, with meaningful uncertainty and smoothing. Keep source location separate from issue existence, size, source reliability and the chance a read settles it. Give the same learned source information to Solo. Randomize the contract holding concentration evidence before evaluating a new system; exploiting `contract_1` would be benchmark fitting.

Use the location model to update “probably elsewhere” after an empty read. Update “probably absent” only when the search process has a defensible chance of detecting a present issue. The blanket absence cuts in the prior simulator did not make that distinction.

For multiple domains, source features and source reliability need domain adapters; memorizing that board minutes often contain answers is not a general solution.

**4. Test independent solutions and reconcile their disagreements with evidence**

Today's roles are sequential and highly coupled. The Lead supplies the beliefs, each document Investigator receives a narrow brief, and the Challenger sees the same record and engine verdict. Every role uses the same pinned model. This limits independent discovery even when role names differ.

The observed errors suggest useful complementarity. Only **12 of 160 deals** were wrong for both Solo and S4. A hypothetical oracle choosing the right existing answer would reach 92.5% accuracy and regret 0.00314. That is only a diagnostic ceiling: it uses truth, and the two original runs had separate reading budgets. It is not a measured hybrid result or a performance promise.

Test two initially independent analyses—one broad investigation and one structured issue analysis—before showing them each other's conclusions. Then reconcile only decision-relevant disagreements. Require each challenge to produce a source check, calculation, counterexample or other verifiable result. A third agent voting on the same uncertain claims is not enough.

Use one shared information budget. Partition initial reads, retain source-linked observations, and allow free access to already-purchased evidence for **every** comparison arm. Include a sequential Solo that gets the same total compute and can revise its answer. This separates useful independence from simply spending more resources.

Start with different search paths and contexts on the same model. Mixed models are a later experimental factor, not an assumed improvement.

**5. Make the belief and evidence interfaces coherent before extending the framework**

Several interfaces are less expressive than their prompts imply:

- The Lead supplies a conditional `[low, high]` range, but open issues are sampled uniformly from **zero** to `max(high, typical_high)`. `Issue` has no open lower-bound field. All 357 final open issues in the main run had a positive supplied lower bound. Changing it cannot change the priced issue. This is an intentional existing convention, but it differs from what the interface says and from what the no-engine valuer sees. Serialize the actual distribution used by the engine; test a coherent alternative without assuming that honoring the lower bound will help.
- The five issue draws are independent. Finding one issue does not automatically update the chances or sizes of related issues. The pair screen tests a few joint amounts, but does not supply a joint probability model. Test conditional beliefs where a domain actually supports dependencies; do not learn hidden case labels from the answer key at inference time.
- `Record.apply()` merges conflicting amounts with a minimum/maximum envelope. Later better evidence cannot narrow that envelope. This needs claim-level provenance, source precedence and explicit supersession before the framework can handle evolving or contradictory real documents.
- There is one record entry per issue type. Two distinct liabilities and two conflicting estimates of the same liability need different aggregation rules; the current schema cannot express that distinction. Add claim identities and dependency links before expanding beyond one synthetic fact per type.
- The Committer verifies quote presence and arithmetic, not semantic support. A direct probe successfully commits zero against a verbatim quote saying a $9M obligation is payable. Zero is exempt from the number-presence check. Require explicit support for a zero finding; for general domains add unit, entity, time-period and entailment checks.

There is a concrete qualification to the earlier “never misread a document” headline. In `test-068`, the authoritative capex range was [1.2, 2.1]. A later report mixed the seller's denial with that source and widened it to [0, 2.1]. A subsequent correct report could not narrow it. The original containment-based audit counts this as containing the truth, and the final decision was still correct. My endpoint audit found this one mismatch among 443 committed issue slots. It does not explain the 35 wrong decisions, but demonstrates why truth containment is weaker than faithful evidence handling.

Keep the narrow, deterministic arithmetic checks. Add semantic and conflict tests before claiming that evidence verification generalizes beyond the current templates.

**6. Treat the simulator as a screening tool with known blind spots**

The simulator was useful and its negative results should constrain the next experiments. But baseline agreement does not validate every counterfactual architecture.

Its simulated Lead largely keeps the opening plan; there is no Challenger; a terminal evidence document reveals the fact perfectly; and the modelled opening plan covers the five fixed issues. It cannot establish whether an independent search strategy, a symmetric challenge, semantic verification, or genuine multi-document inference would work.

The decision-focused variant also groups 4,000 worlds into potentially many observation groups, cross-fits within them, and stops when every estimated score is zero. The existing report acknowledges downward bias and premature stopping. That experiment rejects this particular implementation; it does not rule out a better estimated, multi-step value-of-information policy.

For a new scorer, inspect group sizes, uncertainty in scores, stopping decisions and sensitivity to the world count. Compare a sensitivity fallback and two-step lookahead rather than repeating the same zero-score stopping rule. Validate a changed simulator against a small real trace sample before relying on it for a large run.

Likewise, the greedy combination search required a significant single improvement before trying combinations. It never tested all interactions. A small, predeclared factorial experiment is appropriate for mechanisms that should work together—such as source-directed requests and preserved reading budget. This does not justify indiscriminately trying every combination until one wins.

**7. Strengthen the comparison before calling the benefit a team advantage**

S0 is a single model with the full reading allowance. It made **160/160 correct decisions**, with zero regret, at mean recorded cost $0.174 versus S4's $0.525. It is not a fair comparator under the restricted page cap, but it reveals that this benchmark's central difficulty is finding evidence under artificial scarcity. More discussion alone will not create a broad intelligence advantage here.

Also, S3 is described as “best of two” in places, but [the implementation](../../acqlab/bench/pilot.py) is a two-run vote with NO-GO winning ties. There is no best-answer selector. Its aggregate-token matching includes cached input. In the actual test, S4 generated about 11,905 output tokens per deal, compared with 5,054 for the two Solo runs, and cost approximately twice as much. The predeclared comparison remains valid as specified; it does not establish superiority at matched output budget or cost.

Add these baselines:

1. Solo with the same complete issue checklist, structured evidence record, uncertainty evaluator and deterministic commit checks. Both current systems receive general diligence knowledge, but equivalent information in a prompt does not isolate the effect of roles from enforced scaffolding.
2. Solo with an equivalent compute allowance and an explicit critique/revision stage.
3. Independent runs with verified reconciliation, and the current voting ensemble, clearly named.
4. The simpler Lead-plus-investigators system on a meaningful paired sample.

Report quality-versus-reading-budget and quality-versus-compute curves separately. Preserve the registered Plan 6 verdict; these are comparisons for a new version.

The −engine ablation is also limited: it removes the final valuation step after S4's engine-guided reading, not the engine from the entire workflow. The no-Challenger arm changes the stochastic trajectory, including its opening plan. Neither isolates a universal causal effect of that component as cleanly as its short label may suggest. Use shared initial plans or repeated paired runs for controlled mechanism tests, alongside full-system runs.

For unresolvable ranges, the generator's scored decision uses the midpoint amounts, while S4 propagates distributions through a nonlinear valuation engine. That is the frozen benchmark's definition of knowable truth, not realized-outcome performance. A broader decision benchmark should explicitly choose whether it rewards a stipulated point estimate or expected utility under uncertainty and align the solver and scoring contracts accordingly.

The [recoverability check](plan-6-test-set.md) also reported eight failures involving zero amounts among the sampled facts; the user explicitly chose to proceed after diagnosis. Preserve that disclosure. Repair the awkward zero-value wording in a new benchmark and repeat independent extraction checks. Identical documents for all systems ensure equal inputs, but do not guarantee that ambiguous wording affects every architecture equally.

**8. Build a portable core, then prove gains in distinct domains**

The code directly depends on five acquisition traps, nonnegative downside adjustments, a fixed document map and an LBO evaluator. Manufacturing and services are industry slices of the same task. They are not evidence for general research, programming or operational planning. The new descriptive split finds a more favorable Team–Solo difference in services than manufacturing, but those subgroup results are exploratory and do not establish a cross-domain effect.

Retain a small common core: task state, source-linked observations, typed claims, uncertainty, dependency links, evidence requests, budgets, verification results and an append-only decision log. Put issue schemas, tools, source rules, executable checks and objective functions behind domain adapters. If investigations run concurrently, keep one authoritative owner for budget reservations and record updates; the current sequential trace-and-budget mechanism is not a concurrent scheduler.

| Next task family | Potential team advantage to test | Independent check |
|---|---|---|
| Acquisition/document decisions | Combine dispersed facts and challenge both upside and downside assumptions | Existing valuation engine plus evidence checks |
| Repository debugging | Independent reproduction, implementation and regression discovery | Hidden behavioral tests and a reproducible failure |
| Multi-source research | Cover independent source branches and reconcile contradictions | Source-backed completeness and correctness labels, with a held-out adjudication rubric |
| Operational planning, later | Explore competing feasible plans while checking constraints | Constraint solver or executable simulation |

Use an adaptive workflow: independent branches for separable tasks, implementer/verifier for tasks with executable checks, and a single agent for tightly sequential work when extra coordination does not help. Escalate near unresolved decision boundaries or material disagreement. Evaluate whether the escalation rule predicts actual benefit on held-out tasks; uncertainty alone is not a guarantee that extra agents help.

This direction is consistent with [Anthropic's research-system engineering account](https://www.anthropic.com/engineering/multi-agent-research-system), which emphasizes independent breadth and clear delegation, and [Google's controlled architecture study](https://research.google/blog/towards-a-science-of-scaling-agent-systems-when-and-why-agent-systems-work/), which finds that coordination can help parallelizable tasks and hurt sequential ones. These sources motivate experiments; their results are not measurements of this repository. The [MAST failure study](https://arxiv.org/abs/2503.13657) likewise makes specification, coordination and verification useful categories for a failure log.

**A practical next experiment**

First preserve S4 as the reference and create a separate experimental variant. Instrument whether each challenge changed a read, settled an issue, altered a decision, and ultimately reduced loss. Add tests for the named-source handoff, long-document feasibility, zero-value support and evidence supersession.

On practice data, compare the baseline with two individual changes and their combination: (A) source-specific requests that affect routing, (B) preserving budget for high-value long reads. Test learned source locations separately so its effect is identifiable. Use fresh simulation deals to check any selected design; run a small real-model pilot only after choosing the candidate and obtaining the separate authorization required by the repository's handoff. A pilot checks mechanics and simulator fidelity, not statistical superiority.

In parallel as a research track, define the independent-analysis/reconciliation design and the scaffold-matched Solo baseline. Run them under the same information and compute budgets before expanding to three task families. Keep all old test deals exploratory now that their failures informed these ideas.

For the next confirmatory test, preregister one primary quality objective, resource budgets, task/domain mix, repeated-run policy and per-domain guardrails. Include hidden upside, unknown issue types, genuine cross-document dependencies, source contradictions and varied writing styles. Randomize evidence location. Give each contender the same tools and shared learned knowledge. If repeated runs are used, account for clustering by task; repeats are not new independent tasks.

The existing 737–986-deal estimate concerns detecting the observed **nonzero mean difference** under an approximate power model. It does not guarantee clearing every part of H1, proving a 25% reduction, or winning within each domain. Increasing sample size can establish a small existing advantage more precisely; it cannot make the architecture better. Recalculate power after a development pilot and target practical improvement before funding another large replication.

My recommended order is: **repair the evidence-request handoff and scheduling first; test independent analysis plus verification second; generalize through domain adapters and stronger baselines third.** Keep the engine, evidence provenance and honest experimental discipline. The current evidence does not justify simply adding more agents, dropping the Challenger outright, or assuming the simulator exhausted the design space.

Validation: **368 local tests passed** (`.venv/bin/python -m pytest -q`, 920.62 seconds). The audit reproduced the published main-run paired difference and confidence interval exactly; its issue and deal totals reconcile, the script compiles, and every local report link resolves. These checks validate existing behavior and the audit, not the effectiveness of the proposed changes. The full suite uses simulated model clients, so this validation made no real evaluation-model calls.
