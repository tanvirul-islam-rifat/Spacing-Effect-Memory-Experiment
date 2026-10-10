"""Regression tests: the pipeline must reproduce every statistic reported in the paper."""
from pathlib import Path

import pandas as pd
import pytest

from analysis import analyze

DATA = Path(__file__).resolve().parents[1] / "data" / "spacing_effect_data.csv"


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    base = tmp_path_factory.mktemp("out")
    return analyze.run(DATA, base / "results", base / "figures"), base


def test_dataset_structure():
    df = analyze.load_data(DATA)
    assert len(df) == 36
    assert df.condition.value_counts().to_dict() == {"Massed": 18, "Spaced": 18}
    assert df.gender.value_counts().to_dict() == {"Male": 26, "Female": 10}
    assert df.age.between(22, 26).all()


def test_dataset_has_no_direct_identifiers():
    cols = {c.lower() for c in pd.read_csv(DATA).columns}
    assert not cols & {"name", "email", "phone", "signature", "session_date", "date"}
    ids = pd.read_csv(DATA).participant_id
    assert ids.str.fullmatch(r"P\d{2}").all()


def test_descriptives_match_paper(out):
    res, _ = out
    d = res["desc"].set_index("condition")
    assert d.loc["Massed", "mean"] == pytest.approx(8.17, abs=0.005)
    assert d.loc["Spaced", "mean"] == pytest.approx(12.61, abs=0.005)
    assert d.loc["Massed", "sd"] == pytest.approx(2.07, abs=0.005)
    assert d.loc["Spaced", "sd"] == pytest.approx(2.06, abs=0.005)
    assert (d.loc["Massed", "min"], d.loc["Massed", "max"]) == (4, 11)
    assert (d.loc["Spaced", "min"], d.loc["Spaced", "max"]) == (9, 17)
    assert d.loc["Massed", "median"] == 8.5 and d.loc["Spaced", "median"] == 13.0


def test_assumption_checks_match_paper(out):
    a = out[0]["assume"]
    assert a["shapiro_massed"]["W"] == pytest.approx(0.94, abs=0.005)
    assert a["shapiro_massed"]["p"] == pytest.approx(0.339, abs=0.001)
    assert a["shapiro_spaced"]["W"] == pytest.approx(0.95, abs=0.005)
    assert a["shapiro_spaced"]["p"] == pytest.approx(0.431, abs=0.001)
    assert a["levene"]["F"] == pytest.approx(0.08, abs=0.005)
    assert a["levene"]["p"] == pytest.approx(0.784, abs=0.001)


def test_hypothesis_test_matches_paper(out):
    t = out[0]["tests"]
    assert t["df"] == 34
    assert t["student_t"]["t"] == pytest.approx(6.46, abs=0.005)
    assert t["student_t"]["p_two_sided"] < 0.001
    assert t["mean_difference"] == pytest.approx(4.44, abs=0.005)
    assert t["relative_improvement_pct"] == pytest.approx(54.4, abs=0.05)
    assert t["ci95_difference"][0] == pytest.approx(3.05, abs=0.005)
    assert t["ci95_difference"][1] == pytest.approx(5.84, abs=0.005)
    assert t["cohens_d"] == pytest.approx(2.15, abs=0.005)
    assert t["mann_whitney"]["U"] == 305


def test_distribution_claims(out):
    df = analyze.load_data(DATA)
    massed, spaced = analyze.split(df)
    assert (spaced > massed.mean()).sum() == 18      # "18 of 18 above the massed mean"
    assert (spaced > massed.max()).sum() == 12       # "12 of 18 above the highest massed score"


def test_frequency_table_is_internally_consistent(out):
    f = out[0]["freq"].set_index("score_range")
    assert f.sum().tolist() == [18, 18]
    assert f.loc["10-12", "Spaced"] == 6 and f.loc["13-15", "Spaced"] == 9


def test_effect_survives_adjustment(out):
    rob = out[0]["robust"]
    assert (rob.ci95_low > 0).all() and (rob.p_value < 0.001).all()


def test_outputs_written(out):
    _, base = out
    assert (base / "results" / "analysis_summary.md").exists()
    assert len(list((base / "figures").glob("*.png"))) == 7
