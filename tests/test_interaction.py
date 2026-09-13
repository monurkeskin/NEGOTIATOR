import pytest

from negotiator.application.runner import SessionRunner
from negotiator.application.session import Session, SessionConfig
from negotiator.domain import Domain, Issue
from negotiator.domain.actions import End, Offer
from negotiator.examples import builtin_domain, example_profiles
from negotiator.interaction.input import Interpreter


def test_text_complete_transcript_survives_finalization_and_next_draft_is_empty():
    parser = Interpreter(builtin_domain("holiday"))
    text = "Accommodation=Hotel; Destination=Rome; Events=Museum; Season=Summer"
    result = parser.finalize(text)
    assert result.complete
    assert result.transcript == text
    assert result.bid["Destination"] == "Rome"
    assert parser.current_text == ""
    assert parser.interpret("Hotel").missing == ("Destination", "Events", "Season")


def test_missing_ambiguous_and_negated_text_never_becomes_offer():
    parser = Interpreter(builtin_domain("holiday"))
    assert not parser.interpret("Hotel or Caravan, Rome, Museum, Summer").complete
    assert "Accommodation" in parser.interpret("Hotel or Caravan").ambiguous
    assert not parser.interpret("not Hotel, Rome, Museum, Summer").complete
    assert parser.interpret("I do not accept").intent == "offer"
    assert parser.interpret("I accept").intent == "accept"
    with pytest.raises(ValueError):
        parser.finalize("Hotel")


def test_shared_values_require_issue_names_instead_of_guessing():
    d = Domain("d", (Issue("first", ("red", "blue")), Issue("second", ("red", "blue"))))
    parser = Interpreter(d)
    assert not parser.interpret("red blue").complete
    assert parser.finalize("first=red; second=blue").bid == d.bid(
        {"first": "red", "second": "blue"}
    )


def test_counts_are_domain_driven_and_can_be_corrected():
    d = Domain("resources", (Issue("water", total=7), Issue("map", total=1)))
    parser = Interpreter(d)
    assert parser.finalize("2 water, 1 map").bid == d.bid({"water": 2, "map": 1})
    assert not parser.interpret("8 water, 1 map").complete
    assert "water" in parser.interpret("8 water, 1 map").invalid
    assert parser.finalize("water=3; map=0").complete


def test_english_request_uses_complete_human_share_and_preserves_transcript():
    domain = builtin_domain("fruits")
    parser = Interpreter(domain)
    partial = "I want to take three apples, two bananas and zero oranges"
    draft = parser.interpret(partial)
    assert not draft.complete
    assert draft.missing == ("watermelon",)
    with pytest.raises(ValueError):
        parser.finalize(partial)
    text = partial + " and four watermelons."
    result = parser.finalize(text)
    assert result.transcript == text
    assert result.bid == domain.bid({"apple": 3, "banana": 2, "orange": 0, "watermelon": 4})
    assert parser.current_text == ""


@pytest.mark.parametrize(
    "text",
    [
        "I give you 1 apple, 2 bananas, 3 oranges, 4 watermelons",
        "You keep 1 apple, 2 bananas, 3 oranges, 4 watermelons",
        "I do not want 1 apple, 2 bananas, 3 oranges, 4 watermelons",
        "I don't want 1 apple, 2 bananas, 3 oranges, 4 watermelons",
        "I want at least 1 apple, 2 bananas, 3 oranges, 4 watermelons",
        "I want -1 apple, 2 bananas, 3 oranges, 4 watermelons",
        "I want 1.5 apples, 2 bananas, 3 oranges, 4 watermelons",
        "I want twenty one apples, 2 bananas, 3 oranges, 4 watermelons",
    ],
)
def test_unsupported_allocation_language_never_commits_a_guessed_share(text):
    parser = Interpreter(builtin_domain("fruits"))
    assert not parser.interpret(text).complete
    with pytest.raises(ValueError):
        parser.finalize(text)


@pytest.mark.parametrize(
    "text",
    [
        "I do not want Hotel, Rome, Museum and Summer",
        "I don't want to go to Rome with Hotel, Museum and Summer",
    ],
)
def test_negated_categorical_request_does_not_become_positive_offer(text):
    assert not Interpreter(builtin_domain("holiday")).interpret(text).complete


@pytest.mark.parametrize("text", ["agree", "I agree.", "DEAL!"])
def test_published_english_agreement_vocabulary(text):
    assert Interpreter(builtin_domain("fruits")).finalize(text).intent == "accept"


def test_runner_logs_actual_strategy_decision_without_participant_diagnostics(tmp_path):
    d = builtin_domain("holiday")
    human, agent = example_profiles(d)
    s = Session.create(
        tmp_path, SessionConfig("demo", "P001", "s1", strategy="solver-2025"), human, agent
    )
    runner = SessionRunner(s)
    incoming = min(d.bids(), key=lambda b: agent.utility(b, "agent"))
    s.submit(Offer("h1", "human", incoming), "h1")
    event = runner.respond()
    assert event is not None
    assert "strategy" in event.payload["diagnostics"]
    assert runner.respond() is None
    snap = s.snapshot(role="participant")
    for offer in snap["offers"]:
        assert "diagnostics" not in offer
    assert len(s.state.offers) == 2
    assert runner.agent.model.observations == 1
    s.submit(End("human", "withdrawal"), "withdraw")
    assert runner.respond() is None
