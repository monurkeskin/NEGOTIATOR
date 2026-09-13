"""Pure protocol ordering and evidence checks, independent of GUI and device SDKs."""

import hashlib
from pathlib import Path
from typing import Any, Literal

from negotiator.domain import Preference
from negotiator.domain.importers import from_dict as domain_from_dict
from negotiator.events.journal import digest
from negotiator.examples import builtin_domain

from .contracts import StudySpec


def ordered_conditions(spec: StudySpec) -> list[dict[str, Any]]:
    conditions = [condition.model_dump() for condition in spec.conditions]
    reverse = spec.order == "reversed" or (
        spec.order == "counterbalanced" and spec.participant_index % 2 == 0
    )
    introductory = []
    blocks: dict[tuple[str, str | int], list[dict[str, Any]]] = {}
    previous_block = None
    for index, condition in enumerate(conditions):
        label = condition["block"]
        key = ("block", label) if label is not None else ("session", index)
        if key in blocks and key != previous_block:
            raise ValueError("Protocol blocks must be contiguous.")
        previous_block = key
        if label is None and condition["practice"]:
            introductory.append(condition)
        else:
            blocks.setdefault(key, []).append(condition)
    if reverse:
        conditions = introductory + [c for block in reversed(list(blocks.values())) for c in block]
    position = 0
    for condition in conditions:
        if not condition["practice"]:
            if spec.position_profiles:
                condition.update(spec.position_profiles[position].model_dump())
            position += 1
    return conditions


def protocol_digest(spec: StudySpec) -> str:
    """Identify scientific configuration independently of IDs and local asset paths."""
    excluded = {
        "study_id",
        "participant_id",
        "participant_index",
        "title",
        "protocol",
        "synthetic",
        "purpose",
        "speech_device",
        "perception_device",
    }
    data = spec.model_dump(exclude=excluded)
    for condition in data["conditions"]:
        condition.pop("output_device", None)
    # Absent scale descriptions retain the fingerprint of older configurations.
    for item in data["surveys"]:
        for key in ("minimum_label", "maximum_label"):
            if item.get(key) is None:
                item.pop(key, None)
    return digest(data)


def validate_profiles(spec: StudySpec, conditions: list[dict[str, Any]]) -> None:
    for condition in conditions:
        configured = condition.get("domain") or spec.domain
        domain = (
            builtin_domain(configured)
            if isinstance(configured, str)
            else domain_from_dict(configured)
        )
        for key in ("human_profile", "agent_profile"):
            profile = condition.get(key) or getattr(spec, key)
            if profile is not None:
                Preference.from_dict(domain, profile)


def protocol_readiness(
    spec: StudySpec,
    *,
    verify_hashes: bool = True,
    operation: Literal["execution", "historical-analysis"] = "execution",
) -> list[dict[str, str]]:
    """Missing evidence is visible; possession of a file is not empirical validation."""
    if operation not in ("execution", "historical-analysis"):
        raise ValueError("Choose execution or historical-analysis readiness.")
    if spec.purpose != "published-protocol":
        return []
    assert spec.protocol is not None
    issues = []
    if spec.protocol.configuration_sha256 is None:
        issues.append(
            {"id": "configuration", "reason": "The published protocol configuration is not pinned."}
        )
    elif protocol_digest(spec) != spec.protocol.configuration_sha256:
        issues.append(
            {
                "id": "configuration",
                "reason": "Scientific configuration differs from the pinned protocol.",
            }
        )
    for requirement in spec.protocol.requirements:
        if requirement.required_for != operation:
            continue
        if not requirement.path or not requirement.sha256:
            reason = "Required evidence is not supplied: " + requirement.description
        else:
            path = Path(requirement.path).expanduser()
            try:
                if verify_hashes:
                    with path.open("rb") as stream:
                        actual = hashlib.file_digest(stream, "sha256").hexdigest()
                    reason = (
                        "" if actual == requirement.sha256 else "Required evidence hash differs."
                    )
                else:
                    reason = "" if path.is_file() else "Required evidence file is unavailable."
            except OSError:
                reason = "Required evidence file is unavailable."
        if reason:
            issues.append({"id": requirement.id, "reason": reason})
    return issues
