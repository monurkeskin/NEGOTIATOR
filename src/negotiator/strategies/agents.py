"""Composed negotiation policies with a session-local RNG and opponent estimate."""

import random
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from itertools import pairwise
from types import MappingProxyType
from typing import Any, Protocol

from negotiator.domain import Bid, Preference
from negotiator.domain.actions import Accept, Action, End, Offer
from negotiator.domain.preferences import finite_number
from negotiator.models.cbom import CBOMModel

from .policies import ac_next, behavior_target, emotion_effect, time_target
from .sensitivity import CLASS_ORDER, FixedCentroids, awareness, move, move_rates
from .settings import validate_parameters


@dataclass(frozen=True)
class Observation:
    offers: tuple[Offer, ...]
    elapsed_fraction: float
    emotions: Mapping[str, float] | None = None

    def __post_init__(self) -> None:
        if not 0 <= finite_number(self.elapsed_fraction, "Elapsed fraction") <= 1:
            raise ValueError("Elapsed fraction must lie in [0, 1].")
        object.__setattr__(self, "offers", tuple(self.offers))
        if self.emotions is not None:
            emotion_effect(self.emotions)
            object.__setattr__(self, "emotions", MappingProxyType(dict(self.emotions)))


@dataclass(frozen=True)
class Decision:
    action: Action
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


class Agent(Protocol):
    def decide(self, observation: Observation) -> Decision: ...


