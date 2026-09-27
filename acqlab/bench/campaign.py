"""The Plan 6 main run as one resumable campaign (spec §4): three phases in a fixed order, each checked against the
frozen S4 and the committed test-set fingerprint first; usage limits are waited out; the log shows progress counts,
never results.

  export CLAUDE_BIN="$PWD/data/claude-2.1.280.app/Contents/MacOS/claude"
  nohup caffeinate -i uv run python -m acqlab.bench.campaign --data data/test-r2 --confirm-claude \\
    > data/test-r2/campaign.out 2>&1 &
  uv run python -m acqlab.bench.campaign --data data/test-r2 --status
  uv run python -m acqlab.bench.campaign --data data/test-r2 --stop

Exit codes: 0 every phase done; 1 stopped (a failed check, or an error that survived one retry; see the log); 3
refused (no --confirm-claude, missing or wrong CLAUDE_BIN, or already running)."""
import argparse
import contextlib
import io
import json
import os
import re
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from acqlab.bench import pilot, testset, valuer
from acqlab.llm import LLMUnavailable

N_TEST, N_ABLATION = 160, 40
FROZEN_TAG, FROZEN = "s4-frozen-plan5", ("acqlab/agents", "acqlab/routers")
EXPECTED = Path("docs/results/plan-6-test-set.json")  # the committed fingerprint, relative to the repo
CLAUDE_VERSION = "2.1.280"  # spec §4: every S1b and S4 run so far used it
AFTER_RESET = timedelta(minutes=5)
UNREADABLE_WAIT = timedelta(minutes=30)  # a usage limit whose message names no time
RETRY_WAIT = timedelta(minutes=10)  # any other error: one retry, then stop
RESET = re.compile(r"resets\s+(\d{1,2})(?::(\d{2}))?\s*([ap]m)\b(?:\s*\(([^)]+)\))?", re.I)
LIMIT = re.compile(r"usage limit|hit your .*limit|limit reached", re.I)  # a real usage limit, not a per-deal error
# (system, rep, deals): the runs the campaign owes, for progress and completeness
EXPECTED_RUNS = [("s1b", 0, N_TEST), ("s4", 0, N_TEST), ("s1b", 1, N_TEST), ("s4_nochal", 0, N_ABLATION),
                 ("s4_nosweep", 0, N_ABLATION), ("s4_noengine", 0, N_TEST), ("s4_llmdecides", 0, N_TEST),
                 ("s0", 0, N_TEST)]


def phases(data: Path) -> list[tuple[str, Callable[[], object]]]:
    """(name, step) in the spec's order; every step skips finished runs, so a restart resumes."""
    return [
        ("h1", lambda: (pilot.run(data, N_TEST, ["s1b", "s4"], split="test"),
                        pilot.run(data, N_TEST, ["s1b"], reps=2, split="test"))),  # S3's second S1b run
        ("ablations", lambda: (pilot.run(data, N_ABLATION, ["s4_nochal", "s4_nosweep"], split="test"),
                               pilot.run_replays(data, N_TEST, list(valuer.MODES), split="test"))),
        ("s0", lambda: pilot.run(data, N_TEST, ["s0"], split="test")),
    ]


def counts(data: Path) -> dict[tuple[str, int], int]:
    """Finished runs per (system, rep), test split only."""
    out = {}
    for system, rep, _ in EXPECTED_RUNS:
        runs = (data / "runs" / system).glob("test-*.json" if rep == 0 else f"test-*.r{rep}.json")
        out[(system, rep)] = sum(rep > 0 or p.name.count(".") == 1 for p in runs)  # rep 0: not test-000.r1.json
    return out


def progress(data: Path) -> str:
    done = counts(data)
    return ", ".join(f"{s}{f' rep {r}' if r else ''} {done[(s, r)]}/{n}" for s, r, n in EXPECTED_RUNS)


def complete(data: Path) -> bool:
    done = counts(data)
    return all(done[(s, r)] >= n for s, r, n in EXPECTED_RUNS)


def resume_at(message: str, now: datetime) -> datetime | None:
    """When to resume after a usage-limit message: AFTER_RESET past the next time it names ("resets 9:20pm
    (America/New_York)"; no zone means local time), or None if it names no time."""
    m = RESET.search(message)
    if not m:
        return None
    hour, minute = int(m[1]) % 12 + (12 if m[3].lower() == "pm" else 0), int(m[2] or 0)
    try:
        tz = ZoneInfo(m[4]) if m[4] else now.astimezone().tzinfo
    except (ZoneInfoNotFoundError, ValueError):
        tz = now.astimezone().tzinfo
    local = now.astimezone(tz)
    at = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if at <= local:
        if local - at < timedelta(hours=6):  # a reset time this recent hasn't actually reset yet
            return local + UNREADABLE_WAIT
        at += timedelta(days=1)
    return at + AFTER_RESET


