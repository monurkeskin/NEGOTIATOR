import json

import pytest
from fastapi.testclient import TestClient

from negotiator.web.app import create_app

ADMIN = {"X-Negotiator-Token": "test-admin"}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path, conductor_token="test-admin")) as api:
        yield api


def create(api, **changes):
    spec = {
        "study_id": "study",
        "participant_id": "P001",
        "title": "Synthetic negotiation",
        "domain": "holiday",
        "preference_mode": "elicited",
        "conditions": [
            {"label": "private-A", "strategy": "hybrid", "duration_seconds": 600},
            {"label": "private-B", "strategy": "solver-2025", "duration_seconds": 900},
        ],
        **changes,
    }
    result = api.post("/api/studies", headers=ADMIN, json=spec)
    assert result.status_code == 200, result.text
    body = result.json()
    return body["plan_id"], {"X-Negotiator-Token": body["participant_token"]}


def phase_context(api, pid, token):
    return api.get(f"/api/studies/{pid}", headers=token).json()["phase_id"]


def session_id(api, pid, token):
    return api.get(f"/api/studies/{pid}", headers=token).json()["current"]["config"]["session_id"]


def confirm_preferences(api, plan_id, token):
    state = api.get(f"/api/studies/{plan_id}", headers=token).json()
    issues = state["domain"]["issues"]
    result = api.post(
        f"/api/studies/{plan_id}/preferences",
        headers=token,
        json={
            "phase_id": phase_context(api, plan_id, token),
            "request_id": "prefs-" + str(state["sequence_index"]),
            "issues": [i["name"] for i in issues],
            "values": {i["name"]: i["values"] for i in issues},
        },
    )
    assert result.status_code == 200, result.text


def test_server_restricts_participant_payload_and_conductor_actions(client):
    pid, token = create(client)
    assert client.get("/api/studies", headers=token).status_code == 403
    assert client.get(f"/api/studies/{pid}").status_code == 403
    body = client.get(f"/api/studies/{pid}", headers=token).json()
    text = json.dumps(body)
    for forbidden in ("private-A", "private-B", "agent_profile", "participant_token", "test-admin"):
        assert forbidden not in text
    assert client.post(f"/api/studies/{pid}/start", headers=token).status_code == 403
    other, _ = create(client, participant_id="P002")
    assert client.get(f"/api/studies/{other}", headers=token).status_code == 403


def test_protocol_preview_is_authorized_and_uses_same_block_order_as_execution(client):
    data = {
        "order": "reversed",
        "conditions": [
            {"label": "practice A", "practice": True, "block": "A"},
            {"label": "A", "block": "A"},
            {"label": "B", "block": "B"},
        ],
    }
    assert client.post("/api/preview-study", json=data).status_code == 403
    response = client.post("/api/preview-study", json=data, headers=ADMIN)
    assert response.status_code == 200
    assert [item["label"] for item in response.json()["conditions"]] == ["B", "practice A", "A"]
    assert client.get("/api/studies", headers=ADMIN).json() == []


def test_preferences_then_start_has_immutable_config_and_correct_duration(client):
    pid, token = create(client)
    assert client.post(f"/api/studies/{pid}/start", headers=ADMIN).status_code == 409
    assert (
        client.post(
            f"/api/studies/{pid}/preferences",
            headers=token,
            json={
                "phase_id": phase_context(client, pid, token),
                "request_id": "bad",
                "issues": [],
                "values": {},
            },
        ).status_code
        == 400
    )
    confirm_preferences(client, pid, token)
    started = client.post(f"/api/studies/{pid}/start", headers=ADMIN)
    assert started.status_code == 200, started.text
    assert started.json()["current"]["config"]["duration_seconds"] == 600
    assert (
        client.patch(f"/api/studies/{pid}", headers=ADMIN, json={"title": "changed"}).status_code
        == 409
    )


def test_partial_text_has_no_offer_and_withdrawal_moves_through_two_sessions(client):
    pid, token = create(client)
    confirm_preferences(client, pid, token)
    client.post(f"/api/studies/{pid}/start", headers=ADMIN)
    partial = client.post(
        f"/api/studies/{pid}/command",
        headers=token,
        json={
            "request_id": "draft-1",
            "kind": "text",
            "text": "Hotel",
            "session_id": session_id(client, pid, token),
        },
    )
    assert partial.status_code == 200, partial.text
    assert not partial.json()["committed"]
    assert partial.json()["draft"]["missing"]
    assert partial.json()["state"]["current"]["offers"] == []
    withdrawn = client.post(
        f"/api/studies/{pid}/command",
        headers=token,
        json={
            "request_id": "withdraw-1",
            "kind": "withdraw",
            "session_id": session_id(client, pid, token),
        },
    )
    assert withdrawn.status_code == 200, withdrawn.text
    state = withdrawn.json()["state"]
    first_id = state["current"]["config"]["session_id"]
    assert state["phase"] == "result"
    assert state["current"]["status"] == "ended"
    assert state["current"]["outcome"]["reason"] == "withdrawal"
    assert (
        client.post(
            f"/api/studies/{pid}/next",
            headers=token,
            json={"phase_id": phase_context(client, pid, token), "request_id": "next-1"},
        ).json()["phase"]
        == "break"
    )
    assert (
        client.post(
            f"/api/studies/{pid}/next",
            headers=token,
            json={"phase_id": phase_context(client, pid, token), "request_id": "break-1"},
        ).json()["phase"]
        == "preferences"
    )
    confirm_preferences(client, pid, token)
    started = client.post(f"/api/studies/{pid}/start", headers=ADMIN).json()
    assert started["current"]["offers"] == []
    assert started["current"]["config"]["session_id"] != first_id
    assert started["current"]["config"]["duration_seconds"] == 900
    assert len(started["completed_sessions"]) == 1


