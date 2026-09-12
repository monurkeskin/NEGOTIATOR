import csv
import json
import random

import pytest
from openpyxl import load_workbook

from negotiator.analysis.metrics import classify_move, correlations, reference_points
from negotiator.analysis.report import build_report
from negotiator.application.contracts import Condition, StudySpec
from negotiator.application.studies import StudyStore
from negotiator.examples import run_demo


def test_rank_ties_constants_and_reference_points_have_explicit_semantics():
    assert correlations([1, 1, 2], [2, 2, 1])["spearman"]["value"] == pytest.approx(-1)
    constant = correlations([1, 1], [1, 2])
    assert constant["pearson"] == {"value": None, "reason": "constant_utility"}
    result = reference_points([(1, 0.1), (0.6, 0.6), (0.8, 0.4), (0.1, 0.1)], (0.7, 0.5))
    assert result["social_welfare"] == pytest.approx(1.2)
    assert result["raw_nash_product"] == pytest.approx(0.36)
    assert result["surplus_nash_product"] is None
    assert (0.1, 0.1) not in result["pareto"]
    assert classify_move(0, 0) == "Silent"
    assert classify_move(-0.1, 0.2) == "Concession"


def test_session_snapshot_json_csv_xlsx_and_independent_affect_export_agree(tmp_path):
    session = run_demo(tmp_path / "source")
    session.perception({"source": "synthetic", "valence": 0.2, "arousal": -0.5}, "affect-a")
    session.perception({"source": "synthetic", "valence": -0.8, "arousal": 0.9}, "affect-b")
    before = session.journal.path.read_bytes()
    rng = random.getstate()
    output = build_report(session.journal.path, tmp_path / "report", include_practice=True)
    assert random.getstate() == rng
    assert session.journal.path.read_bytes() == before
    rows = list(csv.DictReader((output / "offers.csv").open()))
    assert float(rows[1]["human_utility"]) == session.state.offers[1]["utilities"]["human"] == 0.2
    book = load_workbook(output / "records.xlsx", data_only=True)
    values = list(book["offers"].values)
    assert values[2][values[0].index("human_utility")] == 0.2
    analysis = json.loads((output / "analysis.json").read_text(encoding="utf-8"))
    report = analysis["sessions"][0]
    assert report["perception"]["valence"]["min"] == -0.8
    assert report["perception"]["arousal"]["min"] == -0.5
    for path in (
        "index.html",
        "sessions/demo-SYNTHETIC001-" + session.config.session_id + "/trajectory.svg",
    ):
        assert (output / path).is_file()
    import hashlib

    snapshot = output / "sessions" / report["key"] / "source-events.jsonl"
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == report["source_sha256"]
    assert "NaN" not in (output / "analysis.json").read_text(encoding="utf-8")


def test_study_reports_keep_planned_missing_sessions_and_exclude_practice(tmp_path):
    store = StudyStore(tmp_path / "data", "test")
    spec = StudySpec(
        participant_id="P001",
        preference_mode="assigned",
        cohort="cohort-a",
        conditions=[Condition(label="Practice", practice=True), Condition(label="Main")],
    )
    pid = store.create(spec)["plan_id"]
    store.start(pid)
    store.terminate(pid, "Synthetic termination", "end")
    output = build_report(tmp_path / "data", tmp_path / "report")
    data = json.loads((output / "analysis.json").read_text(encoding="utf-8"))
    assert data["independent_unit"] == "participant"
    assert data["sessions"][0]["included"] is False
    assert data["planned_sessions"][1]["status"] == "not_run"
    assert data["planned_sessions"][1]["cohort"] == "cohort-a"
    assert data["condition_summaries"] == []
    store.shutdown()


def test_repeated_sessions_do_not_inflate_participants_and_pairs_need_both_conditions():
    from negotiator.analysis.report import aggregate, pair_records

    records = []
    for person, label, u in [
        ("P1", "A", 0.2),
        ("P1", "A", 0.4),
        ("P1", "B", 0.8),
        ("P2", "A", 0.6),
    ]:
        records.append(
            {
                "included": True,
                "domain_sha256": "same-domain",
                "config": {
                    "study_id": "study",
                    "cohort": "c",
                    "participant_id": person,
                    "condition": label,
                    "strategy": "hybrid",
                    "sequence_index": 1,
                },
                "outcome": {"reason": "agreement", "utilities": {"human": u, "agent": 1 - u}},
            }
        )
    summaries, participants = aggregate(records)
    a = next(s for s in summaries if s["condition"] == "A")
    assert a["participants"] == 2 and a["sessions"] == 3
    assert a["mean_human_agreement_utility"] == pytest.approx(0.45)
    pairs = pair_records(participants, [])
    assert sum(p["complete"] for p in pairs) == 1
    assert next(p for p in pairs if p["participant_id"] == "P1")[
        "human_utility_difference"
    ] == pytest.approx(0.5)


