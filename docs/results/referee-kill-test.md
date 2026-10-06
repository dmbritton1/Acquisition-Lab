# Referee kill test: results (exploratory)

The rules were fixed in advance in `referee-kill-test-prereg.md` (commit 980f4fb). Runs are in
`data/test-r2/runs/referee` (code `acqlab/bench/referee.py`). There were 48 real Claude sessions on `claude-opus-5-5`,
costing $5.25 in all ($0.11 per deal); all 48 answered.

The referee used Claude Code CLI 2.1.291. The team and single-Claude runs used an older CLI on the same model:
2.1.266 refused this model on 2026-10-04, so the CLI was updated with the user's OK.

## It passes the bar

On the 48 deals where the team and single Claude disagreed:

| Rule | Correct | Mean regret |
|---|---|---|
| **Referee** | **35 / 48** | **0.0084** |
| The team's call | 25 / 48 | 0.0188 |
| Single Claude's call | 23 / 48 | 0.0315 |
| Always the NO-GO side | 24 / 48 | 0.0191 |

The bar was at least 32 correct and regret below 0.0188. **Both are met.**

- **It isn't just picking a side.** It agreed with the team on 26 deals and said NO-GO on 27, so it is not following
  one analyst or the cautious call.
- **Its mistakes are balanced:** 5 false GOs and 8 false NO-GOs.
- **By case type, it is right on:**
  - interaction: 13 of 17;
  - decoy: 7 of 10;
  - clean: 7 of 8;
  - unresolvable: 7 of 12, its weakest;
  - flip: 1 of 1.

On all 160 test deals, using the referee only where the two disagree gives 84.4% correct and regret 0.0057. The team
alone gets 78.1% and 0.0088; single Claude gets 76.9% and 0.0126.

## Why this is not a result

- **It pools about 1.5 times the reading budget,** and on all 160 deals it costs both full runs plus the referee. The
  84.4% is what reconciling can do with extra evidence, not what a same-budget team does.
- **These deals were already examined, and each got one run.**

## What it earns

The kill test does not stop the track. Designs C and A go to a same-budget pilot on fresh deals, as agreed on
2026-10-04. That pilot gets its own spec and needs the user's OK before any run.
