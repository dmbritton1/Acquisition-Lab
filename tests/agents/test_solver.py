import json
from pathlib import Path

import pytest

from acqlab.agents.knowledge import GUIDE
from acqlab.agents.prompts import ROUTER, system_prompt, user_prompt
from acqlab.agents.solver import MODEL, RunTimeout, solve
from acqlab.llm import LLMUnavailable


def _room(data):
    return data / "deals" / "dev-000" / "room"


def test_the_two_systems_prompts_differ_only_by_the_router_paragraph():
    assert ROUTER in system_prompt(True) and "rank_issues" not in system_prompt(False)
    assert system_prompt(True).replace(ROUTER, "") == system_prompt(False)
    assert GUIDE in system_prompt(False) and "search" in system_prompt(False)  # the same knowledge for every system
    assert "22 units" in user_prompt("# Teaser", 22.0)


def test_only_s0s_prompt_says_its_budget_covers_everything():
    """F1: S0 is not a competing system, so it alone gets the sentence swap; S1b and S1b + router are unaffected."""
    for router in (False, True):
        assert "You cannot read everything, so choose what to read." in system_prompt(router)
        assert "You cannot read everything, so choose what to read." not in system_prompt(router, unbudgeted=True)
        assert "Your budget covers every document, so you can read them all." in system_prompt(router, unbudgeted=True)
    assert system_prompt(False) == system_prompt(False, unbudgeted=False)
    assert system_prompt(True) == system_prompt(True, unbudgeted=False)


def test_a_run_is_sandboxed_and_returns_the_cli_result(data, tmp_path, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "ok")
    out = solve(_room(data), 20, tmp_path / "trace.jsonl", router=True, claude=fake_claude)
    assert out["usage"]["output_tokens"] == 20
    seen = json.loads((tmp_path / "args.json").read_text())
    argv = seen["argv"]
    repo_root = Path(__file__).resolve().parents[2]
    cwd = Path(seen["cwd"]).resolve()
    assert seen["files"] == ["mcp.json"]  # an empty temp dir
    assert cwd != repo_root and repo_root not in cwd.parents  # not inside the repo root
    for flag, value in (("--tools", ""), ("--model", MODEL), ("--setting-sources", ""), ("--output-format", "json")):
        assert argv[argv.index(flag) + 1] == value
    assert {"--strict-mcp-config", "--no-session-persistence", "--disable-slash-commands"} <= set(argv)
    allowed = argv[argv.index("--allowedTools") + 1].split(",")
    assert "mcp__room__rank_issues" in allowed and all(t.startswith("mcp__room__") for t in allowed)
    trace = [json.loads(line) for line in (tmp_path / "trace.jsonl").read_text().splitlines()]
    assert trace[-1]["tool"] == "submit" and "rank_issues" in {r["tool"] for r in trace}


def test_the_plain_system_is_not_offered_the_router(data, tmp_path, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "ok")
    solve(_room(data), 20, tmp_path / "trace.jsonl", router=False, claude=fake_claude)
    argv = json.loads((tmp_path / "args.json").read_text())["argv"]
    assert "rank_issues" not in argv[argv.index("--allowedTools") + 1]
    assert "rank_issues" not in {json.loads(x)["tool"] for x in (tmp_path / "trace.jsonl").read_text().splitlines()}


def test_a_usage_limit_raises_llm_unavailable(data, tmp_path, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "limit")
    with pytest.raises(LLMUnavailable, match="usage limit") as e:
        solve(_room(data), 20, tmp_path / "trace.jsonl", router=False, claude=fake_claude)
    assert not isinstance(e.value, RunTimeout)


def test_a_slow_run_raises_run_timeout(data, tmp_path, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "sleep")
    with pytest.raises(RunTimeout):
        solve(_room(data), 20, tmp_path / "trace.jsonl", router=False, claude=fake_claude, timeout=2)


def test_the_child_env_is_scrubbed_to_an_allowlist(data, tmp_path, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "ok")
    monkeypatch.setenv("CLAUDE_EFFORT", "high")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://example.invalid")
    monkeypatch.setenv("MCP_TIMEOUT", "5")
    out = solve(_room(data), 20, tmp_path / "trace.jsonl", router=False, claude=fake_claude)
    seen_env = json.loads((tmp_path / "args.json").read_text())["env"]
    assert not any(name.startswith(("CLAUDE", "ANTHROPIC", "MCP_")) for name in seen_env)
    # everything we explicitly allowlisted reached the child; the OS may still add a few of its own (e.g. macOS's
    # __CF_USER_TEXT_ENCODING), so this is a subset check, not equality
    assert set(out["env_keys"]) <= set(seen_env) and out["env_keys"] == sorted(out["env_keys"])
