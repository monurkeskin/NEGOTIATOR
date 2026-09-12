"""Explicit maintained choices for constants not specified numerically in the paper."""

from dataclasses import dataclass
from typing import Any

from negotiator.domain.preferences import finite_number


@dataclass(frozen=True)
class SolverParameters:
    adaptation_min_human_offers: int = 9
    concession_step: float = 0.2
    silent_multiplier: float = 0.5
    selfish_multiplier: float = 1.5

    def __post_init__(self) -> None:
        if (
            type(self.adaptation_min_human_offers) is not int
            or not 2 <= self.adaptation_min_human_offers <= 1000
        ):
            raise ValueError("Adaptation threshold must be an integer between 2 and 1000.")
        if not 0 < finite_number(self.concession_step, "Concession step") <= 1:
            raise ValueError("Concession step must lie in (0, 1].")
        if not 0 < finite_number(self.silent_multiplier, "Silent multiplier") < 1:
            raise ValueError("Silent multiplier must lie in (0, 1).")
        if not 1 < finite_number(self.selfish_multiplier, "Selfish multiplier") <= 10:
            raise ValueError("Selfish multiplier must lie in (1, 10].")


def validate_parameters(name: str, parameters: dict[str, Any]) -> SolverParameters:
    if parameters and name != "solver-2025":
        raise ValueError("This strategy has no configurable method parameters.")
    try:
        return SolverParameters(**parameters)
    except TypeError as exc:
        raise ValueError("Unknown Solver parameter.") from exc
