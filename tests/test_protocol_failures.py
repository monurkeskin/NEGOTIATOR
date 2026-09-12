import pytest

from negotiator.application.contracts import Condition, StudySpec, SurveyItem, SurveyRequest
from negotiator.application.studies import PhaseError, StudyStore
from negotiator.events.journal import JournalError


def prepared(root, **changes):
    store = StudyStore(root, "test")
    result = store.create(StudySpec(preference_mode="assigned", **changes))
    return store, result["plan_id"]


def test_crash_after_session_creation_recovers_an_interruption(tmp_path, monkeypatch):
    store, pid = prepared(tmp_path)
    original = store._save

    def fail_start(state, command, request_id):
        if command["kind"] == "start":
            raise JournalError("synthetic disk failure")
        return original(state, command, request_id)

    monkeypatch.setattr(store, "_save", fail_start)
    with pytest.raises(JournalError):
        store.start(pid)
    recovered = StudyStore(tmp_path, "test").snapshot(pid)
    assert recovered["phase"] == "result"
    assert recovered["current"]["outcome"]["reason"] == "interrupted"
    assert len(recovered["completed_sessions"]) == 1


def test_delayed_phase_command_does_not_skip_a_break(tmp_path):
    store, pid = prepared(tmp_path, conditions=[Condition(), Condition()])
    store.start(pid)
    store.terminate(pid, "Synthetic end", "end")
    context = store.snapshot(pid)["phase_id"]
    store.next(pid, "next", context)
    with pytest.raises(PhaseError):
        store.next(pid, "late-click", context)
    assert store.snapshot(pid)["phase"] == "break"


def test_questionnaire_ack_comes_only_from_the_canonical_study_journal(tmp_path, monkeypatch):
    store, pid = prepared(tmp_path, surveys=[SurveyItem(id="q", prompt="Synthetic rating")])
    store.start(pid)
    store.terminate(pid, "Synthetic end", "end")
    store.next(pid, "next", store.snapshot(pid)["phase_id"])
    request = SurveyRequest(
        request_id="answer", phase_id=store.snapshot(pid)["phase_id"], answers={"q": 5}
    )
    original = store._journals[pid].append
    monkeypatch.setattr(
        store._journals[pid], "append", lambda **kw: (_ for _ in ()).throw(JournalError("disk"))
    )
    with pytest.raises(JournalError):
        store.survey(pid, request)
    assert store.snapshot(pid)["answers"] == []
    monkeypatch.setattr(store._journals[pid], "append", original)
    store.survey(pid, request)
    store.survey(pid, request)
    reopened = StudyStore(tmp_path, "test").snapshot(pid)
    assert len(reopened["answers"]) == 1
    assert reopened["answers"][0]["target_session_id"] == f"{pid}-1"


def test_practice_precedes_counterbalanced_conditions_and_output_changes_per_session(tmp_path):
    from negotiator.application.contracts import CommandRequest

    store, pid = prepared(
        tmp_path,
        order="counterbalanced",
        participant_index=2,
        conditions=[
            Condition(label="Practice", practice=True),
            Condition(label="A", output="text"),
            Condition(label="B", output="avatar"),
        ],
    )
    state = store.snapshot(pid)
    assert [c["label"] for c in state["conditions"]] == ["Practice", "B", "A"]
    store.start(pid)
    sid = store.snapshot(pid)["current"]["config"]["session_id"]
    store.command(pid, CommandRequest(session_id=sid, request_id="withdraw", kind="withdraw"))
    store.next(pid, "n1", store.snapshot(pid)["phase_id"])
    store.next(pid, "n2", store.snapshot(pid)["phase_id"])
    assert store.snapshot(pid)["output"] == "avatar"
    store.shutdown()
