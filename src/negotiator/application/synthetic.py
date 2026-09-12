"""Short synthetic protocol execution for installation checks and companion examples."""

from pathlib import Path
from typing import Any
from uuid import uuid4

from .contracts import CommandRequest, StudySpec, SurveyRequest
from .studies import StudyStore


def run_study(spec: StudySpec, output: Path) -> dict[str, Any]:
    if spec.purpose != "demonstration":
        raise ValueError("Synthetic execution requires a demonstration configuration.")
    if (
        spec.output not in ("text", "avatar")
        or any(c.output not in (None, "text", "avatar") for c in spec.conditions)
        or spec.speech_device
        or spec.perception_device
    ):
        raise ValueError(
            "Synthetic run needs a device-free configuration; select the companion synthetic.json."
        )
    if spec.preference_mode != "assigned":
        raise ValueError("Synthetic configurations must explicitly use assigned profiles.")
    spec = spec.model_copy(
        update={"synthetic": True, "participant_id": "SYNTHETIC-" + uuid4().hex[:8]}
    )
    simulated_time = [0.0]
    store = StudyStore(output, now=lambda: simulated_time[0])
    pid = store.create(spec)["plan_id"]
    try:
        for _ in range(500):
            simulated_time[0] += 1.0
            state = store.snapshot(pid)
            phase = state["phase"]
            if phase == "complete":
                return {
                    "synthetic": True,
                    "plan_id": pid,
                    "completed_sessions": state["completed_sessions"],
                }
            if phase == "ready":
                store.start(pid)
            elif phase in ("result", "break"):
                if phase == "break":
                    simulated_time[0] += state["break_remaining_seconds"]
                store.next(pid, uuid4().hex, state["phase_id"])
            elif phase == "survey":
                store.survey(
                    pid,
                    SurveyRequest(
                        request_id=uuid4().hex,
                        phase_id=state["phase_id"],
                        answers={
                            item["id"]: (item["minimum"] + item["maximum"]) // 2
                            for item in state["survey_items"]
                        },
                    ),
                )
            elif phase == "active":
                sid = state["current"]["config"]["session_id"]
                session = store._sessions[sid]
                pending = session.pending
                if state["current"]["interaction_phase"] == "notification":
                    request = CommandRequest(
                        request_id=uuid4().hex,
                        session_id=sid,
                        kind="ready",
                        expected_offer_count=len(session.state.offers),
                    )
                elif (
                    pending
                    and pending.actor == "agent"
                    and len(session.state.offers) >= 3
                    and session.human_profile.utility(pending.bid)
                    >= session.human_profile.reservation
                ):
                    request = CommandRequest(
                        request_id=uuid4().hex,
                        session_id=sid,
                        kind="accept",
                        offer_id=pending.offer_id,
                    )
                elif len(session.state.offers) >= 12:
                    request = CommandRequest(
                        request_id=uuid4().hex, session_id=sid, kind="withdraw"
                    )
                elif state["current"]["interaction_phase"] == "response":
                    assert pending is not None
                    request = CommandRequest(
                        request_id=uuid4().hex,
                        session_id=sid,
                        kind="reject",
                        offer_id=pending.offer_id,
                        expected_offer_count=len(session.state.offers),
                    )
                else:
                    bids = sorted(
                        session.domain.bids(), key=session.human_profile.utility, reverse=True
                    )
                    bid = bids[
                        min(len(bids) - 1, len(session.state.offers) * max(1, len(bids) // 24))
                    ]
                    request = CommandRequest(
                        request_id=uuid4().hex, session_id=sid, kind="offer", values=bid.to_dict()
                    )
                store.command(pid, request)
            else:
                raise ValueError("Unsupported synthetic protocol phase: " + phase)
        raise RuntimeError("Synthetic protocol exceeded its bounded step count.")
    finally:
        store.shutdown()
