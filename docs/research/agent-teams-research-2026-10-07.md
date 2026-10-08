# Agent teams vs. one agent: what the research says, and what it means for acquisition-lab

Research date: 2026-10-07. Sources are listed at the end. Where a number comes from a secondary summary rather than
the paper itself, it says so.

## Bottom line

1. **A team of AI agents beats a single agent only by one of four routes.** Coordination is never a gain in itself;
   it is always a cost. The four routes are:
   - **More total work:** more reading, searching and thinking than one agent would do.
   - **Independent mistakes that can be averaged out.**
   - **A checker that can pick the right answer from several attempts.**
   - **Room:** splitting the work when one agent's context would overflow.

   When none of these applies, the best studies find that the single agent wins or ties.
2. **The headline wins in the field mostly come from route 1, spending more.** Anthropic's research system beat a
   single agent by 90%. But on Anthropic's own BrowseComp analysis, token spend alone explained 80% of the difference
   in performance. Studies that hold spending equal (Stanford, April 2026; Google, December 2025) find single agents
   match or beat teams on step-by-step reasoning.
3. **Teams help less as the single agent gets stronger.** Google's 180-configuration study found that once a single
   agent is right more than about 45% of the time, adding agents gives shrinking or negative returns. Our single
   Claude is right 77–83% of the time.
4. **Our team's main flaw is structural, and the theory names it.**
   - Every part the team adds can only push toward "don't buy":
     - The Challenger only asks whether a problem "could be bigger".
     - An unresolved issue is priced at its likely loss.
     - The seller's own claims are never allowed to settle an issue.
   - In organisation theory this is a "hierarchy": a chain of screens that each must be passed. Sah and Stiglitz
     showed in 1986 that this structure rejects more good projects and accepts fewer bad ones. That is exactly the
     team's pattern: 25 good deals turned down against single Claude's 9, and 10 bad deals bought against 28.
5. **The designs with the strongest evidence for our problem are not "more agents".** Ranked:
   - **(a) A two-sided debate** (a bull case and a bear case) **judged by a referee**, in place of a one-sided
     Challenger.
   - **(b) One reader with a built-in "virtual panel"**, in the style of Microsoft's diagnosis system, which faces the
     same buy-information-under-a-budget problem.
   - **(c) A second opinion from a different model family (GPT/Codex)**, so the two sets of mistakes don't match.
   - **(d) Several independent full reads and a vote or referee**, but only if we accept spending more reading.

   Our own referee kill test already points the same way.

## Part 1. The theory: why a team could win, and why it usually doesn't

### Why a team could win

| Route | The idea | Classic source | When it works |
|---|---|---|---|
| 1. More total work | Several agents together read, search and think more than one | Anthropic 2025; "More Agents Is All You Need" (Li et al. 2024) | The task splits into independent parts (breadth-first research); the budget is not fixed |
| 2. Averaging independent mistakes | A majority vote is right more often than any single voter | Condorcet jury theorem (1785); self-consistency (Wang et al. 2022) | Each voter is better than chance **and their mistakes are independent** |
| 3. Selection by a checker | Generate several answers, keep the one a checker accepts | "Large Language Monkeys" (Brown et al. 2024); AlphaCode/AlphaEvolve | There is a reliable checker (tests, proofs, an engine) |
| 4. Room | Each agent gets a clean, short context instead of one overflowing one | Tran & Kiela 2026; Anthropic 2025 | The material doesn't fit in one context, or a long context degrades |
| 4b. Adversarial checking | Two advocates argue opposite sides before a judge who cannot see everything | AI-safety debate (Irving et al. 2018); Khan et al. 2024 | **The judge has less information than the debaters, and claims can be checked against quotes** |

### Why teams usually don't win

- **Information gets lost at every hand-off.** Under a fixed budget, splitting work across agents passes information
  through extra steps, and each step can only lose information, never add it. This is the "Data Processing
  Inequality" argument in Tran & Kiela (Stanford/Contextual AI, 2026). They found single agents matched or beat
  teams on multi-step reasoning at equal thinking budgets, across three model families. Cognition, the company
  behind Devin, makes the same point from engineering practice: "actions carry implicit decisions", so parallel
  agents make conflicting unspoken choices.
- **Copies of the same model make the same mistakes.** Across more than 350 models, when two models are both wrong
  they pick the *same* wrong answer about 60% of the time. Stronger models are *more* alike in their mistakes
  (Kim et al., ICML 2025). Condorcet's "independent mistakes" condition fails, so voting among copies of one model
  gains far less than the textbook formula promises.
