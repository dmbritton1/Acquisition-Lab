# Hidden-upside pilot, stage 1: results (exploratory)

The fixed rules are in `docs/results/upside-pilot-prereg.md`, and the spec is
`docs/superpowers/specs/2026-10-08-upside-pilot-design.md`. The numbers are in `upside-pilot.json`, written once by
`scripts/upside_pilot.py`.

**Reading under the fixed rule: "team leans on caution"** (not provisional; every run answered).
- On the 16 relief deals, the team turned down 12 good deals and single Claude turned down 7.
- The team's mean regret is higher: 0.0215 against 0.0148.
- Paired difference: +0.0067, with a 95% range of [−0.0031, +0.0168]. 16 deals give a direction, not proof.

## Setup

- **Deals:** 40 `r2u` deals in `data/pilot-r2u`: 16 relief, 8 confirmed and 16 ordinary.
- **Systems:** `s1b` (single Claude) and `s4` (the frozen team), one run each per deal.
- **Model and CLI:** every row is on `claude-opus-5-5`, and the CLI is 2.1.291.
- **Dates:** the runs took place on 2026-10-08, with one usage-limit pause and one sign-in renewal before the first run.
- **Run health:** no timeouts, no unanswered runs and no missing traces.
- **Recorded cost:** $26.03 in all, of which $5.39 for single Claude and $20.64 for the team.

## The main measure: relief deals (16)

A relief deal looks bad at first and is in fact a good deal.

| System | Wrong "pass" calls | Correct | Regret | Opened the settling document | Pages | Cost / deal |
|---|---|---|---|---|---|---|
| Single Claude | 7 | 56% | 0.0148 | 13 of 16 (81%) | 19.6 | $0.14 |
| Team | **12** | **25%** | 0.0215 | 7 of 16 (44%) | 22.9 | $0.52 |
| Single Claude, made as cautious as the team (caution control) | 14 | 12.5% | 0.0249 | (as single Claude) | | |

**Why each system missed** (spec §2.3, item 5):

| System | Never opened the settling document | Opened it and still passed |
|---|---|---|
| Single Claude (7 misses) | 2 | 5 |
| Team (12 misses) | **9** | 3 |

- **The team's misses are mainly a reading problem.**
  - On 9 of its 12 misses it never opened the document that settles the flagged worry.
  - On 5 of those 9 the evidence sat in the board minutes, and on 3 in the audited accounts.
  - When the team did open the settling document (7 deals), it got 4 right.
- **Single Claude's misses are mainly a weighing problem.**
  - It opened the settling document on 13 of 16 deals.
  - Of the 7 deals it missed, it had read the good news on 5 and still passed.

**Did both systems take the warning?** Yes.
- The team's Deal Lead started every flagged deal with a 0.5–0.85 chance on the flagged issue (median 0.7).
- Single Claude noted the flagged issue on all 24 flagged deals.
- So "warning ignored" does not apply: both systems priced the warning, and the result is about what they did next.

**The caution control:**
- Single Claude made exactly as cautious overall as the team (same number of NO-GOs across all 40 deals) does *worse* on relief deals than the team: 14 misses against 12.
- So, at the same overall caution, the team is not worse at picking which deals to turn down.
- Its extra relief misses come from how often it says NO-GO overall: 29 of 40 calls against single Claude's 22
  (wrong NO-GOs: 15 against 9).

## Other measures

| Group | System | Regret | Correct | False GO / NO-GO |
|---|---|---|---|---|
| Confirmed (8) | Single Claude | 0.0000 | 100% | 0 / 0 |
| Confirmed (8) | Team | 0.0000 | 100% | 0 / 0 |
| Ordinary (16) | Single Claude | 0.0064 | 81% | 1 / 2 |
| Ordinary (16) | Team | 0.0122 | 81% | 0 / 3 |
| All 40 | Single Claude | **0.0084** | **75%** | 1 / 9 |
| All 40 | Team | 0.0135 | 62.5% | 0 / 15 |

- **Confirmed deals:** both systems correctly passed on all 8.
- **Ordinary deals by type:**
  - The team was better on interaction deals: 3 of 3 right against 2 of 3.
  - The team was worse on unresolvable deals: 4 of 5 right against 5 of 5.
  - Both missed the 2 clean deals.
- **Cost and effort:** the team cost about 4 times as much ($0.52 against $0.13 per deal), used 10.6 sessions against 1, and read 22.3 pages against 18.3.

## What this means

1. **The team's edge in earlier tests was partly built in by the deals.**
   - In every earlier test, every surprise was bad news.
   - When some warnings turn out to be smaller than feared, the team turns down most of those good deals (12 of 16).
   - Single Claude turns down fewer (7 of 16).
   - Over all 40 deals, single Claude has lower regret and gets more calls right. This matches the 40-deal recon pilot.
2. **It is not that the team judges the evidence worse.** Made equally cautious, single Claude does slightly worse on these deals. The team simply says NO-GO more often.
3. **The team's main failure is not going to look.** Most of its misses are deals where it never opened the document holding the good news, often the board minutes.
   - This fits its design: once a flagged worry is priced as a likely loss, its reading router chases the documents that could make the deal worse.
   - It does not go looking for documents that could clear it.
4. **For the debate design (next):** both failure types appear.
   - The team mostly fails at *reading*, so a bull advocate needs a small reading budget to go and find the good news. Arguing over documents already read would not be enough.
   - Single Claude mostly fails at *weighing*, so a two-sided debate over what it already read could help there.

## Limits

- **Small sample:** 16 relief deals and one run each. The paired range includes zero.
- **Settling-document placement:**
  - On flagged deals the CIM's standard sentence denies the disclosed issue, for both systems and both deal types.
  - The settling document is often the board minutes, which are not in the shared reading guide. That placement may drive part of the "never looked" count.
- **The deals:**
  - Flagged deals are a particular kind of deal: the flagged issue decides the call at 25–40% of its range.
  - The 2:1 relief-to-confirmed ratio is chosen, not a real-world base rate.
  - Template prose only.
  - Add-backs are never flagged (final review).
- **Stage 2 not yet tested:** the worries here only turn out *smaller*, and stage 2 ("genuine extra value") is still to come.
