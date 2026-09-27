import pytest

from acqlab.bench import analysis

CASES = ["interaction", "flip", "clean", "decoy", "unresolvable"] * 4  # 20 deals, 4 of each case type


def _rows(regret=0.0, wae=0.05, decoy=1.0, **by_case):
    """deal -> row; by_case overrides regret for a case type."""
    return {f"test-{i:03d}": {"case_type": c, "regret": by_case.get(c, regret), "walk_away_error": wae,
                              "decoy_pages": decoy} for i, c in enumerate(CASES)}


def _by(**systems):
    base = {"s1b": _rows(0.02), "s3": _rows(0.01), "s4": _rows(0.0), "s4_nochal": _rows(0.0),
            "s4_nosweep": _rows(0.0), "s4_noengine": _rows(wae=0.2), "s4_llmdecides": _rows(0.0),
            "s1b_matched": _rows(0.02)}
    return base | systems


def _analyse(by, missed=0):
    real = {d: {"nwc"} for d in by["s4"]}
    first = {d: (set() if i < missed else {"nwc"}) for i, d in enumerate(sorted(by["s4"]))}
    return analysis.analyse(by, real, first)


def test_h1_needs_a_25_percent_cut_a_ci_below_zero_and_s4_below_s3():
    s1b = {d: r | {"regret": 0.02 * (i % 2)} for i, (d, r) in enumerate(_rows().items())}  # varied, so the CI is real
    out = _analyse(_by(s1b=s1b))["H1"]
    assert out["cut"] == 1.0 and out["s4_minus_s1b"]["ci95"][1] < 0 and out["holds"] is True
    assert _analyse(_by(s1b=s1b, s3=_rows(0.0)))["H1"]["holds"] is False  # not below S3
    s4 = {d: r | {"regret": 0.016 * (i % 2)} for i, (d, r) in enumerate(_rows().items())}
    assert _analyse(_by(s1b=s1b, s4=s4))["H1"]["holds"] is False  # a 20% cut
    assert set(out["s4_minus_s1b"]["by_case"]) == set(analysis.CASES)


def test_h2_holds_when_the_gain_sits_on_interaction_and_flip_deals():
    s1b = _rows(0.0, interaction=0.05, flip=0.04)
    s1b["test-000"] = s1b["test-000"] | {"regret": 0.06}  # some spread inside the target group
    out = _analyse(_by(s1b=s1b))["H2"]
    assert out["n_target"] == 8 and out["n_rest"] == 12 and out["gap"] > 0 and out["holds"] is True
    assert _analyse(_by(s1b=_rows(0.02)))["H2"]["holds"] is False  # the same gain everywhere


def test_h3_and_h4_are_one_sided_paired_comparisons():
    nochal = {d: r | {"regret": 0.03 * (i % 3 > 0)} for i, (d, r) in enumerate(_rows().items())}
    assert _analyse(_by(s4_nochal=nochal))["H3"]["holds"] is True
    assert _analyse(_by())["H3"]["holds"] is False  # no difference: not shown
    s4 = {d: r | {"decoy_pages": 1.0 - 0.5 * (i % 2)} for i, (d, r) in enumerate(_rows().items())}
    assert _analyse(_by(s4=s4))["H4"]["holds"] is True


def test_h5_needs_walk_away_error_to_at_least_double():
    noengine = {d: r | {"walk_away_error": 0.2 + 0.01 * (i % 3)} for i, (d, r) in enumerate(_rows().items())}
    out = _analyse(_by(s4_noengine=noengine))["H5"]
    assert out["ratio"] == pytest.approx(0.21 / 0.05, rel=0.05) and out["holds"] is True
    assert _analyse(_by(s4_noengine=_rows(wae=0.09)))["H5"]["holds"] is False  # 1.8x


def test_h6_looks_only_at_deals_where_a_real_trap_was_missing_from_the_first_plan():
    assert _analyse(_by(), missed=3)["H6"]["holds"] == "too few to test"
    nosweep = {d: r | {"regret": 0.03 + 0.01 * (i % 2)} for i, (d, r) in enumerate(_rows().items())}
    out = _analyse(_by(s4_nosweep=nosweep), missed=6)["H6"]
    assert out["deals"] == [f"test-{i:03d}" for i in range(6)] and out["holds"] is True


def test_the_pessimism_control_and_llm_decides_are_reported_beside_the_hypotheses():
    out = _analyse(_by())
    assert out["also"]["s4_minus_s1b_matched"]["diff"] == pytest.approx(-0.02)
    assert out["also"]["llmdecides_minus_s4"]["n"] == 20


def test_the_analysis_refuses_to_run_before_the_campaign_is_complete(tmp_path, capsys):
    assert analysis.main(["--data", str(tmp_path), "--out", str(tmp_path / "r.json")]) == 1
    assert "not complete (s1b 0/160" in capsys.readouterr().out and not (tmp_path / "r.json").exists()


def test_the_analysis_refuses_to_overwrite_an_existing_out_file(tmp_path, capsys):
    out = tmp_path / "r.json"
    out.write_text("already here")
    assert analysis.main(["--data", str(tmp_path), "--out", str(out)]) == 1
    assert "already exists" in capsys.readouterr().out and out.read_text() == "already here"
