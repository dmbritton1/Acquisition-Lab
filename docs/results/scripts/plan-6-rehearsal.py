"""The Plan 6 rehearsal, step 1 (spec §6): the whole campaign and the analysis on 3 throwaway test-split deals with
the fake claude from the tests. No Claude or Codex calls, no quota.

  uv run python docs/results/scripts/plan-6-rehearsal.py <empty scratch dir>

The deals use seed 3,800,000 (test seeds 3,810,000-3,810,002), clear of the real test set's 3,510,000-3,510,159."""
import json
import os
import sys
from pathlib import Path

from acqlab.bench import analysis, campaign, pilot, testset
from acqlab.generator import batch

out = Path(sys.argv[1]).resolve()
data, repo = out / "data", Path(".").resolve()
assert testset.clashes(3_800_000, 3, {3_510_000 + i for i in range(160)}) == []
assert batch.run(data, {"dev": 0, "test": 3, "hand": 0, "showcase": 0}, seed=3_800_000, mc=20) == []
expected = out / "fingerprint.json"
expected.write_text(json.dumps(testset.fingerprint(data)))

fake = out / "claude"  # the tests' fake claude; the solver's env allowlist drops FAKE_*, so it runs in "ok" mode
fake.write_text(f"#!{sys.executable}\nimport runpy\nrunpy.run_path({str(repo / 'tests/agents/fake_claude.py')!r}, "
                "run_name='__main__')\n")
fake.chmod(0o755)
os.environ["CLAUDE_BIN"] = str(fake)

campaign.N_TEST, campaign.N_ABLATION = 3, 2
campaign.EXPECTED_RUNS = [(s, r, 3 if n == 160 else 2) for s, r, n in campaign.EXPECTED_RUNS]
code = campaign.campaign(data, repo, check=lambda d, r: campaign.preflight(d, r, expected))
print("campaign exit", code, "|", campaign.progress(data))
print((data / "campaign.log").read_text())
assert code == 0 and campaign.complete(data)
assert "regret" not in (data / "campaign.log").read_text()

by, real, first_plan, rows = analysis.load(data)
result = analysis.analyse(by, real, first_plan) | {"systems": pilot.summarize(rows, s3_n=2)}
print({h: result[h]["holds"] for h in ("H1", "H2", "H3", "H4", "H5", "H6")})
print("systems:", sorted(result["systems"]["systems"]))
