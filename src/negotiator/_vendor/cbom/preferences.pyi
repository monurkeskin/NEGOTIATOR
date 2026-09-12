from collections.abc import Mapping

class Preference:
    issue_weights: Mapping[str, float]
    value_weights: Mapping[str, Mapping[str, float]]
    domain: Mapping[str, tuple[str, ...]]
    issues: tuple[str, ...]
    reservation: float
    def __init__(
        self,
        issue_weights: Mapping[str, float],
        value_weights: Mapping[str, Mapping[str, float]],
        reservation: float = ...,
    ) -> None: ...
    def utility(self, bid: Mapping[str, str]) -> float: ...
