"""Deterministic domain-vocabulary interpretation with explicit ambiguity."""

import re
from collections import Counter
from dataclasses import dataclass

from negotiator.domain import Bid, Domain, Value


@dataclass(frozen=True)
class Draft:
    transcript: str
    values: tuple[tuple[str, Value], ...]
    missing: tuple[str, ...]
    ambiguous: tuple[str, ...]
    invalid: tuple[str, ...]
    intent: str = "offer"

    @property
    def complete(self) -> bool:
        return self.intent == "offer" and not (self.missing or self.ambiguous or self.invalid)

    @property
    def bid(self) -> Bid:
        if not self.complete:
            raise ValueError("Draft is incomplete; clarify the highlighted issues before sending.")
        return Bid(dict(self.values))


class Interpreter:
    def __init__(self, domain: Domain):
        self.domain = domain
        self.current_text = ""
        self._value_uses = Counter(str(v).casefold() for i in domain.issues for v in i.values)

    def interpret(self, text: str) -> Draft:
        if not isinstance(text, str) or len(text) > 10_000:
            raise ValueError("Input must be text of at most 10,000 characters.")
        self.current_text = text
        normalized = text.strip().casefold().rstrip(".! ")
        if normalized in ("accept", "i accept", "agreed", "deal"):
            return Draft(text, (), (), (), (), "accept")
        fields: dict[str, Value] = {}
        ambiguous: list[str] = []
        invalid: list[str] = []
        missing: list[str] = []
        # Named pairs also permit values used by more than one issue.
        pairs = {}
        duplicate_pairs = set()
        for fragment in re.split(r"[;,\n]", text):
            if "=" in fragment:
                name, value = fragment.split("=", 1)
                name = name.strip().casefold()
                if name in pairs:
                    duplicate_pairs.add(name)
                pairs[name] = value.strip().casefold()
        known = {i.name.casefold() for i in self.domain.issues}
        invalid.extend(name for name in pairs if name not in known)
        for issue in self.domain.issues:
            name = issue.name.casefold()
            found: list[Value] = []
            if name in duplicate_pairs:
                ambiguous.append(issue.name)
                continue
            if name in pairs:
                found = [v for v in issue.values if str(v).casefold() == pairs[name]]
                if not found:
                    invalid.append(issue.name)
                    continue
            elif issue.total is not None:
                noun = re.escape(name) + r"s?"
                matches = re.findall(r"\b(-?\d+)\s+" + noun + r"\b", normalized)
                matches += re.findall(r"\b" + noun + r"\s+(-?\d+)\b", normalized)
                if any(int(number) not in issue.values for number in matches):
                    invalid.append(issue.name)
                    continue
                found = list(dict.fromkeys(int(number) for number in matches))
            else:
                for value in issue.values:
                    word = str(value).casefold()
                    pattern = r"(?<!\w)" + re.escape(word) + r"(?!\w)"
                    if re.search(pattern, normalized):
                        if re.search(
                            r"\b(?:not|no|without)\s+(?:a\s+|an\s+|the\s+)?" + pattern, normalized
                        ):
                            invalid.append(issue.name)
                        elif self._value_uses[word] != 1:
                            ambiguous.append(issue.name)
                        else:
                            found.append(value)
            if len(found) == 1:
                fields[issue.name] = found[0]
            elif len(found) > 1:
                ambiguous.append(issue.name)
            else:
                missing.append(issue.name)
        return Draft(
            text,
            tuple(fields.items()),
            tuple(missing),
            tuple(dict.fromkeys(ambiguous)),
            tuple(dict.fromkeys(invalid)),
        )

    def finalize(self, text: str) -> Draft:
        result = self.interpret(text)
        if not result.complete and result.intent != "accept":
            raise ValueError("Draft needs clarification before it can be committed.")
        # Return the captured immutable transcript, then reset this session's draft.
        self.current_text = ""
        return result