- **Debate on its own doesn't make anyone more accurate.** Choi, Zhu and Li (NeurIPS 2025) showed mathematically
  that in a standard debate, each agent's belief in the right answer is a "martingale": it doesn't drift up or down
  on average. Most of the gains credited to debate come from the final majority vote, not from the arguing. Other
  studies find that agents defer to each other, collapse onto a consensus too early, and are talked out of correct
  answers (Yao et al. 2025; Wynn et al. 2025; Estornell & Liu 2024).
- **Groups discuss what they all already know.** In the "hidden profile" set-up from social psychology (Stasser &
  Titus 1985), each member holds a different piece of the facts. Groups talk about the shared facts and miss the
  unique ones. With LLM teams the result is the same: 30.1% accuracy when facts were spread across agents, against
  80.7% for one agent holding all of them (HiddenBench, 2025–26). The failure got *worse* as groups grew.
- **Coordination costs grow faster than the work.** In the Google study, centralized teams spent 285% overhead and
  hybrid teams 515%. On step-by-step tasks every team design lost 39–70%. The authors' rule: default to a single
  agent for sequential, state-dependent tasks, and for tasks where the single agent is already above about 45%.
- **Chains of approvals are biased by construction.** Sah & Stiglitz (1986, 1988) compared a "hierarchy", where a
  project must pass every screen, with a "polyarchy", where any one screen can approve it. For screeners of equal
  skill, a hierarchy rejects more good projects and approves fewer bad ones. Adding screens doesn't make an
  organisation smarter; it moves it along a trade-off between the two mistakes.
- **Personas don't add knowledge.** Telling a model "you are a risk expert" does not improve factual accuracy. Some
  2026 studies find expert personas *reduce* accuracy, from 71.6% to 68.0% on MMLU (Zheng et al., revised; Wharton
  2025; USC 2026). A "team" of role-prompted copies of one model is mostly one model in several costumes.

### The one-line model

> A team beats a single agent only to the extent that it **spends more**, **averages truly independent errors**,
> **uses a real checker to select**, or **escapes a context that's too big**. Everything else (roles, debate,
> hand-offs, approvals) is overhead, plus whatever bias the structure builds in.

## Part 2. The evidence: teams that measurably beat a single agent

| System | Result against one agent | Which route explains it | Catch |
|---|---|---|---|
| **Anthropic research system** (2025): an Opus lead with Sonnet subagents | +90.2% on an internal research eval | Route 1: token spend explained 80% of BrowseComp variance; about 15× chat's tokens, against about 4× for one agent | Anthropic says it's a poor fit for tasks where agents need the same context or depend on each other, and for most coding |
| **Google "science of scaling agents"** (Dec 2025) on the Finance-Agent benchmark | Centralized team +80.8% (0.631 against 0.349) | Routes 1 and 4: an analyst task that splits cleanly (filings / news / operations) | The single agent started *below* the 45% threshold; on sequential tasks teams lost 39–70% |
| **Microsoft MAI-DxO** (2025): sequential diagnosis on 304 NEJM cases | o3 alone: 78.6% at $7,850 per case. With the panel: 81.9% at $4,735; budgeted: 79.9% at $2,396; ensemble of panels: 85.5% at $7,184. On average about +11 points across model families | **One model playing five roles**, choosing which tests to buy (route 3-like discipline); the ensemble adds routes 1 and 2 | For o3, the strongest model, the accuracy gain without a budget was *not* significant; the gain was the cost cut. Self-reported and not peer reviewed; 56-case test set |
| **Debate with an information-limited judge** (Khan et al., ICML 2024 best paper) | LLM judge: 76% with debate, against 48% without and 54% with a single advocate ("consultancy", secondary figure). Human judge: 88% against 60% | Route 4b: the judge can't read the story; debaters cite checked quotes | Works where the judge sees less than the debaters. DeepMind (Kenton et al. 2024) found mixed results without that information gap, but debate beat a single advocate on every task |
| **Mixture-of-Agents** (Wang et al. 2024) | Open models beat GPT-4o on AlpacaEval (65.1% against 57.5%) | Routes 1 and 3 | **Self-MoA**, one strong model sampled several times, beat the mixed team by 6.6% (Li et al. 2025). Quality beats diversity |
| **ReConcile** (Chen et al., ACL 2024): ChatGPT, Bard and Claude in a round-table | Up to +11.4% over single and multi-agent baselines | Route 2: *different* model families; the ablation says diversity is the key ingredient | 2023-era models |
| **MDAgents** (NeurIPS 2024, medical) | Best on 7 of 10 benchmarks | Sends easy cases to one agent and hard cases to a team | Margins of 4–6.5%; self-reported |
| **Cognition / Devin** (2026 update) | Review agent catches about 2 bugs per PR, 58% of them severe | Route 3: a reviewer with a **clean context** (sees the diff, not the spec) | Their rule: "writes stay single-threaded", so extra agents contribute *intelligence*, not *actions* |
| **LLM forecasting crowd** (Schoenegger et al. 2024) | 12 models averaged matched a 925-person human crowd | Route 2: 12 *different* models | 31 questions only |

