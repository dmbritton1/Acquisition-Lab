import json
import math
from collections import Counter
from functools import partial

import pytest

from acqlab.dataroom.tools import BUDGET_SHARE, DataRoom
from acqlab import llm
from acqlab.generator import batch
from acqlab.generator.truth import PROFILES

COUNTS = {"dev": 4, "test": 3, "hand": 2, "showcase": 1}


def test_batch_writes_rooms_answer_keys_and_splits(tmp_path):
    assert batch.run(tmp_path, COUNTS, mc=20) == []
    assert json.loads((tmp_path / "problems.json").read_text()) == []  # saved for the calibration check
    splits = json.loads((tmp_path / "splits.json").read_text())
    assert {k: len(v) for k, v in splits.items()} == COUNTS
    for ids in splits.values():
        for deal_id in ids:
            room = tmp_path / "deals" / deal_id / "room"
            key = json.loads((tmp_path / "truth" / f"{deal_id}.json").read_text())
            assert {p.name for p in room.iterdir() if p.suffix == ".json"} == {"index.json", "engine.json"}
            assert set(json.loads((room / "engine.json").read_text())) == {"teaser", "deal"}  # visible numbers only
            dr = DataRoom(room)
            pages = sum(d["pages"] for d in dr.list_documents())
            assert key["budget"] == dr.budget == math.ceil(BUDGET_SHARE * pages)
            assert set(key["retrieval_cost"]) == {"addback", "debt_like", "concentration", "nwc", "capex"}
    showcase = json.loads((tmp_path / "truth" / "showcase-000.json").read_text())
    assert showcase["truth"]["case_type"] == "flip"


def test_recoverability_is_phased_in_to_hand_showcase_and_a_dev_sample(tmp_path):
    asked = set()

    def extract(prompt, schema=None):
        asked.add(prompt)
        return '{"low": null, "high": null}', 0

    problems = batch.run(tmp_path, COUNTS, mc=20, recover=1, extract=extract)
    checked = {p.split(":")[0] for p in problems}  # this extractor fails every deal it is shown
    assert {"hand-000", "hand-001", "showcase-000"} <= checked
    assert sum(d.startswith("dev-") for d in checked) == 1 and not any(d.startswith("test-") for d in checked)


def test_a_profile_sets_the_deals_and_the_budget_share(tmp_path):
    assert batch.run(tmp_path, {"dev": 2, "test": 0, "hand": 0, "showcase": 0}, mc=20, profile="r3") == []
    key = json.loads((tmp_path / "truth" / "dev-000.json").read_text())
    pages = sum(d["pages"] for d in DataRoom(tmp_path / "deals" / "dev-000" / "room").list_documents())
    assert key["truth"]["profile"] == "r3" and key["budget"] == math.ceil(PROFILES["r3"]["budget_share"] * pages)


def test_cli_runs_without_an_llm(tmp_path):
    code = batch.main(["--out", str(tmp_path), "--dev", "2", "--test", "1", "--hand", "0", "--showcase", "0",
                       "--mc", "20"])
    assert code == 0 and (tmp_path / "truth" / "dev-000.json").exists()


def _prose_runner(limit=None):
    """Fake Codex that writes valid prose, and hits a usage limit after `limit` calls if given."""
    state = {"calls": 0}

    def run(prompt, schema):
        if limit is not None and state["calls"] >= limit:
            raise llm.LLMUnavailable("usage limit reached")
        state["calls"] += 1
        if schema is None:
            return "Plain passage.", 1
        slots = [line[len("- id: "):] for line in prompt.splitlines() if line.startswith("- id: ")]
        meanings = [line.split('meaning: "', 1)[1][:-1] for line in prompt.splitlines() if "  meaning: " in line]
        return json.dumps({sid: "Put simply, " + m for sid, m in zip(slots, meanings)}), 1

    return run, state


def test_a_codex_limit_stops_the_batch_and_a_rerun_resumes_from_the_cache(tmp_path):
    counts, cache = {"dev": 2, "test": 0, "hand": 0, "showcase": 0}, tmp_path / "cache"
    flaky, _ = _prose_runner(limit=5)
    with pytest.raises(llm.LLMUnavailable):
        batch.run(tmp_path / "a", counts, mc=20, llm=partial(llm.complete, run=flaky, cache_dir=cache))
    assert len(list(cache.glob("*.json"))) == 5  # the five good replies were kept
    resumed, state = _prose_runner()
    assert batch.run(tmp_path / "a", counts, mc=20, llm=partial(llm.complete, run=resumed, cache_dir=cache)) == []
    fresh, fresh_state = _prose_runner()
    batch.run(tmp_path / "b", counts, mc=20, llm=partial(llm.complete, run=fresh, cache_dir=tmp_path / "c2"))
    assert state["calls"] == fresh_state["calls"] - 5  # nothing already answered was paid for again
    for deal in ("dev-000", "dev-001"):
        a, b = (tmp_path / r / "deals" / deal / "room" / "cim.md" for r in ("a", "b"))
        assert a.read_text() == b.read_text()