def preflight(data: Path, repo: Path, expected: Path = EXPECTED) -> str | None:
    """Why the campaign must not run now, or None: S4's files must match the frozen tag (no edits, no new files),
    and the test set must match its committed fingerprint."""
    diff = subprocess.run(["git", "-C", str(repo), "diff", "--quiet", FROZEN_TAG, "--", *FROZEN],
                          capture_output=True, text=True)
    new = subprocess.run(["git", "-C", str(repo), "ls-files", "--others", "--exclude-standard", "--", *FROZEN],
                         capture_output=True, text=True)
    if diff.returncode != 0 or new.returncode != 0 or new.stdout.strip():
        return f"S4's files differ from {FROZEN_TAG} ({(diff.stderr + new.stdout).strip()[:300] or 'edited'})"
    if testset.fingerprint(data) != json.loads((repo / expected).read_text()):
        return "the test set does not match its committed fingerprint"
    return None


def campaign(data: Path, repo: Path, *, steps: list | None = None, check: Callable = preflight,
             now: Callable[[], datetime] = lambda: datetime.now().astimezone(), sleep: Callable = time.sleep,
             log: Callable[[str], None] | None = None) -> int:
    """Run every phase to the end. A usage limit is waited out; any other error gets one retry after RETRY_WAIT
    (again after progress resumes), then the campaign stops. Runs' own output (it carries regret) is never logged."""
    log = log or logger(data)
    for name, step in (phases(data) if steps is None else steps):
        retried, at_error = False, None
        while True:
            problem = check(data, repo)
            if problem:
                log(f"stopped before phase {name}: {problem}")
                return 1
            log(f"phase {name}: running ({progress(data)})")
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    step()
                break
            except Exception as e:  # every failure is either waited out, retried once or reported
                text = f"{type(e).__name__}: {e}"
                wake = resume_at(str(e), now()) if isinstance(e, LLMUnavailable) else None
                if isinstance(e, LLMUnavailable) and (wake or LIMIT.search(str(e))):
                    wake = wake or now() + UNREADABLE_WAIT
                    log(f"usage limit in phase {name} ({progress(data)}): {text[:200]}; "
                        f"waiting until {wake:%Y-%m-%d %H:%M %Z}")
                else:
                    if progress(data) != at_error:  # progress since the last error: it gets its own retry
                        retried = False
                    if retried:
                        log(f"stopped in phase {name}: {text}")
                        return 1
                    retried, at_error, wake = True, progress(data), now() + RETRY_WAIT
                    log(f"error in phase {name}: {text}; one retry at {wake:%Y-%m-%d %H:%M %Z}")
                while (left := (wake - now()).total_seconds()) > 0:  # macOS sleep() ignores lid-close time
                    sleep(min(left, 60))
        log(f"phase {name}: done ({progress(data)})")
    log("campaign complete")
    return 0


def logger(data: Path) -> Callable[[str], None]:
    def log(line: str) -> None:
        with (data / "campaign.log").open("a") as f:
            f.write(f"{datetime.now().astimezone():%Y-%m-%d %H:%M:%S %Z} {line}\n")
    return log


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def _pinned() -> str | None:
    """Why CLAUDE_BIN is not properly pinned, or None if it is."""
    claude_bin = os.environ.get("CLAUDE_BIN")
    if not claude_bin:
        return "CLAUDE_BIN environment variable is not set"
    try:
        result = subprocess.run([claude_bin, "--version"], capture_output=True, text=True, timeout=30)
        if not result.stdout.startswith(CLAUDE_VERSION):
            return f"CLAUDE_BIN points to {result.stdout.strip()}, not {CLAUDE_VERSION}"
    except (OSError, subprocess.TimeoutExpired):
        return f"CLAUDE_BIN={claude_bin} is not executable or timed out"
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--repo", type=Path, default=Path("."), help="the repo holding the frozen tag and the fingerprint")
    ap.add_argument("--confirm-claude", action="store_true", help="required to make real Claude calls")
    ap.add_argument("--status", action="store_true", help="progress and the log's last lines; no Claude")
    ap.add_argument("--stop", action="store_true", help="stop a running campaign (it resumes when started again)")
    args = ap.parse_args(argv)
    pid_file, log_file = args.data / "campaign.pid", args.data / "campaign.log"
    pid = int(pid_file.read_text()) if pid_file.exists() else None
    running = pid is not None and _alive(pid)
    if args.status:
        print(f"{'running (pid ' + str(pid) + ')' if running else 'not running'}; {progress(args.data)}")
        print("".join((log_file.read_text().splitlines(keepends=True) if log_file.exists() else [])[-5:]), end="")
        return 0
    if args.stop:
        if running:
            os.kill(pid, signal.SIGTERM)
            print(f"stopped the campaign (pid {pid})")
        else:
            print("no campaign is running")
        return 0
    if not args.confirm_claude:
        print("Refusing to run: this uses your Claude subscription for days. Add --confirm-claude to proceed.")
        return 3
    pinned_problem = _pinned()
    if pinned_problem:
        print(f"Refusing to run: {pinned_problem}")
        return 3
    if running:
        print(f"Refusing to run: a campaign is already running (pid {pid}).")
        return 3
    pid_file.write_text(str(os.getpid()))
    log = logger(args.data)
    signal.signal(signal.SIGTERM, lambda *_: (log("stopped by --stop"), pid_file.unlink(missing_ok=True),
                                              sys.exit(1)))
    try:
        return campaign(args.data, args.repo.resolve(), log=log)
    finally:
        pid_file.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
