"""The analyst board's local JSON API on 127.0.0.1: settings, deals, uploads, the Claude steps, typed numbers and the
recalculated board. Every answer is JSON; errors carry {"error": message}."""
import base64
import binascii
import json
import math
import re
import sys
import tempfile
import threading
import traceback
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from acqlab.app import board, steps
from acqlab.app.ingest import Unreadable, ingest
from acqlab.app.steps import Incomplete
from acqlab.app.store import deals, load, write
from acqlab.app.verify import FIELDS
from acqlab.engine import Financing, Policy
from acqlab.llm import LLMUnavailable

PAGE = Path(__file__).parent / "static" / "index.html"
ID = re.compile(r"[a-z0-9-]+")
EXTENSIONS = (".pdf", ".md", ".txt")
STEPS = ("read", "price", "second")


class NotFound(Exception):
    """An unknown deal, step or path."""


class Refused(Exception):
    """A request turned away with this status: a foreign page (403), a non-JSON POST (415) or a busy deal (409)."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


LOCKS: dict[str, threading.Lock] = {}  # one per deal, made on first use
LOCKS_GUARD = threading.Lock()
SETTINGS_LOCK = threading.Lock()


@contextmanager
def _busy(deal: Path):
    """Hold this deal's lock for a mutating request, or refuse with 409 at once if another one has it (so a double
    click never bills a step twice and two writes never lose each other's update)."""
    with LOCKS_GUARD:
        lock = LOCKS.setdefault(deal.name, threading.Lock())
    if not lock.acquire(blocking=False):
        raise Refused(409, "a step is running for this deal; try again when it finishes")
    try:
        yield
    finally:
        lock.release()


def _float(text: str) -> float:
    """A JSON number as a float; a number too big to be finite is an error, not an infinity."""
    x = float(text)
    if not math.isfinite(x):
        raise ValueError(f"number too large: {text[:20]}")
    return x


def _reject(name: str):
    raise ValueError(f"{name} is not allowed")


def _obj(x, what: str = "the request") -> dict:
    """x if it is a JSON object, else a ValueError."""
    if not isinstance(x, dict):
        raise ValueError(f"{what} must be a JSON object")
    return x


def _num(x) -> bool:
    """A finite number (not a bool)."""
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _upload(tmp: Path, key: str, f) -> Path:
    """Save one {"filename", "base64"} upload into tmp and return its path."""
    f = _obj(f, key)
    name, data = f.get("filename"), f.get("base64")
    suffix = Path(name).suffix.lower() if isinstance(name, str) else ""  # ".pdf" alone has no suffix
    if suffix not in EXTENSIONS:
        raise ValueError(f"{key}: the file must be a .pdf, .md or .txt")
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, TypeError, ValueError) as e:
        raise ValueError(f"{key}: the file is not valid base64") from e
    path = tmp / (key + suffix)
    path.write_bytes(raw)
    return path


