import json
import subprocess
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from acqlab.bench import campaign, testset
from acqlab.llm import LLMUnavailable

NY = ZoneInfo("America/New_York")


def _at(day, hour, minute):
    return datetime(2026, 9, day, hour, minute, tzinfo=NY)


@pytest.mark.parametrize("message, now, expected", [
    ("You've hit your session limit · resets 4:20pm (America/New_York)", _at(26, 14, 6), _at(26, 16, 25)),
    ("claude -p failed (exit 1): You've hit your session limit · resets 9:20pm (America/New_York)", _at(26, 22, 0),
     _at(26, 22, 30)),  # 40 minutes past: not reset yet, wait the unreadable-time default instead of a day
    ("resets 12:05am (America/New_York)", _at(26, 23, 50), _at(27, 0, 10)),
    ("resets 9pm (Europe/London)", _at(26, 14, 0), datetime(2026, 9, 26, 21, 5, tzinfo=ZoneInfo("Europe/London"))),
    ("Claude AI usage limit reached", _at(26, 14, 0), None),
    ("resets 4:20pm (America/New_York)", _at(26, 23, 0), _at(27, 16, 25)),  # 6h40m past: still rolls to tomorrow
])
def test_the_resume_time_is_five_minutes_after_the_next_reset_the_message_names(message, now, expected):
    assert campaign.resume_at(message, now) == expected


def test_a_reset_with_no_zone_is_local_time():
    now = datetime(2026, 9, 26, 14, 0).astimezone()
    assert campaign.resume_at("resets 4am", now) == now.replace(hour=4, minute=5) + timedelta(days=1)


class Clock:
    def __init__(self, start):
        self.t, self.slept = start, []

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.t += timedelta(seconds=seconds)


def _run(tmp_path, steps, clock):
    lines = []
    code = campaign.campaign(tmp_path, tmp_path, steps=steps, check=lambda data, repo: None, now=clock.now,
                             sleep=clock.sleep, log=lines.append)
    return code, lines


def test_a_usage_limit_is_waited_out_and_the_phase_resumes(tmp_path):
    clock, calls = Clock(_at(26, 14, 6)), []

    def h1():
        calls.append("h1")
        print("s4 test-000 r0: regret 0.123")  # a run's own line: never reaches the log
        if len(calls) == 1:
            raise LLMUnavailable("claude -p failed (exit 1): You've hit your session limit · resets 4:20pm "
                                 "(America/New_York)")

    code, lines = _run(tmp_path, [("h1", h1), ("s0", lambda: calls.append("s0"))], clock)
    assert code == 0 and calls == ["h1", "h1", "s0"]
    assert sum(clock.slept) == (_at(26, 16, 25) - _at(26, 14, 6)).seconds and all(s <= 60 for s in clock.slept)
    assert any("waiting until 2026-09-26 16:25" in x for x in lines) and lines[-1] == "campaign complete"
    assert any("You've hit your session limit" in x for x in lines)  # the message, not just "waiting until"
    assert not any("regret" in x for x in lines)


def test_a_limit_with_no_readable_time_waits_thirty_minutes(tmp_path):
    clock, calls = Clock(_at(26, 14, 0)), []

    def h1():
        calls.append(1)
        if len(calls) == 1:
            raise LLMUnavailable("Claude AI usage limit reached")

    code, lines = _run(tmp_path, [("h1", h1)], clock)
    assert code == 0 and sum(clock.slept) == 30 * 60 and all(s <= 60 for s in clock.slept)


def test_a_per_deal_limit_message_is_not_a_usage_limit_and_gets_the_retry_path(tmp_path):
    clock, calls = Clock(_at(26, 14, 0)), []

    def h1():
        calls.append("h1")
        raise LLMUnavailable("input length and max_tokens exceed context limit")

    code, lines = _run(tmp_path, [("h1", h1), ("s0", lambda: calls.append("s0"))], clock)
    assert code == 1 and calls == ["h1", "h1"] and sum(clock.slept) == 600
    assert not any("usage limit" in x for x in lines)


def test_any_other_error_gets_one_retry_then_the_campaign_stops(tmp_path):
    clock, calls = Clock(_at(26, 14, 0)), []

    def h1():
        calls.append("h1")
        raise LLMUnavailable("claude -p failed (exit 1): invalid API key")

    code, lines = _run(tmp_path, [("h1", h1), ("s0", lambda: calls.append("s0"))], clock)
    assert code == 1 and calls == ["h1", "h1"] and sum(clock.slept) == 600
    assert "stopped in phase h1: LLMUnavailable: claude -p failed (exit 1): invalid API key" in lines[-1]


