"""Reported outcome measures and movement settings must be unambiguous."""

import csv
import json

import pytest
from openpyxl import load_workbook

from negotiator.analysis import metrics
from negotiator.analysis.report import build_report, read_session
from negotiator.application.session import Session, SessionConfig
from negotiator.domain import Domain, Issue, Preference
from negotiator.domain.actions import End
from negotiator.examples import run_demo
from negotiator.strategies.sensitivity import move


def empty_session(root):
    domain = Domain("choice", (Issue("choice", ("a", "b")),))
    preference = Preference(domain, {"choice": 1}, {"choice": {"a": 1, "b": 0}})
    return Session.create(root, SessionConfig("study", "P001", "s1"), preference, preference)


@pytest.mark.parametrize("threshold", [0, -0.03, float("nan"), float("inf")])
def test_invalid_report_threshold_is_rejected_even_without_comparable_offers(tmp_path, threshold):
    session = empty_session(tmp_path / "source")
    session.submit(End("human", "withdrawal"), "end")
    before = session.journal.path.read_bytes()
    with pytest.raises(ValueError, match="threshold"):
        read_session(session.journal.path, threshold=threshold)
    with pytest.raises(ValueError, match="threshold"):
        build_report(session.journal.path, tmp_path / "report", threshold=threshold)
    assert not (tmp_path / "report").exists()
    assert session.journal.path.read_bytes() == before


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("actor", [0, 1])
def test_undefined_deltas_cannot_become_valid_move_categories(value, actor):
    deltas = [0.1, 0.1]
    deltas[actor] = value
    with pytest.raises(ValueError, match="finite"):
        metrics.classify_move(*deltas)


def test_sum_product_and_normalized_product_are_distinct_measures():
    # Independent arithmetic, with a domain maximum matching the IVA paper example.
    result = metrics.outcome_metrics((0.8, 0.6), 0.64)
    assert result["utility_sum"] == pytest.approx(1.4)
    assert result["utility_product"] == pytest.approx(0.48)
    assert result["normalized_utility_product"] == pytest.approx(0.75)
    assert result["normalized_utility_product_missing_reason"] is None
    assert metrics.outcome_metrics((0.8, 0.8), 0.64)["normalized_utility_product"] == pytest.approx(
        1
    )


@pytest.mark.parametrize(
    ("point", "maximum", "reason"),
    [
        (None, 0.64, "no_agreement"),
        ((0.8, 0.6), None, "unknown_maximum_product"),
        ((0, 0), 0, "zero_maximum_product"),
    ],
)
def test_unavailable_normalization_is_not_a_zero_score(point, maximum, reason):
    result = metrics.outcome_metrics(point, maximum)
    assert result["normalized_utility_product"] is None
    assert result["normalized_utility_product_missing_reason"] == reason
    if point is None:
        assert result["utility_sum"] is None and result["utility_product"] is None


@pytest.mark.parametrize("point", [(float("nan"), 0.5), (0.4, float("inf")), (-0.1, 0.5)])
def test_invalid_utility_is_rejected(point):
    with pytest.raises(ValueError, match="utilities"):
        metrics.outcome_metrics(point, 0.64)


def test_export_records_outcome_measure_identity_and_full_precision(tmp_path):
    session = run_demo(tmp_path / "source")
    before = session.journal.path.read_bytes()
    output = build_report(session.journal.path, tmp_path / "report", include_practice=True)
    data = json.loads((output / "analysis.json").read_text())
    result = data["sessions"][0]["outcome_metrics"]
    assert result["utility_sum"] == pytest.approx(1.2)
    assert result["utility_product"] == pytest.approx(0.2)
    assert result["normalized_utility_product"] == pytest.approx(1)
    assert (
        data["metric_definitions"]["normalized_utility_product"]["id"]
        == "normalized-utility-product-v1"
    )
    with (output / "sessions.csv").open() as stream:
        row = next(csv.DictReader(stream))
    book = load_workbook(output / "records.xlsx", data_only=True)
    columns, cells = list(book["sessions"].values)
    for key in ("utility_sum", "utility_product", "normalized_utility_product"):
        assert float(row[key]) == pytest.approx(result[key])
        assert cells[columns.index(key)] == pytest.approx(result[key])
    book.close()
    assert session.journal.path.read_bytes() == before


def test_post_session_categories_are_not_solver_decision_features(tmp_path):
    assert metrics.classify_move(0.02, 0.02) == "Silent"
    assert move(0.02, 0.02) == "fortunate"
    assert metrics.classify_move(0.03, 0.03) == "Fortunate"
    session = run_demo(tmp_path / "source")
    result = read_session(session.journal.path, threshold=0.05)
    assert result["movement_contract"]["threshold"] == 0.05
    assert result["movement_contract"]["utility_source"] == "recorded_profiles"
    for row in result["offers"]:
        assert row["move_threshold"] == 0.05
        assert row["move_definition"] == result["movement_contract"]["id"]