**Null and negative results that matter just as much:**
- **Single agent with good prompts ≈ best multi-agent discussion** (Wang et al., ACL 2024). Discussion helped only
  when the prompt had no worked examples.
- **Simple retry baselines** matched complex agents at up to 50× lower cost (Kapoor et al., "AI Agents That Matter").
  Their lesson: always compare on a cost-against-accuracy chart.
- **"Agentless"** (Xia et al. 2024): a fixed three-step pipeline beat agent frameworks on SWE-bench Lite.
- **Why multi-agent systems fail** (Cemri et al., NeurIPS 2025): 14 failure modes in three groups (system design,
  agents misaligned with each other, and weak checking), from 1,600+ traces across 7 frameworks. They conclude
  failures come mainly from system design, not the model.
- **Google's automated search over team designs** (MASS, ICLR 2026): the best systems "often emerge from simpler
  design spaces", and prompts matter as much as the shape of the team.

### The pattern across the wins

Every clear win has at least one of these features:
- **an unfixed budget** (the team simply did more);
- **different model families** (the mistakes really are independent);
- **a real checker** (tests, quotes or an engine);
- **an information-limited judge with two-sided argument**;
- **a sub-45% single-agent baseline on a task that splits into independent parts.**

None of the clear wins comes from role-playing copies of a strong model splitting a fixed budget on a sequential
task.

## Part 3. Our team through this lens

How our set-up scores on each route:

| Route | Our set-up | Prediction |
|---|---|---|
| 1. More total work | **Removed by design:** the same page budget for both | No gain from breadth |
| 2. Independent mistakes | Every role is Claude Opus 5.5, so mistakes are correlated | Little gain from voting |
| 3. Checker | **Present:** the Committer checks quotes and the engine does the arithmetic | Gain in reliability: the team never misread a document ✔ |
| 4. Room | Budgets of 18–27 pages fit in one context | No gain from splitting |
| Task shape | Sequential: what to read next depends on what was found | Google's study predicts teams *lose* here |
| Baseline | The single agent is right 77–83% of the time, well above 45% | Shrinking or negative returns |

So the theory predicts our team should tie or lose on accuracy. It should win on traceability. It should cost far
more. That is exactly what we measured.

**Why the team leans toward "don't buy".** Reading S4's code shows the bias is built in, not accidental. Every part
the team adds can only *add* downside:
- **The Challenger** (`acqlab/agents/panel_prompts.py`) is told to ask whether each issue "could be bigger, or
  somewhere else". It never asks whether an issue could be smaller or absent.
- **Pending objections** are priced at the larger of their chance and the Lead's chance, at the larger of their
  stated top and the typical top (`acqlab/agents/record.py`).
- **Open issues** are priced as an expected loss.
- **The seller's documents** can never settle an issue (`committer.py`), so reassurance from them doesn't count.
- **Findings below zero** are rejected, so upside can never enter.

In debate-research terms, our Challenger is a **one-sided "consultant", not a debate**. That is the format Khan and
Kenton found does *worse* than two-sided debate. In organisation terms, it is a Sah–Stiglitz hierarchy, which
produces our exact error pattern: few bad deals bought and many good deals turned down. On deals with hidden upside
(our untested track), the theory predicts the team will do worse still.

**Why the referee kill test worked and the reconciliation pilot didn't.**
- **The referee** saw two *full* budgets of reading (route 1), from two different systems (partly route 2), and
  judged with quotes (route 4b). It got 35 of 48 disputed deals right, against the team's 25 and single Claude's 23.
- **The pilot designs** split *one* budget, which removed route 1. The analysts then rarely disagreed, so the
  referee seldom ran.

Both results are what the theory predicts.