def test_a_crash_is_retried_once_too_and_a_failed_check_stops_before_any_run(tmp_path):
    clock = Clock(_at(26, 14, 0))

    def boom():
        raise RuntimeError("s4_noengine/test-003: S4's run is missing, so there is nothing to replay")

    code, _ = _run(tmp_path, [("ablations", boom)], clock)
    assert code == 1 and sum(clock.slept) == 600
    lines = []
    code = campaign.campaign(tmp_path, tmp_path, steps=[("h1", lambda: pytest.fail("ran"))],
                             check=lambda data, repo: "the test set does not match its committed fingerprint",
                             log=lines.append)
    assert code == 1 and lines == ["stopped before phase h1: the test set does not match its committed fingerprint"]


def _repo(tmp_path):
    """A git repo with S4's frozen files tagged and a data dir whose fingerprint is committed."""
    repo, data = tmp_path / "repo", tmp_path / "data"
    (repo / "acqlab" / "agents").mkdir(parents=True)
    (repo / "acqlab" / "agents" / "panel.py").write_text("S4 = 1\n")
    (data / "truth").mkdir(parents=True)
    (data / "truth" / "test-000.json").write_text('{"truth": {"seed": 3510000}}')
    (repo / campaign.EXPECTED).parent.mkdir(parents=True)
    (repo / campaign.EXPECTED).write_text(json.dumps(testset.fingerprint(data)))
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t"]
    for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "frozen"], ["tag", campaign.FROZEN_TAG]):
        subprocess.run(git + cmd, check=True)
    return repo, data


def test_the_preflight_refuses_an_edited_or_added_s4_file_and_a_changed_test_set(tmp_path):
    repo, data = _repo(tmp_path)
    assert campaign.preflight(data, repo) is None
    (repo / "acqlab" / "agents" / "panel.py").write_text("S4 = 2\n")
    assert "differ from s4-frozen-plan5" in campaign.preflight(data, repo)
    (repo / "acqlab" / "agents" / "panel.py").write_text("S4 = 1\n")
    (repo / "acqlab" / "agents" / "new.py").write_text("")
    assert "new.py" in campaign.preflight(data, repo)
    (repo / "acqlab" / "agents" / "new.py").unlink()
    (data / "truth" / "test-000.json").write_text('{"truth": {"seed": 3510001}}')
    assert campaign.preflight(data, repo) == "the test set does not match its committed fingerprint"


def test_progress_counts_each_system_s_finished_test_runs(tmp_path):
    for rel in ("s1b/test-000.json", "s1b/test-000.r1.json", "s1b/test-001.json", "s4/test-000.json",
                "s4/test-000.trace.jsonl", "s1b/dev-000.json"):
        (tmp_path / "runs" / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "runs" / rel).write_text("{}")
    assert campaign.progress(tmp_path).startswith("s1b 2/160, s4 1/160, s1b rep 1 1/160, s4_nochal 0/40")
    assert not campaign.complete(tmp_path)


def test_the_cli_refuses_without_the_flag_and_reports_status(tmp_path, capsys):
    assert campaign.main(["--data", str(tmp_path)]) == 3
    (tmp_path / "campaign.log").write_text("2026-09-27 10:00:00 EDT phase h1: running\n")
    assert campaign.main(["--data", str(tmp_path), "--status"]) == 0
    out = capsys.readouterr().out
    assert "not running; s1b 0/160" in out and "phase h1: running" in out
    assert campaign.main(["--data", str(tmp_path), "--stop"]) == 0 and "no campaign" in capsys.readouterr().out


def test_the_cli_refuses_without_the_pinned_claude(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("CLAUDE_BIN", raising=False)
    assert campaign.main(["--data", str(tmp_path), "--confirm-claude"]) == 3
    assert not (tmp_path / "campaign.pid").exists()
    wrong_version = tmp_path / "claude_wrong"
    wrong_version.write_text('#!/bin/sh\necho "2.1.281 (Claude Code)"\n')
    wrong_version.chmod(0o755)
    monkeypatch.setenv("CLAUDE_BIN", str(wrong_version))
    assert campaign.main(["--data", str(tmp_path), "--confirm-claude"]) == 3
    assert not (tmp_path / "campaign.pid").exists()
