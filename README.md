# Acquisition Lab

**Can a team of AI agents do buyout diligence better than one strong AI agent working alone?**

Acquisition Lab is a test bench for that question. It builds synthetic private-equity deals, each with a data room
that hides problems a careful analyst should find. It then lets AI systems investigate under a fixed reading budget
and scores the go/no-go call each one makes against the hidden truth.

The short answer so far: **sometimes, and not by enough to claim it.** The details are below, including the results
that went against the idea.

---

## The problem

A sponsor is looking at a leveraged buyout. The teaser shows revenue, adjusted EBITDA, an asking price and a lender
term sheet. The documents behind it may tell a different story:

- an EBITDA add-back that is not really one-off
- debt-like items such as an earnout, an unfunded pension or deferred revenue
- a customer that is a third of revenue and has just given notice
- a working-capital peg set too low, years of skipped capex, or pending litigation

Each of these changes what the company is worth. Because lenders size debt as a multiple of EBITDA, a small fake
add-back also cuts how much the sponsor can borrow, so a small fact can flip the decision. An analyst can't read
everything, so the job is to **choose what to read**, then decide whether to buy and what to pay at most.

## How it works

```
 deal generator ──► data room (CIM, QoE, credit agreement, contracts, board minutes, filler …)
       │                    │  list / search / open document, each costs budget
       ▼                    ▼
 hidden truth        AI system under test  ──►  beliefs about each issue
       │                                              │
       │                                              ▼
       │                                   LBO engine (plain Python, no AI)
       │                                              │
       ▼                                              ▼
 true walk-away price  ◄──── scored against ────  walk-away price + GO / NO-GO
```

- **LBO engine** (`acqlab/engine`): the only source of financial numbers. It sizes the debt (lender cap, downside
  covenant test, minimum equity) and finds the **walk-away price**, the highest price that still clears the sponsor's
  20% base-case IRR hurdle. No language model does arithmetic that gets scored.
- **Deal generator** (`acqlab/generator`): samples a mid-market company and its financing, plants 2–5 hidden facts
  (decision flips, decoys, two-issue interactions, unresolvable questions, clean deals), and renders the data room.
  Code writes every number; prose is template text by default, or written by Codex. Every deal is checked so the
  teaser doesn't give the answer away and each fact can be recovered from the documents meant to hold it.
- **Systems under test** (`acqlab/agents`), all on the same Claude model, with the same tools and budget:
  - **Solo (S1b):** one agent with the data-room tools and the engine as a tool. This is the fair opponent.
  - **Best-of-2 Solo (S3):** two Solo runs that vote, with NO-GO winning ties, to rule out "the team just used more
    tokens".
  - **The Team (S4):** a Deal Lead who proposes issues and their likely size, Investigators who read, a Challenger who
    argues against the current view, and a code Router that prices each next read by how much it could change the
    decision. A code Committer accepts a finding only if it's quoted from a document, computed from quotes, or
    recorded as a contradiction between documents.
- **Scoring** (`acqlab/bench`): the main measure is **decision regret**. Buying a bad deal costs the overpayment;
  passing on a good deal costs the value forgone. Both are scaled by the asking price, so lower is better.

## What we found

Every main hypothesis was written down and committed before the test deals existed
([pre-registration](docs/results/plan-4b-preregistration.md)). The main run used 160 fresh deals and was analysed once.

| System | Mean decision regret (lower is better) |
|---|---|
| Solo (S1b) | 0.0126 |
| Best-of-2 Solo (S3) | 0.0105 |
| **The Team (S4)** | **0.0088** |

- **The Team's regret was 30% lower than Solo's, but that isn't a proven win.** The bar was "at least 25% lower, with
  a 95% confidence interval that excludes zero". The interval was −0.0100 to +0.0016, which includes zero, so the
  headline hypothesis **fails as pre-registered**.
- **The gain comes from hard deals.** On deals where two issues interact, the Team was clearly better. On deals where
  the true answer differs from what the teaser suggests, its regret was 0.0072 against Solo's 0.0224. On decoy deals
  it was clearly *worse*.
