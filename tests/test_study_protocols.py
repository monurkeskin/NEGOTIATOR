"""Protocol invariants use a fake monotonic clock, never a real experiment."""

import hashlib

import pytest

from negotiator.application.contracts import CommandRequest, StudySpec, SurveyRequest
from negotiator.application.studies import PhaseError, StudyStore
from negotiator.examples import builtin_domain, example_profiles


def profiles():
    human, agent = example_profiles(builtin_domain("fruits"))
    return {"human_profile": human.to_dict(), "agent_profile": agent.to_dict()}


def spec(**changes):
    return StudySpec.model_validate(
        {
            "domain": "fruits",
            "preference_mode": "assigned",
            **profiles(),
            **changes,
        }
    )


def advance(store, pid, request):
    store.next(pid, request, store.snapshot(pid)["phase_id"])


def withdraw(store, pid):
    store.start(pid)
    sid = store.snapshot(pid)["current"]["config"]["session_id"]
    store.command(pid, CommandRequest(request_id="withdraw", session_id=sid, kind="withdraw"))


def test_legacy_configuration_is_explicitly_a_demonstration():
    assert StudySpec().purpose == "demonstration"


def test_real_assigned_study_cannot_silently_generate_synthetic_profiles():
    with pytest.raises(ValueError, match="explicit profiles"):
        StudySpec(purpose="custom-study", preference_mode="assigned")


def test_published_protocol_requires_identity():
    with pytest.raises(ValueError, match="protocol reference"):
        spec(purpose="published-protocol")


def test_published_missing_or_changed_asset_blocks_start_before_journal(tmp_path):
    from negotiator.application.protocol import protocol_digest

    asset = tmp_path / "approved-instrument.txt"
    protocol = {
        "id": "fixture-protocol",
        "revision": "1",
        "paper": "https://example.org/paper",
        "requirements": [
            {
                "id": "instrument",
                "description": "Verified instrument",
                "path": str(asset),
                "sha256": hashlib.sha256(b"approved").hexdigest(),
            }
        ],
    }
    store = StudyStore(tmp_path / "data")
    configured = spec(purpose="published-protocol", protocol=protocol)
    configured.protocol.configuration_sha256 = protocol_digest(configured)
    pid = store.create(configured)["plan_id"]
    for content in (None, "changed"):
        if content is not None:
            asset.write_text(content, encoding="utf-8")
        with pytest.raises(ValueError, match="instrument"):
            store.start(pid)
        assert store.snapshot(pid)["current"] is None
    asset.write_text("approved", encoding="utf-8")
    store.start(pid)
    assert store.snapshot(pid)["current"]["config"]["purpose"] == "published-protocol"
    store.shutdown()


def test_published_protocol_must_be_frozen_and_edits_are_detected(tmp_path):
    from negotiator.application.protocol import protocol_digest

    configured = spec(
        purpose="published-protocol",
        protocol={"id": "fixture", "revision": "1", "paper": "https://example.org/paper"},
    )
    store = StudyStore(tmp_path)
    pid = store.create(configured)["plan_id"]
    with pytest.raises(ValueError, match="configuration"):
        store.start(pid)
    configured.protocol.configuration_sha256 = protocol_digest(configured)
    configured.conditions[0].duration_seconds = 17
    pid = store.create(configured)["plan_id"]
    with pytest.raises(ValueError, match="configuration"):
        store.start(pid)
    store.shutdown()


def test_historical_records_do_not_block_a_new_protocol_session(tmp_path):
    from negotiator.application.protocol import protocol_digest, protocol_readiness

    configured = spec(
        purpose="published-protocol",
        protocol={
            "id": "fixture",
            "revision": "1",
            "paper": "https://example.org/paper",
            "requirements": [
                {
                    "id": "old-records",
                    "description": "Historical participant records",
                    "required_for": "historical-analysis",
                }
            ],
        },
    )
    configured.protocol.configuration_sha256 = protocol_digest(configured)
    assert protocol_readiness(configured) == []
    historical = protocol_readiness(configured, operation="historical-analysis")
    assert [item["id"] for item in historical] == ["old-records"]
    store = StudyStore(tmp_path)
    pid = store.create(configured)["plan_id"]
    store.start(pid)
    assert store.snapshot(pid)["current"]["config"]["purpose"] == "published-protocol"
    store.shutdown()


def test_runtime_training_input_is_still_required_even_with_historical_records_separated(tmp_path):
    from negotiator.application.protocol import protocol_digest, protocol_readiness

    configured = spec(
        purpose="published-protocol",
        protocol={
            "id": "fixture",
            "revision": "1",
            "paper": "https://example.org/paper",
            "requirements": [
                {
                    "id": "old-records",
                    "description": "Historical records",
                    "required_for": "historical-analysis",
                },
                {"id": "calibration", "description": "Input required by this session"},
            ],
        },
    )
    configured.protocol.configuration_sha256 = protocol_digest(configured)
    assert [item["id"] for item in protocol_readiness(configured)] == ["calibration"]
    store = StudyStore(tmp_path)
    pid = store.create(configured)["plan_id"]
    with pytest.raises(ValueError, match="calibration"):
        store.start(pid)
    assert store.snapshot(pid)["current"] is None
    store.shutdown()


def test_invalid_later_profile_is_detected_before_any_session_is_created(tmp_path):
    bad = profiles()["human_profile"]
    bad["weights"] = {"missing_issue": 1.0}
    store = StudyStore(tmp_path)
    with pytest.raises(ValueError):
        store.create(spec(conditions=[{}, {"human_profile": bad}]))
    assert store.list() == []
    store.shutdown()


