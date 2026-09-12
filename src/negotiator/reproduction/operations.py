"""Named calculations with no access to the expected paper scores."""

import random
from collections import defaultdict
from dataclasses import dataclass
from math import fsum
from typing import Annotated, Any, Literal

from pydantic import Field

from negotiator.analysis.metrics import reference_points
from negotiator.application.contracts import StrictModel
from negotiator.domain import Preference
from negotiator.domain.importers import from_dict
from negotiator.strategies.policies import behavior_target, emotion_effect, time_target


@dataclass
class Computation:
    results: dict[str, Any]
    rows: list[dict[str, Any]]
    points: list[tuple[float, float]] | None = None


class ProfileInput(StrictModel):
    domain: dict[str, Any]
    human_profile: dict[str, Any]
    agent_profile: dict[str, Any]


def profile_space(data: dict[str, Any], parameters: dict[str, Any]) -> Computation:
    if parameters:
        raise ValueError("profile-space has no analysis parameters.")
    data = ProfileInput.model_validate(data).model_dump()
    domain = from_dict(data["domain"])
    human = Preference.from_dict(domain, data["human_profile"])
    agent = Preference.from_dict(domain, data["agent_profile"])
    rows: list[dict[str, Any]] = [
        {
            **bid.to_dict(),
            "human_utility": human.utility(bid),
            "agent_utility": agent.utility(bid, "agent"),
        }
        for bid in domain.bids()
    ]
    points = [(row["human_utility"], row["agent_utility"]) for row in rows]
    geometry = reference_points(points, (human.reservation, agent.reservation))
    results = {
        "outcome_count": len(rows),
        "human_min": min(p[0] for p in points),
        "human_max": max(p[0] for p in points),
        "agent_min": min(p[1] for p in points),
        "agent_max": max(p[1] for p in points),
        "pareto_count": len(geometry["pareto"]),
        "social_welfare": geometry["social_welfare"],
        "raw_nash_product": geometry["raw_nash_product"],
        "surplus_nash_product": geometry["surplus_nash_product"],
    }
    return Computation(results, rows, points)


class SessionRow(StrictModel):
    study_id: str = Field(min_length=1)
    participant_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    condition: str = Field(min_length=1)
    cohort: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    rounds: int = Field(ge=0, strict=True)
    utility: float | None = Field(ge=0, le=1)
    practice: bool = False


class SessionInput(StrictModel):
    records: list[SessionRow]


class PairedParameters(StrictModel):
    conditions: tuple[str, str]
    minimum_rounds: int = Field(default=0, ge=0, strict=True)
    bootstrap_samples: int = Field(default=2000, ge=100, le=20000, strict=True)
    seed: int = Field(default=42, strict=True)
    confidence_level: float = Field(default=0.95, gt=0, lt=1)
    domain_groups: dict[str, str] = Field(default_factory=dict)


def percentile(sorted_values: list[float], fraction: float) -> float:
    position = (len(sorted_values) - 1) * fraction
    low = int(position)
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (position - low) * (sorted_values[high] - sorted_values[low])


