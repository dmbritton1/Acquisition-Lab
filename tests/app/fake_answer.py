"""A stand-in for `claude -p` for the analyst board: it answers with the text in $FAKE_ANSWERS/reader.txt or
pricer.txt (by system prompt), spending no quota. FAKE_ARGS, if set, gets this call's argv and stdin (the prompt); FAKE_CLAUDE=limit fails; FAKE_CLAUDE=sleep waits FAKE_SLEEP seconds first."""
import json
import os
import sys
import time
from pathlib import Path

from acqlab.app.prompts import READER

argv = sys.argv[1:]
prompt = sys.stdin.read()
if os.environ.get("FAKE_ARGS"):
    Path(os.environ["FAKE_ARGS"]).write_text(json.dumps({"argv": argv, "stdin": prompt, "cwd": os.getcwd(),
                                                         "files": os.listdir(".")}))
if os.environ.get("FAKE_CLAUDE") == "sleep":
    time.sleep(float(os.environ.get("FAKE_SLEEP", "1")))
if os.environ.get("FAKE_CLAUDE") == "limit":
    print(json.dumps({"type": "result", "is_error": True, "result": "Claude AI usage limit reached"}))
    sys.exit(1)
name = "reader.txt" if argv[argv.index("--system-prompt") + 1] == READER else "pricer.txt"
print(json.dumps({"type": "result", "is_error": False, "result": (Path(os.environ["FAKE_ANSWERS"]) / name).read_text(),
                  "usage": {"input_tokens": 1000, "output_tokens": 100},
                  "modelUsage": {argv[argv.index("--model") + 1]: {}}}))
