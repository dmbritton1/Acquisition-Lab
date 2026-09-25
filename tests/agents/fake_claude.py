"""A stand-in for `claude -p` in tests: it drives our tool server the way Claude would, spending no quota.
FAKE_CLAUDE picks the behaviour: ok | nosubmit | noserver | limit | sleep. FAKE_ARGS, if set, is a file that gets
this call's argv and working directory."""
import json
import os
import subprocess
import sys
import time

mode = os.environ.get("FAKE_CLAUDE", "ok")
argv = sys.argv[1:]
if os.environ.get("FAKE_ARGS"):
    with open(os.environ["FAKE_ARGS"], "w") as f:
        json.dump({"argv": argv, "cwd": os.getcwd(), "files": sorted(os.listdir(".")), "env": sorted(os.environ)}, f)
if mode == "limit":
    print(json.dumps({"type": "result", "is_error": True, "result": "Claude AI usage limit reached"}))
    sys.exit(1)
if mode == "sleep":
    time.sleep(60)
calls = []
if mode != "noserver":
    spec = json.load(open(argv[argv.index("--mcp-config") + 1]))["mcpServers"]["room"]
    proc = subprocess.Popen([spec["command"], *spec["args"]], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    n = 0

    def rpc(method, params=None):
        global n
        n += 1
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": n, "method": method, "params": params or {}}) + "\n")
        proc.stdin.flush()
        return json.loads(proc.stdout.readline())["result"]

    def tool(tool_name, **args):
        calls.append(tool_name)
        reply = rpc("tools/call", {"name": tool_name, "arguments": args})
        text = reply["content"][0]["text"]
        return text if tool_name == "open_document" or reply["isError"] else json.loads(text)

    rpc("initialize", {"protocolVersion": "2025-06-18"})
    names = [t["name"] for t in rpc("tools/list")["tools"]]
    docs = tool("list_documents")
    if mode == "ok":
        tool("note_issue", name="add-back", type="addback", chance=0.5, low=0, high=5, docs=["qoe"])
        tool("open_document", doc_id=docs[-1]["id"])  # a short filler document
        face = tool("evaluate", adjustments={})
        if "rank_issues" in names:
            tool("rank_issues")
        tool("submit", go=not face["go"], walk_away=face["walk_away"] - 1, reason="fake")
    proc.stdin.close()
    proc.wait()
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "done", "num_turns": len(calls),
                  "duration_ms": 1234, "total_cost_usd": 0.5,
                  "usage": {"input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": 50,
                            "cache_creation_input_tokens": 10}}))
