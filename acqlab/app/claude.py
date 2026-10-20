"""One tool-less `claude -p` call that answers in JSON (the same sandbox as the solver: an empty folder, no tools, no
settings, a scrubbed env)."""
import json
import subprocess
import tempfile

from acqlab.agents.solver import TIMEOUT, RunTimeout, child_env, claude_bin
from acqlab.llm import LLMUnavailable


def ask(prompt: str, system: str, model: str, *, claude: str | None = None, timeout: float = TIMEOUT) -> tuple[dict, dict]:
    """The JSON object in Claude's answer (from its first { to its last }) and the CLI's result. Raises RunTimeout
    after `timeout` seconds, or LLMUnavailable on a failed run or an answer that is not JSON."""
    cmd = [claude or claude_bin(), "-p", prompt, "--output-format", "json", "--model", model, "--tools", "",
           "--setting-sources", "", "--disable-slash-commands", "--system-prompt", system, "--no-session-persistence"]
    with tempfile.TemporaryDirectory() as tmp:
        try:
            proc = subprocess.run(cmd, cwd=tmp, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                  timeout=timeout, env=child_env())
        except subprocess.TimeoutExpired as e:
            raise RunTimeout(f"claude -p timed out after {timeout:g}s") from e
        except OSError as e:
            raise LLMUnavailable(f"claude -p could not run: {e}") from e
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        out = None
    result = out.get("result") if isinstance(out, dict) else None
    text = result if isinstance(result, str) else ""
    if proc.returncode != 0 or not isinstance(out, dict) or out.get("is_error"):
        raise LLMUnavailable(f"claude -p failed (exit {proc.returncode}): "
                             f"{text[-500:] or proc.stderr.strip()[-500:] or 'no output'}")
    try:
        return json.loads(text[text.index("{"):text.rindex("}") + 1]), out
    except ValueError as e:  # no braces, or JSONDecodeError (a ValueError)
        raise LLMUnavailable(f"claude's answer was not JSON: {text[-500:] or 'no output'}") from e
