"""Questionnaire provenance, scale semantics and planned-observation boundaries."""

import pytest

from negotiator.analysis.report import study_records
from negotiator.application.contracts import StudySpec, SurveyItem, SurveyRequest
from negotiator.application.protocol import protocol_digest
from negotiator.application.studies import StudyStore


def rating(**changes):
    return SurveyItem(
        id="rating", prompt="Synthetic rating", minimum=1, maximum=9,
        required=False, **changes,
    )


@pytest.mark.parametrize("value", [True, False, 3.0, "3"])
def test_ratings_reject_coercion_into_an_observed_integer(value):
    with pytest.raises(ValueError):
        SurveyRequest(request_id="answer", phase_id="phase", answers={"rating": value})


def test_legacy_questionnaire_configuration_keeps_its_identity():
    spec = StudySpec(preference_mode="assigned", surveys=[rating()])
    # Recorded with the 2.0.0 schema before optional scale descriptions were added.
    assert protocol_digest(spec) == (
        "36b98a85847300cbc041404afa2719c20f4e8ea6a6c16d4ef7a522494a16afad"
    )


def test_scale_descriptions_are_part_of_the_scientific_configuration():
    spec = StudySpec(preference_mode="assigned", surveys=[rating(
        minimum_label="Strongly disagree", maximum_label="Strongly agree",
    )])
    old = protocol_digest(spec)
    spec.surveys[0].maximum_label = "Very satisfied"
    assert protocol_digest(spec) != old


@pytest.mark.parametrize("include_practice, expected_positions", [(False, [2, 3]), (True, [1, 2, 3])])
def test_unscheduled_practice_ratings_are_not_missing_observations(
    tmp_path, include_practice, expected_positions
):
    store = StudyStore(tmp_path)
    try:
        store.create(StudySpec(
            preference_mode="assigned", conditions=[{"practice": True}, {}, {}],
            surveys=[rating(include_practice=include_practice)],
        ))
        _, answers, _ = study_records(tmp_path)
        assert [a["sequence_index"] for a in answers] == expected_positions
        assert all(a["value"] is None and a["missing_reason"] == "not_administered"
                   for a in answers)
    finally:
        store.shutdown()


def test_skipped_scale_preserves_anchors_and_null_on_journal_replay(tmp_path):
    store = StudyStore(tmp_path)
    state = store.create(StudySpec(preference_mode="assigned", surveys=[rating(
        phase="pre_study", minimum_label="Strongly disagree",
        maximum_label="Strongly agree", source="Synthetic instrument",
    )]))
    store.survey(state["plan_id"], SurveyRequest(
        request_id="skip", phase_id=store.snapshot(state["plan_id"])["phase_id"],
        answers={"rating": None},
    ))
    store.shutdown()
    reopened = StudyStore(tmp_path)
    try:
        _, answers, _ = study_records(tmp_path)
        assert len(answers) == 1
        assert answers[0]["minimum_label"] == "Strongly disagree"
        assert answers[0]["maximum_label"] == "Strongly agree"
        assert answers[0]["value"] is None
        assert answers[0]["missing_reason"] == "not_answered"
    finally:
        reopened.shutdown()