class Handler(BaseHTTPRequestHandler):
    """Routes by splitting the path; `home` and `claude` are set on a subclass by make()."""
    home: Path
    claude: str | None

    def log_message(self, *args):
        """No per-request access log."""

    def do_GET(self):
        self._serve("GET")

    def do_POST(self):
        self._serve("POST")

    def _send(self, status: int, body: bytes, ctype: str):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _guard(self, method: str):
        """Refuse a request from another web page: a Host that is not this server's (DNS rebinding), or a POST that
        is not JSON (a cross-origin page can only send other types without a preflight, which is never answered)."""
        port = self.server.server_address[1]
        if self.headers.get("Host") not in (f"127.0.0.1:{port}", f"localhost:{port}"):
            raise Refused(403, "wrong Host header")
        if method == "POST" and self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            raise Refused(415, "POST bodies must be application/json")

    def _serve(self, method: str):
        ctype = "application/json"
        try:
            self._guard(method)
            parts = [unquote(p) for p in urlsplit(self.path).path.strip("/").split("/")]
            if method == "GET" and parts == [""]:
                status, out, ctype = 200, PAGE.read_bytes(), "text/html; charset=utf-8"
            else:
                status, out = 200, self._route(method, parts)
        except Refused as e:
            status, out = e.status, {"error": str(e)}
        except NotFound:
            status, out = 404, {"error": "not found"}
        except (ValueError, Incomplete, Unreadable) as e:
            status, out = 400, {"error": str(e)}
        except LLMUnavailable as e:
            status, out = 502, {"error": "failed, try again: " + str(e)}
        except Exception:
            traceback.print_exc(file=sys.stderr)
            status, out = 500, {"error": "internal error"}
        try:
            body = out if isinstance(out, bytes) else json.dumps(out, allow_nan=False).encode()
        except Exception:
            traceback.print_exc(file=sys.stderr)
            status, ctype, body = 500, "application/json", b'{"error": "internal error"}'
        try:
            self._send(status, body, ctype)
        except OSError:  # the page went away
            pass

    def _body(self) -> dict:
        """The request body as a JSON object; no NaN, no infinities, whole numbers read as floats."""
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        return _obj(json.loads(raw, parse_int=_float, parse_float=_float, parse_constant=_reject))

    def _deal(self, id_: str) -> Path:
        deal = self.home / "deals" / id_
        if not (ID.fullmatch(id_) and (deal / "deal.json").exists()):
            raise NotFound
        return deal

    def _route(self, method: str, parts: list[str]):
        if parts[0] != "api" or len(parts) < 2:
            raise NotFound
        match method, parts[1:]:
            case "GET", ["settings"]:
                return load(self.home / "settings.json", {})
            case "POST", ["settings"]:
                return self._settings()
            case "GET", ["deals"]:
                return deals(self.home)
            case "POST", ["deals"]:
                return self._create()
            case "GET", ["deals", id_]:
                return self._detail(self._deal(id_))
            case "GET", ["deals", id_, "estimate", step] if step in STEPS:
                return {"dollars": steps.estimate(self._deal(id_), step)}
            case "POST", ["deals", id_, "run", step] if step in STEPS:
                return self._locked(self._run, id_, step)
            case "POST", ["deals", id_, "numbers"]:
                return self._locked(self._numbers, id_)
            case "POST", ["deals", id_, "board"]:
                return self._locked(self._board, id_)
        raise NotFound

    def _locked(self, fn, id_: str, *args):
        """Run a mutating deal route under the deal's lock."""
        deal = self._deal(id_)
        with _busy(deal):
            return fn(deal, *args)

    def _settings(self) -> dict:
        """Validate the sections given, merge them over the saved ones, save."""
        body = self._body()
        with SETTINGS_LOCK:
            saved = load(self.home / "settings.json", {})
            for group, cls in (("financing", Financing), ("policy", Policy)):
                if group in body:
                    saved[group] = cls(**_obj(body[group], group)).model_dump()
            write(self.home / "settings.json", saved)
        return saved

    def _create(self) -> dict:
        body = self._body()
        name, price = body.get("name"), body.get("price")
        if not (isinstance(name, str) and name.strip()):
            raise ValueError("the deal needs a name")
        if not (_num(price) and price > 0):
            raise ValueError("the price must be a number above 0")
        with tempfile.TemporaryDirectory() as tmp:
            files = {k: _upload(Path(tmp), k, body.get(k)) for k in ("teaser", "cim")}
            deal = ingest(self.home, name.strip(), float(price), files)
        return {"id": deal.name}

    def _detail(self, deal: Path) -> dict:
        return {"id": deal.name, "deal": load(deal / "deal.json"),
                "docs": [load(f) for f in sorted((deal / "docs").glob("*.json"))],
                **{k: load(deal / f"{k}.json") for k in ("numbers", "worries", "board", "second_numbers", "second_worries")}}

    def _run(self, deal: Path, step: str) -> dict:
        settings = load(self.home / "settings.json", {})
        if step == "read":
            return steps.read(deal, claude=self.claude)
        if step == "price":
            return steps.price(deal, settings, claude=self.claude)
        return steps.second_look(deal, settings, claude=self.claude)

    def _numbers(self, deal: Path) -> dict:
        """Save typed numbers as the analyst's own."""
        body = self._body()
        if bad := [k for k, v in body.items() if k not in FIELDS or not _num(v)]:
            raise ValueError("not a known field or not a finite number: " + ", ".join(bad))
        saved = load(deal / "numbers.json") or {"name": load(deal / "deal.json")["name"], "industry": "",
                                                 "numbers": {}, "hints": []}
        saved["numbers"] |= {k: {"value": v, "status": "you", "quotes": [], "why": ""} for k, v in body.items()}
        write(deal / "numbers.json", saved)
        return saved

    def _board(self, deal: Path) -> dict:
        """Recompute from the overrides and save them; add the second look when it is a fresh pair."""
        overrides = _obj(self._body().get("overrides", {}), "overrides")
        overrides = {t: _obj(o, f"override {t}") for t, o in overrides.items()}
        settings = load(self.home / "settings.json", {})
        meta, info = load(deal / "numbers.json", {}), load(deal / "deal.json")
        nums = meta.get("numbers", {})
        if missing := steps._missing(nums, settings):
            raise Incomplete("fill in first: " + ", ".join(missing))
        mine = steps.values(nums)
        face = board.face(mine, settings, info["price"], meta.get("name") or info["name"], meta.get("industry") or "")
        worries, yours = board.apply((load(deal / "worries.json", {}) or {}).get("worries", {}), overrides)
        out = board.compute(face, worries, yours)
        out["worries"] = worries
        write(deal / "board.json", {"overrides": overrides})
        n2, w2 = deal / "second_numbers.json", deal / "second_worries.json"
        if n2.exists() and w2.exists() and w2.stat().st_mtime_ns >= n2.stat().st_mtime_ns:
            theirs = steps.values(load(n2).get("numbers", {}))
            out["second"] = board.compute(face, (load(w2) or {}).get("worries", {}), set()) | {
                "differences": {f: {"board": mine[f], "second": theirs.get(f)} for f in FIELDS if theirs.get(f) != mine[f]}}
        return out


def make(home: Path, port: int = 0, claude: str | None = None) -> ThreadingHTTPServer:
    """A server on the laptop only (port 0 picks a free one); not yet serving."""
    return ThreadingHTTPServer(("127.0.0.1", port), type("Bound", (Handler,), {"home": home, "claude": claude}))
