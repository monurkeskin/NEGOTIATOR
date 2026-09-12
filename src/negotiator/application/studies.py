"""Study sequencing and durable configuration, shared by the local web views."""

import copy
import json
import os
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import uuid4

from negotiator import __version__
from negotiator.adapters.process import BridgeConfig, BridgeError, ProcessBridge
from negotiator.application.contracts import (
    CommandRequest,
    PreferencesRequest,
    StudySpec,
    SurveyRequest,
)
from negotiator.domain import Preference, ranked_preferences
from negotiator.domain.actions import Accept, Action, End, Offer
from negotiator.domain.importers import from_dict as domain_from_dict
from negotiator.domain.importers import to_dict as domain_to_dict
from negotiator.events.journal import Journal, digest
from negotiator.examples import builtin_domain, example_profiles
from negotiator.interaction.dialogue import handle_dialogue
from negotiator.interaction.input import Interpreter
from negotiator.interaction.presentation import PresentationWorker
from negotiator.strategies import create_agent

from .clock import SessionClock
from .protocol import ordered_conditions, protocol_readiness, validate_profiles
from .runner import SessionRunner
from .session import Session, SessionConfig


class PhaseError(ValueError):
    """A valid command is unavailable in the current protocol phase."""


def write_json(path: Path, data: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp-" + uuid4().hex)
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class StudyStore:
    def __init__(
        self,
        root: Path,
        conductor_token: str | None = None,
        devices: dict[str, BridgeConfig] | None = None,
        *,
        now: Callable[[], float] = time.monotonic,
    ):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._now = now
        self._break_clocks: dict[str, SessionClock] = {}
        self._restarted_breaks: set[str] = set()
        self._credentials_path = self.root / "access.json"
        self._credentials = (
            json.loads(self._credentials_path.read_text(encoding="utf-8"))
            if self._credentials_path.exists()
            else {"participants": {}}
        )
        self.conductor_token = (
            conductor_token or self._credentials.get("conductor") or secrets.token_urlsafe(32)
        )
        self._credentials["conductor"] = self.conductor_token
        write_json(self._credentials_path, self._credentials)
        self._plans: dict[str, dict[str, Any]] = {}
        self._journals: dict[str, Journal] = {}
        self._events: dict[str, list[Any]] = {}
        self._sessions: dict[str, Session] = {}
        self._runners: dict[str, SessionRunner] = {}
        self._interpreters: dict[str, Interpreter] = {}
        self.devices = devices or {}
        self._prepared_devices: dict[str, dict[str, ProcessBridge]] = {}
        self._session_devices: dict[str, dict[str, ProcessBridge]] = {}
        self._presenters: dict[str, PresentationWorker] = {}
        self.errors: dict[str, str] = {}
        for path in (self.root / "_plans").glob("*/events.jsonl"):
            journal = Journal(path)
            events = journal.read()
            if not events:
                continue
            state = events[-1].payload["state"]
            pid = state["plan_id"]
            self._plans[pid], self._journals[pid], self._events[pid] = state, journal, events
            if state["phase"] == "break" and state.get("break_duration_seconds", 0) > 0:
                self._break_clocks[pid] = SessionClock(state["break_duration_seconds"], now=now)
                self._restarted_breaks.add(pid)
            for session_id in state["session_ids"]:
                session_path = self._session_path(state, session_id)
                self._sessions[session_id] = Session.open(session_path)
            self._recover_pending(pid)
            self._refresh(pid)

    @staticmethod
    def _phase_id(state: dict[str, Any]) -> str:
        return f"{state['plan_id']}:{state['sequence_index']}:{state['phase']}:{state['survey_phase'] or ''}"

    def _check_phase(self, state: dict[str, Any], phase_id: str) -> None:
        if phase_id != self._phase_id(state):
            raise PhaseError("This command belongs to an earlier protocol phase. Refresh the view.")

    def _recover_pending(self, pid: str) -> None:
        state = self._state(pid)
        sid = f"{pid}-{state['sequence_index']}"
        path = self._session_path(state, sid)
        if sid in state["session_ids"] or not path.exists():
            return
        session = Session.open(path)
        if session.config.session_id != sid:
            raise ValueError("Pending session identity does not match its study.")
        self._sessions[sid] = session
        state["session_ids"].append(sid)
        state.update(current_session_id=sid, phase="active")
        self._save(state, {"kind": "recovered_start", "session_id": sid}, f"recover-{sid}")

    def role(self, token: str | None, plan_id: str | None = None) -> str:
        if token and secrets.compare_digest(token, self.conductor_token):
            return "conductor"
        participant = self._credentials["participants"].get(plan_id)
        if token and participant and secrets.compare_digest(token, participant):
            return "participant"
        raise PermissionError("This view requires its own access link.")

    def _state(self, plan_id: str) -> dict[str, Any]:
        if plan_id not in self._plans:
            raise KeyError("Study record not found.")
        return copy.deepcopy(self._plans[plan_id])

    def _session_path(self, state: dict[str, Any], session_id: str) -> Path:
        spec = state["spec"]
        return (
            self.root
            / str(spec["study_id"])
            / str(spec["participant_id"])
            / session_id
            / "events.jsonl"
        )

    def _duplicate(self, pid: str, request_id: str, command: dict[str, Any]) -> bool:
        for event in self._events[pid]:
            if event.request_id == request_id:
                if event.to_dict()["request_fingerprint"] != digest(command):
                    raise ValueError("Request ID was used for a different command.")
                return True
        return False

    def _save(self, state: dict[str, Any], command: dict[str, Any], request_id: str) -> None:
        pid = state["plan_id"]
        event = self._journals[pid].append(
            session_id=pid,
            kind="study.changed",
            payload={"state": state, "command": command},
            request_id=request_id,
            fingerprint=digest(command),
            elapsed_seconds=0.0,
            expected_sequence=len(self._events[pid]) + 1,
        )
        self._events[pid].append(event)
        previous = self._plans.get(pid, {})
        if state["phase"] == "break" and previous.get("phase") != "break":
            duration = state.get("break_duration_seconds", 0)
            if duration > 0:
                self._break_clocks[pid] = SessionClock(duration, now=self._now)
        elif state["phase"] != "break":
            self._break_clocks.pop(pid, None)
            self._restarted_breaks.discard(pid)
        self._plans[pid] = copy.deepcopy(state)

    @staticmethod
    def _questions(state: dict[str, Any], phase: str) -> list[dict[str, Any]]:
        practice = state["conditions"][state["sequence_index"] - 1]["practice"]
        return [
            item
            for item in state["spec"]["surveys"]
            if item["phase"] == phase
            and (
                phase not in ("pre_session", "post_session")
                or not practice
                or item.get("include_practice", False)
            )
        ]

    def _survey_or(self, state: dict[str, Any], phase: str, after: str) -> None:
        if self._questions(state, phase):
            state.update(phase="survey", survey_phase=phase, after_survey=after)
        else:
            state["phase"] = after

    def _prepare(self, state: dict[str, Any]) -> None:
        condition = state["conditions"][state["sequence_index"] - 1]
        spec = state["spec"]
        configured = condition.get("domain") or spec["domain"]
        domain = (
            builtin_domain(configured)
            if isinstance(configured, str)
            else domain_from_dict(configured)
        )
        state["domain"] = domain_to_dict(domain)
        human, agent = example_profiles(domain)
        for name, fallback in (("human_profile", human), ("agent_profile", agent)):
            data = condition.get(name) or spec.get(name)
            state[name] = (Preference.from_dict(domain, data) if data else fallback).to_dict()
        if state["spec"]["preference_mode"] == "elicited":
            state["phase"] = "preferences"
        else:
            self._survey_or(state, "pre_session", "ready")

    def create(self, spec: StudySpec) -> dict[str, Any]:
        with self._lock:
            domain = (
                builtin_domain(spec.domain)
                if isinstance(spec.domain, str)
                else domain_from_dict(spec.domain)
            )
            human, agent = example_profiles(domain)
            if spec.human_profile is not None:
                human = Preference.from_dict(domain, spec.human_profile)
            if spec.agent_profile is not None:
                agent = Preference.from_dict(domain, spec.agent_profile)
            pid = uuid4().hex
            conditions = ordered_conditions(spec)
            validate_profiles(spec, conditions)
            state = {
                "schema_version": 1,
                "plan_id": pid,
                "spec": spec.model_dump(),
                "config_version": 1,
                "conditions": conditions,
                "sequence_index": 1,
                "domain": domain_to_dict(domain),
                "human_profile": human.to_dict(),
                "agent_profile": agent.to_dict(),
                "phase": "preferences",
                "survey_phase": None,
                "after_survey": None,
                "answers": [],
                "session_ids": [],
                "current_session_id": None,
            }
            if self._questions(state, "pre_study"):
                self._survey_or(state, "pre_study", "prepare")
            else:
                self._prepare(state)
            journal = Journal.create(
                self.root / "_plans" / pid,
                {
                    "schema_version": 1,
                    "framework_version": __version__,
                    "configuration_sha256": digest(state),
                    "configuration": state,
                },
            )
            self._journals[pid], self._events[pid] = journal, []
            self._save(state, {"kind": "create"}, "create")
            token = secrets.token_urlsafe(32)
            self._credentials["participants"][pid] = token
            write_json(self._credentials_path, self._credentials)
            return {"plan_id": pid, "participant_token": token, "state": self.snapshot(pid)}

    def update(self, pid: str, changes: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            state = self._state(pid)
            if state["session_ids"]:
                raise PhaseError(
                    "Started configurations are immutable; create another study record."
                )
            # Before start, the title/instructions can be revised without invalidating elicited ranks.
            if set(changes) - {"title", "instructions"}:
                raise ValueError("Create a new configuration to change domain, agents or timing.")
            spec = StudySpec.model_validate({**state["spec"], **changes})
            state["spec"] = spec.model_dump()
            state["config_version"] += 1
            self._save(
                state, {"kind": "edit", "changes": changes}, f"edit-{state['config_version']}"
            )
            return self.snapshot(pid)

    def preferences(self, pid: str, request: PreferencesRequest) -> None:
        with self._lock:
            command = {"kind": "preferences", **request.model_dump()}
            if self._duplicate(pid, request.request_id, command):
                return
            state = self._state(pid)
            if state["phase"] != "preferences":
                raise PhaseError("Preferences can only be confirmed before the session starts.")
            self._check_phase(state, request.phase_id)
            domain = domain_from_dict(state["domain"])
            human, agent = ranked_preferences(domain, request.issues, request.values)
            state["human_profile"], state["agent_profile"] = human.to_dict(), agent.to_dict()
            self._survey_or(state, "pre_session", "ready")
            self._save(state, command, request.request_id)

    def start(self, pid: str) -> None:
        with self._lock:
            self._recover_pending(pid)
            self._refresh(pid)
            state = self._state(pid)
            if state["phase"] != "ready":
                raise PhaseError(
                    "Complete preferences and scheduled questionnaires before starting."
                )
            spec = state["spec"]
            self.preflight(pid)
            domain = domain_from_dict(state["domain"])
            human, own = (
                Preference.from_dict(domain, state[key])
                for key in ("human_profile", "agent_profile")
            )
            index = state["sequence_index"]
            condition = state["conditions"][index - 1]
            # Expensive bid-space/model setup precedes the session's monotonic clock.
            agent = create_agent(
                condition["strategy"],
                own,
                seed=spec["seed"] + index - 1,
                parameters=condition.get("strategy_parameters", {}),
            )
            session_id = f"{pid}-{index}"
            session = Session.create(
                self.root,
                SessionConfig(
                    spec["study_id"],
                    spec["participant_id"],
                    session_id,
                    duration_seconds=condition["duration_seconds"],
                    strategy=condition["strategy"],
                    seed=spec["seed"] + index - 1,
                    first_actor=spec["first_actor"],
                    condition=condition["label"],
                    cohort=spec["cohort"],
                    practice=condition["practice"],
                    synthetic=spec.get("synthetic", False),
                    sequence_index=index,
                    config_version=state["config_version"],
                    purpose=spec.get("purpose", "demonstration"),
                    protocol_id=(spec.get("protocol") or {}).get("id"),
                    protocol_revision=(spec.get("protocol") or {}).get("revision"),
                    citation_ids=tuple(spec.get("citation_ids", [])),
                    interaction_protocol=spec.get("interaction_protocol", "direct-offer"),
                    gestures=condition.get("gestures", True),
                    score_targets=condition.get("score_targets", {}),
                    reward_minimums=condition.get("reward_minimums", {}),
                    strategy_parameters=condition.get("strategy_parameters", {}),
                    mood_policy=condition.get("mood_policy", "generic"),
                    mood_parameters=condition.get("mood_parameters", {}),
                ),
                human,
                own,
                now=self._now,
            )
            self._sessions[session_id] = session
            self._runners[session_id] = SessionRunner(session, agent=agent)
            self._interpreters[session_id] = Interpreter(domain)
            device_set = self._prepared_devices.pop(pid, {})
            self._session_devices[session_id] = device_set
            session.record(
                "protocol.phase",
                {
                    "plan_id": pid,
                    "phase": "session_start",
                    "configuration_sha256": digest(state),
                    "devices": {name: device.receipt for name, device in device_set.items()},
                },
                "protocol-start",
            )
            if "output" in device_set:
                self._presenters[session_id] = PresentationWorker(session, device_set["output"])
            for name, device in device_set.items():
                if name != "output":
                    session.on_close(device.close)
            state["session_ids"].append(session_id)
            state["current_session_id"] = session_id
            state["phase"] = "active"
            self._save(state, {"kind": "start", "session_id": session_id}, f"start-{index}")
            self._runners[session_id].respond()
            if session_id in self._presenters:
                self._presenters[session_id].publish()
            self._refresh(pid)

    def _refresh(self, pid: str) -> None:
        state = self._state(pid)
        sid = state["current_session_id"]
        if (
            sid
            and state["phase"] == "active"
            and self._sessions[sid].snapshot()["status"] == "ended"
        ):
            state["phase"] = "result"
            self._save(state, {"kind": "result", "session_id": sid}, f"result-{sid}")
        if sid and sid in self._presenters:
            presenter = self._presenters[sid]
            failed = any(
                e.kind == "presentation.failed" for e in self._sessions[sid].journal.read()
            )
            if presenter.error or failed:
                self.errors[pid] = (
                    presenter.error
                    or "Device delivery is unknown. Inspect the record and terminate if the protocol cannot continue."
                )

    def command(self, pid: str, request: CommandRequest) -> dict[str, Any]:
        with self._lock:
            state = self._state(pid)
            sid = state["current_session_id"]
            if not sid:
                raise PhaseError("Start the session before sending an action.")
            if request.session_id != sid:
                raise PhaseError(
                    "This action belongs to another session. Refresh the participant view."
                )
            session = self._sessions[sid]
            if (
                request.kind != "withdraw"
                and state["phase"] == "active"
                and self._presentation_pending(sid)
            ):
                raise PhaseError("Wait for the selected device to finish presenting the offer.")
            body = request.model_dump()
            try:
                handled, kind = handle_dialogue(session, body)
            except ValueError as exc:
                raise PhaseError(str(exc)) from exc
            if handled:
                return {"committed": False, "draft": None}
            if kind != request.kind:
                request = request.model_copy(update={"kind": kind})
            # A draft observation preserves the complete submitted text and request
            # identity even when no formal offer is committed.
            draft = None
            action: Action
            if request.kind == "text":
                parser = self._interpreters.setdefault(sid, Interpreter(session.domain))
                draft = parser.interpret(request.text or "")
                session.record(
                    "input.draft", {**asdict(draft), "command": body}, f"input-{request.request_id}"
                )
                if not draft.complete and draft.intent != "accept":
                    return {"committed": False, "draft": asdict(draft)}
                if draft.intent == "accept":
                    action = Accept("human", request.offer_id or "missing-offer-id")
                else:
                    action = Offer(f"human-{request.request_id}", "human", draft.bid)
            elif request.kind == "offer":
                action = Offer(
                    f"human-{request.request_id}", "human", session.domain.bid(request.values or {})
                )
            elif request.kind == "accept":
                action = Accept("human", request.offer_id or "missing-offer-id")
            else:
                action = End("human", "withdrawal")
            event = session.submit(action, request.request_id)
            if sid in self._runners:
                self._runners[sid].respond()
            if sid in self._presenters:
                self._presenters[sid].publish()
            if draft and draft.complete:
                self._interpreters[sid].current_text = ""
            self._refresh(pid)
            return {
                "committed": True,
                "event_id": event.to_dict()["event_id"],
                "draft": asdict(draft) if draft else None,
            }

    def _after_session(self, state: dict[str, Any]) -> None:
        if state["sequence_index"] < len(state["conditions"]):
            state["phase"] = "break"
            condition = state["conditions"][state["sequence_index"] - 1]
            state["break_duration_seconds"] = condition.get("break_after_seconds", 0)
        else:
            self._survey_or(state, "post_study", "complete")

    def next(self, pid: str, request_id: str, phase_id: str) -> None:
        with self._lock:
            command = {"kind": "next", "phase_id": phase_id}
            if self._duplicate(pid, request_id, command):
                return
            self._refresh(pid)
            state = self._state(pid)
            self._check_phase(state, phase_id)
            if state["phase"] == "result":
                if self._questions(state, "post_session"):
                    self._survey_or(state, "post_session", "after_session")
                else:
                    self._after_session(state)
            elif state["phase"] == "break":
                clock = self._break_clocks.get(pid)
                if clock and clock.remaining_seconds > 0:
                    raise PhaseError("Complete the scheduled break before continuing.")
                state["sequence_index"] += 1
                state["current_session_id"] = None
                self._prepare(state)
            else:
                raise PhaseError("Finish the current protocol phase before continuing.")
            self._save(state, command, request_id)

    def survey(self, pid: str, request: SurveyRequest) -> None:
        with self._lock:
            command = {"kind": "survey", **request.model_dump()}
            if self._duplicate(pid, request.request_id, command):
                return
            state = self._state(pid)
            if state["phase"] != "survey":
                raise PhaseError("There is no questionnaire scheduled now.")
            self._check_phase(state, request.phase_id)
            phase = state["survey_phase"]
            items = self._questions(state, phase)
            if set(request.answers) - {i["id"] for i in items}:
                raise ValueError("Questionnaire response contains unknown items.")
            for item in items:
                value = request.answers.get(item["id"])
                if value is None and item["required"]:
                    raise ValueError(f"Answer the required item: {item['id']}.")
                if value is not None and not item["minimum"] <= value <= item["maximum"]:
                    raise ValueError(f"Answer outside the configured scale: {item['id']}.")
            sid = (
                f"{pid}-{state['sequence_index']}"
                if phase == "pre_session"
                else state["current_session_id"]
                if phase == "post_session"
                else None
            )
            payload = {
                "phase": phase,
                "target_session_id": sid,
                "sequence_index": state["sequence_index"],
                "items": items,
                "answers": request.answers,
            }
            state["answers"].append(payload)
            after = state["after_survey"]
            state["survey_phase"] = None
            if after == "prepare":
                self._prepare(state)
            elif after == "after_session":
                self._after_session(state)
            else:
                state["phase"] = after
            self._save(state, command, request.request_id)

    def terminate(
        self, pid: str, text: str, request_id: str, *, phase_id: str | None = None
    ) -> None:
        with self._lock:
            state = self._state(pid)
            if phase_id is not None:
                self._check_phase(state, phase_id)
            sid = state["current_session_id"]
            if not sid or state["phase"] != "active":
                raise PhaseError("There is no active session to terminate.")
            self._sessions[sid].note(text, f"reason-{request_id}")
            self._sessions[sid].submit(End("human", "operator"), request_id)
            self._refresh(pid)

    def note(self, pid: str, text: str, request_id: str, *, phase_id: str | None = None) -> None:
        with self._lock:
            state = self._state(pid)
            if phase_id is not None:
                self._check_phase(state, phase_id)
            sid = state["current_session_id"]
            if sid:
                self._sessions[sid].note(text, request_id)
            else:
                self._save(state, {"kind": "note", "text": text}, request_id)

    def preview_offer(self, pid: str, values: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            state = self._state(pid)
            domain = domain_from_dict(state["domain"])
            human = Preference.from_dict(domain, state["human_profile"])
            return {"utility": human.utility(domain.bid(values)), "provenance": human.provenance}

    def snapshot(self, pid: str, role: str = "conductor") -> dict[str, Any]:
        with self._lock:
            self._refresh(pid)
            state = self._state(pid)
            spec = state["spec"]
            sid = state["current_session_id"]
            result = {
                "plan_id": pid,
                "title": spec["title"],
                "instructions": spec["instructions"],
                "participant_id": spec["participant_id"],
                "phase": state["phase"],
                "break_remaining_seconds": self._break_clocks[pid].remaining_seconds
                if pid in self._break_clocks
                else 0,
                "break_restarted": pid in self._restarted_breaks,
                "phase_id": self._phase_id(state),
                "sequence_index": state["sequence_index"],
                "session_count": len(state["conditions"]),
                "domain": state["domain"],
                "human_profile": state["human_profile"],
                "current": self._sessions[sid].snapshot(role=role) if sid else None,
                "survey_phase": state["survey_phase"],
                "survey_items": self._questions(state, state["survey_phase"])
                if state["survey_phase"]
                else [],
                "output": state["conditions"][state["sequence_index"] - 1].get("output")
                or spec["output"],
                "manual_affect": spec.get("manual_affect", False),
                "speech_available": bool(spec.get("speech_device")),
                "perception_available": bool(spec.get("perception_device")),
                "presentation_pending": bool(sid and self._presentation_pending(sid)),
                "error": self.errors.get(pid)
                if role == "conductor"
                else (
                    "A device or recording problem needs conductor attention."
                    if self.errors.get(pid)
                    else None
                ),
                "completed_sessions": [],
            }
            for previous in state["session_ids"]:
                session = self._sessions[previous]
                if session.state.status == "ended":
                    result["completed_sessions"].append(
                        {
                            "session_id": previous,
                            "sequence_index": session.config.sequence_index,
                            "practice": session.config.practice,
                            "outcome": session.snapshot(role=role)["outcome"],
                        }
                    )
            if role == "conductor":
                result.update(
                    purpose=spec.get("purpose", "demonstration"),
                    readiness=protocol_readiness(
                        StudySpec.model_validate(spec), verify_hashes=False
                    ),
                    spec=spec,
                    conditions=state["conditions"],
                    agent_profile=state["agent_profile"],
                    participant_token=self._credentials["participants"].get(pid),
                    config_version=state["config_version"],
                    answers=state["answers"],
                )
            return result

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [self.snapshot(pid) for pid in self._plans]

    def tick(self) -> None:
        with self._lock:
            for pid in list(self._plans):
                try:
                    self._refresh(pid)
                except (OSError, RuntimeError, ValueError) as exc:
                    self.errors[pid] = str(exc)

    def shutdown(self) -> None:
        with self._lock:
            for session in self._sessions.values():
                if session.state.status == "active":
                    session.submit(End("agent", "interrupted"), "server-shutdown")
            for devices in self._prepared_devices.values():
                for device in devices.values():
                    device.close()
        for presenter in self._presenters.values():
            presenter.thread.join(timeout=presenter.bridge.config.timeout_seconds + 2)

    def preflight(self, pid: str) -> dict[str, Any]:
        with self._lock:
            state = self._state(pid)
            if state["phase"] == "active":
                raise PhaseError("Run preflight before the session starts.")
            problems = protocol_readiness(StudySpec.model_validate(state["spec"]))
            if problems:
                raise ValueError(
                    "Protocol preflight: "
                    + "; ".join(item["id"] + ": " + item["reason"] for item in problems)
                )
            if pid in self._prepared_devices:
                return {key: device.receipt for key, device in self._prepared_devices[pid].items()}
            spec = state["spec"]
            output = (
                state["conditions"][state["sequence_index"] - 1].get("output") or spec["output"]
            )
            selected = {
                "output": (
                    state["conditions"][state["sequence_index"] - 1].get("output_device") or output
                )
                if output not in ("text", "avatar")
                else None,
                "speech": spec.get("speech_device"),
                "perception": spec.get("perception_device"),
            }
            prepared: dict[str, ProcessBridge] = {}
            try:
                for role, name in selected.items():
                    if name:
                        if name not in self.devices:
                            raise ValueError(
                                "Device preflight needs a configured local bridge: " + name
                            )
                        device = ProcessBridge(self.devices[name])
                        prepared[role] = device
                        receipt = device.connect()
                        capability = {
                            "output": "speech",
                            "speech": "transcript",
                            "perception": "affect",
                        }[role]
                        if capability not in receipt["capabilities"]:
                            raise BridgeError("Selected device lacks capability: " + capability)
                self._prepared_devices[pid] = prepared
                return {key: device.receipt for key, device in prepared.items()}
            except (OSError, ValueError, BridgeError):
                for device in prepared.values():
                    device.close()
                raise

    def _presentation_pending(self, sid: str) -> bool:
        if sid not in self._presenters:
            return False
        session = self._sessions[sid]
        events = session.journal.read()
        agent_offers = [
            e for e in events if e.kind == "offer.committed" and e.payload["actor"] == "agent"
        ]
        if not agent_offers:
            return False
        eid = agent_offers[-1].to_dict()["event_id"]
        return not any(
            e.kind == "presentation.delivered" and e.payload["event_id"] == eid for e in events
        )

    def _current_session(self, pid: str, sid: str, *, active: bool = True) -> Session:
        state = self._state(pid)
        if state["current_session_id"] != sid:
            raise PhaseError("This input belongs to another session.")
        session = self._sessions[sid]
        if active and session.snapshot()["status"] != "active":
            raise PhaseError("This session has ended.")
        return session

    def visible(self, pid: str, sid: str, event_id: str) -> None:
        with self._lock:
            session = self._current_session(pid, sid, active=False)
            if not any(
                e.to_dict()["event_id"] == event_id
                and e.kind in ("offer.committed", "session.ended")
                for e in session.journal.read()
            ):
                raise ValueError("Visibility can only acknowledge a committed action.")
            session.record(
                "presentation.visible",
                {
                    "event_id": event_id,
                    "source": "participant_browser",
                    "meaning": "rendered_in_visible_document",
                },
                f"visible-{event_id}",
            )

    def affect(self, pid: str, sid: str, values: dict[str, Any], request_id: str) -> None:
        with self._lock:
            if not self._state(pid)["spec"].get("manual_affect"):
                raise PhaseError("Manual affect input is not configured for this study.")
            session = self._current_session(pid, sid)
            session.perception({**values, "source": "participant_self_report"}, request_id)

    def capture(self, pid: str, sid: str, kind: str, request_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._current_session(pid, sid)
            device = self._session_devices.get(sid, {}).get(kind)
            if device is None:
                raise PhaseError("No device is configured for this input.")
        # Device waits never hold the study lock or stop the session's clock.
        result = device.request(sid, request_id, "listen" if kind == "speech" else "observe", {})
        with self._lock:
            self._current_session(pid, sid)
            if kind == "speech":
                draft = Interpreter(session.domain).interpret(result["transcript"])
                session.record(
                    "input.draft",
                    {**asdict(draft), "source": result.get("source"), "device": device.receipt},
                    f"capture-{request_id}",
                )
                return {"draft": asdict(draft)}
            session.perception({**result, "device": device.receipt}, request_id)
            return {"saved": True}
