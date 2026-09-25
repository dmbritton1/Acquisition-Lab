"""One solver run: `claude -p` on the user's Claude subscription, sandboxed (Plan 4a design §2). It starts in an
empty temp directory with every built-in tool off, no user or project settings, no skills, and one MCP server: ours.

The command is injectable (`claude=`), so tests use a fake and never spend quota."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from acqlab.agents.prompts import system_prompt, user_prompt
from acqlab.agents.server import tool_names
from acqlab.llm import LLMUnavailable

MODEL = "claude-opus-5-5"
TIMEOUT = 20 * 60  # seconds, per run
SERVER = "room"
ENV_KEEP = ("PATH", "HOME", "USER", "LOGNAME", "SHELL", "TMPDIR", "LANG", "TERM")  # allowlist: the child gets
# nothing else, so no CLAUDE*/ANTHROPIC*/MCP_* setting from whatever session launches the pilot leaks into a scored
# run (tests widen this via monkeypatch, never in production code)


class RunTimeout(LLMUnavailable):
    """The run hit the hard timeout. The pilot scores it as "no answer" and carries on."""


def claude_bin() -> str:
    return os.environ.get("CLAUDE_BIN", "claude")


def child_env() -> dict[str, str]:
    """The env the `claude -p` child gets: ENV_KEEP plus any LC_* locale variable. Nothing else."""
    return {k: v for k, v in os.environ.items() if k in ENV_KEEP or k.startswith("LC_")}


def command(claude: str, prompt: str, system: str, mcp_config: Path, tools: list[str]) -> list[str]:
    return [claude, "-p", prompt, "--output-format", "json", "--model", MODEL, "--tools", "",
            "--mcp-config", str(mcp_config), "--strict-mcp-config",
            "--allowedTools", ",".join(f"mcp__{SERVER}__{t}" for t in tools),
            "--setting-sources", "", "--disable-slash-commands", "--system-prompt", system,
            "--no-session-persistence"]


def solve(room: Path, budget: float, trace: Path, router: bool, *, claude: str | None = None,
          timeout: float = TIMEOUT, unbudgeted: bool = False) -> dict:
    """One single-agent run; the tool server writes the trace. Returns the CLI's JSON result (usage, turns, cost,
    text). Raises RunTimeout after `timeout` seconds, or LLMUnavailable on any other failure (usage limit, auth,
    crash)."""
    teaser = json.loads((room / "index.json").read_text())["teaser"]
    return run_session(room, budget, trace, user_prompt(teaser, budget), system_prompt(router, unbudgeted),
                       tool_names(router), ["--router"] if router else [], claude=claude, timeout=timeout)


def run_session(room: Path, budget: float, trace: Path, prompt: str, system: str, tools: list[str],
                server_args: list[str], *, claude: str | None = None, timeout: float = TIMEOUT) -> dict:
    """One sandboxed `claude -p` session on our tool server (started with `server_args` added). S4 runs one per
    panel role turn (acqlab.agents.panel)."""
    room, trace = room.resolve(), trace.resolve()
    with tempfile.TemporaryDirectory() as tmp:
        config = Path(tmp) / "mcp.json"
        args = ["-m", "acqlab.agents.server", "--room", str(room), "--budget", str(budget), "--trace", str(trace)]
        config.write_text(json.dumps({"mcpServers": {SERVER: {"command": sys.executable, "args": args + server_args}}}))
        cmd = command(claude or claude_bin(), prompt, system, config, tools)
        env = child_env()
        try:
            proc = subprocess.run(cmd, cwd=tmp, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                  timeout=timeout, env=env)
        except subprocess.TimeoutExpired as e:
            raise RunTimeout(f"claude -p timed out after {timeout:g}s") from e
        except OSError as e:
            raise LLMUnavailable(f"claude -p could not run: {e}") from e
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        out = None
    if proc.returncode != 0 or not isinstance(out, dict) or out.get("is_error"):
        result = isinstance(out, dict) and out.get("result")
        detail = (result if isinstance(result, str) and result else None) or proc.stderr.strip()[-500:] or "no output"
        raise LLMUnavailable(f"claude -p failed (exit {proc.returncode}): {detail}")
    out["env_keys"] = sorted(env)
    return out