def paired_summary(data: dict[str, Any], parameters: dict[str, Any]) -> Computation:
    params = PairedParameters.model_validate(parameters)
    left, right = params.conditions
    if left == right:
        raise ValueError("Paired conditions must be distinct.")
    groups: dict[tuple[str, str, str], dict[str, dict[str, SessionRow]]] = defaultdict(dict)
    seen = set()
    ignored = 0
    for row in SessionInput.model_validate(data).records:
        identity = (row.study_id, row.participant_id, row.session_id)
        if identity in seen:
            raise ValueError("Duplicate session identity in analysis input.")
        seen.add(identity)
        if row.practice or row.condition not in params.conditions:
            ignored += 1
            continue
        domain = params.domain_groups.get(row.domain, row.domain)
        group = groups[(row.study_id, row.cohort, domain)]
        participant_rows = group.setdefault(row.participant_id, {})
        if row.condition in participant_rows:
            raise ValueError(
                "Duplicate participant-condition observation; do not count offers as people."
            )
        participant_rows[row.condition] = row
    summaries, excluded, rows = [], [], []
    for (study, cohort, domain), participants in sorted(groups.items()):
        differences = []
        for participant, pair in sorted(participants.items()):
            reason = None
            if set(pair) != set(params.conditions):
                reason = "missing_condition"
            elif any(row.utility is None for row in pair.values()):
                reason = "missing_utility"
            elif any(row.rounds < params.minimum_rounds for row in pair.values()):
                reason = "below_prespecified_round_threshold"
            if reason:
                excluded.append(
                    {
                        "study_id": study,
                        "cohort": cohort,
                        "domain": domain,
                        "participant_id": participant,
                        "reason": reason,
                    }
                )
                continue
            left_utility, right_utility = pair[left].utility, pair[right].utility
            assert left_utility is not None and right_utility is not None
            differences.append(left_utility - right_utility)
        n = len(differences)
        ci = None
        if n >= 2:
            rng = random.Random(params.seed)
            bootstrap = sorted(
                fsum(rng.choice(differences) for _ in range(n)) / n
                for _ in range(params.bootstrap_samples)
            )
            tail = (1 - params.confidence_level) / 2
            ci = [percentile(bootstrap, tail), percentile(bootstrap, 1 - tail)]
        summary = {
            "study_id": study,
            "cohort": cohort,
            "domain": domain,
            "complete_pairs": n,
            "mean_difference": fsum(differences) / n if n else None,
            "ci": ci,
            "ci_missing_reason": "fewer_than_two_complete_participants" if ci is None else None,
            "confidence_level": params.confidence_level,
            "interval_method": "percentile_bootstrap_over_participants",
            "contrast": f"{left} minus {right}",
        }
        summaries.append(summary)
        rows.append(
            {
                **{key: value for key, value in summary.items() if key != "ci"},
                "ci_lower": ci[0] if ci else None,
                "ci_upper": ci[1] if ci else None,
            }
        )
    return Computation(
        {
            "independent_unit": "participant",
            "complete_pairs": sum(g["complete_pairs"] for g in summaries),
            "groups": summaries,
            "excluded_pairs": excluded,
            "ignored_rows": ignored,
            "parameters": params.model_dump(),
        },
        rows,
    )


class TimeArguments(StrictModel):
    t: float = Field(ge=0, le=1)
    p0: float = 0.9
    p1: float = 0.7
    p2: float = 0.4


class BehaviorArguments(StrictModel):
    previous: float = Field(ge=0, le=1)
    differences: list[Annotated[float, Field(ge=-1, le=1)]]
    t: float = Field(ge=0, le=1)
    awareness: float = Field(default=0, ge=0, le=1)
    emotion: float = Field(default=0, ge=-1, le=1)
    multiplier: float = Field(default=1, ge=0)


class MethodCase(StrictModel):
    id: str = Field(min_length=1)
    operation: Literal["time", "solver-behavior", "categorical-effect"]
    arguments: dict[str, Any]


class MethodInput(StrictModel):
    cases: list[MethodCase] = Field(min_length=1)


def method_vectors(data: dict[str, Any], parameters: dict[str, Any]) -> Computation:
    if parameters:
        raise ValueError("method-vectors parameters belong in each input case.")
    rows: list[dict[str, Any]] = []
    for case in MethodInput.model_validate(data).cases:
        operation = case.operation
        arguments = case.arguments
        value: float | None
        if operation == "time":
            value = time_target(**TimeArguments.model_validate(arguments).model_dump())
        elif operation == "solver-behavior":
            value = behavior_target(**BehaviorArguments.model_validate(arguments).model_dump())
        elif operation == "categorical-effect":
            value = emotion_effect(arguments)
        else:
            raise ValueError("Unsupported method vector operation.")
        rows.append({"case": case.id, "operation": operation, "value": value})
    if len({row["case"] for row in rows}) != len(rows):
        raise ValueError("Method vector case IDs must be distinct.")
    return Computation(
        {"case_count": len(rows), **{row["case"]: row["value"] for row in rows}}, rows
    )


OPERATIONS = {
    "profile-space": profile_space,
    "paired-summary": paired_summary,
    "method-vectors": method_vectors,
}
