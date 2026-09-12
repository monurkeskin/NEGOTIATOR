"""Domain interchange, including the resource-only legacy Island XML."""

import json
from dataclasses import dataclass
from typing import Any
from xml.etree.ElementTree import ParseError

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring

from .preferences import Preference
from .values import Domain, Issue


@dataclass(frozen=True)
class ImportResult:
    domain: Domain
    notes: tuple[str, ...]
    profile: Preference | None = None


def to_dict(domain: Domain) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "name": domain.name,
        "issues": [
            {
                "name": i.name,
                **({"total": i.total} if i.total is not None else {"values": list(i.values)}),
            }
            for i in domain.issues
        ],
    }


def from_dict(data: dict[str, Any]) -> Domain:
    if not isinstance(data, dict) or not isinstance(data.get("issues"), list):
        raise ValueError("A domain needs a JSON object containing an issues list.")
    if not all(isinstance(i, dict) and "name" in i for i in data["issues"]):
        raise ValueError("Each issue must be a named JSON object.")
    if data.get("schema_version", 1) != 1:
        raise ValueError("Unsupported domain schema version.")
    return Domain(
        data["name"],
        tuple(Issue(i["name"], tuple(i.get("values", ())), i.get("total")) for i in data["issues"]),
    )


def to_json(domain: Domain) -> str:
    return json.dumps(to_dict(domain), indent=2, allow_nan=False)


def from_json(text: str) -> Domain:
    if len(text) > 2_000_000:
        raise ValueError("Domain JSON exceeds the 2 MB import limit.")
    try:
        return from_dict(json.loads(text))
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid domain JSON: {exc}") from exc


def from_xml(text: str, *, name: str = "Imported domain") -> ImportResult:
    if len(text) > 2_000_000:
        raise ValueError("Domain XML exceeds the 2 MB import limit.")
    try:
        root = fromstring(text)
        space = root if root.tag == "utility_space" else root.find(".//utility_space")
        if space is None:
            raise ValueError("XML has no utility_space.")
        notes = []
        if not space.get("domain_name"):
            notes.append("Domain name was absent; the provided import name is used.")
        issues = []
        for node in space.findall("issue"):
            total = node.get("max_count")
            if total is not None:
                issues.append(Issue(node.attrib["name"], total=int(total)))
                if not node.findall("item"):
                    notes.append(f"{node.attrib['name']}: generated counts 0 through {total}.")
            else:
                issues.append(
                    Issue(
                        node.attrib["name"],
                        tuple(item.attrib["value"] for item in node.findall("item")),
                    )
                )
        domain = Domain(space.get("domain_name", name), tuple(issues))
        profile = None
        nodes = space.findall("issue")
        weights_by_index = {
            n.attrib["index"]: float(n.attrib["value"]) for n in space.findall("weight")
        }
        if len(weights_by_index) != len(space.findall("weight")):
            raise ValueError("Duplicate issue weights in domain XML.")
        complete = all(
            len(node.findall("item")) == len(issue.values)
            and all("evaluation" in item.attrib for item in node.findall("item"))
            and node.get("index") in weights_by_index
            for node, issue in zip(nodes, issues, strict=True)
        )
        if complete:
            weights = {
                issue.name: weights_by_index[node.attrib["index"]]
                for node, issue in zip(nodes, issues, strict=True)
            }
            scores = {
                issue.name: {
                    (
                        int(item.attrib["value"]) if domain.allocation else item.attrib["value"]
                    ): float(item.attrib["evaluation"])
                    for item in node.findall("item")
                }
                for node, issue in zip(nodes, issues, strict=True)
            }
            reservation = space.find("reservation")
            profile = Preference(
                domain,
                weights,
                scores,
                "assigned",
                float(reservation.get("value", "0")) if reservation is not None else 0.0,
            )
            notes.append(
                "Complete additive profile imported at full precision; no normalization was inferred."
            )
        elif weights_by_index:
            notes.append(
                "Issue weights were present but value scores were incomplete. Import contains domain only; configure or elicit a full profile."
            )
        return ImportResult(domain, tuple(notes), profile)
    except (DefusedXmlException, ParseError, KeyError, TypeError) as exc:
        raise ValueError(f"Invalid domain XML: {exc}") from exc


def to_xml(domain: Domain, profile: "Preference | None" = None) -> str:
    from xml.etree.ElementTree import Element, SubElement, tostring

    if profile is not None and profile.domain != domain:
        raise ValueError("Profile and exported domain must match.")
    root = Element("negotiation_domain")
    space = SubElement(root, "utility_space", domain_name=domain.name)
    for index, issue in enumerate(domain.issues, 1):
        attrs = {"index": str(index), "name": issue.name}
        if issue.total is not None:
            attrs["max_count"] = str(issue.total)
        node = SubElement(space, "issue", attrs)
        for position, value in enumerate(issue.values, 1):
            attrs = {"index": str(position), "value": str(value)}
            if profile is not None:
                attrs["evaluation"] = str(profile.scores[issue.name][value])
            SubElement(node, "item", attrs)
        if profile is not None:
            SubElement(space, "weight", index=str(index), value=str(profile.weights[issue.name]))
    if profile is not None:
        SubElement(space, "reservation", value=str(profile.reservation))
    return tostring(root, encoding="unicode")
