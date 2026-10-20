"""The analyst board's local JSON API, called over HTTP on a thread."""
import base64
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from acqlab.agents import solver
from acqlab.app.server import make
from acqlab.app.store import load, write
from acqlab.app.verify import FIELDS
from tests.conftest import make_full

FAKE = Path(__file__).parent / "fake_answer.py"
VALUES = dict(zip(FIELDS, [200, 30, 2, 32, 0.05, 0.03, 0.10, 0.025, 0.25]))


def b64(text): return base64.b64encode(text.encode()).decode()


def full_settings():
    d = make_full()
    return {"financing": d.financing.model_dump(), "policy": d.policy.model_dump()}


@pytest.fixture
def srv(tmp_path, monkeypatch):
    """A running server on a temp home with the fake claude: (base url, home)."""
    monkeypatch.setattr(solver, "ENV_KEEP", solver.ENV_KEEP + ("FAKE_CLAUDE", "FAKE_ARGS", "FAKE_ANSWERS", "FAKE_SLEEP"))
    answers = tmp_path / "answers"
    answers.mkdir()
    (answers / "reader.txt").write_text('{"name": "Cedar Co", "industry": "tools", "numbers": {}, "worries": []}')
    monkeypatch.setenv("FAKE_ANSWERS", str(answers))
    monkeypatch.setenv("FAKE_ARGS", str(tmp_path / "args.json"))
    exe = tmp_path / "claude"
    exe.write_text(f"#!{sys.executable}\nimport runpy\nrunpy.run_path({str(FAKE)!r}, run_name='__main__')\n")
    exe.chmod(0o755)
    home = tmp_path / "home"
    server = make(home, claude=str(exe))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}", home
    server.shutdown()
    server.server_close()


def call(base, path, body=None, raw=None, headers=None):
    """(status, parsed JSON or raw bytes, content type). A body (or raw bytes) makes it a POST, sent as JSON like the
    page does."""
    data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
    head = {"Content-Type": "application/json"} | (headers or {})
    try:
        r = urllib.request.urlopen(urllib.request.Request(base + path, data=data, headers=head,
                                                          method="GET" if data is None else "POST"))
    except urllib.error.HTTPError as e:
        r = e
    ctype, out = r.headers.get("Content-Type", ""), r.read()
    return r.status, (json.loads(out) if "json" in ctype else out), ctype


def new_deal(base, name="Cedar", price=230):
    return call(base, "/api/deals", {"name": name, "price": price,
                                     "teaser": {"filename": "t.md", "base64": b64("Revenue of $200M.")},
                                     "cim": {"filename": "c.md", "base64": b64("Adjusted EBITDA is $32M after add-backs.")}})


def test_it_listens_on_the_laptop_only(srv, tmp_path):
    server = make(tmp_path / "other")
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()


def test_the_page_is_served(srv):
    status, body, ctype = call(srv[0], "/")
    assert status == 200 and ctype.startswith("text/html") and b"<title>" in body


def test_settings_round_trip_and_bad_settings_are_refused(srv):
    base, _ = srv
    assert call(base, "/api/settings", full_settings())[0] == 200
    assert call(base, "/api/settings")[1] == full_settings()
    status, body, _ = call(base, "/api/settings", {"policy": {"exit_multiple": "x"}})
    assert status == 400 and "error" in body
    assert call(base, "/api/settings", [1])[0] == 400
    assert call(base, "/api/settings", {"policy": 3})[0] == 400


def test_a_deal_is_created_from_uploaded_text_files(srv):
    base, _ = srv
    status, body, _ = new_deal(base)
    assert status == 200 and body["id"] == "cedar"
    assert [d["id"] for d in call(base, "/api/deals")[1]] == ["cedar"]
    detail = call(base, "/api/deals/cedar")[1]
    assert detail["deal"]["name"] == "Cedar" and {d["id"] for d in detail["docs"]} == {"teaser", "cim"}
    assert detail["numbers"] is None and detail["board"] is None
    assert call(base, "/api/deals/cedar/estimate/read")[1]["dollars"] > 0
    assert call(base, "/api/deals/cedar/estimate/nope")[0] == 404