class NegotiationAgent:
    def __init__(
        self,
        name: str,
        own: Preference,
        *,
        seed: int = 42,
        parameters: dict[str, Any] | None = None,
    ):
        self.parameters = validate_parameters(name, parameters or {})
        self.name = name
        self.own = own
        self.rng = random.Random(seed)
        self.model = CBOMModel(own)
        self.centroids = FixedCentroids() if name.startswith("solver-") else None
        self.p0, self.p1, self.p2 = 0.9, 0.7, 0.4
        self.delta_multiplier = 1.0
        self.awareness = 0.5
        self._previous_class: str | None = None
        self._seen: set[str] = set()
        self._decision_key: tuple[Any, ...] | None = None
        self._decision: Decision | None = None
        self._pool = sorted(
            ((own.utility(bid, "agent"), bid) for bid in own.domain.bids()),
            key=lambda item: item[0],
            reverse=True,
        )
        self._pool = [(u, b) for u, b in self._pool if u >= own.reservation]

    def update_sensitivity(self, category: str) -> None:
        if category not in CLASS_ORDER:
            raise ValueError("Unknown sensitivity category.")
        if category == self._previous_class:
            return
        step = self.parameters.concession_step if self.name == "solver-2025" else 0.2
        if category == "fortunate":
            self.p1 -= step
        elif category == "concession":
            self.p1 += step
            self.p2 += step
        elif category == "selfish":
            self.delta_multiplier = (
                self.delta_multiplier * 1.5
                if self.name == "solver-2021"
                else self.parameters.selfish_multiplier
            )
        elif category == "silent" and self.name == "solver-2025":
            self.delta_multiplier = self.parameters.silent_multiplier
        self._previous_class = category

    def _moves(self, offers: list[Offer], estimated: Preference, actor: str) -> list[str]:
        result = []
        for previous, current in pairwise(offers):
            agent_delta = self.own.utility(current.bid, "agent") - self.own.utility(
                previous.bid, "agent"
            )
            human_delta = estimated.utility(current.bid) - estimated.utility(previous.bid)
            result.append(
                move(human_delta, agent_delta)
                if actor == "human"
                else move(agent_delta, human_delta)
            )
        return result

    def _sensitivity(self, received: list[Offer], own_offers: list[Offer]) -> str | None:
        threshold = self.parameters.adaptation_min_human_offers if self.name == "solver-2025" else 9
        if self.centroids is None or len(received) < threshold:
            return None
        estimated = self.model.preference
        human_moves = self._moves(received, estimated, "human")
        agent_moves = self._moves(own_offers, estimated, "agent")
        value = awareness(agent_moves, human_moves)
        self.awareness = value
        category = CLASS_ORDER[self.centroids.classify(move_rates(human_moves))]
        self.update_sensitivity(category)
        return category

    def _choose_below(self, target: float) -> tuple[float, Bid] | None:
        candidates = [(u, b) for u, b in self._pool if u < target]
        return self.rng.choice(candidates[:3]) if candidates else None

    def _tsbt(self, t: float) -> tuple[float, Bid] | None:
        low = time_target(t, 0.94, 0.5, 0.4)
        high = time_target(t, 1.0, 0.9, 0.7)
        # The legacy tactic widens an empty interval by .01. Its bounded utility
        # domain lets this implementation stop explicitly if reservation excludes all bids.
        for step in range(102):
            candidates = [
                (u, b) for u, b in self._pool if low - 0.01 * step <= u < high + 0.01 * step
            ]
            if candidates:
                return self.rng.choice(candidates)
        return None

    def decide(self, observation: Observation) -> Decision:
        if observation.elapsed_fraction >= 1:
            return Decision(End("agent", "deadline"))
        key = (
            observation.offers,
            observation.elapsed_fraction,
            tuple(sorted(observation.emotions.items()))
            if observation.emotions is not None
            else None,
        )
        if key == self._decision_key:
            assert self._decision is not None
            return self._decision
        received = [o for o in observation.offers if o.actor == "human"]
        own_offers = [o for o in observation.offers if o.actor == "agent"]
        for offer in received:
            if offer.offer_id not in self._seen:
                self.model.observe(offer.bid)
                self._seen.add(offer.offer_id)
        pending = (
            observation.offers[-1]
            if observation.offers and observation.offers[-1].actor == "human"
            else None
        )
        t = observation.elapsed_fraction
        target_time = time_target(t, self.p0, self.p1, self.p2)
        category = self._sensitivity(received, own_offers) if self.centroids else None
        if self.name == "solver-2025":
            target_time = time_target(t, self.p0, self.p1, self.p2)
        effect = emotion_effect(observation.emotions) if self.centroids else None
        target = target_time
        warmup = 2 if self.name == "hybrid" else 1
        if len(received) > warmup and own_offers:
            differences = [
                self.own.utility(b.bid, "agent") - self.own.utility(a.bid, "agent")
                for a, b in pairwise(received)
            ]
            previous = self.own.utility(own_offers[-1].bid, "agent")
            behavior = behavior_target(
                previous,
                differences,
                t,
                awareness=self.awareness if self.centroids else 0.0,
                emotion=effect if effect is not None else 0.0,
                multiplier=self.delta_multiplier,
            )
            target = (1 - t * t) * behavior + t * t * target_time
        if self.name == "babt":
            if len(received) < 2 or not own_offers:
                target = 0.95
            else:
                delta = self.own.utility(received[-1].bid, "agent") - self.own.utility(
                    received[-2].bid, "agent"
                )
                target = self.own.utility(own_offers[-1].bid, "agent") - (0.5 + 0.5 * t) * delta
        if self.name == "tsbt":
            candidate = self._tsbt(t)
        elif self.name == "babt":
            if (
                len(received) >= 2
                and own_offers
                and self.own.utility(received[-1].bid, "agent")
                == self.own.utility(received[-2].bid, "agent")
            ):
                candidate = (self.own.utility(own_offers[-1].bid, "agent"), own_offers[-1].bid)
            elif self._pool:
                # BABT requests the nearest available utility; equal targets are
                # not forced into the strictly-below selector used by Hybrid.
                distance = min(abs(u - target) for u, _ in self._pool)
                candidate = self.rng.choice(
                    [(u, b) for u, b in self._pool if abs(u - target) == distance]
                )
            else:
                candidate = None
        else:
            candidate = self._choose_below(target)
        candidate_rule = "strategy"
        nash_status = "not-applicable"
        if self.name == "solver-2025":
            nash_status = "warmup"
            if len(received) >= self.parameters.adaptation_min_human_offers and self._pool:
                estimated = self.model.preference
                nash = max(self._pool, key=lambda item: item[0] * estimated.utility(item[1]))
                nash_status = "compared"
                if candidate is not None and nash[0] > candidate[0]:
                    candidate = nash
                    candidate_rule = "nash-improves-own-utility"
        incoming = self.own.utility(pending.bid, "agent") if pending else None
        if candidate is not None and ac_next(incoming, candidate[0], self.own.reservation):
            assert pending is not None
            action: Action = Accept("agent", pending.offer_id)
        elif candidate is None:
            if incoming is not None and incoming >= max(target, self.own.reservation):
                assert pending is not None
                action = Accept("agent", pending.offer_id)
            else:
                action = End("agent", "candidate_exhaustion")
        else:
            action = Offer(f"agent-{len(own_offers) + 1}", "agent", candidate[1])
        diagnostics = {
            "strategy": self.name,
            "time_target": target_time,
            "target": target,
            "awareness": self.awareness if self.centroids else None,
            "emotion_effect": effect,
            "emotion_missing_reason": "not_observed" if self.centroids and effect is None else None,
            "sensitivity": category,
            "opponent_model": "public-cbom-41345ae",
            "model_observations": self.model.observations,
            "method_revision": "maintained-2",
        }
        if self.name == "solver-2025":
            diagnostics["candidate_rule"] = candidate_rule
            diagnostics["nash_comparison"] = nash_status
            diagnostics["method_parameters"] = {
                **asdict(self.parameters),
                "parameter_evidence": "maintained-choices",
                "silent_multiplier_evidence": "explicit-maintenance-choice",
                "adaptation_trigger": "class-change",
                "awareness_zero_denominator": 0.0,
            }
        decision = Decision(action, MappingProxyType(diagnostics))
        self._decision_key, self._decision = key, decision
        return decision


def strategy_names() -> tuple[str, ...]:
    return ("hybrid", "solver-2021", "solver-2025", "tsbt", "babt")


def create_agent(
    name: str, own: Preference, *, seed: int = 42, parameters: dict[str, Any] | None = None
) -> NegotiationAgent:
    if name not in strategy_names():
        raise ValueError(f"Unknown strategy {name!r}; choose {', '.join(strategy_names())}.")
    return NegotiationAgent(name, own, seed=seed, parameters=parameters)
