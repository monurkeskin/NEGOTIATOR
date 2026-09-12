"""One session owns its clock, journal and state. UI and agents submit the same actions."""

import copy
import json
import re
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from negotiator import __version__
from negotiator.domain import Actor, Bid, Preference
from negotiator.domain.actions import Accept, Action, End, Offer, validate_accept
from negotiator.domain.importers import from_dict as domain_from_dict
from negotiator.domain.importers import to_dict as domain_to_dict
from negotiator.domain.preferences import finite_number
from negotiator.domain.values import check_actor
from negotiator.events.journal import Event, Journal, JournalError, digest
from negotiator.events.projection import SessionState, replay
from negotiator.interaction.dialogue import dialogue_phase
from negotiator.strategies.policies import categorical_probabilities

from .clock import SessionClock


def validate_id(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", value):
        raise ValueError("Use 1–80 letters, digits, hyphens or underscores for record IDs.")


@dataclass(frozen=True)
class SessionConfig:
    study_id: str
    participant_id: str
    session_id: str
    duration_seconds: float = 600.0
    strategy: str = "hybrid"
    seed: int = 42
    first_actor: Actor = "human"
    condition: str = "default"
    cohort: str = "default"
    practice: bool = False
    synthetic: bool = False
    sequence_index: int = 1
    config_version: int = 1
    purpose: str = "demonstration"
    protocol_id: str | None = None
    protocol_revision: str | None = None
    citation_ids: tuple[str, ...] = ()
    interaction_protocol: str = "direct-offer"
    gestures: bool = True
    score_targets: dict[str, float] = field(default_factory=dict)
    reward_minimums: dict[str, float] = field(default_factory=dict)
    strategy_parameters: dict[str, Any] = field(default_factory=dict)
    mood_policy: str = "generic"
    mood_parameters: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        from negotiator.domain.scoring import validate_thresholds

        validate_thresholds(self.score_targets)
        validate_thresholds(self.reward_minimums)
        for value in (self.study_id, self.participant_id, self.session_id):
            validate_id(value)
        if finite_number(self.duration_seconds, "Duration") <= 0:
            raise ValueError("Duration must be positive seconds.")
        check_actor(self.first_actor)
        if (
            type(self.seed) is not int
            or type(self.sequence_index) is not int
            or self.sequence_index < 1
        ):
            raise ValueError("Seed and sequence index must be integers; sequence begins at 1.")


def action_payload(action: Action) -> dict[str, Any]:
    if isinstance(action, Offer):
        return {
            "kind": "offer",
            "actor": action.actor,
            "offer_id": action.offer_id,
            "bid": action.bid.to_dict(),
        }
    if isinstance(action, Accept):
        return {"kind": "accept", "actor": action.actor, "offer_id": action.offer_id}
    return {"kind": "end", "actor": action.actor, "reason": action.reason}


class Session:
    def __init__(self, journal: Journal, *, now: Callable[[], float] = time.monotonic):
        self.journal = journal
        self._events = journal.read()
        self._state = replay(self._events)
        if not self._events:
            raise JournalError("The session has no committed start event.")
        self.config = SessionConfig(**self._state.config)
        self.domain = domain_from_dict(self._state.domain)
        self.human_profile = Preference.from_dict(self.domain, self._state.human_profile)
        self.agent_profile = Preference.from_dict(self.domain, self._state.agent_profile)
        self.clock = SessionClock(self.config.duration_seconds, now=now)
        self._lock = threading.RLock()
        self._closers: list[Callable[[], None]] = []
        self._requests = {e.request_id: e for e in self._events}

    @classmethod
    def create(
        cls,
        root: Path,
        config: SessionConfig,
        human: Preference,
        agent: Preference,
        *,
        now: Callable[[], float] = time.monotonic,
    ) -> "Session":
        if human.domain != agent.domain:
            raise ValueError("Both profiles must describe the same domain.")
        from negotiator.software import runtime_identity

        payload = {
            "software": runtime_identity(),
            "config": asdict(config),
            "domain": domain_to_dict(human.domain),
            "human_profile": human.to_dict(),
            "agent_profile": agent.to_dict(),
        }
        manifest = {
            "schema_version": 1,
            "framework_version": __version__,
            "configuration_sha256": digest(payload),
            "configuration": payload,
            "time_semantics": "monotonic elapsed seconds; normalized by duration_seconds",
            "bid_perspective": "human",
            "raw_recordings": False,
        }
        directory = Path(root) / config.study_id / config.participant_id / config.session_id
        journal = Journal.create(directory, manifest)
        journal.append(
            session_id=config.session_id,
            kind="session.started",
            payload=payload,
            request_id="session-start",
            fingerprint=digest(payload),
            elapsed_seconds=0.0,
            expected_sequence=1,
        )
        return cls(journal, now=now)

    @classmethod
    def open(cls, path: Path) -> "Session":
        session = cls(Journal(path))
        manifest = json.loads(path.with_name("manifest.json").read_text(encoding="utf-8"))
        payload = session._events[0].payload
        if (
            digest(payload) != manifest["configuration_sha256"]
            or digest(manifest["configuration"]) != manifest["configuration_sha256"]
        ):
            raise JournalError("Manifest configuration hash does not match the start event.")
        if session._state.status == "active":
            session._commit(
                "session.ended",
                {
                    "reason": "interrupted",
                    "actor": None,
                    "agreement": None,
                    "utilities": None,
                    "detail": "server_restart",
                    "missing_reason": "elapsed_time_across_restart_unknown",
                },
                "server-interruption",
                digest({"reason": "server_restart"}),
                elapsed=session._state.elapsed_seconds,
            )
            session.clock.stop()
        return session

    @property
    def state(self) -> SessionState:
        return copy.deepcopy(self._state)

    @property
    def pending(self) -> Offer | None:
        if not self._state.offers or self._state.status != "active":
            return None
        last = self._state.offers[-1]
        return Offer(last["offer_id"], last["actor"], Bid(last["bid"]))

    def _duplicate(self, request_id: str, fingerprint: str) -> Event | None:
        event = self._requests.get(request_id)
        if event is not None and event.to_dict()["request_fingerprint"] != fingerprint:
            raise ValueError("This request ID was already used for a different command.")
        return event

    def _commit(
        self,
        kind: str,
        payload: dict[str, Any],
        request_id: str,
        fingerprint: str,
        *,
        elapsed: float | None = None,
    ) -> Event:
        event = self.journal.append(
            session_id=self.config.session_id,
            kind=kind,
            payload=payload,
            request_id=request_id,
            fingerprint=fingerprint,
            elapsed_seconds=self.clock.elapsed_seconds if elapsed is None else elapsed,
            expected_sequence=self._state.sequence + 1,
        )
        self._events.append(event)
        self._state = replay(self._events)
        self._requests[request_id] = event
        return event

    def _utilities(self, bid: Bid) -> dict[str, float]:
        return {
            "human": self.human_profile.utility(bid, "human"),
            "agent": self.agent_profile.utility(bid, "agent"),
        }

    def submit(
        self, action: Action, request_id: str, *, diagnostics: dict[str, Any] | None = None
    ) -> Event:
        with self._lock:
            payload = action_payload(action)
            fingerprint = digest(payload)
            duplicate = self._duplicate(request_id, fingerprint)
            if duplicate is not None:
                return duplicate
            if self._state.status != "active":
                raise ValueError("Session has ended; create a new session to negotiate again.")
            if self.clock.expired:
                return self._end("deadline", None, None, request_id, fingerprint)
            if isinstance(action, End):
                return self._end(
                    action.reason,
                    action.actor,
                    None,
                    request_id,
                    fingerprint,
                    diagnostics=diagnostics,
                )
            if action.actor != self._state.next_actor:
                raise ValueError("It is the other actor's turn.")
            if isinstance(action, Accept):
                pending = self.pending
                validate_accept(action, pending)
                assert pending is not None
                profile = self.human_profile if action.actor == "human" else self.agent_profile
                if profile.utility(pending.bid, action.actor) < profile.reservation:
                    raise ValueError("Agreement is below the accepting actor's reservation.")
                return self._end(
                    "agreement",
                    action.actor,
                    pending,
                    request_id,
                    fingerprint,
                    diagnostics=diagnostics,
                )
            self.domain.validate(action.bid)
            if any(o["offer_id"] == action.offer_id for o in self._state.offers):
                raise ValueError("Offer IDs must be unique within the session.")
            payload.pop("kind")
            payload["utilities"] = self._utilities(action.bid)
            payload["round"] = len(self._state.offers) + 1
            if diagnostics is not None:
                payload["diagnostics"] = diagnostics
            elapsed = self.clock.elapsed_seconds
            if elapsed >= self.config.duration_seconds:
                return self._end("deadline", None, None, request_id, fingerprint)
            return self._commit(
                "offer.committed", payload, request_id, fingerprint, elapsed=elapsed
            )

    def _end(
        self,
        reason: str,
        actor: str | None,
        agreement: Offer | None,
        request_id: str,
        fingerprint: str,
        *,
        diagnostics: dict[str, Any] | None = None,
    ) -> Event:
        from negotiator.domain.scoring import reward_scores

        utilities = self._utilities(agreement.bid) if agreement else None
        elapsed = self.clock.elapsed_seconds
        if elapsed >= self.config.duration_seconds:
            reason, actor, agreement, utilities = "deadline", None, None, None
        event = self._commit(
            "session.ended",
            {
                "reason": reason,
                "actor": actor,
                "offer_id": agreement.offer_id if agreement else None,
                "agreement": agreement.bid.to_dict() if agreement else None,
                "utilities": utilities,
                "payoffs": reward_scores(utilities, self.config.reward_minimums, reason),
                "scoring_revision": "threshold-reward-v1",
                **({"diagnostics": diagnostics} if diagnostics is not None else {}),
            },
            request_id,
            fingerprint,
            elapsed=elapsed,
        )
        self.clock.stop()
        closers, self._closers = self._closers, []
        for index, close in enumerate(closers):
            try:
                close()
            except Exception as exc:
                self._commit(
                    "resource.close_failed",
                    {"resource": index, "error": type(exc).__name__},
                    f"resource-close-{index}",
                    digest({"resource": index}),
                    elapsed=self._state.elapsed_seconds,
                )
        return event

    def tick(self) -> None:
        with self._lock:
            if self._state.status == "active" and self.clock.expired:
                self._end("deadline", None, None, "deadline", digest({"reason": "deadline"}))

    def on_close(self, close: Callable[[], None]) -> None:
        with self._lock:
            if self._state.status != "active":
                raise ValueError("Cannot attach a resource to an ended session.")
            self._closers.append(close)

    def record(self, kind: str, payload: dict[str, Any], request_id: str) -> Event:
        """Record ancillary observations; negotiation transitions use submit()."""
        if kind not in (
            "operator.note",
            "perception.observed",
            "input.draft",
            "survey.response",
            "presentation.attempted",
            "presentation.delivered",
            "presentation.failed",
            "presentation.visible",
            "protocol.phase",
        ):
            raise ValueError("Unsupported ancillary event kind.")
        with self._lock:
            fingerprint = digest({"kind": kind, "payload": payload})
            duplicate = self._duplicate(request_id, fingerprint)
            if duplicate is not None:
                return duplicate
            elapsed = (
                self.clock.elapsed_seconds
                if self._state.status == "active"
                else self._state.elapsed_seconds
            )
            return self._commit(kind, payload, request_id, fingerprint, elapsed=elapsed)

    def note(self, text: str, request_id: str) -> Event:
        if not text.strip():
            raise ValueError("An operator note cannot be empty.")
        return self.record("operator.note", {"text": text}, request_id)

    def perception(self, values: dict[str, Any], request_id: str) -> Event:
        if not values.get("source"):
            raise ValueError("An observation needs a source.")
        emotions = values.get("emotions")
        if emotions is not None:
            if not isinstance(emotions, dict):
                raise ValueError("Unknown categorical emotion labels.")
            categorical_probabilities(emotions)
            count = values.get("frame_count", 1)
            if type(count) is not int or count < 1:
                raise ValueError("Categorical frame_count must be a positive integer.")
        for name in ("valence", "arousal"):
            value = values.get(name)
            if value is None:
                if not values.get("missing_reason"):
                    raise ValueError("Absent affect needs a missing_reason.")
            elif not -1 <= finite_number(value, name) <= 1:
                raise ValueError(f"{name} must be in [-1, 1].")
        return self.record("perception.observed", values, request_id)

    def snapshot(self, *, role: str = "conductor") -> dict[str, Any]:
        with self._lock:
            self.tick()
            result = self._state.to_dict()
            result["interaction_phase"] = (
                dialogue_phase(self._events)
                if self.config.interaction_protocol == "ready-offer-response"
                else "direct-offer"
            )
            elapsed = (
                self.clock.elapsed_seconds
                if self._state.status == "active"
                else self._state.elapsed_seconds
            )
            result["terminal_event_id"] = (
                next(
                    (
                        e.to_dict()["event_id"]
                        for e in reversed(self.journal.read())
                        if e.kind == "session.ended"
                    ),
                    None,
                )
                if self._state.status == "ended"
                else None
            )
            result["elapsed_seconds"] = elapsed
            result["elapsed_fraction"] = min(1.0, elapsed / self.config.duration_seconds)
            result["remaining_seconds"] = max(0.0, self.config.duration_seconds - elapsed)
            if role == "participant":
                result.pop("agent_profile")
                result["config"] = {
                    key: value
                    for key, value in result["config"].items()
                    if key in ("session_id", "duration_seconds", "practice", "sequence_index")
                }
                for key in ("score_targets", "reward_minimums"):
                    result["config"][key] = {
                        a: v for a, v in getattr(self.config, key).items() if a == "human"
                    }
                if result["outcome"] and result["outcome"].get("payoffs") is not None:
                    result["outcome"]["payoffs"] = {"human": result["outcome"]["payoffs"]["human"]}
                for offer in result["offers"]:
                    offer.pop("diagnostics", None)
                    offer["utilities"] = {"human": offer["utilities"]["human"]}
                if result["outcome"]:
                    result["outcome"].pop("diagnostics", None)
                if result["outcome"] and result["outcome"]["utilities"] is not None:
                    result["outcome"]["utilities"] = {
                        "human": result["outcome"]["utilities"]["human"]
                    }
            elif role != "conductor":
                raise ValueError("Unknown session view.")
            return result
