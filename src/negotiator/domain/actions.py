"""Proposals and validated acceptance; actions carry no presentation behavior."""

from dataclasses import dataclass
from typing import Literal

from .values import Actor, Bid, check_actor

EndReason = Literal["deadline", "withdrawal", "candidate_exhaustion", "operator", "interrupted"]


@dataclass(frozen=True)
class Offer:
    offer_id: str
    actor: Actor
    bid: Bid

    def __post_init__(self) -> None:
        check_actor(self.actor)
        if not self.offer_id:
            raise ValueError("Offer ID is required.")


@dataclass(frozen=True)
class Accept:
    actor: Actor
    offer_id: str

    def __post_init__(self) -> None:
        check_actor(self.actor)
        if not self.offer_id:
            raise ValueError("Acceptance must reference an offer ID.")


@dataclass(frozen=True)
class End:
    actor: Actor
    reason: EndReason

    def __post_init__(self) -> None:
        check_actor(self.actor)
        if self.reason not in (
            "deadline",
            "withdrawal",
            "candidate_exhaustion",
            "operator",
            "interrupted",
        ):
            raise ValueError("Invalid ending reason; agreement requires a valid acceptance.")


Action = Offer | Accept | End


def validate_accept(accept: Accept, pending: Offer | None) -> None:
    if pending is None or pending.actor == accept.actor or pending.offer_id != accept.offer_id:
        raise ValueError("Accept must reference the current opponent offer.")
