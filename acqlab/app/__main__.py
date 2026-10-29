"""python -m acqlab.app [--home ~/AcqLab] [--port 8765]: serve the analyst board until Ctrl-C."""
import argparse
from pathlib import Path

from acqlab.app.server import make
from acqlab.app.store import HOME, checkouts

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--home", type=Path, default=HOME)
p.add_argument("--port", type=int, default=8765)
args = p.parse_args()
home = args.home.expanduser().resolve()
if inside := [c for c in checkouts() if home.is_relative_to(c)]:  # covers every data/ folder: deals stay outside
    p.error(f"--home must be outside the repository ({inside[0]}), not {home}")
server = make(home, args.port)
print(f"Acquisition Lab: http://127.0.0.1:{server.server_address[1]}")
try:
    server.serve_forever()
except KeyboardInterrupt:
    pass
