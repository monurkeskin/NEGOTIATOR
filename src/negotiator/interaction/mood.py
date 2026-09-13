"""Published framework's optional utility/move-based presentation policy."""

from negotiator.domain import Bid, Preference


class MoodPolicy:
    def __init__(self, own: Preference):
        self.own = own
        self.history: list[Bid] = []
        self.previous: float | None = None
        self.warnings: set[float] = set()

    def observe(self, bid: Bid, elapsed_fraction: float) -> str | None:
        utility = self.own.utility(bid, "agent")
        mood = None
        warning = next(
            (t for t in (0.6, 0.73, 0.86) if elapsed_fraction > t and t not in self.warnings), None
        )
        if warning is not None:
            self.warnings.add(warning)
            mood = "Worried"
        elif utility < 0.4 or (utility < 0.5 and elapsed_fraction > 0.73):
            mood = "Frustrated"
        elif self.previous is not None:
            delta = utility - self.previous
            if len(self.history) >= 2 and bid == self.history[-1] == self.history[-2]:
                mood = "Frustrated"
            elif bid == self.history[-1]:
                mood = "Annoyed"
            elif delta == 0:
                mood = "Neutral"
            elif 0 < delta <= 0.25:
                mood = "Convinced"
            elif delta > 0.25:
                mood = "Content"
            elif delta >= -0.25:
                mood = "Dissatisfied"
            else:
                mood = "Annoyed"
        self.history.append(bid)
        self.previous = utility
        return mood


class JenniferMoodPolicy:
    """Published priority; warning time and BABT mild threshold remain explicit inputs."""

    def __init__(
        self,
        year: int,
        *,
        warning_fraction: float,
        reservation: float,
        offended_threshold: float | None = None,
    ):
        from negotiator.domain.preferences import finite_number

        if year not in (2021, 2022):
            raise ValueError("Choose the 2021 or 2022 Jennifer policy.")
        if not 0 < finite_number(warning_fraction, "Warning time") < 1:
            raise ValueError("Warning time must lie strictly between zero and one.")
        if not 0 <= finite_number(reservation, "Reservation") <= 1:
            raise ValueError("Reservation must lie in [0, 1].")
        if (
            offended_threshold is not None
            and not 0 <= finite_number(offended_threshold, "Offended threshold") <= 1
        ):
            raise ValueError("Offended threshold must lie in [0, 1].")
        self.year, self.warning_fraction, self.reservation = year, warning_fraction, reservation
        # Older journals did not record a separate social threshold. Preserve
        # their replay behavior; new study configurations can specify it.
        self.offended_threshold = reservation if offended_threshold is None else offended_threshold
        self.previous: float | None = None
        self.warned = False

    def observe(
        self, utility: float, elapsed_fraction: float, *, next_utility: float, mild_threshold: float
    ) -> str | None:
        from negotiator.domain.preferences import finite_number

        if any(
            not 0 <= finite_number(v, "Mood input") <= 1
            for v in (utility, elapsed_fraction, next_utility, mild_threshold)
        ):
            raise ValueError("Mood utilities and time must lie in [0, 1].")
        previous, self.previous = self.previous, utility
        if elapsed_fraction >= 1:
            return "Times up"
        if utility >= max(next_utility, self.reservation):
            return "Acceptance" if self.year == 2021 else "Satisfied"
        if previous is None:
            return None
        if elapsed_fraction >= self.warning_fraction and not self.warned:
            self.warned = True
            return "Hurry up" if self.year == 2021 else "Stressed"
        if utility < self.offended_threshold:
            return "Offended"
        if utility >= mild_threshold:
            return "Mild"
        if utility > previous:
            return "Pleasant"
        if utility == previous:
            return "Neutral"
        return "Dissatisfied" if self.year == 2021 else "Unpleasant"


def validate_mood_parameters(policy: str, parameters: dict[str, float]) -> None:
    if policy == "generic":
        if parameters:
            raise ValueError("The generic presentation policy takes no parameters.")
        return
    if policy not in ("jennifer-2021", "jennifer-2022"):
        raise ValueError("Unknown presentation policy.")
    required = {"warning_fraction", "mild_multiplier"}
    if not required <= set(parameters) or set(parameters) - required - {"offended_threshold"}:
        raise ValueError("Jennifer requires explicit warning_fraction and mild_multiplier.")
    JenniferMoodPolicy(
        int(policy[-4:]),
        warning_fraction=parameters["warning_fraction"],
        reservation=0,
        offended_threshold=parameters.get("offended_threshold"),
    )
    from negotiator.domain.preferences import finite_number

    if not 0 < finite_number(parameters["mild_multiplier"], "Mild multiplier") <= 1:
        raise ValueError("Mild multiplier must lie in (0, 1].")
