import json
import shutil
from pathlib import Path

import pytest

from acqlab.agents import solver
from acqlab.agents.solver import RunTimeout
from acqlab.bench import haiku, mix

RATES = {"addback": 0.3, "debt_like": 0.2, "concentration": 0.4, "nwc": 0.1, "capex": 0.2}
TEASER = "Seller discloses: customer prepayments; estimated exposure up to $13.4M.\nAsking price: $1,078.4M\n"


def _row(tool, args=None, cost=0.0):
    return {"i": 1, "tool": tool, "args": args or {}, "cost": cost, "refused": False, "error": None}


def _submit(go=True, wa=100.0):
    return _row("submit", {"go": go, "walk_away": wa, "reason": "r"})


@pytest.fixture
def room(data):
    return data / "deals" / "dev-000" / "room"


# --- the model switch, per step ------------------------------------------------------------------------------------

def test_on_model_sets_the_model_and_effort_and_restores_the_original(fake_claude, room, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "ok")
    original = solver.command
    with mix.on_model(mix.SONNET, "low"):
        solver.solve(room, 5, tmp_path / "t.jsonl", False, claude=fake_claude)
    argv = json.loads((tmp_path / "args.json").read_text())["argv"]
    assert argv[argv.index("--model") + 1] == "claude-sonnet-5-5" and argv[argv.index("--effort") + 1] == "low"
    assert solver.command is original
    with pytest.raises(RuntimeError):
        with mix.on_model(mix.OPUS):
            raise RuntimeError("boom")
    assert solver.command is original


@pytest.fixture
def fakes(monkeypatch):
    """The reader and pricers replaced by sessions that write a scripted trace (scripts[step]; none scripted = a
    timeout) and record the model and effort their command line would carry (seen[step])."""
    f = {"scripts": {}, "seen": {}}

    def run(*args, trace, **kw):
        name = trace.name.split(".")[-2]
        cmd = solver.command("claude", "p", "s", Path("m.json"), [])
        f["seen"][name] = (cmd[cmd.index("--model") + 1], cmd[cmd.index("--effort") + 1] if "--effort" in cmd else None,
                           args)
        if name not in f["scripts"]:
            raise RunTimeout("fake timeout")
        trace.write_text("".join(json.dumps(r) + "\n" for r in f["scripts"][name]))
        model = cmd[cmd.index("--model") + 1]
        return {"total_cost_usd": 0.5, "usage": {"output_tokens": 1_000_000}, "modelUsage": {model: {}}}

    monkeypatch.setattr(mix, "draft", run)
    monkeypatch.setattr(mix, "second_zero", run)
    return f


def test_a_pipeline_runs_each_step_on_its_own_model_and_prices_it_step_by_step(fakes, room, tmp_path):
    reads = [_row("open_document", {"doc_id": "qoe"}, 4.0)]
    fakes["scripts"] |= {"reader": [*reads, _submit(False)], "pricer1": [_submit(True)]}
    s = mix.CANDIDATES["mix_h_opus1"].settings
    trace, cli, steps = mix.run_pipeline(room, 20.0, "dev-000", tmp_path / "x.json", rates=RATES, **s)
    assert fakes["seen"]["reader"][:2] == ("claude-haiku-5-5", None)
    assert fakes["seen"]["pricer1"][:2] == ("claude-opus-5-5", None) and fakes["seen"]["pricer1"][2][1] == ["qoe"]
    assert [x["step"] for x in steps] == ["reader", "pricer1"]
    assert [x["models"] for x in steps] == [["claude-haiku-5-5"], ["claude-opus-5-5"]]
    assert mix.row_cost({"steps": steps}) == pytest.approx(0.50 + 20.0)  # a million output tokens each
    assert set(cli["calls"]) == {"reader", "pricer1"} and mix.call_of(trace) is not None
    assert solver.command.__module__ == "acqlab.agents.solver"


def test_a_single_run_carries_its_effort_and_a_timeout_costs_nothing_known(fakes, room, tmp_path):
    rows, cli, steps = mix.run_single(room, 20.0, "dev-000", tmp_path / "x.json", model=mix.OPUS, effort="low")
    assert fakes["seen"]["solo"][:2] == ("claude-opus-5-5", "low") and cli is None
    assert steps == [{"step": "solo", "models": [], "tokens": dict.fromkeys(mix.USAGE, 0)}]
    assert mix.row_cost({"steps": steps}) == 0.0