- **The Team reads more decoy pages, not fewer** (1.5 against 1.0 per deal), which is the opposite of the prediction.
- **The engine matters.** Without it, walk-away price errors were about 1.5 times larger. That is clearly worse, but
  short of the 2× bar we had set.
- **Making Solo as cautious as the Team doesn't reproduce the Team's result**, so the Team's edge isn't just saying
  NO-GO more often.

Full write-up: [docs/results/plan-6-main-run.md](docs/results/plan-6-main-run.md).

### Follow-up experiments

Each one had its rules fixed in advance. Most of them didn't work, and they're kept here because that is useful too.

| Experiment | Question | Outcome |
|---|---|---|
| [Reading simulator](docs/results/reading-simulator.md) | Can a rule-based copy of the Team test reading changes for free? | Matches the real Team on 89–97% of calls. None of 7 reading or pricing changes beat today's Team. |
| [Reconciling analysts](docs/results/recon-pilot.md) | Two independent analysts plus a referee, at the same budget? | No better than Solo (0.0102 against 0.0085). The analysts rarely disagree. |
| [Hidden upside](docs/results/upside-pilot.md) | Deals that look bad but are good. Is the Team too cautious? | Yes. 12 false NO-GOs against Solo's 7, mostly because the Team never opened the document that settled the worry. |
| [Debate](docs/results/debate-pilot.md) | A bull, a bear and a referee? | Doesn't help. The referee sided with the reader on 39 of 40 deals. |

## Getting started

You need Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/dmbritton1/Acquisition-Lab.git
cd Acquisition-Lab
uv sync
uv run pytest -q
```

The 451 tests run offline and take a few minutes.

**Generate some deals (free, offline):**

```bash
uv run python -m acqlab.generator.batch --out data/demo --dev 5 --test 0 --hand 0 --showcase 0
```

Each deal lands in `data/demo/deals/<id>/room/` as Markdown documents, with its hidden answer in
`data/demo/truth/<id>.json`. Open `cim.md` and then `board_minutes.md` to see what an analyst would be up against.

**Run real AI systems (costs money):** the runners call the [Claude Code](https://claude.com/claude-code) CLI
(`claude -p`) and make no AI calls unless you pass `--confirm-claude`. A 40-deal pilot cost about $25–50.

```bash
uv run python -m acqlab.bench.pilot --data data/demo --n 5 --systems s1b,s4 --confirm-claude
uv run python -m acqlab.bench.pilot --data data/demo --n 5 --systems s1b,s4 --report
```

## Repository map

| Path | What's there |
|---|---|
| `acqlab/engine/` | LBO model, debt sizing, walk-away price, belief sampling |
| `acqlab/generator/` | Deal sampler, trap library, document rendering and validation |
| `acqlab/dataroom/` | The budgeted list / search / open tools every system shares |
| `acqlab/agents/` | Solo, the Team (Deal Lead, Investigator, Challenger), Committer, deal record |
| `acqlab/routers/` | Code routers that price the next read, and the offline router benchmark |
| `acqlab/bench/` | Runners, the main campaign, analysis, simulator and the follow-up pilots |
| `docs/superpowers/specs/` | Design documents, starting with [the original design](docs/superpowers/specs/2026-09-22-acquisition-lab-design.md) and [the reframe](docs/superpowers/specs/2026-09-24-reframe-design.md) |
| `docs/results/` | Every pre-registration and result, with the raw numbers as JSON |

## Limits

- The deals are synthetic. The ranges are drawn from mid-market LBO sources, but the documents are generated, and
  passing the recoverability check means "an AI can extract the fact", not "a human analyst would find it".
- The engine tests covenants annually and uses a single term loan. The exit multiple is fixed by sponsor policy.
- Every system ran on one model family (Claude). Whether the results carry over to other models is untested.

## Where it's going

The benchmark has done its job: it shows where a team of agents helps (tangled, multi-issue deals) and where it hurts
(caution and decoys). The next step is to turn the parts that held up, the engine and the evidence rules, into a tool
for PE analysts.
