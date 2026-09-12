import pytest

from negotiator.application.clock import SessionClock
from negotiator.domain import Bid
from negotiator.domain.actions import Accept, End, Offer, validate_accept


def test_clock_has_separate_bounded_units_and_freezes():
    instant = [100.0]
    clock = SessionClock(10, now=lambda: instant[0])
    assert clock.elapsed_fraction == 0
    assert clock.remaining_seconds == 10
    for offset, fraction, remaining in [(5, 0.5, 5), (10, 1, 0), (15, 1, 0)]:
        instant[0] = 100 + offset
        assert clock.elapsed_fraction == fraction
        assert clock.remaining_seconds == remaining
    assert clock.expired
    clock.stop()
    instant[0] = 999
    assert clock.elapsed_fraction == 1


def test_clock_resists_backward_source_and_stops_before_deadline():
    instant = [0.0]
    clock = SessionClock(10, now=lambda: instant[0])
    instant[0] = 4
    assert clock.elapsed_seconds == 4
    instant[0] = 2
    assert clock.elapsed_seconds == 4
    clock.stop()
    instant[0] = 9
    assert clock.remaining_seconds == 6


@pytest.mark.parametrize("duration", [0, -1, True, float("nan"), float("inf")])
def test_clock_rejects_invalid_duration(duration):
    with pytest.raises(ValueError):
        SessionClock(duration)


def test_accept_references_current_opponent_offer():
    offer = Offer("o1", "agent", Bid({"x": "a"}))
    validate_accept(Accept("human", "o1"), offer)
    for action, pending in [
        (Accept("agent", "o1"), offer),
        (Accept("human", "old"), offer),
        (Accept("human", "o1"), None),
    ]:
        with pytest.raises(ValueError):
            validate_accept(action, pending)
    with pytest.raises(ValueError):
        End("human", "agreement")