def test_a_bad_price_or_unknown_deal_is_a_clear_error(srv):
    base, _ = srv
    for price in (0, -1, "x", True, 1e999):
        status, body, _ = new_deal(base, price=price)
        assert status == 400 and "error" in body, price
    assert call(base, "/api/deals/nope")[0] == 404
    assert call(base, "/api/nothing")[0] == 404
    bad = {"name": "A", "price": 5, "teaser": {"filename": "t.exe", "base64": b64("x")},
           "cim": {"filename": "c.md", "base64": b64("x" * 40)}}
    assert call(base, "/api/deals", bad)[0] == 400
    bad["teaser"] = {"filename": ".pdf", "base64": b64("x")}  # an extension with no name before it
    assert call(base, "/api/deals", bad)[0] == 400
    bad["teaser"] = {"filename": "t.md", "base64": "!!!"}
    assert call(base, "/api/deals", bad)[0] == 400
    assert call(base, "/api/deals", raw=b"{nope")[0] == 400
    assert call(base, "/api/deals", raw=b'{"price": NaN}')[0] == 400
    assert call(base, "/api/deals", [1])[0] == 400


def test_an_unknown_or_dotted_deal_id_is_not_found(srv):
    base, home = srv
    new_deal(base)
    write(home / "secret.json", {"x": 1})
    for path in ("/api/deals/..", "/api/deals/%2e%2e", "/api/deals/..%2f..", "/api/deals/CEDAR"):
        assert call(base, path)[0] == 404, path
    assert call(base, "/api/deals/cedar/run/nope", {})[0] == 404


def test_numbers_you_type_are_saved_as_yours(srv):
    base, home = srv
    new_deal(base)
    status, body, _ = call(base, "/api/deals/cedar/numbers", {"tax_rate": 0.25})
    assert status == 200
    saved = load(home / "deals" / "cedar" / "numbers.json")
    assert saved["numbers"]["tax_rate"] == {"value": 0.25, "status": "you", "quotes": [], "why": ""}
    for bad in ({"tax_rate": "abc"}, {"tax_rate": True}, {"nope": 1}, {"tax_rate": 1e999}, {"tax_rate": None}):
        assert call(base, "/api/deals/cedar/numbers", bad)[0] == 400, bad
    assert call(base, "/api/deals/cedar/numbers", raw=b'{"tax_rate": Infinity}')[0] == 400
    assert call(base, "/api/deals/cedar/numbers", raw=b'{"tax_rate": 1' + b"0" * 400 + b"}")[0] == 400


def board_setup(base, home):
    new_deal(base)
    deal = home / "deals" / "cedar"
    write(home / "settings.json", full_settings())
    write(deal / "numbers.json", {"name": "Cedar Co", "industry": "tools", "hints": [], "numbers": {
        f: {"value": v, "status": "you", "quotes": [], "why": ""} for f, v in VALUES.items()}})
    write(deal / "worries.json", {"worries": {"addback": {"chance": 0.3, "low": 1, "high": 4, "reason": "r"}}, "cost": 0})
    return deal


def test_the_board_recalculates_from_overrides(srv):
    base, home = srv
    deal = board_setup(base, home)
    status, body, _ = call(base, "/api/deals/cedar/board", {"overrides": {"addback": {"chance": 1, "high": 5}}})
    assert status == 200 and "go" in body and "ask" in body and "second" not in body
    assert load(deal / "board.json")["overrides"] == {"addback": {"chance": 1, "high": 5}}
    assert call(base, "/api/deals/cedar")[1]["board"]["overrides"]["addback"]["chance"] == 1
    for bad in ({"addback": {"chance": 2, "high": 5}}, {"addback": 3}, {"nope": {"chance": 0, "high": 0}}, [1]):
        assert call(base, "/api/deals/cedar/board", {"overrides": bad})[0] == 400, bad
    assert call(base, "/api/deals/cedar/board", [1])[0] == 400


def test_the_board_needs_complete_numbers_and_settings(srv):
    base, home = srv
    deal = board_setup(base, home)
    (home / "settings.json").unlink()
    status, body, _ = call(base, "/api/deals/cedar/board", {"overrides": {}})
    assert status == 400 and "financing.max_leverage" in body["error"]
    write(home / "settings.json", full_settings())
    call(base, "/api/deals/cedar/numbers", {"tax_rate": 0.25})
    (deal / "worries.json").unlink()
    assert call(base, "/api/deals/cedar/board", {"overrides": {}})[0] == 200  # face-value call, no worries
    nums = load(deal / "numbers.json")
    nums["numbers"]["growth"] = {"value": None, "status": "blank"}
    write(deal / "numbers.json", nums)
    status, body, _ = call(base, "/api/deals/cedar/board", {"overrides": {}})
    assert status == 400 and "growth" in body["error"]