def test_survey_scale_target_and_phase_are_validated(client):
    items = [
        {
            "id": "experience",
            "prompt": "Synthetic example rating",
            "minimum": 1,
            "maximum": 7,
            "phase": "post_session",
            "source": "synthetic example",
        }
    ]
    pid, token = create(client, preference_mode="assigned", surveys=items)
    client.post(f"/api/studies/{pid}/start", headers=ADMIN)
    client.post(
        f"/api/studies/{pid}/command",
        headers=token,
        json={"kind": "withdraw", "request_id": "w", "session_id": session_id(client, pid, token)},
    )
    phase = client.post(
        f"/api/studies/{pid}/next",
        headers=token,
        json={"phase_id": phase_context(client, pid, token), "request_id": "next"},
    ).json()
    assert phase["phase"] == "survey"
    assert phase["survey_phase"] == "post_session"
    assert (
        client.post(
            f"/api/studies/{pid}/survey",
            headers=token,
            json={
                "phase_id": phase_context(client, pid, token),
                "request_id": "survey-bad",
                "answers": {"experience": 9},
            },
        ).status_code
        == 400
    )
    result = client.post(
        f"/api/studies/{pid}/survey",
        headers=token,
        json={
            "phase_id": phase_context(client, pid, token),
            "request_id": "survey-ok",
            "answers": {"experience": 6},
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["phase"] == "break"


def test_command_retry_is_safe_after_terminal_state(client):
    pid, token = create(client, preference_mode="assigned")
    client.post(f"/api/studies/{pid}/start", headers=ADMIN)
    body = {"kind": "withdraw", "request_id": "w", "session_id": session_id(client, pid, token)}
    assert client.post(f"/api/studies/{pid}/command", headers=token, json=body).status_code == 200
    retry = client.post(f"/api/studies/{pid}/command", headers=token, json=body)
    assert retry.status_code == 200, retry.text
    assert retry.json()["state"]["current"]["outcome"]["reason"] == "withdrawal"


def test_restarting_server_recovers_records_as_interrupted(tmp_path):
    with TestClient(create_app(tmp_path, conductor_token="test-admin")) as first:
        pid, token = create(first, preference_mode="assigned")
        first.post(f"/api/studies/{pid}/start", headers=ADMIN)
    with TestClient(create_app(tmp_path, conductor_token="test-admin")) as second:
        result = second.get(f"/api/studies/{pid}", headers=token)
        assert result.status_code == 200
        assert result.json()["current"]["outcome"]["reason"] == "interrupted"


def test_invalid_configuration_and_unavailable_device_fail_before_start(client):
    assert (
        client.post(
            "/api/studies",
            headers=ADMIN,
            json={"study_id": "../bad", "participant_id": "P1", "conditions": []},
        ).status_code
        == 422
    )
    pid, _ = create(client, preference_mode="assigned", output="nao")
    start = client.post(f"/api/studies/{pid}/start", headers=ADMIN)
    assert start.status_code == 400
    assert "preflight" in start.json()["detail"].lower()


def test_preview_uses_the_session_profile_and_does_not_commit(client):
    pid, token = create(client, preference_mode="assigned")
    client.post(f"/api/studies/{pid}/start", headers=ADMIN)
    values = {
        "Accommodation": "Hotel",
        "Destination": "Rome",
        "Events": "Museum",
        "Season": "Summer",
    }
    before = client.get(f"/api/studies/{pid}", headers=token).json()
    result = client.post(
        f"/api/studies/{pid}/preview-offer", headers=token, json={"values": values}
    )
    assert result.status_code == 200, result.text
    assert set(result.json()) == {"utility", "provenance"}
    assert result.json()["provenance"] == "assigned"
    assert (
        client.get(f"/api/studies/{pid}", headers=token).json()["current"]["offers"]
        == before["current"]["offers"]
    )


def test_survey_retry_is_idempotent_and_presession_target_is_known(client):
    item = {"id": "q", "prompt": "Synthetic rating", "phase": "pre_session"}
    pid, token = create(client, preference_mode="assigned", surveys=[item])
    payload = {
        "phase_id": phase_context(client, pid, token),
        "request_id": "r1",
        "answers": {"q": 4},
    }
    first = client.post(f"/api/studies/{pid}/survey", headers=token, json=payload)
    assert first.status_code == 200, first.text
    retry = client.post(f"/api/studies/{pid}/survey", headers=token, json=payload)
    assert retry.status_code == 200, retry.text
    state = client.get(f"/api/studies/{pid}", headers=ADMIN).json()
    assert state["answers"][0]["target_session_id"] == f"{pid}-1"
    assert len(state["answers"]) == 1


def test_stale_command_cannot_attach_to_the_next_session(client):
    pid, token = create(client, preference_mode="assigned")
    first = client.post(f"/api/studies/{pid}/start", headers=ADMIN).json()
    first_id = first["current"]["config"]["session_id"]
    client.post(
        f"/api/studies/{pid}/command",
        headers=token,
        json={"kind": "withdraw", "request_id": "w", "session_id": first_id},
    )
    client.post(
        f"/api/studies/{pid}/next",
        headers=token,
        json={"phase_id": phase_context(client, pid, token), "request_id": "n1"},
    )
    client.post(
        f"/api/studies/{pid}/next",
        headers=token,
        json={"phase_id": phase_context(client, pid, token), "request_id": "n2"},
    )
    client.post(f"/api/studies/{pid}/start", headers=ADMIN)
    stale = client.post(
        f"/api/studies/{pid}/command",
        headers=token,
        json={"kind": "withdraw", "request_id": "late", "session_id": first_id},
    )
    assert stale.status_code == 409, stale.text
    assert client.get(f"/api/studies/{pid}", headers=token).json()["current"]["status"] == "active"


def test_visible_ack_refers_to_a_committed_action_in_the_same_session(client):
    pid, token = create(client, preference_mode="assigned", first_actor="agent")
    state = client.post(f"/api/studies/{pid}/start", headers=ADMIN).json()
    sid = state["current"]["config"]["session_id"]
    body = {"request_id": "visible", "session_id": sid, "event_id": f"{sid}:9999"}
    bad = client.post(f"/api/studies/{pid}/visible", headers=token, json=body)
    assert bad.status_code == 400
    offer = state["current"]["offers"][0]
    body["event_id"] = f"{sid}:{offer['sequence']}"
    first = client.post(f"/api/studies/{pid}/visible", headers=token, json=body)
    assert first.status_code == 200, first.text
    assert client.post(f"/api/studies/{pid}/visible", headers=token, json=body).status_code == 200


def test_manual_affect_requires_opt_in_and_preserves_independent_values(client):
    pid, token = create(client, preference_mode="assigned")
    client.post(f"/api/studies/{pid}/start", headers=ADMIN)
    body = {
        "request_id": "rating",
        "session_id": session_id(client, pid, token),
        "values": {"valence": 0.2, "arousal": -0.5, "emotions": {"Happy": 1}},
    }
    assert client.post(f"/api/studies/{pid}/affect", headers=token, json=body).status_code == 409
    pid, token = create(client, preference_mode="assigned", manual_affect=True)
    client.post(f"/api/studies/{pid}/start", headers=ADMIN)
    body["session_id"] = session_id(client, pid, token)
    result = client.post(f"/api/studies/{pid}/affect", headers=token, json=body)
    assert result.status_code == 200, result.text
    events = client.app.state.store._sessions[body["session_id"]].journal.read()
    observed = next(e for e in events if e.kind == "perception.observed")
    assert observed.payload["source"] == "participant_self_report"
    assert observed.payload["valence"] != observed.payload["arousal"]


def test_operator_commands_cannot_attach_to_a_later_phase(client):
    pid, token = create(client, preference_mode="assigned")
    before = phase_context(client, pid, ADMIN)
    client.post(f"/api/studies/{pid}/start", headers=ADMIN)
    for action in ("note", "terminate"):
        result = client.post(
            f"/api/studies/{pid}/{action}",
            headers=ADMIN,
            json={"phase_id": before, "request_id": "late-" + action, "text": "Delayed request"},
        )
        assert result.status_code == 409, result.text
    assert client.get(f"/api/studies/{pid}", headers=token).json()["phase"] == "active"


def test_conductor_cannot_claim_participant_visibility(client):
    pid, _ = create(client, preference_mode="assigned")
    client.post(f"/api/studies/{pid}/start", headers=ADMIN)
    result = client.post(
        f"/api/studies/{pid}/visible",
        headers=ADMIN,
        json={
            "session_id": session_id(client, pid, ADMIN),
            "event_id": "unknown",
            "request_id": "visible",
        },
    )
    assert result.status_code == 403, result.text
