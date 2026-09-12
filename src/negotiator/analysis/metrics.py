"""Negotiation geometry and descriptive metrics; no policy RNG or tournament state."""

from collections.abc import Sequence
from math import fsum, hypot, isfinite, sqrt
from typing import Any


def classify_move(own_delta: float, other_delta: float, threshold: float = 0.03) -> str:
    """NegoLog move categories with an explicit report-only threshold."""
    if not isfinite(threshold) or threshold <= 0:
        raise ValueError("Movement threshold must be finite and positive.")
    if abs(own_delta) < threshold and abs(other_delta) < threshold:
        return "Silent"
    if abs(own_delta) < threshold and other_delta > 0:
        return "Nice"
    if own_delta < 0 and other_delta >= 0:
        return "Concession"
    if own_delta <= 0 and other_delta < 0:
        return "Unfortunate"
    if own_delta > 0 and other_delta <= 0:
        return "Selfish"
    return "Fortunate"


def mean(values: Sequence[float]) -> float | None:
    return fsum(values) / len(values) if values else None


def average_ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + 1 + end) / 2
        for i in order[start:end]:
            ranks[i] = rank
        start = end
    return ranks


def _pearson(x: Sequence[float], y: Sequence[float]) -> dict[str, Any]:
    if len(x) < 2:
        return {"value": None, "reason": "fewer_than_two_outcomes"}
    mx, my = fsum(x) / len(x), fsum(y) / len(y)
    dx, dy = [v - mx for v in x], [v - my for v in y]
    denominator = sqrt(fsum(v * v for v in dx) * fsum(v * v for v in dy))
    if denominator == 0:
        return {"value": None, "reason": "constant_utility"}
    return {
        "value": max(
            -1.0, min(1.0, fsum(a * b for a, b in zip(dx, dy, strict=True)) / denominator)
        ),
        "reason": None,
    }


def correlations(reference: Sequence[float], estimated: Sequence[float]) -> dict[str, Any]:
    if len(reference) != len(estimated) or not all(isfinite(v) for v in (*reference, *estimated)):
        raise ValueError("Metrics need equally sized finite utility vectors.")
    return {
        "pearson": _pearson(reference, estimated),
        "spearman": _pearson(average_ranks(reference), average_ranks(estimated)),
    }


def model_errors(reference: Sequence[float], estimated: Sequence[float]) -> dict[str, Any]:
    result = correlations(reference, estimated)
    if not reference:
        return {**result, "rmse": None, "mape": None, "reason": "empty_outcome_space"}
    result["rmse"] = sqrt(
        fsum((a - b) ** 2 for a, b in zip(reference, estimated, strict=True)) / len(reference)
    )
    result["mape"] = (
        fsum(abs((a - b) / a) for a, b in zip(reference, estimated, strict=True)) / len(reference)
        if all(a != 0 for a in reference)
        else None
    )
    result["mape_missing_reason"] = None if result["mape"] is not None else "zero_reference_utility"
    return result


def reference_points(
    points: Sequence[tuple[float, float]], reservations: tuple[float, float] = (0, 0)
) -> dict[str, Any]:
    if not points or not all(isfinite(x) and isfinite(y) for x, y in points):
        raise ValueError("Reference geometry needs finite outcome utilities.")
    best_other = float("-inf")
    pareto = []
    for human, agent in sorted(set(points), reverse=True):
        if agent > best_other:
            pareto.append((human, agent))
            best_other = agent
    social = max(h + a for h, a in points)
    nash = max(h * a for h, a in points)
    feasible = [
        (h - reservations[0]) * (a - reservations[1])
        for h, a in points
        if h >= reservations[0] and a >= reservations[1]
    ]
    return {
        "pareto": pareto,
        "social_welfare": social,
        "raw_nash_product": nash,
        "raw_nash_points": [(h, a) for h, a in sorted(set(points)) if h * a == nash],
        "surplus_nash_product": max(feasible) if feasible else None,
        "surplus_missing_reason": None if feasible else "no_individually_rational_outcome",
    }


def distance(point: tuple[float, float], targets: Sequence[tuple[float, float]]) -> float | None:
    return min((hypot(point[0] - h, point[1] - a) for h, a in targets), default=None)
