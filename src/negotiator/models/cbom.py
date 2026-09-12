"""Adapt the pinned public CBOM model to canonical human-perspective bids."""

from negotiator._vendor.cbom.model import ConflictBasedOpponentModel
from negotiator._vendor.cbom.preferences import Preference as CBOMPreference
from negotiator.domain import Bid, Preference


class CBOMModel:
    def __init__(self, own: Preference, history_size: int = 1000):
        self.domain = own.domain
        # CBOM's inverse initialization needs own utility expressed in the same
        # value coordinates as received bids, including allocation complements.
        scores = {}
        for issue in self.domain.issues:
            scores[issue.name] = {
                str(value): own.scores[issue.name][
                    issue.total - int(value) if issue.total is not None else value
                ]
                for value in issue.values
            }
        self.reference = CBOMPreference(
            {i.name: own.weights[i.name] for i in self.domain.issues}, scores
        )
        self._model = ConflictBasedOpponentModel(self.reference, history_size=history_size)

    @property
    def observations(self) -> int:
        return self._model.observations

    def observe(self, bid: Bid) -> None:
        self.domain.validate(bid)
        self._model.update({name: str(value) for name, value in bid.items})

    @property
    def preference(self) -> Preference:
        current = self._model.preference
        return Preference(
            self.domain,
            dict(current.issue_weights),
            {
                i.name: {v: current.value_weights[i.name][str(v)] for v in i.values}
                for i in self.domain.issues
            },
            provenance="estimated",
            conversion="public-cbom-41345ae",
        )
