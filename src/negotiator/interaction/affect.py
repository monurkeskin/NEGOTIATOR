"""Categorical observations in the interval from an agent offer to the human response."""

from collections.abc import Sequence
from dataclasses import dataclass
from math import fsum
from typing import Any

from negotiator.events.journal import Event
from negotiator.strategies.policies import categorical_probabilities


@dataclass(frozen=True)
class AffectWindow:
    probabilities: dict[str, float] | None
    receipt: dict[str, Any]


def response_window(events: Sequence[Event]) -> AffectWindow:
    offers = [
        (index, event) for index, event in enumerate(events) if event.kind == "offer.committed"
    ]
    receipt: dict[str, Any] = {
        "revision": "response-window-v1",
        "sample_count": 0,
        "frame_count": 0,
        "aggregation": "frame_weighted_arithmetic_mean",
        "missing_reason": None,
    }
    if not offers or offers[-1][1].payload["actor"] != "human":
        return AffectWindow(None, {**receipt, "missing_reason": "no_human_response"})
    end, response = offers[-1]
    preceding = [
        (index, event) for index, event in offers[:-1] if event.payload["actor"] == "agent"
    ]
    if not preceding:
        return AffectWindow(None, {**receipt, "missing_reason": "no_preceding_agent_offer"})
    start, offer = preceding[-1]
    receipt.update(
        start_event_id=offer.to_dict()["event_id"],
        end_event_id=response.to_dict()["event_id"],
        start_basis="offer_committed",
    )
    for index in range(start + 1, end):
        event = events[index]
        if (
            event.kind == "presentation.attempted"
            and event.payload.get("event_id") == offer.to_dict()["event_id"]
        ):
            start = index
            receipt.update(
                start_event_id=event.to_dict()["event_id"], start_basis="presentation_attempted"
            )
            break
    samples = []
    for event in events[start + 1 : end]:
        if event.kind == "perception.observed" and event.payload.get("emotions") is not None:
            values = categorical_probabilities(event.payload["emotions"])
            count = event.payload.get("frame_count", 1)
            if type(count) is not int or count < 1:
                raise ValueError("A categorical sample needs a positive integer frame_count.")
            samples.append((values, count))
    if not samples:
        return AffectWindow(None, {**receipt, "missing_reason": "no_samples_in_response_window"})
    count = sum(weight for _, weight in samples)
    labels = sorted({label for values, _ in samples for label in values})
    result = {
        label: fsum(values.get(label, 0) * weight for values, weight in samples) / count
        for label in labels
    }
    receipt.update(sample_count=len(samples), frame_count=count)
    return AffectWindow(result, receipt)