def test_unanswered_scheduled_questionnaires_remain_missing(tmp_path):
    from negotiator.application.contracts import SurveyItem

    store = StudyStore(tmp_path / "data", "test")
    store.create(
        StudySpec(preference_mode="assigned", surveys=[SurveyItem(id="q", prompt="Synthetic")])
    )
    output = build_report(tmp_path / "data", tmp_path / "report")
    items = json.loads((output / "analysis.json").read_text(encoding="utf-8"))["questionnaires"]
    assert items[0]["value"] is None
    assert items[0]["missing_reason"] == "not_administered"
    store.shutdown()


def test_legacy_arousal_bug_is_marked_unrecoverable_without_editing_original(tmp_path):
    from negotiator.analysis.legacy import import_legacy

    source = tmp_path / "legacy.csv"
    source.write_text("V,A,HU\n0.7,0.7,0.0\n", encoding="utf-8")
    before = source.read_bytes()
    output = import_legacy(
        source,
        {"valence": "V", "arousal": "A", "human_utility": "HU"},
        tmp_path / "import.json",
        arousal_overwritten=True,
    )
    row = json.loads(output.read_text(encoding="utf-8"))["rows"][0]
    assert row["reported_values"]["arousal"] is None
    assert row["reported_values"]["valence"] == 0.7
    assert row["reported_values"]["human_utility"] == 0.0
    assert "unrecoverable" in row["missing_reasons"]["arousal"]
    assert source.read_bytes() == before


def test_planned_domain_hashes_follow_each_condition(tmp_path):
    from negotiator.analysis.report import study_records
    from negotiator.domain.importers import to_dict
    from negotiator.events.journal import digest
    from negotiator.examples import builtin_domain

    store = StudyStore(tmp_path, "test")
    store.create(
        StudySpec(
            preference_mode="assigned",
            conditions=[
                Condition(label="A", domain="holiday"),
                Condition(label="B", domain="holiday-b"),
            ],
        )
    )
    plans, _, _ = study_records(tmp_path)
    assert [p["domain_sha256"] for p in plans] == [
        digest(to_dict(builtin_domain(name))) for name in ("holiday", "holiday-b")
    ]
    store.shutdown()


def test_skipped_optional_survey_has_one_missing_row_and_verifiable_protocol_source(tmp_path):
    import hashlib

    from negotiator.application.contracts import SurveyItem, SurveyRequest

    store = StudyStore(tmp_path / "data", "test")
    pid = store.create(
        StudySpec(
            preference_mode="assigned",
            surveys=[
                SurveyItem(
                    id="optional",
                    prompt="Synthetic optional item",
                    required=False,
                    phase="pre_study",
                )
            ],
        )
    )["plan_id"]
    store.survey(
        pid, SurveyRequest(request_id="skip", phase_id=store.snapshot(pid)["phase_id"], answers={})
    )
    output = build_report(tmp_path / "data", tmp_path / "report")
    data = json.loads((output / "analysis.json").read_text(encoding="utf-8"))
    assert len(data["questionnaires"]) == 1
    assert data["questionnaires"][0]["missing_reason"] == "not_answered"
    receipt = data["study_sources"][0]
    snapshot = output / receipt["relative_path"]
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == receipt["sha256"]
    assert (
        snapshot.read_bytes() == (tmp_path / "data" / "_plans" / pid / "events.jsonl").read_bytes()
    )
    store.shutdown()


def test_unicode_session_reports_do_not_depend_on_system_text_encoding(tmp_path, monkeypatch):
    from pathlib import Path

    from negotiator.analysis.report import read_session
    from negotiator.application.session import Session, SessionConfig
    from negotiator.domain import Domain, Issue, Preference
    from negotiator.domain.actions import End

    domain = Domain("İstanbul", (Issue("şehir", ("İzmir", "Ankara")),))
    profile = Preference(domain, {"şehir": 1}, {"şehir": {"İzmir": 1, "Ankara": 0}})
    session = Session.create(tmp_path, SessionConfig("unicode", "P001", "s1"), profile, profile)
    session.submit(End("human", "withdrawal"), "end")
    original = Path.read_text

    def legacy_locale_read(path, encoding=None, errors=None):
        return original(path, encoding=encoding or "cp1252", errors=errors)

    monkeypatch.setattr(Path, "read_text", legacy_locale_read)
    assert read_session(session.journal.path)["status"] == "ended"
