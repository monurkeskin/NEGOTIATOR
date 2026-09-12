"""Small synthetic fixtures for installation and workflow checks."""

from dataclasses import replace
from importlib.resources import files
from pathlib import Path
from uuid import uuid4

from negotiator.application.session import Session, SessionConfig
from negotiator.domain import Domain, Issue, Preference, ranked_preferences
from negotiator.domain.actions import Accept, Offer
from negotiator.domain.importers import from_xml


def builtin_domain(name: str) -> Domain:
    names = {
        "holiday": "Holiday_A",
        "holiday-b": "Holiday_B",
        "fruits": "Fruits",
        "island": "Island",
    }
    if name not in names:
        raise ValueError(f"Unknown bundled domain {name!r}; choose {', '.join(names)}.")
    text = (
        files("negotiator")
        .joinpath("data", "domains", f"{names[name]}.xml")
        .read_text(encoding="utf-8")
    )
    return from_xml(text, name=names[name]).domain


def example_profiles(domain: Domain) -> tuple[Preference, Preference]:
    """Synthetic rank assignment; real studies must configure or elicit preferences."""
    human, agent = ranked_preferences(
        domain,
        [i.name for i in domain.issues],
        {
            i.name: list(reversed(i.values)) if domain.allocation else list(i.values)
            for i in domain.issues
        },
    )
    return replace(
        human, provenance="assigned", conversion="synthetic-rank-linear-paired-v1"
    ), agent


def run_demo(root: Path) -> Session:
    domain = Domain("Synthetic city choice", (Issue("city", ("Berlin", "London")),))
    human = Preference(domain, {"city": 1}, {"city": {"Berlin": 0.9, "London": 0.2}})
    agent = Preference(domain, {"city": 1}, {"city": {"Berlin": 0.1, "London": 1.0}})
    session = Session.create(
        root,
        SessionConfig(
            "demo", "SYNTHETIC001", f"demo-{uuid4().hex[:12]}", practice=True, synthetic=True
        ),
        human,
        agent,
    )
    session.submit(Offer("human-1", "human", domain.bid({"city": "Berlin"})), "demo-offer-1")
    session.submit(Offer("agent-1", "agent", domain.bid({"city": "London"})), "demo-offer-2")
    session.submit(Accept("human", "agent-1"), "demo-accept")
    return session
