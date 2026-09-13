"""Deterministic domain-vocabulary interpretation with explicit ambiguity."""

import re
from collections import Counter
from dataclasses import dataclass

from negotiator.domain import Bid, Domain, Value

_NUMBER_WORDS = dict(
    enumerate(
        (
            "zero",
            "one",
            "two",
            "three",
            "four",
            "five",
            "six",
            "seven",
            "eight",
            "nine",
            "ten",
            "eleven",
            "twelve",
            "thirteen",
            "fourteen",
            "fifteen",
            "sixteen",
            "seventeen",
            "eighteen",
            "nineteen",
            "twenty",
        )
    )
)
_WORD_NUMBERS = {word: number for number, word in _NUMBER_WORDS.items()}
_QUANTITY = r"(?<![\w.\-])(-?\d+|" + "|".join(_WORD_NUMBERS) + r")(?![\w.\-])"
_REQUEST_WORDS = re.compile(
    r"(?:[\s,;.!]|and\b|please\b|"
    r"i\s+(?:want|would\s+like)(?:\s+to\s+(?:take|keep|have|get))?\b|"
    r"i\s+(?:take|keep|choose)\b)*"
)


def _allocation_counts(text: str, name: str) -> tuple[list[int], str]:
    """Consume explicit quantities; leave unsupported wording for clarification."""
    noun = r"\b" + re.escape(name) + r"s?\b"
    pattern = re.compile(_QUANTITY + r"\s+" + noun + "|" + noun + r"\s+" + _QUANTITY)
    counts = []

    def consume(match: re.Match[str]) -> str:
        quantity = match.group(1) or match.group(2)
        counts.append(_WORD_NUMBERS[quantity] if quantity in _WORD_NUMBERS else int(quantity))
        return " "

    remainder = pattern.sub(consume, text)
    return counts, remainder


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
        if normalized in ("accept", "i accept", "agree", "i agree", "agreed", "deal"):
            return Draft(text, (), (), (), (), "accept")
        fields: dict[str, Value] = {}
        ambiguous: list[str] = []
        invalid: list[str] = []
        missing: list[str] = []
        remainder = normalized
        # Named pairs also permit values used by more than one issue.
        pairs = {}
        duplicate_pairs = set()
        fragments = [part for part in re.split(r"[;,\n]", text) if part.strip()]
        named_only = bool(fragments) and all("=" in part for part in fragments)
        for fragment in fragments:
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
                matches, remainder = _allocation_counts(remainder, name)
                if any(number not in issue.values for number in matches):
                    invalid.append(issue.name)
                    continue
                found = list(dict.fromkeys(matches))
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
        if not named_only:
            if self.domain.allocation and not _REQUEST_WORDS.fullmatch(remainder):
                invalid.append("Use exact quantities for your own share, or issue=value pairs")
            elif not self.domain.allocation and re.search(
                r"\b(?:not|never|without|don['’]t|can['’]t|won['’]t)\b", normalized
            ):
                invalid.append(
                    "State the values you want without negation, or use issue=value pairs"
                )
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
