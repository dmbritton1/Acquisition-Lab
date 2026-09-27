import json
import shutil

import numpy as np
import pytest

from acqlab.bench import testset
from acqlab.generator import batch
from acqlab.llm import ToolUsed


@pytest.fixture(scope="module")
def tests_batch(tmp_path_factory):
    """Two generated test-split deals (seed 0: test seeds 10000 and 10001)."""
    out = tmp_path_factory.mktemp("testset")
    assert batch.run(out, {"dev": 0, "test": 2, "hand": 0, "showcase": 0}, mc=20) == []
    return out


def test_a_clash_is_a_used_seed_equal_to_a_test_seed_or_one_of_its_retries():
    used = {3_510_005, 1_510_007, 42, 510_200, 3_510_160}  # a test seed; a retry relative; unrelated; beyond n
    assert testset.clashes(3_500_000, 160, used) == [1_510_007, 3_510_005]
    assert testset.clashes(3_500_000, 160, {10_000, 620_000, 1_930_182}) == []


def test_used_seeds_reads_every_answer_key_under_the_roots_and_skips_junk(tmp_path):
    for rel, body in (("a/truth/x.json", {"truth": {"seed": 7}}), ("b/c/truth/y.json", {"truth": {"seed": 9}}),
                      ("a/truth/no_seed.json", {"truth": {}})):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(json.dumps(body))
    (tmp_path / "a" / "truth" / "bad.json").write_text("not json")
    assert testset.used_seeds([tmp_path / "a", tmp_path / "b"]) == {7, 9}


def test_the_fingerprint_changes_when_any_answer_key_changes(tests_batch, tmp_path):
    copy = shutil.copytree(tests_batch / "truth", tmp_path / "d" / "truth")
    before = testset.fingerprint(tmp_path / "d")
    assert set(before["files"]) == {"test-000.json", "test-001.json"}
    assert testset.fingerprint(tmp_path / "d") == before  # stable
    (copy / "test-001.json").write_text((copy / "test-001.json").read_text() + " ")
    after = testset.fingerprint(tmp_path / "d")
    assert after["all"] != before["all"] and after["files"]["test-000.json"] == before["files"]["test-000.json"]


def test_the_recoverability_sample_is_seeded_and_a_tool_using_extractor_fails_each_deal(tests_batch):
    def uses_a_tool(prompt, schema=None):
        raise ToolUsed("codex exec used command_execution")

    chosen, problems = testset.recover_sample(tests_batch, n=5, extract=uses_a_tool)
    assert chosen == ["test-000", "test-001"]  # n above the split's size: every deal, in order
    assert problems == [f"{d}: the extractor used a tool (codex exec used command_execution)" for d in chosen]
    deals = json.loads((tests_batch / "splits.json").read_text())["test"]
    assert testset.recover_sample(tests_batch, n=1, extract=uses_a_tool)[0] == sorted(
        np.random.default_rng(0).choice(deals, 1, replace=False).tolist())


def test_an_extractor_that_finds_nothing_fails_every_fact_it_should_have_found(tests_batch):
    _, problems = testset.recover_sample(tests_batch, n=1, extract=lambda prompt, schema=None: ('{"low": null, '
                                                                                               '"high": null}', 1))
    assert problems and all("extractor answered None-None" in p for p in problems)


def test_the_cli_refuses_codex_calls_without_the_flag_and_checks_seeds(tests_batch, tmp_path, capsys):
    assert testset.main(["recover", "--data", str(tests_batch)]) == 3
    assert testset.main(["seeds", "--base", "0", "--n", "2", "--roots", str(tests_batch)]) == 1  # its own seeds
    assert testset.main(["seeds", "--base", "3500000", "--n", "160", "--roots", str(tests_batch)]) == 0
    assert testset.main(["fingerprint", "--data", str(tests_batch)]) == 0
    assert json.loads(capsys.readouterr().out.split("clashes with base 3500000: none\n")[-1]) == testset.fingerprint(
        tests_batch)
