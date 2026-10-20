"""A stand-in for `claude -p` for the analyst board: it answers with the text in $FAKE_ANSWERS/reader.txt or
pricer.txt (by system prompt), spending no quota. FAKE_ARGS, if set, gets this call's argv; FAKE_CLAUDE=limit fails."""
import json
import os
import sys
from pathlib import Path

from acqlab.app.prompts import READER

argv = sys.argv[1:]
if os.environ.get("FAKE_ARGS"):
    Path(os.environ["FAKE_ARGS"]).write_text(json.dumps({"argv": argv, "cwd": os.getcwd(), "files": os.listdir(".")}))
if os.environ.get("FAKE_CLAUDE") == "limit":
    print(json.dumps({"type": "result", "is_error": True, "result": "Claude AI usage limit reached"}))
    sys.exit(1)
name = "reader.txt" if argv[argv.index("--system-prompt") + 1] == READER else "pricer.txt"
print(json.dumps({"type": "result", "is_error": False, "result": (Path(os.environ["FAKE_ANSWERS"]) / name).read_text(),
                  "usage": {"input_tokens": 1000, "output_tokens": 100},
                  "modelUsage": {argv[argv.index("--model") + 1]: {}}}))