def test_row_cost_prices_single_model_rows_from_their_summed_tokens():
    tokens = {"input_tokens": 1_000_000, "output_tokens": 0, "cache_read_input_tokens": 1_000_000,
              "cache_creation_input_tokens": 0}
    assert mix.row_cost({"models": ["claude-sonnet-5-5"], "tokens": tokens}) == pytest.approx(2.0 + 0.20)
    assert mix.row_cost({"models": ["claude-opus-5-5"], "tokens": tokens}) == pytest.approx(4.0 + 0.20)
    assert mix.row_cost({"models": [], "tokens": tokens}) is None


def test_row_cost_raises_on_a_step_it_cannot_price_and_costs_a_timeout_step_nothing():
    tokens = {"input_tokens": 1_000_000, "output_tokens": 0, "cache_read_input_tokens": 0,
              "cache_creation_input_tokens": 0}
    mixed = {"step": "pricer1", "models": ["claude-haiku-5-5", "claude-opus-5-5"], "tokens": tokens}
    with pytest.raises(ValueError):
        mix.row_cost({"steps": [mixed]})
    assert mix.row_cost({"steps": [{"step": "solo", "models": [], "tokens": tokens}]}) == 0.0


# --- cascades ------------------------------------------------------------------------------------------------------

def _run(go=True, wa=1000.0, answered=True, calls=None, correct=True, regret=0.0, cost_tokens=1_000_000):
    return {"go": go, "walk_away": wa, "answered": answered, "calls": calls, "correct": correct, "regret": regret,
            "case_type": "clean", "models": ["claude-haiku-5-5"],
            "tokens": {"input_tokens": 0, "output_tokens": cost_tokens, "cache_read_input_tokens": 0,
                       "cache_creation_input_tokens": 0}}


def test_each_signal_fires_as_specified():
    assert mix.asking_price(TEASER) == pytest.approx(1078.4)
    plain = TEASER.replace("Seller discloses", "Seller notes")
    assert mix.fires("pass", _run(go=False), plain) and not mix.fires("pass", _run(go=True), plain)
    split = {"reader": {"go": True}, "pricer1": {"go": True}, "pricer2": {"go": False}, "pricer3": None}
    assert mix.fires("split", _run(calls=split), plain)
    assert not mix.fires("split", _run(calls={"pricer1": {"go": True}, "pricer2": {"go": True}}), plain)
    assert not mix.fires("split", _run(calls=None), plain)
    assert mix.fires("close:0.05", _run(wa=1078.4 * 1.04), plain) and not mix.fires("close:0.02", _run(wa=1078.4 * 1.04), plain)
    assert mix.fires("flag", _run(), TEASER) and not mix.fires("flag", _run(), plain)
    assert mix.fires("pass|flag", _run(go=True), TEASER) and not mix.fires("pass|flag", _run(go=True), plain)
    assert mix.fires("flag", _run(answered=False), plain)  # a cheap run that never answered is always escalated


def test_a_cascade_takes_the_strong_call_and_pays_for_it_only_when_it_escalates():
    cheap, strong = _run(go=False, correct=False, regret=0.04), _run(go=True, correct=True, regret=0.0)
    strong |= {"models": ["claude-opus-5-5"]}
    up = mix.cascade(cheap, strong, "pass", TEASER)
    assert up["escalated"] and up["go"] and up["regret"] == 0.0 and up["cost"] == pytest.approx(0.50 + 20.0)
    stay = mix.cascade(_run(go=True), strong, "pass", TEASER.replace("Seller discloses", "Seller notes"))
    assert not stay["escalated"] and stay["cost"] == pytest.approx(0.50)


def test_cascade_names_parse():
    assert mix.parse("cascade:mix_haiku_solo>s1b@split|close:0.05") == ("mix_haiku_solo", "s1b", "split|close:0.05")
    assert mix.parse("mix_opus_low") is None


def test_the_frontier_keeps_undominated_mixes_and_the_two_named_picks_first():
    points = {"a": (0.020, 0.01), "b": (0.015, 0.05), "c": (0.012, 0.20), "d": (0.016, 0.06), "e": (0.009, 0.50),
              "f": (0.010, 0.40)}
    # d is dominated by b; s1b costs 0.13 and s4 0.53: best under 0.13 is b, best under 0.53 is e
    assert mix.frontier(points, 0.13, 0.53) == ["b", "e", "a", "c"]
    assert mix.frontier(points, 0.13, 0.53, k=2) == ["b", "e"]
    assert mix.frontier({"x": (0.02, 0.9)}, 0.13, 0.53) == ["x"]  # nothing cheaper: only the cheapest-first fill
    clones = {"cascade:a>s1b@split": (0.020, 0.01), "a": (0.020, 0.01), "cascade:a>s1b@flag": (0.010, 0.05),
              "cascade:a>s1b@flag|close:0.05": (0.010, 0.05)}
    assert mix.frontier(clones, 0.13, 0.53) == ["cascade:a>s1b@flag", "a"]  # a tie counts once, as the simplest


