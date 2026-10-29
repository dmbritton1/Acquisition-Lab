"""Local storage for the analyst board: JSON files in deal folders under ~/AcqLab."""
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

HOME = Path.home() / "AcqLab"
REPO = Path(__file__).resolve().parents[2]


def checkouts() -> list[Path]:
    """The repository's main checkout and every worktree of it (each holds a data/ folder); this checkout alone if
    git can't tell. A deal home inside any of them is refused."""
    git = lambda *a: subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True, check=True).stdout
    try:
        main = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir").strip()).parent
        trees = [Path(line[9:]) for line in git("worktree", "list", "--porcelain").splitlines() if line.startswith("worktree ")]
    except (OSError, subprocess.CalledProcessError):
        return [REPO]
    return [p.resolve() for p in [REPO, main, *trees]]


def write(path: Path, obj) -> None:
    """Atomic JSON write: a temp file in the same folder, then os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, path)


def load(path: Path, default=None):
    """The parsed JSON, or `default` if the file is missing."""
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default


def new_deal(home: Path, name: str) -> Path:
    """Create home/deals/<slug>, or <slug>-2, <slug>-3 if taken."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "deal"
    n = 1
    while True:
        folder = home / "deals" / (slug if n == 1 else f"{slug}-{n}")
        try:
            folder.mkdir(parents=True)
            return folder
        except FileExistsError:
            n += 1


def deals(home: Path) -> list[dict]:
    """Each deal.json plus its folder name as "id", newest first."""
    found = [{**load(f / "deal.json"), "id": f.name}
             for f in (home / "deals").glob("*") if (f / "deal.json").exists()]
    return sorted(found, key=lambda d: d["created"], reverse=True)
