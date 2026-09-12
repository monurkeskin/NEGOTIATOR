"""Notification, offer and response stages from the published Jennifer protocol."""

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from negotiator.events.journal import Event

if TYPE_CHECKING:
    from negotiator.application.session import Session


def dialogue_phase(events: Sequence[Event]) -> str:
    if any(event.kind == "session.ended" for event in events):
        return "complete"
    offers = [event for event in events if event.kind == "offer.committed"]
    for event in reversed(events):
        if (
            event.kind == "protocol.phase"
            and "dialogue_phase" in event.payload
            and event.payload["offer_count"] == len(offers)
        ):
            return str(event.payload["dialogue_phase"])
    if not offers:
        return "notification"
    return "response" if offers[-1].payload["actor"] == "agent" else "agent_response"


def handle_dialogue(session: "Session", command: dict[str, Any]) -> tuple[bool, str]:
    kind = str(command["kind"])
    if session.config.interaction_protocol == "direct-offer":
        if kind in ("ready", "reject"):
            raise ValueError("Notification commands require the ready-offer-response protocol.")
        return False, kind
    if kind == "withdraw":
        return False, kind
    events = session.journal.read()
    request_id = "dialogue-" + command["request_id"]
    previous = next((event for event in events if event.request_id == request_id), None)
    if previous:
        if previous.payload["command"] != command:
            raise ValueError("Request ID was used for another dialogue command.")
        return True, kind
    phase = dialogue_phase(events)
    if kind == "text":
        text = " ".join((command.get("text") or "").strip().lower().rstrip(".!").split())
        if phase == "notification" and text in ("ready", "i am ready", "i'm ready"):
            kind = "ready"
        elif phase == "response" and text in ("yes", "i accept", "accept"):
            kind = "accept"
        elif phase == "response" and text in ("no", "reject", "i reject"):
            kind = "reject"
    count = len(session.state.offers)
    if kind in ("ready", "reject"):
        if command.get("expected_offer_count") != count:
            raise ValueError("This dialogue command belongs to an earlier offer. Refresh the view.")
        if (kind == "ready" and phase != "notification") or (
            kind == "reject" and phase != "response"
        ):
            raise ValueError("This dialogue command is unavailable in the current stage.")
        if kind == "reject" and (
            session.pending is None or command.get("offer_id") != session.pending.offer_id
        ):
            raise ValueError("Reject must refer to the currently displayed offer.")
        session.record(
            "protocol.phase",
            {
                "dialogue_phase": "offer" if kind == "ready" else "notification",
                "offer_count": count,
                "command": command,
            },
            request_id,
        )
        return True, kind
    if kind == "accept" and phase == "response":
        return False, kind
    if kind in ("offer", "text") and phase == "offer":
        return False, kind
    raise ValueError("Follow the ready, offer, then accept/reject stages before continuing.")