**Why the pitch can still be honest.** Real data rooms run to hundreds of documents. That is where route 4 (room)
and Google's "splits cleanly" condition (legal / financial / commercial workstreams) start to apply. Our benchmark's
small budgets can't show that advantage. It is a hypothesis, not a result.

## Part 4. What to try next, ranked by evidence for our problem

S4 stays frozen. These would be new systems, compared with single Claude at equal pages, and with cost reported
(Kapoor's rule).

1. **Two-sided debate plus referee (cheapest change with the strongest theory).**
   - **Design:** after one reader's pass, a *bull* advocate argues GO and a *bear* advocate argues NO-GO. Both cite
     quotes the Committer checks. A referee who did not read decides, pricing with the engine.
   - **Evidence:** Khan 2024 and Kenton 2024 (debate beats one-sided advocacy); our own kill test.
   - **Expected effect:** remove the NO-GO bias without losing the protection against bad deals.
   - **Cost:** about 3–4 sessions per deal. No extra reading if the advocates only argue from what was read.
2. **One reader with a built-in virtual panel (MAI-DxO style).**
   - **Design:** a single Claude session with one context and one budget, prompted to run a fixed loop on every read:
     - a GO/NO-GO probability (Dr. Hypothesis);
     - the next document by value per page (Test-Chooser);
     - a two-sided challenge (Challenger);
     - a budget check (Stewardship);
     - a stop-and-commit rule.
   - **Evidence:** MAI-DxO is the closest published match to our task, buying information under a cost before a
     decision. It gained about 11 points on average across models, but little accuracy for the strongest model.
   - **Expected effect:** small accuracy gain and fewer pages read. Keeps Cognition's "single-threaded" rule.
   - **Cost:** about the same as single Claude.
3. **A second opinion from a different model family.**
   - **Design:** run Codex/GPT as an independent single reader. Where it and Claude disagree, send the deal to a
     referee, as in the kill test.
   - **Evidence:** correlated errors are highest within a provider (Kim 2025); diversity drove ReConcile's gains;
     Cognition reports "real gains" from Claude and GPT together on the hardest tasks.
   - **Cost:** doubles reading unless the second reader is limited to the first reader's documents.
   - *Needs your OK for Codex calls.*
4. **Several independent full reads plus a vote or referee.**
   - **Evidence:** the kill test (35/48 on disputes) and MAI-DxO's ensemble (85.5%) both say this works.
   - **Cost:** it works by buying more reading.
   - **The real question is a business one:** is the page budget a hard limit (analyst time), or is it AI spend that
     we can trade for accuracy?
5. **Not recommended:** more roles, more debate rounds, or splitting one budget more finely. Every source above says
   these add overhead without adding any of the four routes.

**Fixes for how we test, from the same literature:**
- Always report a **cost-against-accuracy chart**, not just accuracy.
- Count **tokens/dollars as well as pages**: the team used 4× the dollars and still didn't win, which is strong
  evidence against the structure itself.
- Include **hidden-upside deals** before any claim. A cautious structure looks good only when every surprise is bad
  news.

## Limits of this research

- Many of the wins are **self-reported by their builders** (Anthropic, Microsoft, MDAgents, ReConcile), and several
  2026 papers are preprints.
- Several results use **2023–25 models**. The capability-saturation finding suggests team gains shrink further with
  today's stronger models.
- I found **no published study that compares a multi-agent investment committee with a single agent** on deal
  screening. The finance evidence is adjacent: Finance-Agent analysis, trading, and VC diligence frameworks without
  single-agent baselines.
- The Sah–Stiglitz link to S4 is an analogy. S4 is an additive pricing chain, not literally a series of yes/no
  approvals, but the direction of the bias is the same.

## Sources

**Theory and controlled comparisons**
- Kim, Liu et al., *Towards a Science of Scaling Agent Systems* (Google, 2025): [arXiv 2512.08296](https://arxiv.org/html/2512.08296v2), [Google blog](https://research.google/blog/towards-a-science-of-scaling-agent-systems-when-and-why-agent-systems-work/)
- Tran & Kiela, *Single-Agent LLMs Outperform Multi-Agent Systems on Multi-Hop Reasoning Under Equal Thinking Token Budgets* (2026): [arXiv 2604.02460](https://arxiv.org/abs/2604.02460)
- Choi, Zhu & Li, *Debate or Vote* (NeurIPS 2025): [arXiv 2508.17536](https://arxiv.org/abs/2508.17536)
- Kim, Garg et al., *Correlated Errors in Large Language Models* (ICML 2025): [arXiv 2506.07962](https://arxiv.org/abs/2506.07962)
- Cemri et al., *Why Do Multi-Agent LLM Systems Fail?* (NeurIPS 2025): [arXiv 2503.13657](https://arxiv.org/html/2503.13657v3)
- Li, Naito & Shirado, *HiddenBench / Systematic Failures in Collective Reasoning under Distributed Information*: [arXiv 2505.11556](https://arxiv.org/html/2505.11556v3)
- Wang et al., *Rethinking the Bounds of LLM Reasoning: Are Multi-Agent Discussions the Key?* (ACL 2024): [arXiv 2402.18272](https://arxiv.org/abs/2402.18272)
- Kapoor et al., *AI Agents That Matter*: [agents.cs.princeton.edu](https://agents.cs.princeton.edu/)
- Sah & Stiglitz, *The Architecture of Economic Systems: Hierarchies and Polyarchies*: [NBER w1334](https://www.nber.org/papers/w1334.pdf); *Committees, Hierarchies and Polyarchies* (1988): [PDF](https://www.raajsah.com/uploads/4/3/4/9/43495347/p_1988_committees_hierarchies_and_polyarchies.pdf)
- Brown et al., *Large Language Monkeys*: [arXiv 2407.21787](https://arxiv.org/abs/2407.21787v1)
- Zheng et al., *When "A Helpful Assistant" Is Not Really Helpful*: [arXiv 2311.10054](https://arxiv.org/abs/2311.10054v2); USC, *Expert Personas Improve LLM Alignment but Damage Accuracy*: [arXiv 2603.18507](https://arxiv.org/pdf/2603.18507); Wharton, *Prompting Science Report 4*: [SSRN](https://papers.ssrn.com/abstract=5879722)
- Sycophancy and conformity in debate: Yao et al. 2025 [arXiv 2509.05396](https://arxiv.org/abs/2509.05396v2); Kasprova et al. 2026 [arXiv 2604.02668](https://arxiv.org/pdf/2604.02668)

**Systems with measured wins**
- Anthropic, *How we built our multi-agent research system*: [anthropic.com](https://www.anthropic.com/engineering/multi-agent-research-system)
- Anthropic, *Building effective agents*: [anthropic.com](https://www.anthropic.com/engineering/building-effective-agents)
- Nori et al., *Sequential Diagnosis with Language Models* (MAI-DxO): [arXiv 2506.22405](https://arxiv.org/html/2506.22405)
- Khan et al., *Debating with More Persuasive LLMs Leads to More Truthful Answers* (ICML 2024): [arXiv 2402.06782](https://arxiv.org/html/2402.06782v4)
- Kenton et al., *On scalable oversight with weak LLMs judging strong LLMs* (NeurIPS 2024): [arXiv 2407.04622](https://arxiv.org/html/2407.04622v2)
- Li et al., *Rethinking Mixture-of-Agents* (Self-MoA): [arXiv 2502.00674](https://arxiv.org/abs/2502.00674)
- Chen, Saha & Bansal, *ReConcile*: [arXiv 2309.13007](https://arxiv.org/abs/2309.13007v3)
- Kim et al., *MDAgents* (NeurIPS 2024): [arXiv 2404.15155](https://arxiv.org/html/2404.15155v2)
- Zhou et al., *Multi-Agent Design: Optimizing Agents with Better Prompts and Topologies* (ICLR 2026): [arXiv 2502.02533](https://arxiv.org/abs/2502.02533)
- Schoenegger et al., *Wisdom of the Silicon Crowd*: [arXiv 2402.19379](https://arxiv.org/html/2402.19379v6)
- Cognition, *Don't Build Multi-Agents* (2025): [cognition.ai](https://cognition.ai/blog/dont-build-multi-agents); *Multi-Agents: What's Actually Working* (2026): [cognition.com](https://cognition.com/blog/multi-agents-working)

**Background (from prior knowledge, not re-fetched)**
- Du et al., *Improving Factuality and Reasoning through Multiagent Debate* (2023), arXiv 2305.14325
- Wang et al., *Self-Consistency* (2022), arXiv 2203.11171
- Li et al., *More Agents Is All You Need* (2024), arXiv 2402.05120
- Huang et al., *Large Language Models Cannot Self-Correct Reasoning Yet* (2023), arXiv 2310.01798
- Xia et al., *Agentless* (2024), arXiv 2407.01489
- Stasser & Titus, *Pooling of unshared information in group decision making* (1985)
