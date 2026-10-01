# Plan 6: the main run (H1–H6 as pre-registered)

160 fresh `r2` test deals (`data/test-r2`, fingerprint in `plan-6-test-set.json`), rules fixed in
`plan-4b-preregistration.md` and `plan-6-preregistration-addendum.md` before any test deal existed. The analysis
(`acqlab.bench.analysis`) ran once, on 2026-10-01, after the campaign logged `campaign complete`. Every number below is
from `plan-6-main-run.json`. Regret is normalised by the asking price; lower is better. Every comparison is a paired
per-deal difference with a paired bootstrap 95% CI (2,000 resamples, seed 0).

## Verdicts

| | Rule (short) | Result | Verdict |
|---|---|---|---|
| H1 | S4 ≥ 25% below S1b, CI below zero, and below S3 | 30% below S1b, below S3, but CI [−0.0100, +0.0016] includes zero | **Fails** |
| H2 | S4's gain on interaction and flip deals exceeds its gain on the rest | gap +0.0153, CI [+0.0032, +0.0293] | **Holds** |
| H3 | −Challenger's regret exceeds S4's (40 deals) | +0.0042, CI [−0.0021, +0.0147] | Fails (not shown) |
| H4 | S4 reads fewer decoy pages than S1b | +0.48 pages, CI [+0.02, +0.96]: S4 reads *more* | **Fails** |
| H5 | −engine's walk-away error ≥ 2× S4's, CI above zero | 1.54×, difference +0.0262, CI [+0.0177, +0.0353] | **Fails** (the ratio) |
| H6 | −sweep's regret exceeds S4's on deals S4's first plan missed | 0 such deals | Too few to test |

## H1: the Team against Solo

| | Mean regret |
|---|---|
| S4 (the Team) | 0.0088 |
| S3 (best of 2 Solo runs) | 0.0105 |
| S1b (Solo) | 0.0126 |

S4's mean regret is 30.3% below S1b's and below S3's, so two of the three conditions hold. The third does not: the
paired difference S4 − S1b is −0.0038 with a 95% CI of [−0.0100, +0.0016], which includes zero. S4 − S3 is −0.0017,
CI [−0.0074, +0.0034]. **H1 fails as written.**

By case type (S4 − S1b, 95% CI):

| Case type | Deals | S4 − S1b | 95% CI |
|---|---|---|---|
| interaction | 43 | −0.0174 | [−0.0333, −0.0041] |
| unresolvable | 42 | −0.0069 | [−0.0172, +0.0019] |
| flip | 12 | −0.0012 | [−0.0037, +0.0000] |
| clean | 26 | +0.0044 | [−0.0089, +0.0159] |
| decoy | 37 | +0.0088 | [+0.0020, +0.0168] |

S4 is clearly better on interaction deals and clearly worse on decoy deals. On the 79 deals where the true call
differs from the face call (decision flips, any case type), S4's regret is 0.0072 against S1b's 0.0224.

**The pessimism control** (S1b with its least confident GO calls switched to NO-GO until it says NO-GO as often as
S4): its mean regret is 0.0139, worse than plain S1b. S4 − matched S1b is −0.0051, CI [−0.0115, +0.0010]. As on the
dev batches, making Solo as cautious as the Team does not reproduce the Team's result; here the CI includes zero.

## H2: where the Team gains

S4's gain over S1b on interaction and flip deals (55) minus its gain on the rest (105) is +0.0153, CI (resampling
within each group) [+0.0032, +0.0293]. **H2 holds.**

## H3: the Challenger

On `test-000`–`test-039`, −Challenger − S4 is +0.0042, CI [−0.0021, +0.0147]. The point estimate favours the
Challenger, but the CI includes zero: **not shown.** 40 deals give this test little power (addendum: a CI that
includes zero is "not shown", not evidence against). −Challenger made 35 correct calls of 40.

## H4: decoy pages

S4 opened 1.52 decoy pages per deal against S1b's 1.04: +0.48, CI [+0.02, +0.96]. The prediction was fewer; S4 reads
more. **H4 fails.** S4 also reads more pages in all (22.5 against 19.0).

## H5: the engine