# --- the registry and the runner -----------------------------------------------------------------------------------

def test_the_aliases_are_the_same_systems_as_the_haiku_track_ran():
    lean, h3 = haiku.CANDIDATES["haiku_lean_zero_w0"], mix.CANDIDATES["mix_h_haiku3"]
    assert lean.prompts == h3.prompts and lean.settings["w"] == h3.settings["w"] == 0.0
    assert lean.settings["pricers"] == h3.settings["pricers"] and lean.settings["zero"]
    assert haiku.CANDIDATES["haiku_solo"].prompts == mix.CANDIDATES["mix_haiku_solo"].prompts
    assert set(mix.ALIASES) <= set(mix.CANDIDATES)


def test_fingerprints_differ_and_models_are_listed():
    shas = {n: mix.fingerprint(n) for n in mix.CANDIDATES}
    assert len(set(shas.values())) == len(shas)
    assert mix.models_of("mix_h_opus1") == ["claude-haiku-5-5", "claude-opus-5-5"]
    assert mix.models_of("mix_opus_low") == ["claude-opus-5-5"]


def test_the_fresh_sets_are_refused_before_the_freeze(tmp_path, monkeypatch):
    for name in mix.TEST_SETS:
        with pytest.raises(mix.Refused, match="held out"):
            mix.run(tmp_path / name, ["mix_opus_low"], split="dev")
    with pytest.raises(mix.Refused, match="held out"):
        mix.run(tmp_path / "cal-r2", ["mix_opus_low"], split="test")
    with pytest.raises(mix.Refused, match="no frozen mixes"):
        mix.run(tmp_path / "mix-test-r2", ["mix_opus_low"], split="test", final=True)
    monkeypatch.setattr(mix, "FINAL", ("cascade:mix_haiku_solo>mix_opus_low@pass", "mix_h_opus1"))
    with pytest.raises(mix.Refused, match="test split"):
        mix.run(tmp_path / "mix-test-r2", ["mix_opus_low"], split="dev", final=True)
    with pytest.raises(mix.Refused, match="not \\['mix_sonnet_solo'\\]"):
        mix.run(tmp_path / "mix-test-r2", ["mix_h_opus1", "mix_sonnet_solo"], split="test", final=True)
    assert mix.main(["--data", str(tmp_path / "mix-test-r2u"), "--systems", "mix_opus_low", "--split", "test",
                     "--confirm-claude"]) == 3
    assert mix.main(["--data", str(tmp_path), "--systems", "mix_x", "--confirm-claude"]) == 1
    assert mix.main(["--data", str(tmp_path / "cal-r2"), "--systems", "mix_opus_low"]) == 3


def test_the_runner_refuses_an_old_cli(data, tmp_path, monkeypatch):
    monkeypatch.setattr(haiku, "cli_version", lambda: "2.1.280")
    assert mix.main(["--data", str(data), "--systems", "mix_opus_low", "--confirm-claude"]) == 3


def test_mixes_run_end_to_end_with_the_fake_claude(data, tmp_path, fake_claude, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE", "ok")
    monkeypatch.setattr(haiku, "load_rates", lambda: RATES)
    d = tmp_path / "d"
    shutil.copytree(data, d)
    rows = mix.run(d, ["mix_opus_low", "mix_h_opus1"], deals=["dev-001"], cli="2.1.291", claude=fake_claude)
    assert [(r["system"], r["deal"]) for r in rows] == [("mix_opus_low", "dev-001"), ("mix_h_opus1", "dev-001")]
    for r in rows:
        assert r["answered"] and r["spent"] <= r["budget"] + 1e-9 and r["cli"] == "2.1.291"
        assert r["prompts"] == mix.fingerprint(r["system"])
    assert [s["step"] for s in rows[1]["steps"]] == ["reader", "pricer1"] and rows[1]["sessions"] == 2
    argv = json.loads((tmp_path / "args.json").read_text())["argv"]
    assert argv[argv.index("--model") + 1] == "claude-opus-5-5"  # the last session was the Opus pricer
    assert not list((d / "runs").glob("*/*.tmp"))
    assert mix.run(d, ["mix_opus_low", "mix_h_opus1"], deals=["dev-001"], claude=fake_claude) == []


def test_no_step_reads_the_answer_key():
    source = Path(mix.__file__).read_text().split("def run(")[0]
    assert not any(word in source for word in ("AnswerKey", "truth", "model_validate"))
