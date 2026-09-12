"""Presentation follows durable actions; uncertain delivery never creates a new bid."""

import queue
import threading
from time import monotonic
from typing import Any

from negotiator.adapters.process import BridgeError, ProcessBridge
from negotiator.application.session import Session
from negotiator.domain import Bid
from negotiator.events.journal import Event
from negotiator.strategies.policies import time_target

from .mood import JenniferMoodPolicy, MoodPolicy


def planned_mood(session: Session, target: Event) -> str | None:
    """Rebuild presentation state from committed offers; retries cannot consume it."""
    config = session.config
    generic = MoodPolicy(session.agent_profile)
    jennifer = (
        JenniferMoodPolicy(
            int(config.mood_policy[-4:]),
            warning_fraction=config.mood_parameters["warning_fraction"],
            reservation=session.agent_profile.reservation,
        )
        if config.mood_policy != "generic"
        else None
    )
    pending = None
    mood = None
    for event in session.journal.read():
        if event.sequence > target.sequence:
            break
        if event.kind == "offer.committed" and event.payload["actor"] == "human":
            pending = event
        elif (
            event.kind == "offer.committed" and event.payload["actor"] == "agent"
        ) or event.kind == "session.ended":
            if (
                jennifer
                and event.kind == "session.ended"
                and event.payload["reason"] != "agreement"
            ):
                mood = "Times up" if event.payload["reason"] == "deadline" else None
            elif pending is not None:
                bid = Bid(pending.payload["bid"])
                t = min(
                    1.0,
                    max(0.0, float(event.to_dict()["elapsed_seconds"]) / config.duration_seconds),
                )
                if jennifer:
                    incoming = session.agent_profile.utility(bid, "agent")
                    proposed = (
                        session.agent_profile.utility(Bid(event.payload["bid"]), "agent")
                        if event.kind == "offer.committed"
                        else incoming
                    )
                    mild = (
                        time_target(t, 0.94, 0.5, 0.4)
                        if config.strategy == "tsbt"
                        else proposed * config.mood_parameters["mild_multiplier"]
                    )
                    mood = jennifer.observe(incoming, t, next_utility=proposed, mild_threshold=mild)
                else:
                    mood = generic.observe(
                        bid, float(pending.to_dict()["elapsed_seconds"]) / config.duration_seconds
                    )
            pending = None
    return mood


class Presenter:
    def __init__(self, session: Session, bridge: ProcessBridge):
        self.session, self.bridge = session, bridge
        self._lock = threading.RLock()

    def deliver(self, event: Event) -> None:
        with self._lock:
            eid = event.to_dict()["event_id"]
            attempt = f"present-{eid}"
            if any(e.request_id == attempt for e in self.session.journal.read()):
                return
            payload = event.payload
            mood = planned_mood(self.session, event)
            if event.kind == "offer.committed":
                prefix = "Your share: " if self.session.domain.allocation else "I propose: "
                text = (
                    prefix
                    + "; ".join(f"{key}: {value}" for key, value in payload["bid"].items())
                    + "."
                )
            else:
                text = (
                    "We have an agreement."
                    if payload["reason"] == "agreement"
                    else "The negotiation has ended."
                )
            command: dict[str, Any] = {
                "event_id": eid,
                "text": text,
                "mood": mood,
                "gesture": self.bridge.config.gestures.get(mood or "")
                if self.session.config.gestures
                else None,
                "face": self.bridge.config.faces.get(mood or ""),
            }
            self.session.record("presentation.attempted", command, attempt)
            started = monotonic()
            try:
                result = self.bridge.request(
                    self.session.config.session_id, eid, "present", command
                )
                if result.get("delivered") is not True:
                    raise BridgeError("Device did not acknowledge delivery.")
                self.session.record(
                    "presentation.delivered",
                    {
                        "event_id": eid,
                        "receipt": result,
                        "request_elapsed_seconds": monotonic() - started,
                    },
                    f"delivered-{eid}",
                )
            except BridgeError as exc:
                self.session.record(
                    "presentation.failed",
                    {
                        "event_id": eid,
                        "error": str(exc),
                        "delivery_status": "unknown",
                        "request_elapsed_seconds": monotonic() - started,
                    },
                    f"failed-{eid}",
                )


class PresentationWorker:
    def __init__(self, session: Session, bridge: ProcessBridge):
        self.session, self.bridge = session, bridge
        self.presenter = Presenter(session, bridge)
        self._queue: queue.Queue[Event | None] = queue.Queue()
        self._queued: set[str] = set()
        self._lock = threading.RLock()
        self._finished = False
        self.error: str | None = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        session.on_close(self.finish)

    def publish(self) -> None:
        with self._lock:
            if self._finished:
                return
            for event in self.session.journal.read():
                relevant = event.kind == "session.ended" or (
                    event.kind == "offer.committed" and event.payload["actor"] == "agent"
                )
                eid = event.to_dict()["event_id"]
                if relevant and eid not in self._queued:
                    self._queued.add(eid)
                    self._queue.put(event)

    def finish(self) -> None:
        with self._lock:
            if not self._finished:
                self.publish()
                self._finished = True
                self._queue.put(None)

    def _run(self) -> None:
        try:
            while (event := self._queue.get()) is not None:
                self.presenter.deliver(event)
        except (OSError, RuntimeError, ValueError) as exc:
            self.error = str(exc)
        finally:
            self.bridge.close()
