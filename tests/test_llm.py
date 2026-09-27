import json
import subprocess
from pathlib import Path

import pytest

from acqlab import llm


def test_complete_caches_by_prompt_and_schema(tmp_path):
    calls = []

    def fake(prompt, schema):
        calls.append((prompt, schema))
        return f"echo {prompt}", 7

    assert llm.complete("hi", run=fake, cache_dir=tmp_path) == ("echo hi", 7)
    assert llm.complete("hi", run=fake, cache_dir=tmp_path) == ("echo hi", 7)
    llm.complete("hi", schema={"type": "object"}, run=fake, cache_dir=tmp_path)
    assert calls == [("hi", None), ("hi", {"type": "object"})]


def test_a_failed_call_is_never_cached(tmp_path):
    def limit(prompt, schema):
        raise llm.LLMUnavailable("usage limit reached")

    with pytest.raises(llm.LLMUnavailable):
        llm.complete("hi", run=limit, cache_dir=tmp_path)
    assert not list(tmp_path.glob("*.json"))
    assert llm.complete("hi", run=lambda p, s: ("ok", 1), cache_dir=tmp_path) == ("ok", 1)


def test_usage_tokens_sums_nested_usage_and_skips_junk():
    stream = "\n".join([json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}}),
                        "not json", json.dumps({"msg": {"usage": {"input_tokens": 1, "output_tokens": 2}}})])
    assert llm._usage_tokens(stream) == 18
    assert llm._usage_tokens("") == 0


def _fake_codex(monkeypatch, *, reply="answer", code=0, events=(), seen=None):
    def fake_run(cmd, **kwargs):
        if seen is not None:
            seen["cmd"] = cmd
            if "--output-schema" in cmd:
                seen["schema"] = json.loads(Path(cmd[cmd.index("--output-schema") + 1]).read_text())
        if reply is not None:
            Path(cmd[cmd.index("--output-last-message") + 1]).write_text(reply + "\n")
        stdout = "\n".join(json.dumps(e) for e in events)
        return subprocess.CompletedProcess(cmd, code, stdout=stdout, stderr="boom" if code else "")

    monkeypatch.setattr(llm.subprocess, "run", fake_run)
    monkeypatch.setenv("CODEX_BIN", "/opt/codex")


def test_run_codex_uses_an_empty_temp_dir_and_reads_the_last_message(monkeypatch):
    seen = {}
    _fake_codex(monkeypatch, events=[{"type": "turn.completed", "usage": {"input_tokens": 3, "output_tokens": 4}}],
                seen=seen)
    assert llm.run_codex("the prompt", {"type": "object"}) == ("answer", 7)
    cmd = seen["cmd"]
    assert cmd[:2] == ["/opt/codex", "exec"] and cmd[-1] == "the prompt"
    assert "--ephemeral" in cmd and seen["schema"] == {"type": "object"}  # ephemeral: stays out of Codex history
    workdir = Path(cmd[cmd.index("-C") + 1])
    assert "read-only" in cmd and workdir != Path.cwd() and not workdir.exists()  # temp dir, removed afterwards


def test_run_codex_raises_on_any_sign_of_failure(monkeypatch):
    for kwargs in ({"code": 1}, {"events": [{"type": "error", "message": "usage limit reached"}]},
                   {"events": [{"type": "turn.failed", "error": {"message": "rate limited"}}]}, {"reply": None},
                   {"reply": "   "}):
        _fake_codex(monkeypatch, **kwargs)
        with pytest.raises(llm.LLMUnavailable):
            llm.run_codex("the prompt")


def test_run_codex_refuses_an_answer_that_used_a_tool(monkeypatch):
    """Plan 6 spec §2: an extractor that ran a command, changed or read a file, called a tool or searched may not have
    answered from its prompt alone."""
    for item in ("command_execution", "file_change", "mcp_tool_call", "web_search"):
        _fake_codex(monkeypatch, events=[{"type": "item.started", "item": {"id": "i0", "type": item}}])
        with pytest.raises(llm.ToolUsed, match=item):
            llm.run_codex("the prompt")
    _fake_codex(monkeypatch, events=[{"type": "item.completed", "item": {"id": "i0", "type": "reasoning"}},
                                     {"type": "item.completed", "item": {"id": "i1", "type": "agent_message"}}])
    assert llm.run_codex("the prompt")[0] == "answer"


def test_codex_bin_falls_back_to_the_chatgpt_app_copy(monkeypatch):
    monkeypatch.delenv("CODEX_BIN", raising=False)
    monkeypatch.setattr(llm.shutil, "which", lambda name: None)
    assert llm.codex_bin() == llm.APP_CODEX


def test_run_codex_turns_a_hang_or_missing_binary_into_llm_unavailable(monkeypatch):
    monkeypatch.setenv("CODEX_BIN", "/opt/codex")
    for error in (subprocess.TimeoutExpired(["codex"], 600), FileNotFoundError("/opt/codex")):
        def fake_run(cmd, error=error, **kwargs):
            raise error

        monkeypatch.setattr(llm.subprocess, "run", fake_run)
        with pytest.raises(llm.LLMUnavailable):
            llm.run_codex("the prompt")


def test_a_corrupt_cache_file_is_a_miss_and_is_overwritten(tmp_path):
    llm.complete("hi", run=lambda p, s: ("ok", 1), cache_dir=tmp_path)
    (path,) = tmp_path.glob("*.json")
    path.write_text('{"text": "half-writ')  # a kill mid-write left this behind
    assert llm.complete("hi", run=lambda p, s: ("again", 2), cache_dir=tmp_path) == ("again", 2)
    assert json.loads(path.read_text()) == {"text": "again", "tokens": 2}
    assert [p.name for p in tmp_path.iterdir()] == [path.name]  # no temp files left behind
