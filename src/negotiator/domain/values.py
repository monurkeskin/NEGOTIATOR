"""Immutable discrete outcomes. Allocation bids are stored from the human's view."""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from itertools import product
from math import prod
from typing import Literal

Value = str | int
Actor = Literal["human", "agent"]
MAX_OUTCOMES = 50_000


def check_actor(actor: str) -> None:
    if actor not in ("human", "agent"):
        raise ValueError("Actor must be 'human' or 'agent'.")


@dataclass(frozen=True, init=False)
class Bid:
    items: tuple[tuple[str, Value], ...]

    def __init__(self, values: Mapping[str, Value]):
        if not values or any(not isinstance(k, str) or not k for k in values):
            raise ValueError("A bid needs named issues.")
        if any(type(v) not in (str, int) for v in values.values()):
            raise ValueError("Bid values must be strings or integer counts.")
        object.__setattr__(self, "items", tuple(sorted(values.items())))

    def __getitem__(self, issue: str) -> Value:
        for name, value in self.items:
            if name == issue:
                return value
        raise KeyError(issue)

    def to_dict(self) -> dict[str, Value]:
        return dict(self.items)


@dataclass(frozen=True)
class Issue:
    name: str
    values: tuple[Value, ...] = ()
    total: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Issue name cannot be empty.")
        values = tuple(self.values)
        if self.total is not None:
            if type(self.total) is not int or self.total < 0 or values:
                raise ValueError("An allocation issue needs a nonnegative integer total only.")
            if self.total >= MAX_OUTCOMES:
                raise ValueError("An issue may contain at most 50,000 values. Reduce its total.")
            values = tuple(range(self.total + 1))
        elif not values or any(not isinstance(v, str) or not v for v in values):
            raise ValueError("A categorical issue needs nonempty string values.")
        if len(set(values)) != len(values):
            raise ValueError("Issue values must be unique.")
        if len(values) > MAX_OUTCOMES:
            raise ValueError("An issue may contain at most 50,000 values.")
        object.__setattr__(self, "values", values)


@dataclass(frozen=True)
class Domain:
    name: str
    issues: tuple[Issue, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "issues", tuple(self.issues))
        if not isinstance(self.name, str) or not self.name.strip() or not self.issues:
            raise ValueError("A domain needs a name and at least one issue.")
        if len({i.name for i in self.issues}) != len(self.issues):
            raise ValueError("Duplicate issue names.")
        if len({i.total is None for i in self.issues}) != 1:
            raise ValueError("Use either categorical issues or allocation issues in a domain.")

    @property
    def allocation(self) -> bool:
        return self.issues[0].total is not None

    @property
    def size(self) -> int:
        return prod(len(i.values) for i in self.issues)

    def bid(self, values: Mapping[str, Value]) -> Bid:
        bid = Bid(values)
        self.validate(bid)
        return bid

    def validate(self, bid: Bid) -> None:
        if {name for name, _ in bid.items} != {i.name for i in self.issues}:
            raise ValueError("A complete bid must contain every domain issue exactly once.")
        for issue in self.issues:
            value = bid[issue.name]
            expected = int if self.allocation else str
            if type(value) is not expected or value not in issue.values:
                raise ValueError(f"Invalid value for {issue.name}: {value!r}.")

    def for_actor(self, canonical_bid: Bid, actor: Actor) -> Bid:
        check_actor(actor)
        self.validate(canonical_bid)
        if not self.allocation or actor == "human":
            return canonical_bid
        values: dict[str, Value] = {}
        for issue in self.issues:
            assert issue.total is not None
            values[issue.name] = issue.total - int(canonical_bid[issue.name])
        return Bid(values)

    def canonical(self, actor_bid: Bid, actor: Actor) -> Bid:
        """Complementing twice is the identity for an allocation."""
        return self.for_actor(actor_bid, actor)

    def bids(self) -> Iterator[Bid]:
        if self.size > MAX_OUTCOMES:
            raise ValueError(
                f"Domain has {self.size:,} outcomes; full enumeration is limited to 50,000. "
                "Reduce issue counts or supply a strategy with an explicit larger-domain contract."
            )
        names = [i.name for i in self.issues]
        for values in product(*(i.values for i in self.issues)):
            yield Bid(dict(zip(names, values, strict=True)))
