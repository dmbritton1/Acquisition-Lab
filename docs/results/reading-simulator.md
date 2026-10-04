# The reading simulator: results (exploratory)

**Exploratory, not confirmatory.** This is a free, offline test bench. It was used to choose a design and size a test;
it makes no claim of its own. Spec: `docs/superpowers/specs/2026-10-01-reading-simulator-design.md`; numbers:
`reading-simulator.json`; code: `acqlab/bench/sim.py`, `acqlab/bench/simrun.py`. No Claude or Codex call was made.

## 1. What the simulator is

It runs S4's real loop, Deal Record, document router and engine. Only the AI turns are replaced by rules:

- **The reader:** opening a document reveals exactly what the answer key places there. A fact is revealed by the
  last document of its evidence, as the real readers did on all 173 two-document commits.
- **The Lead:** proposes an opening plan and keeps it.
  - On deals with a real S4 run, the plan is the real Lead's logged one.
  - On the template deals, it is modelled from the 60 practice deals' logged plans.
- **The Challenger:** left out.

It assumes perfect reading. That was true of S4 in Plan 6: 0 misread values in 800.

## 2. Faithfulness: passed

The simulated team, with each deal's logged opening plan, against the real one. The bars were fixed in the spec
before the check ran: at least 85% of calls the same, the regret gap under 0.003, and a CI that includes zero.

| Deals | n | Same call | Regret, simulated / real | Gap (sim − real), 95% CI | Document overlap | Pass |
|---|---|---|---|---|---|---|
| Practice (`cal-r2`, `heldout-r2`) | 60 | 96.7% | 0.0096 / 0.0090 | +0.0006 [−0.0012, +0.0029] | 0.73 | yes |
| Test (`test-r2`) | 160 | 88.7% | 0.0100 / 0.0088 | +0.0012 [−0.0020, +0.0045] | 0.79 | yes |
| Test, real −Challenger | 40 | 92.5% | 0.0051 / 0.0061 | −0.0010 [−0.0142, +0.0083] | 0.81 | yes |

The test deals served only here, never to judge a strategy.

## 3. The strategies, on 300 template deals

The deals are fresh template-prose `r2` deals (base seed 7,000,000; some deals used retry seeds; no clash with
`cal-r2`, `heldout-r2` or `test-r2`, the sets checked; 53% truly NO-GO), with the modelled Lead. Every strategy ran on
the same 300 deals and is compared with the baseline deal by deal.

| Strategy | Regret | Correct | Pages on documents with no facts | Real facts reached | Says NO-GO | − baseline, 95% CI |
|---|---|---|---|---|---|---|
| **Baseline (today's team)** | **0.0066** | **83.7%** | 47% | 55% | 58% | — |
| Decision-focused picker | 0.0094 | 78.7% | 54% | 39% | 61% | +0.0028 [+0.0003, +0.0055] |
| Softer page discount (0.5) | 0.0085 | 81.3% | 34% | 57% | 59% | +0.0019 [−0.0007, +0.0045] |
| No page discount | 0.0097 | 79.3% | 27% | 46% | 59% | +0.0032 [+0.0000, +0.0064] |
| Calibrated starting guesses | 0.0086 | 82.0% | 49% | 56% | 53% | +0.0021 [−0.0001, +0.0045] |
| Lower a guess after finding nothing (−25%) | 0.0149 | 80.3% | 45% | 59% | 35% | +0.0084 [+0.0039, +0.0133] |
| Lower a guess after finding nothing (−50%) | 0.0159 | 78.0% | 44% | 60% | 32% | +0.0093 [+0.0046, +0.0144] |
| No sweep | 0.0066 | 83.7% | 47% | 55% | 58% | 0 (same calls on all 300) |

**Nothing beats today's team.** No alternative has a lower mean regret. Four of the seven (three of the five ideas)
are clearly worse, with the CI above zero:

- **Lowering a guess after finding nothing** makes the team optimistic. Its false GOs rise from 17 to 57–65, and its
  false NO-GOs fall from 32 to 1–2. In these deals every issue is settled somewhere, so "not found here" means "it is
  elsewhere". Treating it as "probably fine" is wrong.
- **The decision-focused picker** reaches fewer real facts (39% against 55%) and reads fewer pages (20.9 against
  22.3). It stops once no single document looks able to change the call, which leaves issues unread. Its cross-fitted
  scores are computed over fine groups of worlds, which biases them toward zero, so it also stops reading earlier for
  that reason.
- **No page discount** (only just above zero: the CI's lower bound is +0.0000) cuts pages on empty documents (27%
  against 47%) but reaches fewer real facts (46%).
  - The short documents the baseline reads are cheap ways to rule issues out.
  - The empty-page share in the post-hoc look was not waste.

The **softer page discount** comes closest: regret 0.0085, gap +0.0019 [−0.0007, +0.0045], against +0.0021
[−0.0001, +0.0045] for calibrated starting guesses. Neither CI excludes zero.

Separately, calibrated starting guesses make the team say NO-GO exactly as often as the truth (53%) and balance its
mistakes (27 false NO-GOs, 27 false GOs), yet regret still rises. A bad deal bought costs more than a good deal passed
up, so the baseline's lean toward NO-GO pays.

**A caveat on the two "lower a guess" rows.** The tested cut fires after any read that could have settled the issue but
didn't. Leftover router weight goes to every other document, so that is nearly every read: this is the harshest form
of the idea. The post-hoc page (`plan-6-posthoc.md`, "version 2", item 2) proposed a cut only after an issue's
likeliest documents are read, and said it would pay only alongside better reading (item 1). That pairing was never run,
because no single strategy beat the baseline.

The sweep never changed a call: it read differently on 18 of the 300 deals, but the calls were the same.

## 4. The combination

The rule starts from the best single strategy whose CI against the baseline lies below zero. None does, so the
combination is the baseline itself and no combination was run (`combination.json`: `{"combo": "baseline"}`). There
is no change to confirm, so the JSON has no confirmation block.

## 5. Sizing

With no simulated gain, a real re-test of today's team against Solo rests on Plan 6's gap alone (−0.0038; per-deal
SD 0.0368). It would need **737 deals for 80% power, 986 for 90%** (two-sided, 5%).

## 6. Recommendation

- **Don't spend on a real run of a reading or pricing change.** None of the seven changes tested (five ideas) improves
  on today's team in the simulator, and four of them (three of the five ideas) make it clearly worse. No page
  discount is only just above zero. That includes the two from the post-hoc look: steering
  away from cheap documents, and lowering a guess after finding nothing.
- **The team's reading and pricing look well tuned for these deals.** Its lean toward NO-GO is the right bet when
  buying a bad deal costs more than passing on a good one. That conclusion depends on the deals containing only
  downside surprises. Hidden-upside cases (still open) are the test that could change it.
- **If H1 is to be re-tested as it stands,** it needs about 740–990 fresh deals: roughly 5–6 times Plan 6's test.
- **Any real run is a separate plan** that needs the user's OK.

Limits: the template deals use a modelled Lead, and the simulator has no Challenger. Its faithfulness was checked only
for today's design, so the alternatives' numbers rest on the same rules being right for them.

Two more limits on the faithfulness check. The no-Challenger row compares against the real −Challenger runs, but uses
S4's logged opening plan, not the −Challenger runs' own (they differ on all 40), and its CI is wide
[−0.0142, +0.0083]. And the spec's "first divergent document and its cause" was reported only as a median position,
without causes.
