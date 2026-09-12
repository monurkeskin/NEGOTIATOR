"""Translate committed observations to an agent decision without exposing human preferences."""

import threading
from typing import Any

from negotiator.domain import Bid
from negotiator.domain.actions import Offer
from negotiator.events.journal import Event
from negotiator.interaction.affect import response_window
from negotiator.strategies import Agent, Observation, create_agent
from negotiator.strategies.agents import Decision

from .session import Session


class SessionRunner:
    def __init__(self, session: Session, *, agent: Agent | None = None):
        self.session = session
        self.agent = agent or create_agent(
            session.config.strategy,
            session.agent_profile,
            seed=session.config.seed,
            parameters=session.config.strategy_parameters,
        )
        self._lock = threading.RLock()
        self._pending: tuple[tuple[Offer, ...], Decision, dict[str, Any]] | None = None

    def respond(self) -> Event | None:
        with self._lock:
            snapshot = self.session.snapshot()
            if snapshot["status"] != "active" or snapshot["next_actor"] != "agent":
                return None
            offers = tuple(
                Offer(o["offer_id"], o["actor"], Bid(o["bid"])) for o in snapshot["offers"]
            )
            if self._pending is None or self._pending[0] != offers:
                window = response_window(self.session.journal.read())
                decision = self.agent.decide(
                    Observation(offers, snapshot["elapsed_fraction"], window.probabilities)
                )
                self._pending = (
                    offers,
                    decision,
                    {**decision.diagnostics, "affect_window": window.receipt},
                )
            _, decision, diagnostics = self._pending
            result = self.session.submit(
                decision.action,
                f"agent-response-{len(offers)}",
                diagnostics=diagnostics,
            )
            self._pending = None
            return result
