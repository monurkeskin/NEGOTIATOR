"""Reproduction computes from inputs; published references only judge the result."""

import hashlib
import json

import pytest

from negotiator import __version__


def make_manifest(root, *, analysis="profile-space", expected=None, data=None, parameters=None):
    root.mkdir(parents=True, exist_ok=True)
    data = (
        data
        if data is not None
        else {
            "domain": {
                "schema_version": 1,
                "name": "two-fruits",
                "issues": [{"name": "apple", "total": 1}, {"name": "banana", "total": 1}],
            },
            "human_profile": {
                "weights": {"apple": 0.8, "banana": 0.2},
                "scores": {
                    "apple": [{"value": 0, "score": 0}, {"value": 1, "score": 1}],
                    "banana": [{"value": 0, "score": 0}, {"value": 1, "score": 1}],
                },
            },
            "agent_profile": {
                "weights": {"apple": 0.2, "banana": 0.8},
                "scores": {
                    "apple": [{"value": 0, "score": 0}, {"value": 1, "score": 1}],
                    "banana": [{"value": 0, "score": 0}, {"value": 1, "score": 1}],
                },
            },
        }
    )
    raw = json.dumps(data).encode()
    (root / "input.json").write_bytes(raw)
    manifest = {
        "schema_version": 1,
        "paper_id": "fixture",
        "result_id": "example",
        "claim_scope": "synthetic-validation",
        "analysis": analysis,
        "parameters": parameters or {},
        "environment": {"framework": __version__},
        "inputs": [
            {"id": "records", "path": "input.json", "sha256": hashlib.sha256(raw).hexdigest()}
        ],
        "expected": expected
        or [
            {
                "key": "outcome_count",
                "value": 4,
                "atol": 0,
                "rtol": 0,
                "source": "four independently enumerable allocations",
            }
        ],
    }
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_profile_result_is_calculated_and_exports_are_linked(tmp_path):
    from negotiator.reproduction import run_reproduction

    manifest = make_manifest(tmp_path / "inputs")
    report = run_reproduction(manifest, tmp_path / "output")
    assert report["status"] == "verified"
    assert report["results"]["outcome_count"] == 4
    assert report["results"]["social_welfare"] == pytest.approx(1.6)
    for name in (
        "report.json",
        "results.csv",
        "table.tex",
        "index.html",
        "ro-crate-metadata.json",
        "outcome-space.svg",
        "outcome-space.pdf",
    ):
        assert (tmp_path / "output" / name).is_file()


def test_expected_paper_scores_never_change_computation(tmp_path):
    from negotiator.reproduction import run_reproduction

    manifest = make_manifest(tmp_path / "inputs")
    first = run_reproduction(manifest, tmp_path / "first")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["expected"][0]["value"] = 700
    manifest.write_text(json.dumps(data), encoding="utf-8")
    second = run_reproduction(manifest, tmp_path / "second")
    assert first["results"] == second["results"]
    assert second["status"] == "mismatch"
    assert second["comparisons"][0]["actual"] == 4