def test_the_second_look_shows_only_as_a_fresh_pair(srv):
    base, home = srv
    deal = board_setup(base, home)
    second = {**load(deal / "numbers.json")}
    second["numbers"] = {**second["numbers"], "growth": {"value": 0.01, "status": "quoted"}}
    write(deal / "second_numbers.json", second)
    assert "second" not in call(base, "/api/deals/cedar/board", {"overrides": {}})[1]  # no second worries yet
    write(deal / "second_worries.json", {"worries": {"addback": {"chance": 0.9, "low": 1, "high": 4}}, "cost": 0})
    body = call(base, "/api/deals/cedar/board", {"overrides": {}})[1]
    assert "go" in body["second"] and body["second"]["differences"] == {"growth": {"board": 0.05, "second": 0.01}}
    write(deal / "second_numbers.json", second)  # a newer read than the worries: stale pair
    assert "second" not in call(base, "/api/deals/cedar/board", {"overrides": {}})[1]


def test_a_step_runs_through_claude(srv):
    base, home = srv
    new_deal(base)
    status, body, _ = call(base, "/api/deals/cedar/run/read", {})
    assert status == 200 and body["name"] == "Cedar Co"
    assert (home / "deals" / "cedar" / "numbers.json").exists()
    assert call(base, "/api/deals/cedar/run/price", {})[0] == 400  # blank numbers: Incomplete, nothing spent


def test_a_failed_claude_call_says_try_again(srv, monkeypatch):
    base, _ = srv
    new_deal(base)
    monkeypatch.setenv("FAKE_CLAUDE", "limit")
    status, body, _ = call(base, "/api/deals/cedar/run/read", {})
    assert status == 502 and body["error"].startswith("failed, try again")


def test_another_web_page_cannot_use_the_api(srv):
    base, home = srv
    new_deal(base)
    status, body, _ = call(base, "/api/deals", headers={"Host": "evil.example:80"})
    assert status == 403 and "error" in body
    assert call(base, "/api/deals", headers={"Host": "127.0.0.1:1"})[0] == 403  # right name, wrong port
    assert call(base, "/api/deals", headers={"Host": base.replace("127.0.0.1", "localhost")[7:]})[0] == 200
    before = (home / "deals" / "cedar" / "numbers.json").exists()
    # a cross-origin page can send text/plain without a preflight: refused, and nothing ran
    for ctype in ("text/plain", "application/x-www-form-urlencoded", "text/plain;application/json"):
        status, body, _ = call(base, "/api/deals/cedar/run/read", raw=b"{}", headers={"Content-Type": ctype})
        assert status == 415 and "error" in body, ctype
    assert call(base, "/api/settings", raw=b"{}", headers={"Content-Type": "application/json; charset=utf-8"})[0] == 200
    assert (home / "deals" / "cedar" / "numbers.json").exists() == before


def test_a_second_write_to_a_busy_deal_is_refused(srv, monkeypatch):
    base, home = srv
    new_deal(base)
    new_deal(base, name="Birch")
    monkeypatch.setenv("FAKE_CLAUDE", "sleep")
    monkeypatch.setenv("FAKE_SLEEP", "3")
    first = {}
    t = threading.Thread(target=lambda: first.update(r=call(base, "/api/deals/cedar/run/read", {})))
    t.start()
    for _ in range(100):  # the fake writes its args file as soon as it starts
        if (home.parent / "args.json").exists():
            break
        time.sleep(0.1)
    for path in ("/run/read", "/numbers", "/board"):
        status, body, _ = call(base, "/api/deals/cedar" + path, {})
        assert status == 409 and "try again" in body["error"], path
    assert call(base, "/api/deals/cedar")[0] == 200  # reading is never blocked
    assert call(base, "/api/deals/birch/numbers", {"tax_rate": 0.2})[0] == 200  # another deal is free
    t.join()
    assert first["r"][0] == 200
    assert call(base, "/api/deals/cedar/numbers", {"tax_rate": 0.2})[0] == 200  # released when the run ends
