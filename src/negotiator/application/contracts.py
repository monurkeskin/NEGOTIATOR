"""Validated configuration and command boundary for the local application."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from negotiator.application.session import validate_id
from negotiator.strategies import strategy_names


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Condition(StrictModel):
    label: str = Field(default="Condition A", min_length=1, max_length=120)
    strategy: str = "hybrid"
    duration_seconds: float = Field(default=600.0, gt=0, le=86400)
    practice: bool = False
    output: Literal["text", "avatar", "nao", "pepper", "qt"] | None = None
    domain: str | dict[str, Any] | None = None
    output_device: str | None = None
    human_profile: dict[str, Any] | None = None
    agent_profile: dict[str, Any] | None = None
    block: str | None = Field(default=None, min_length=1, max_length=100)
    break_after_seconds: float = Field(default=0.0, ge=0, le=86400)
    gestures: bool = True
    score_targets: dict[str, float] = Field(default_factory=dict)
    reward_minimums: dict[str, float] = Field(default_factory=dict)
    strategy_parameters: dict[str, Any] = Field(default_factory=dict)
    mood_policy: Literal["generic", "jennifer-2021", "jennifer-2022"] = "generic"
    mood_parameters: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_method_parameters(self) -> "Condition":
        from negotiator.strategies.settings import validate_parameters

        validate_parameters(self.strategy, self.strategy_parameters)
        from negotiator.domain.scoring import validate_thresholds

        validate_thresholds(self.score_targets)
        validate_thresholds(self.reward_minimums)
        from negotiator.interaction.mood import validate_mood_parameters

        validate_mood_parameters(self.mood_policy, self.mood_parameters)
        return self

    @field_validator("strategy")
    @classmethod
    def supported_strategy(cls, value: str) -> str:
        if value not in strategy_names():
            raise ValueError("Choose an installed strategy.")
        return value


class SurveyItem(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
    prompt: str = Field(min_length=1, max_length=2000)
    minimum: int = 1
    maximum: int = 7
    phase: Literal["pre_study", "pre_session", "post_session", "post_study"] = "post_session"
    required: bool = True
    include_practice: bool = False
    source: str = Field(default="researcher supplied", min_length=1, max_length=500)

    @model_validator(mode="after")
    def valid_scale(self) -> "SurveyItem":
        if self.minimum >= self.maximum or self.maximum - self.minimum > 100:
            raise ValueError("Survey scale must increase and contain at most 101 choices.")
        return self


class ProtocolRequirement(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
    description: str = Field(min_length=1, max_length=2000)
    path: str | None = None
    sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class ProtocolReference(StrictModel):
    id: str = Field(min_length=1, max_length=150)
    revision: str = Field(min_length=1, max_length=100)
    paper: str = Field(min_length=1, max_length=500)
    configuration_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    requirements: list[ProtocolRequirement] = Field(default_factory=list)


class PositionProfiles(StrictModel):
    human_profile: dict[str, Any]
    agent_profile: dict[str, Any]


class StudySpec(StrictModel):
    study_id: str = "study"
    participant_id: str = "P001"
    title: str = Field(default="Negotiation study", min_length=1, max_length=200)
    instructions: str = Field(
        default="Agree on an offer that meets your preferences before the time ends.",
        max_length=10000,
    )
    domain: str | dict[str, Any] = "holiday"
    preference_mode: Literal["elicited", "assigned"] = "elicited"
    human_profile: dict[str, Any] | None = None
    agent_profile: dict[str, Any] | None = None
    conditions: list[Condition] = Field(
        default_factory=lambda: [Condition()], min_length=1, max_length=20
    )
    order: Literal["as_entered", "reversed", "counterbalanced"] = "as_entered"
    participant_index: int = Field(default=1, ge=1)
    cohort: str = Field(default="default", min_length=1, max_length=100)
    seed: int = 42
    first_actor: Literal["human", "agent"] = "human"
    interaction_protocol: Literal["direct-offer", "ready-offer-response"] = "direct-offer"
    output: Literal["text", "avatar", "nao", "pepper", "qt"] = "text"
    speech_device: str | None = None
    perception_device: str | None = None
    manual_affect: bool = False
    synthetic: bool = False
    citation_ids: list[str] = Field(default_factory=list, max_length=30)
    purpose: Literal["demonstration", "published-protocol", "custom-study"] = "demonstration"
    protocol: ProtocolReference | None = None
    position_profiles: list[PositionProfiles] = Field(default_factory=list, max_length=20)
    surveys: list[SurveyItem] = Field(default_factory=list, max_length=200)

    @field_validator("study_id", "participant_id")
    @classmethod
    def valid_id(cls, value: str) -> str:
        validate_id(value)
        return value

    @model_validator(mode="after")
    def unique_items(self) -> "StudySpec":
        ids = [(item.phase, item.id) for item in self.surveys]
        if len(set(ids)) != len(ids):
            raise ValueError("Survey item IDs must be unique within a phase.")
        if self.purpose == "published-protocol" and self.protocol is None:
            raise ValueError("A published study needs a protocol reference.")
        if self.synthetic and self.purpose != "demonstration":
            raise ValueError("Synthetic runs must be labelled demonstration.")
        if self.interaction_protocol == "ready-offer-response" and self.first_actor != "human":
            raise ValueError("The notification protocol starts with a human offer.")
        if self.position_profiles and len(self.position_profiles) != sum(
            not condition.practice for condition in self.conditions
        ):
            raise ValueError("Position profiles must cover every main session.")
        if self.purpose != "demonstration" and self.preference_mode == "assigned":
            for condition in self.conditions:
                if not condition.practice and self.position_profiles:
                    continue
                if not all(
                    getattr(condition, key) or getattr(self, key)
                    for key in ("human_profile", "agent_profile")
                ):
                    raise ValueError("Assigned studies need explicit profiles for both actors.")
        if self.protocol:
            requirement_ids = [item.id for item in self.protocol.requirements]
            if len(set(requirement_ids)) != len(requirement_ids):
                raise ValueError("Protocol requirement IDs must be unique.")
        return self


class Request(StrictModel):
    request_id: str = Field(min_length=1, max_length=160)


class PhaseRequest(Request):
    phase_id: str = Field(min_length=1, max_length=160)


class PreferencesRequest(PhaseRequest):
    issues: list[str]
    values: dict[str, list[str | int]]


class CommandRequest(Request):
    session_id: str = Field(min_length=1, max_length=80)
    kind: Literal["offer", "text", "accept", "withdraw", "ready", "reject"]
    expected_offer_count: int | None = Field(default=None, ge=0)
    values: dict[str, str | int] | None = None
    text: str | None = Field(default=None, max_length=10000)
    offer_id: str | None = None


class SurveyRequest(PhaseRequest):
    answers: dict[str, int | None]


class NoteRequest(PhaseRequest):
    text: str = Field(min_length=1, max_length=10000)


class SessionRequest(Request):
    session_id: str = Field(min_length=1, max_length=80)


class VisibleRequest(SessionRequest):
    event_id: str = Field(min_length=1, max_length=100)


class AffectRequest(SessionRequest):
    values: dict[str, Any]


class CaptureRequest(SessionRequest):
    kind: Literal["speech", "perception"]