def test_counterbalance_keeps_practice_attached_to_its_block(tmp_path):
    conditions = [
        {"label": "practice A", "practice": True, "block": "A"},
        {"label": "main A", "block": "A"},
        {"label": "practice B", "practice": True, "block": "B"},
        {"label": "main B", "block": "B"},
    ]
    store = StudyStore(tmp_path)
    result = store.create(spec(conditions=conditions, order="counterbalanced", participant_index=2))
    assert [c["label"] for c in result["state"]["conditions"]] == [
        "practice B",
        "main B",
        "practice A",
        "main A",
    ]
    store.shutdown()


def test_position_profiles_do_not_swap_with_robot_order(tmp_path):
    first = profiles()
    second = {"human_profile": first["agent_profile"], "agent_profile": first["human_profile"]}
    store = StudyStore(tmp_path)
    result = store.create(
        spec(
            conditions=[{"label": "NAO"}, {"label": "Virtual"}],
            order="reversed",
            position_profiles=[first, second],
        )
    )
    assert result["state"]["conditions"][0]["label"] == "Virtual"
    assert result["state"]["human_profile"] == first["human_profile"]
    store.shutdown()


def test_break_is_durable_timed_and_cannot_be_skipped(tmp_path):
    now = [100.0]
    store = StudyStore(tmp_path, now=lambda: now[0])
    pid = store.create(spec(conditions=[{"break_after_seconds": 300}, {}]))["plan_id"]
    withdraw(store, pid)
    advance(store, pid, "show-break")
    assert store.snapshot(pid)["break_remaining_seconds"] == 300
    with pytest.raises(PhaseError, match="break"):
        advance(store, pid, "too-soon")
    now[0] += 299
    assert store.snapshot(pid)["break_remaining_seconds"] == 1
    now[0] += 1
    advance(store, pid, "continue")
    assert store.snapshot(pid)["phase"] == "ready"
    assert store.snapshot(pid)["current"] is None
    store.shutdown()


def test_break_clock_starts_only_after_successful_durable_write(tmp_path, monkeypatch):
    now = [100.0]
    store = StudyStore(tmp_path, now=lambda: now[0])
    pid = store.create(spec(conditions=[{"break_after_seconds": 10}, {}]))["plan_id"]
    withdraw(store, pid)
    journal = store._journals[pid]
    append = journal.append

    def fail(**kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(journal, "append", fail)
    with pytest.raises(OSError, match="disk full"):
        advance(store, pid, "start-break")
    now[0] += 100
    assert store.snapshot(pid)["phase"] == "result"
    monkeypatch.setattr(journal, "append", append)
    advance(store, pid, "start-break")
    assert store.snapshot(pid)["break_remaining_seconds"] == 10
    store.shutdown()


def test_restarted_break_conservatively_requires_full_duration(tmp_path):
    now = [0.0]
    store = StudyStore(tmp_path, now=lambda: now[0])
    pid = store.create(spec(conditions=[{"break_after_seconds": 30}, {}]))["plan_id"]
    withdraw(store, pid)
    advance(store, pid, "break")
    now[0] += 20
    store.shutdown()
    reopened = StudyStore(tmp_path, now=lambda: now[0])
    assert reopened.snapshot(pid)["break_remaining_seconds"] == 30
    assert reopened.snapshot(pid)["break_restarted"] is True
    reopened.shutdown()


def test_main_questionnaire_is_not_accidentally_collected_after_practice(tmp_path):
    store = StudyStore(tmp_path)
    pid = store.create(
        spec(
            conditions=[{"practice": True}, {}],
            surveys=[
                {
                    "id": "rating",
                    "prompt": "Synthetic rating",
                    "phase": "post_session",
                    "include_practice": False,
                }
            ],
        )
    )["plan_id"]
    withdraw(store, pid)
    advance(store, pid, "after-practice")
    assert store.snapshot(pid)["phase"] == "break"
    advance(store, pid, "prepare-main")
    withdraw(store, pid)
    advance(store, pid, "after-main")
    state = store.snapshot(pid)
    assert state["phase"] == "survey"
    store.survey(
        pid, SurveyRequest(request_id="rating", phase_id=state["phase_id"], answers={"rating": 5})
    )
    assert store.snapshot(pid)["phase"] == "complete"
    store.shutdown()


def test_synthetic_execution_does_not_run_or_relabel_a_published_protocol(tmp_path):
    from negotiator.application.synthetic import run_study

    with pytest.raises(ValueError, match="demonstration"):
        run_study(spec(purpose="custom-study"), tmp_path)
    assert list(tmp_path.rglob("events.jsonl")) == []


def test_synthetic_execution_completes_timed_break_without_real_wait(tmp_path):
    from negotiator.application.synthetic import run_study

    result = run_study(spec(conditions=[{"break_after_seconds": 900}, {}]), tmp_path)
    assert result["synthetic"]
    assert len(result["completed_sessions"]) == 2


@pytest.mark.parametrize("order", ["as_entered", "reversed", "counterbalanced"])
def test_noncontiguous_blocks_are_invalid_for_every_participant(order):
    from negotiator.application.protocol import ordered_conditions

    spec = StudySpec(order=order, conditions=[{"block": "A"}, {"block": "B"}, {"block": "A"}])
    with pytest.raises(ValueError, match="contiguous"):
        ordered_conditions(spec)


def test_participant_instruction_changes_invalidate_the_published_protocol():
    from negotiator.application.protocol import protocol_digest, protocol_readiness

    spec = StudySpec(
        purpose="published-protocol",
        protocol={"id": "paper", "revision": "1", "paper": "https://example.org"},
    )
    spec.protocol.configuration_sha256 = protocol_digest(spec)
    assert protocol_readiness(spec) == []
    changed = spec.model_copy(update={"instructions": "A different incentive or goal."})
    assert any(item["id"] == "configuration" for item in protocol_readiness(changed))
