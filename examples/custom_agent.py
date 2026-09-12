"""Complete synthetic session with an independently supplied Agent object."""

import argparse
from pathlib import Path

from negotiator.application.runner import SessionRunner
from negotiator.application.session import Session, SessionConfig
from negotiator.domain import Preference
from negotiator.domain.actions import Accept, End, Offer
from negotiator.examples import builtin_domain, example_profiles
from negotiator.strategies import Decision, Observation


class FixedOfferAgent:
    """Offer the best own bid; accept an opponent bid at least as good."""

    def __init__(self, own: Preference):
        self.own = own
        self.best = max(own.domain.bids(), key=lambda b: own.utility(b, "agent"))

    def decide(self, observation: Observation) -> Decision:
        if observation.elapsed_fraction >= 1:
            return Decision(End("agent", "deadline"))
        pending = observation.offers[-1] if observation.offers else None
        if (
            pending
            and pending.actor == "human"
            and self.own.utility(pending.bid, "agent")
            >= max(self.own.reservation, self.own.utility(self.best, "agent"))
        ):
            return Decision(Accept("agent", pending.offer_id))
        if self.own.utility(self.best, "agent") < self.own.reservation:
            return Decision(End("agent", "candidate_exhaustion"))
        return Decision(Offer(f"fixed-{len(observation.offers)}", "agent", self.best))


def run(output: Path) -> Session:
    human, own = example_profiles(builtin_domain("fruits"))
    session = Session.create(
        output,
        SessionConfig(
            "custom-agent",
            "SYNTHETIC001",
            "session-1",
            strategy="fixed-example",
            first_actor="agent",
            practice=True,
            synthetic=True,
        ),
        human,
        own,
    )
    runner = SessionRunner(session, agent=FixedOfferAgent(own))
    runner.respond()
    pending = session.pending
    if pending:
        session.submit(Accept("human", pending.offer_id), "synthetic-human-accept")
    return session


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("custom-demo"))
    print(run(parser.parse_args().output).journal.path)