The valuer without the engine (−engine) has mean walk-away error 0.0745 against S4's 0.0483: 1.54 times as large, and
the difference (+0.0262, CI [+0.0177, +0.0353]) is clearly above zero. The pre-registered bar was at least twice as
large, so **H5 fails** on the ratio, although the engine clearly helps. 8 of 160 −engine turns never submitted and were
scored as B0's call, as the rules require.

**LLM decides** (the valuer makes the call but keeps the engine's walk-away): LLM decides − S4 is +0.0012, CI
[−0.0010, +0.0041]; no evidence that the code decision matters for regret.

## H6: the residual sweep

On the 40 ablation deals, every real trap was among the issue types in S4's first accepted plan, so the set of deals
H6 tests is empty: **too few to test** (the addendum's rule for fewer than 5). −sweep's overall regret on those 40 is
in the table below.

## Every system

Means per deal. −Challenger and −sweep ran on the first 40 deals only, so their rows are not comparable with the
160-deal rows (paired comparisons are in H3 and H6).

| System | Deals | Regret | Correct | Walk-away error | Pages | Decoy pages | Sessions | Cost | No answer |
|---|---|---|---|---|---|---|---|---|---|
| S0 (perfect reader) | 160 | 0.0000 | 100% | 0.0042 | 47.4 | 3.83 | 1 | $0.17 | 0 |
| S4 (the Team) | 160 | 0.0088 | 78.1% | 0.0483 | 22.5 | 1.52 | 11.5 | $0.53 | 0 |
| LLM decides | 160 | 0.0100 | 76.9% | 0.0483 | 22.5 | 1.52 | 1 | $0.03 | 0 |
| S3 (best of 2 Solo) | 160 | 0.0105 | 78.7% | 0.0532 | 38.3 | 2.08 | — | $0.26 | 1 |
| S1b (Solo) | 160 | 0.0126 | 76.9% | 0.0545 | 19.0 | 1.04 | 1 | $0.13 | 1 |
| −engine | 160 | 0.0134 | 73.1% | 0.0745 | 22.5 | 1.52 | 1 | $0.08 | 8 |
| S1b, pessimism-matched | 160 | 0.0139 | 73.1% | 0.0545 | 19.0 | 1.04 | 1 | $0.13 | 1 |
| −Challenger | 40 | 0.0061 | 87.5% | 0.0411 | 22.2 | 0.95 | 9.3 | $0.39 | 0 |
| −sweep | 40 | 0.0076 | 87.5% | 0.0479 | 22.3 | 0.70 | 11.5 | $0.52 | 0 |

The −engine and LLM-decides rows reuse S4's reading (pages, decoy pages); their cost is the valuer turn alone.

**Floors** (no AI): B0 0.0356 (walk-away error 0.1244), always GO 0.0411, always NO-GO 0.0507, the margin rule
0.0234. Every system beats every floor; S0 shows the deals are fully solvable from the documents.

## Conduct

- **Campaign:** 2026-09-28 10:51 to 2026-10-01 00:34 EDT, 12 usage-limit waits, no errors, no retries, no stops.
  Every run has status "ok" and no session timed out. Every call used `claude-opus-5-5` through Claude Code 2.1.280
  (pinned). Notional cost $206.80. The runs used two of the user's Claude accounts (the first 19 deals on one, the rest
  on the other); the model and version were the same throughout.
- **Unanswered runs:** S1b 1 of 320 (so S3 has 1), −engine 8 of 160; each was scored as B0's call and counted.
- **Recoverability:** 8 problems on 20 deals, all zero-amount facts in awkward template wording; understood, reported
  in `plan-6-test-set.md`, and the run went ahead by the user's decision.
- **Peeking:** the campaign logged counts only; no result was looked at until this analysis, which ran once.

## In plain terms

The Team's average loss is 30% lower than Solo's and lower than best-of-2 Solo, but on 160 deals that gap is not
large enough to rule out chance, so the headline claim (H1) fails as pre-registered. The Team's advantage is real and
concentrated where it was predicted (H2): deals where issues interact or the true call differs from the face call.
It gives some of that back on decoy deals, where it reads more of the decoy material and loses to Solo. The engine
helps the valuation (walk-away error 35% lower than without it) but not by the factor of two that H5 required; the
Challenger and the residual sweep could not be shown to matter on 40 deals.
