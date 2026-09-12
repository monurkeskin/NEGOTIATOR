"""Reusable behavioral checks for independently contributed negotiation agents."""

import random
from collections.abc import Callable
from typing import Any

from negotiator.domain import Preference
from negotiator.domain.actions import Accept, End, Offer
from negotiator.strategies import Agent, Observation


class AgentContractError(AssertionError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AgentContractError(message)


def assert_agent_contract(
    factory: Callable[[Preference, int], Agent], own: Preference
) -> dict[str, Any]:
    """Check legal actions, local randomness, replay determinism and deadline handling.

    Pass a factory accepting (own_preference, seed); it must construct a fresh agent.
    These synthetic checks do not measure negotiating strength or paper equivalence.
    """
    initial = random.getstate()
    try:
        first, second = factory(own, 17), factory(own, 17)
        require(random.getstate() == initial, "Agent construction changed the process-global RNG.")
        offers: tuple[Offer, ...] = ()
        actions = 0
        low = min(own.domain.bids(), key=lambda bid: own.utility(bid, "agent"))
        for index in range(6):
            human = Offer(f"human-{index}", "human", low)
            offers = (*offers, human)
            observation = Observation(offers, index / 8)
            a, b = first.decide(observation), second.decide(observation)
            require(a.action == b.action, "The same seed and history produced different actions.")
            require(
                first.decide(observation).action == a.action, "Retry changed the pending decision."
            )
            require(random.getstate() == initial, "Agent decision changed the process-global RNG.")
            action = a.action
            require(action.actor == "agent", "The agent must act as agent, not as the human.")
            if isinstance(action, Offer):
                own.domain.validate(action.bid)
                require(action.offer_id not in {o.offer_id for o in offers}, "Offer ID was reused.")
                require(
                    own.utility(action.bid, "agent") >= own.reservation,
                    "Offer is below own reservation.",
                )
                offers = (*offers, action)
            elif isinstance(action, Accept):
                require(
                    action.offer_id == human.offer_id,
                    "Acceptance must identify the pending human offer.",
                )
                require(
                    own.utility(human.bid, "agent") >= own.reservation,
                    "Acceptance is below own reservation.",
                )
            else:
                require(isinstance(action, End), "Unknown action type.")
            actions += 1
            if not isinstance(action, Offer):
                break
        deadline = first.decide(Observation(offers, 1)).action
        require(isinstance(deadline, End), "An agent must not offer after the deadline.")
        return {
            "actions_checked": actions,
            "deadline_checked": True,
            "scope": "synthetic API contract",
        }
    finally:
        random.setstate(initial)