def test_tampered_input_cannot_be_reproduced(tmp_path):
    from negotiator.reproduction import run_reproduction

    manifest = make_manifest(tmp_path / "inputs")
    manifest.with_name("input.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="hash"):
        run_reproduction(manifest, tmp_path / "output")


def test_unavailable_original_data_yields_no_fabricated_results(tmp_path):
    from negotiator.reproduction import run_reproduction

    manifest = make_manifest(tmp_path / "inputs")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["claim_scope"] = "published-result"
    data["inputs"] = [
        {"id": "original", "missing_reason": "Original participant records unavailable"}
    ]
    manifest.write_text(json.dumps(data), encoding="utf-8")
    report = run_reproduction(manifest, tmp_path / "output")
    assert report["status"] == "unavailable"
    assert report["results"] is None
    assert report["comparisons"] == []
    assert "Original participant records unavailable" in (tmp_path / "output/index.html").read_text(
        encoding="utf-8"
    )


def test_reproduction_preserves_existing_output(tmp_path):
    from negotiator.reproduction import run_reproduction

    manifest = make_manifest(tmp_path / "inputs")
    out = tmp_path / "output"
    out.mkdir()
    with pytest.raises(FileExistsError):
        run_reproduction(manifest, out)


@pytest.mark.parametrize(
    "change",
    [
        {"analysis": "shell:curl https://example.org"},
        {"expected": [{"key": "outcome_count", "value": 4, "atol": -1, "source": "fixture"}]},
        {"environment": {"framework": "0.0.0"}},
    ],
)
def test_invalid_recipe_or_environment_is_rejected(tmp_path, change):
    from negotiator.reproduction import run_reproduction

    manifest = make_manifest(tmp_path / "inputs")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    manifest.write_text(json.dumps({**data, **change}), encoding="utf-8")
    with pytest.raises(ValueError):
        run_reproduction(manifest, tmp_path / "output")


def session(participant, condition, utility, *, cohort="C1", domain="D1", rounds=5, practice=False):
    return {
        "study_id": "study",
        "participant_id": participant,
        "session_id": participant + condition,
        "condition": condition,
        "cohort": cohort,
        "domain": domain,
        "rounds": rounds,
        "utility": utility,
        "practice": practice,
    }


def test_paired_analysis_uses_people_preserves_cohorts_and_applies_pair_exclusion(tmp_path):
    from negotiator.reproduction import run_reproduction

    rows = [
        session("P1", "A", 0.8),
        session("P1", "B", 0.4),
        session("P2", "A", 0.5),
        session("P2", "B", 0.4),
        session("P3", "A", 0.9, rounds=4),
        session("P3", "B", 0.1),
        session("P4", "A", 0.5),
        session("P4", "B", None),
        session("P5", "A", 0.7, cohort="C2"),
        session("P5", "B", 0.5, cohort="C2"),
        session("P6", "A", 1, practice=True),
        session("P6", "B", 0, practice=True),
    ]
    manifest = make_manifest(
        tmp_path / "inputs",
        analysis="paired-summary",
        data={"records": rows},
        parameters={
            "conditions": ["A", "B"],
            "minimum_rounds": 5,
            "bootstrap_samples": 500,
            "seed": 17,
        },
        expected=[{"key": "complete_pairs", "value": 3, "atol": 0, "rtol": 0, "source": "fixture"}],
    )
    result = run_reproduction(manifest, tmp_path / "output")
    assert result["status"] == "verified"
    data = result["results"]
    assert data["independent_unit"] == "participant"
    assert data["groups"][0]["mean_difference"] == pytest.approx(0.25)
    assert data["groups"][0]["complete_pairs"] == 2
    assert data["groups"][1]["mean_difference"] == pytest.approx(0.2)
    assert data["groups"][1]["ci"] is None
    assert {r["participant_id"] for r in data["excluded_pairs"]} == {"P3", "P4"}
    assert "confidence_level" in data["groups"][0]


def test_duplicate_session_is_not_counted_as_an_independent_participant(tmp_path):
    from negotiator.reproduction import run_reproduction

    rows = [session("P1", "A", 0.5), session("P1", "A", 0.6), session("P1", "B", 0.4)]
    manifest = make_manifest(
        tmp_path / "inputs",
        analysis="paired-summary",
        data={"records": rows},
        parameters={"conditions": ["A", "B"]},
    )
    with pytest.raises(ValueError, match="Duplicate"):
        run_reproduction(manifest, tmp_path / "output")


def test_reproduce_cli_reports_status_and_nonzero_for_unavailable(tmp_path, capsys):
    from negotiator.cli import main

    manifest = make_manifest(tmp_path / "inputs")
    assert main(["reproduce", str(manifest), "--output", str(tmp_path / "good")]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "verified"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["inputs"] = [{"id": "original", "missing_reason": "Original data unavailable"}]
    manifest.write_text(json.dumps(data), encoding="utf-8")
    assert main(["reproduce", str(manifest), "--output", str(tmp_path / "missing")]) == 3
    assert json.loads(capsys.readouterr().out)["status"] == "unavailable"


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"cases": []},
        {"cases": [{"id": "bad-time", "operation": "time", "arguments": {"t": 1.1}}]},
        {"cases": [{"id": "bad-argument", "operation": "time", "arguments": {"unknown": 2}}]},
        {"cases": [{"id": "leak", "operation": "time", "arguments": {"t": 0.2}, "expected": 0.8}]},
    ],
)
def test_invalid_method_inputs_fail_before_creating_output(tmp_path, data):
    from negotiator.reproduction import run_reproduction

    manifest = make_manifest(tmp_path / "in", analysis="method-vectors", data=data)
    with pytest.raises(ValueError):
        run_reproduction(manifest, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_paired_report_table_and_figure_are_computed_from_participants(tmp_path):
    from negotiator.reproduction import run_reproduction

    records = []
    for index, (left, right) in enumerate([(0.8, 0.4), (0.5, 0.4), (0.6, 0.8)]):
        for condition, utility in [("A", left), ("B", right)]:
            records.append(
                dict(
                    study_id="fixture",
                    participant_id=f"SYNTHETIC-{index}",
                    session_id=f"{index}-{condition}",
                    cohort="c",
                    domain="d",
                    rounds=5,
                    condition=condition,
                    utility=utility,
                )
            )
    manifest = make_manifest(
        tmp_path / "in",
        analysis="paired-summary",
        data={"records": records},
        parameters={"conditions": ["A", "B"], "seed": 3},
        expected=[
            {"key": "complete_pairs", "value": 3, "source": "three explicit paired participants"}
        ],
    )
    report = run_reproduction(manifest, tmp_path / "out")
    assert report["status"] == "verified"
    assert report["results"]["groups"][0]["mean_difference"] == pytest.approx(0.1)
    assert "mean" in (tmp_path / "out/table.tex").read_text(encoding="utf-8").lower()
    assert (tmp_path / "out/paired-contrasts.pdf").is_file()
    assert (tmp_path / "out/paired-contrasts.svg").is_file()
