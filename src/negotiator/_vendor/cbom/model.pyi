from collections.abc import Mapping

from .preferences import Preference

class ConflictBasedOpponentModel:
    observations: int
    def __init__(self, reference: Preference, history_size: int = ...) -> None: ...
    @property
    def preference(self) -> Preference: ...
    def update(self, bid: Mapping[str, str], t: float | None = ...) -> None: ...
