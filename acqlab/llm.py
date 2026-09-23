"""Minimal LLM adapter: prompt in, (text, tokens) out, cached on disk.
ponytail: Codex CLI only, for the Plan 2 renderer and extractor. Plan 4 adds `claude -p`, the solver sandbox and an
API backend behind this same signature."""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

Runner = Callable[[str, dict | None], tuple[str, int]]
CACHE_DIR = Path("data/llm_cache")
# The ChatGPT desktop app bundles the Codex CLI without putting it on PATH.
APP_CODEX = "/Applications/ChatGPT.app/Contents/Resources/codex"
# Flags checked against `codex exec --help` (codex-cli 0.155.0-alpha.9.2). --ephemeral keeps thousands of
# generator calls out of the user's Codex session history.
CODEX_ARGS = ["exec", "--json", "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only"]
ERROR_EVENTS = {"error", "turn.failed"}  # JSONL event types that mean the call did not complete


class LLMUnavailable(RuntimeError):
    """A call failed (usage limit, auth, network). Nothing was cached, so rerunning the same command resumes."""


def codex_bin() -> str:
    return os.environ.get("CODEX_BIN") or shutil.which("codex") or APP_CODEX


def _events(jsonl: str) -> list[dict]:
    out = []
    for line in jsonl.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            out.append(event)
    return out


def _usage_tokens(jsonl: str) -> int:
    """Sum input+output tokens over every `usage` object in Codex's JSONL event stream (0 if none reported)."""
    total = 0
    stack: list = _events(jsonl)
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            usage = node.get("usage")
            if isinstance(usage, dict):
                total += int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))
            stack.extend(v for k, v in node.items() if k != "usage")
        elif isinstance(node, list):
            stack.extend(node)
    return total


def run_codex(prompt: str, schema: dict | None = None) -> tuple[str, int]:
    """One Codex call with an empty temp dir as its working directory and a sandbox that blocks writes. This does
    not stop Codex reading other paths (the repo, answer keys); real read isolation is Plan 4's job.
    Raises LLMUnavailable on any sign of failure, so a limit message is never mistaken for an answer."""
    with tempfile.TemporaryDirectory() as tmp:
        last = Path(tmp) / "last_message.txt"
        cmd = [codex_bin(), *CODEX_ARGS, "-C", tmp, "--output-last-message", str(last)]
        if schema is not None:
            (Path(tmp) / "schema.json").write_text(json.dumps(schema))
            cmd += ["--output-schema", str(Path(tmp) / "schema.json")]
        try:
            proc = subprocess.run([*cmd, prompt], capture_output=True, text=True, timeout=600)
        except (subprocess.TimeoutExpired, OSError) as e:
            raise LLMUnavailable(f"codex exec could not run: {e}") from e
        failed = [e for e in _events(proc.stdout) if e.get("type") in ERROR_EVENTS]
        text = last.read_text().strip() if last.exists() else ""
        if proc.returncode != 0 or failed or not text:
            detail = (failed and json.dumps(failed[-1])) or proc.stderr.strip()[-500:] or "empty reply"
            raise LLMUnavailable(f"codex exec failed (exit {proc.returncode}): {detail}")
        return text, _usage_tokens(proc.stdout)


def complete(prompt: str, *, schema: dict | None = None, run: Runner = run_codex,
             cache_dir: Path = CACHE_DIR) -> tuple[str, int]:
    """Cached call: the same prompt (and schema) never costs twice. Tokens are those recorded when it first ran.
    Only successful replies are cached; a failed call raises and leaves nothing behind. Writes are atomic (temp file
    then rename), and an unreadable cache file is treated as a miss."""
    key = prompt if schema is None else prompt + "\n" + json.dumps(schema, sort_keys=True)
    path = cache_dir / f"{hashlib.sha256(key.encode()).hexdigest()}.json"
    if path.exists():
        try:
            hit = json.loads(path.read_text())
            return hit["text"], hit["tokens"]
        except (json.JSONDecodeError, KeyError, TypeError):
            pass  # corrupt entry: call again and overwrite it
    text, tokens = run(prompt, schema)
    cache_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=cache_dir, suffix=".tmp", delete=False) as f:
        json.dump({"text": text, "tokens": tokens}, f)
    os.replace(f.name, path)
    return text, tokens