def test_cli_reports_a_codex_stop_and_exits_2(tmp_path, monkeypatch, capsys):
    def limit(prompt, **kwargs):
        raise llm.LLMUnavailable("usage limit reached")

    monkeypatch.setattr(llm, "complete", limit)
    code = batch.main(["--out", str(tmp_path), "--dev", "1", "--test", "0", "--hand", "0", "--showcase", "0",
                       "--mc", "20", "--llm"])
    assert code == 2 and "Run the same command again" in capsys.readouterr().out


def _recording_llm(reply=None):
    """Fake cached LLM: records prompts; valid prose unless a fixed `reply` is given."""
    prompts, (run, _) = [], _prose_runner()

    def complete(prompt, schema=None):
        prompts.append(prompt)
        return (reply, 1) if reply is not None else run(prompt, schema)

    return complete, prompts


def test_two_deals_never_send_codex_the_same_prompt():
    seen = []
    for deal_id, seed in (("dev-000", 0), ("dev-001", 1)):
        complete, prompts = _recording_llm()
        batch.build(deal_id, "dev", seed, mc=20, llm=complete)
        seen.append(set(prompts))
    assert seen[0] and seen[1] and not seen[0] & seen[1]


def test_answer_key_counts_paragraphs_left_as_template():
    complete, _ = _recording_llm()
    key, _, _ = batch.build("dev-000", "dev", 0, mc=20, llm=complete)
    assert key.prose_fallbacks == 0
    junk, _ = _recording_llm(reply="Revenue rose 12 percent.")  # never acceptable
    key, docs, _ = batch.build("dev-000", "dev", 0, mc=20, llm=junk)
    assert key.prose_fallbacks == sum(1 for d in docs for b in d.blocks if not isinstance(b, str)) > 0


def test_engine_and_leak_checks_run_before_any_codex_call(monkeypatch):
    complete, prompts = _recording_llm()
    monkeypatch.setattr(batch, "check_engine", lambda t: ["always fails"])
    with pytest.raises(RuntimeError):
        batch.build("dev-000", "dev", 0, mc=20, llm=complete)
    assert prompts == []


def test_cli_keeps_the_codex_cache_beside_the_batch_output(tmp_path, monkeypatch):
    seen = {}

    def limit(prompt, **kwargs):
        seen.update(kwargs)
        raise llm.LLMUnavailable("usage limit reached")

    monkeypatch.setattr(llm, "complete", limit)
    batch.main(["--out", str(tmp_path), "--dev", "1", "--test", "0", "--hand", "0", "--showcase", "0", "--mc", "20",
                "--llm"])
    assert seen["cache_dir"] == tmp_path / "llm_cache"


def test_splits_lists_every_split_even_when_empty(tmp_path):
    batch.run(tmp_path, {"dev": 1, "test": 0, "hand": 0, "showcase": 0}, mc=20)
    assert json.loads((tmp_path / "splits.json").read_text()) == {"dev": ["dev-000"], "test": [], "hand": [],
                                                                    "showcase": []}


def test_cli_reports_a_deal_that_keeps_failing_validation_and_exits_3(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(batch, "check_engine", lambda t: ["always fails"])
    code = batch.main(["--out", str(tmp_path), "--dev", "1", "--test", "0", "--hand", "0", "--showcase", "0",
                       "--mc", "20"])
    assert code == 3 and "dev-000" in capsys.readouterr().out


def test_cases_for_gives_exact_seeded_quotas_and_nothing_without_one():
    cases = batch.cases_for(40, "r2u", 11_260_000)
    assert Counter(cases) == {"relief": 16, "confirmed": 8, None: 16}
    assert cases == batch.cases_for(40, "r2u", 11_260_000) and cases != batch.cases_for(40, "r2u", 1)
    assert Counter(batch.cases_for(7, "r2u", 0)) == {"relief": 3, "confirmed": 1, None: 3}  # 2.8 and 1.4, rounded
    assert batch.cases_for(40, "r2", 0) == [None] * 40


def test_an_r2u_batch_has_its_quota_and_flagged_teasers(tmp_path):
    assert batch.run(tmp_path, {"dev": 0, "test": 5, "hand": 0, "showcase": 0}, mc=20, profile="r2u") == []
    keys = [json.loads((tmp_path / "truth" / f"test-{i:03d}.json").read_text())["truth"] for i in range(5)]
    assert Counter(k["case_type"] for k in keys if k["case_type"] in ("relief", "confirmed")) == {"relief": 2,
                                                                                                "confirmed": 1}
    for i, k in enumerate(keys):
        teaser = json.loads((tmp_path / "deals" / f"test-{i:03d}" / "room" / "index.json").read_text())["teaser"]
        assert ("Seller discloses" in teaser) == (k["flag"] is not None) == (k["case_type"] in ("relief", "confirmed"))
