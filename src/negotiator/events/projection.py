"""Deterministic projection shared by live sessions and offline replay."""

import copy
from dataclasses import asdict, dataclass, field
from typing import Any

from .journal import Event, JournalError


@dataclass
class SessionState:
    config: dict[str, Any] = field(default_factory=dict)
    domain: dict[str, Any] = field(default_factory=dict)
    human_profile: dict[str, Any] = field(default_factory=dict)
    agent_profile: dict[str, Any] = field(default_factory=dict)
    status: str = "prepared"
    next_actor: str = "human"
    offers: list[dict[str, Any]] = field(default_factory=list)
    outcome: dict[str, Any] | None = None
    sequence: int = 0
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def replay(events: list[Event]) -> SessionState:
    state = SessionState()
    for event in events:
        record = event.to_dict()
        if event.sequence != state.sequence + 1:
            raise JournalError("Projection received events out of order.")
        payload = event.payload
        if event.kind == "session.started":
            if state.status != "prepared":
                raise JournalError("Session was started twice.")
            state.config = payload["config"]
            state.domain = payload["domain"]
            state.human_profile = payload["human_profile"]
            state.agent_profile = payload["agent_profile"]
            state.next_actor = state.config["first_actor"]
            state.status = "active"
        elif event.kind == "offer.committed":
            if state.status != "active":
                raise JournalError("Offer outside active session.")
            state.offers.append(
                {
                    **payload,
                    "elapsed_seconds": record["elapsed_seconds"],
                    "sequence": event.sequence,
                }
            )
            state.next_actor = "agent" if payload["actor"] == "human" else "human"
        elif event.kind == "session.ended":
            if state.status != "active":
                raise JournalError("Duplicate or unstarted session ending.")
            state.status = "ended"
            state.outcome = payload
        elif state.status == "prepared":
            raise JournalError("Session journal has no start event.")
        state.sequence = event.sequence
        if state.outcome is None or event.kind == "session.ended":
            state.elapsed_seconds = record["elapsed_seconds"]
    return copy.deepcopy(state)
