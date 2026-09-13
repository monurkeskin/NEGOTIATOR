"""Rebuildable session/participant/study reports from verified canonical journals."""

import csv
import hashlib
import html
import json
import platform
from collections import defaultdict
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path
from typing import Any

from negotiator import __version__
from negotiator.application.session import SessionConfig
from negotiator.domain import Bid, Preference
from negotiator.domain.importers import from_dict, to_dict
from negotiator.events.journal import Journal, JournalError, canonical_json, digest
from negotiator.events.projection import replay
from negotiator.examples import builtin_domain
from negotiator.models.cbom import CBOMModel

from .metrics import (
    classify_move,
    distance,
    mean,
    model_errors,
    outcome_metrics,
    reference_points,
    validate_movement_threshold,
)
from .plots import session_figures

MOVEMENT_DEFINITION = "negolog-f7a4f88-with-explicit-missingness"


def read_session(
    path: Path, *, include_practice: bool = False, threshold: float = 0.03
) -> dict[str, Any]:
    validate_movement_threshold(threshold)
    events = Journal(path).read()
    if not events or events[0].kind != "session.started":
        raise ValueError("Expected a canonical session journal.")
    manifest = json.loads(path.with_name("manifest.json").read_text(encoding="utf-8"))
    if (
        digest(events[0].payload) != manifest["configuration_sha256"]
        or digest(manifest["configuration"]) != manifest["configuration_sha256"]
    ):
        raise JournalError("Report source manifest does not match the session configuration.")
    state = replay(events)
    config = state.config
    if state.outcome and "payoffs" in state.outcome:
        from negotiator.domain.scoring import reward_scores

        expected_scores = reward_scores(
            state.outcome["utilities"], config.get("reward_minimums", {}), state.outcome["reason"]
        )
        if state.outcome["payoffs"] != expected_scores:
            raise JournalError("Stored game scores disagree with the configured reward rule.")
    SessionConfig(**config)
    domain = from_dict(state.domain)
    human = Preference.from_dict(domain, state.human_profile)
    agent = Preference.from_dict(domain, state.agent_profile)
    model = CBOMModel(agent)
    offers = []
    previous: dict[str, dict[str, Any]] = {}
    for offer in state.offers:
        bid = Bid(offer["bid"])
        utilities = {"human": human.utility(bid), "agent": agent.utility(bid, "agent")}
        if utilities != offer["utilities"]:
            raise JournalError("Stored offer utilities disagree with the canonical bid/profile.")
        row = {
            **config,
            "offer_id": offer["offer_id"],
            "actor": offer["actor"],
            "bid": offer["bid"],
            "elapsed_seconds": offer["elapsed_seconds"],
            "event_sequence": offer["sequence"],
            "human_utility": utilities["human"],
            "agent_utility": utilities["agent"],
            "move": None,
            "move_definition": MOVEMENT_DEFINITION,
            "move_threshold": threshold,
        }
        actor = offer["actor"]
        other = "agent" if actor == "human" else "human"
        if actor in previous:
            prior = previous[actor]["utilities"]
            row["move"] = classify_move(
                utilities[actor] - prior[actor], utilities[other] - prior[other], threshold
            )
        previous[actor] = offer
        if actor == "human":
            model.observe(bid)
        offers.append(row)
    if state.outcome and state.outcome["reason"] == "agreement":
        pending = state.offers[-1] if state.offers else None
        if (
            not pending
            or state.outcome["offer_id"] != pending["offer_id"]
            or state.outcome["agreement"] != pending["bid"]
            or state.outcome["utilities"] != pending["utilities"]
            or state.outcome["actor"] == pending["actor"]
        ):
            raise JournalError("Agreement does not match the pending opponent offer.")
    exclusions = []
    if config["practice"] and not include_practice:
        exclusions.append("practice")
    if state.status != "ended":
        exclusions.append("session_in_progress")
    if state.outcome and state.outcome["reason"] in ("interrupted", "operator"):
        exclusions.append(state.outcome["reason"])
    observations = [
        {
            **e.payload,
            "session_id": config["session_id"],
            "elapsed_seconds": e.to_dict()["elapsed_seconds"],
            "event_sequence": e.sequence,
        }
        for e in events
        if e.kind == "perception.observed"
    ]
    perception = {}
    for field in ("valence", "arousal"):
        values = [o[field] for o in observations if o.get(field) is not None]
        perception[field] = {
            "count": len(values),
            "missing": len(observations) - len(values),
            "min": min(values) if values else None,
            "max": max(values) if values else None,
            "mean": mean(values),
            "missing_reason": None if values else "not_observed",
        }
    utility_space, reference, errors = [], None, None
    if state.status == "ended" and human.provenance != "estimated":
        bids = list(domain.bids())
        utility_space = [(human.utility(b), agent.utility(b, "agent")) for b in bids]
        reference = reference_points(utility_space, (human.reservation, agent.reservation))
        estimated_profile = model.preference
        errors = model_errors(
            [p[0] for p in utility_space], [estimated_profile.utility(b) for b in bids]
        )
        errors.update(
            observations=model.observations,
            stage="after_session",
            model="public-cbom-41345ae",
            reference_provenance=human.provenance,
        )
        reference["model_pareto_precision"] = None
        reference["model_pareto_recall"] = None
        estimated = [(estimated_profile.utility(b), agent.utility(b, "agent")) for b in bids]
        estimated_front = set(reference_points(estimated)["pareto"])
        estimated_ids = {i for i, p in enumerate(estimated) if p in estimated_front}
        true_front = set(reference["pareto"])
        true_ids = {i for i, p in enumerate(utility_space) if p in true_front}
        reference["model_pareto_precision"] = len(true_ids & estimated_ids) / len(estimated_ids)
        reference["model_pareto_recall"] = len(true_ids & estimated_ids) / len(true_ids)
        if state.outcome and state.outcome["utilities"]:
            point = (state.outcome["utilities"]["human"], state.outcome["utilities"]["agent"])
            reference["agreement_pareto_distance"] = distance(point, reference["pareto"])
            reference["agreement_raw_nash_distance"] = distance(point, reference["raw_nash_points"])
    presentations = [
        {
            **e.payload,
            "kind": e.kind,
            "elapsed_seconds": e.to_dict()["elapsed_seconds"],
            "wall_time_utc": e.to_dict()["wall_time_utc"],
            "session_id": config["session_id"],
        }
        for e in events
        if e.kind.startswith("presentation.")
    ]
    key = f"{config['study_id']}-{config['participant_id']}-{config['session_id']}"
    snapshot_bytes = ("\n".join(e.record_json for e in events) + "\n").encode()
    agreement = (
        (state.outcome["utilities"]["human"], state.outcome["utilities"]["agent"])
        if state.outcome and state.outcome["reason"] == "agreement"
        else None
    )
    return {
        "key": key,
        "config": config,
        "included": not exclusions,
        "exclusions": exclusions,
        "source_sha256": hashlib.sha256(snapshot_bytes).hexdigest(),
        "last_event_sequence": len(events),
        "domain_sha256": digest(state.domain),
        "human_provenance": human.provenance,
        "status": state.status,
        "outcome": state.outcome,
        "outcome_metrics": outcome_metrics(
            agreement, reference["raw_nash_product"] if reference else None
        ),
        "movement_contract": {
            "id": MOVEMENT_DEFINITION,
            "threshold": threshold,
            "near_zero_comparison": "absolute_delta_strictly_less_than_threshold",
            "utility_source": "recorded_profiles",
            "comparison": "successive_offers_by_the_same_actor",
            "role": "post_session_report_not_solver_decision_features",
        },
        "elapsed_seconds": state.elapsed_seconds,
        "offers": offers,
        "observations": observations,
        "perception": perception,
        "presentations": presentations,
        "reference": reference,
        "model_errors": errors,
        "reference_missing_reason": None
        if reference
        else "session_in_progress_or_estimated_profile",
        "utility_space": utility_space,
        "source_events": [e.to_dict() for e in events],
        "manifest": manifest,
    }


def study_records(
    root: Path, plan_id: str | None = None, *, snapshots: dict[str, bytes] | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[str] | None]:
    plans, answers = [], []
    selected_ids: set[str] | None = set() if plan_id else None
    for path in sorted((root / "_plans").glob("*/events.jsonl")):
        events = Journal(path).read()
        if not events:
            continue
        state = events[-1].payload["state"]
        if plan_id and state["plan_id"] != plan_id:
            continue
        if selected_ids is not None:
            selected_ids.update(state["session_ids"])
        spec = state["spec"]
        if snapshots is not None:
            from negotiator.application.session import validate_id

            validate_id(state["plan_id"])
            snapshots[state["plan_id"]] = ("\n".join(e.record_json for e in events) + "\n").encode()
        for index, condition in enumerate(state["conditions"], 1):
            sid = f"{state['plan_id']}-{index}"
            configured = condition.get("domain") or spec["domain"]
            domain = (
                builtin_domain(configured) if isinstance(configured, str) else from_dict(configured)
            )
            plans.append(
                {
                    "study_id": spec["study_id"],
                    "participant_id": spec["participant_id"],
                    "cohort": spec["cohort"],
                    "session_id": sid,
                    "sequence_index": index,
                    **condition,
                    "domain_sha256": digest(to_dict(domain)),
                    "status": "recorded" if sid in state["session_ids"] else "not_run",
                    "phase_at_export": state["phase"],
                    "order": spec["order"],
                    "plan_id": state["plan_id"],
                }
            )
        for response in state["answers"]:
            for item in response["items"]:
                value = response["answers"].get(item["id"])
                answers.append(
                    {
                        "study_id": spec["study_id"],
                        "participant_id": spec["participant_id"],
                        "cohort": spec["cohort"],
                        "phase": response["phase"],
                        "session_id": response["target_session_id"],
                        "sequence_index": response["sequence_index"],
                        "item_id": item["id"],
                        "prompt": item["prompt"],
                        "minimum": item["minimum"],
                        "maximum": item["maximum"],
                        "minimum_label": item.get("minimum_label"),
                        "maximum_label": item.get("maximum_label"),
                        "source": item["source"],
                        "value": value,
                        "missing_reason": "not_answered" if value is None else None,
                    }
                )
        for item in spec["surveys"]:
            phase = item["phase"]
            targets = (
                [(None, None)]
                if phase in ("pre_study", "post_study")
                else [
                    (f"{state['plan_id']}-{i}", i)
                    for i, condition in enumerate(state["conditions"], 1)
                    if not condition.get("practice", False) or item.get("include_practice", False)
                ]
            )
            for target_sid, target_index in targets:
                answered = any(
                    r["phase"] == phase
                    and r["target_session_id"] == target_sid
                    and any(i["id"] == item["id"] for i in r["items"])
                    for r in state["answers"]
                )
                if answered:
                    continue
                shown = any(
                    e.payload["state"]["phase"] == "survey"
                    and e.payload["state"]["survey_phase"] == phase
                    and (
                        target_index is None or e.payload["state"]["sequence_index"] == target_index
                    )
                    for e in events
                )
                answers.append(
                    {
                        "study_id": spec["study_id"],
                        "participant_id": spec["participant_id"],
                        "cohort": spec["cohort"],
                        "phase": phase,
                        "session_id": target_sid,
                        "sequence_index": target_index,
                        "item_id": item["id"],
                        "prompt": item["prompt"],
                        "minimum": item["minimum"],
                        "maximum": item["maximum"],
                        "minimum_label": item.get("minimum_label"),
                        "maximum_label": item.get("maximum_label"),
                        "source": item["source"],
                        "value": None,
                        "missing_reason": "not_answered" if shown else "not_administered",
                    }
                )
    return plans, answers, selected_ids


def aggregate(sessions: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for session in sessions:
        if session["included"]:
            c = session["config"]
            key = (
                c["study_id"],
                c["cohort"],
                session["domain_sha256"],
                c["condition"],
                c["strategy"],
            )
            grouped[key].append(session)
    summaries, participant_rows = [], []
    for group_key, records in grouped.items():
        people: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in records:
            people[record["config"]["participant_id"]].append(record)
        common = dict(
            zip(
                ("study_id", "cohort", "domain_sha256", "condition", "strategy"),
                group_key,
                strict=True,
            )
        )
        rows: list[dict[str, Any]] = []
        for person, values in people.items():
            agreements = [v for v in values if v["outcome"]["reason"] == "agreement"]
            row = {
                **common,
                "participant_id": person,
                "session_count": len(values),
                "agreement_rate": len(agreements) / len(values),
                "human_agreement_utility": mean(
                    [v["outcome"]["utilities"]["human"] for v in agreements]
                ),
                "agent_agreement_utility": mean(
                    [v["outcome"]["utilities"]["agent"] for v in agreements]
                ),
                "human_game_score": mean(
                    [
                        v["outcome"]["payoffs"]["human"]
                        for v in values
                        if v["outcome"].get("payoffs") is not None
                    ]
                ),
                "sessions_with_game_score": sum(
                    v["outcome"].get("payoffs") is not None for v in values
                ),
                "sequence_indices": [v["config"]["sequence_index"] for v in values],
            }
            rows.append(row)
            participant_rows.append(row)
        defined = [
            r["human_agreement_utility"] for r in rows if r["human_agreement_utility"] is not None
        ]
        summaries.append(
            {
                **common,
                "participants": len(people),
                "sessions": len(records),
                "mean_participant_agreement_rate": mean([r["agreement_rate"] for r in rows]),
                "participants_with_agreement": len(defined),
                "mean_human_agreement_utility": mean(defined),
                "mean_human_game_score": mean(
                    [r["human_game_score"] for r in rows if r["human_game_score"] is not None]
                ),
            }
        )
    return summaries, participant_rows


def pair_records(
    participants: list[dict[str, Any]], planned: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], dict[str, dict[str, float | None]]] = defaultdict(dict)
    conditions: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for row in participants:
        key = (row["study_id"], row["cohort"], row["domain_sha256"])
        condition = row["condition"] + " / " + row["strategy"]
        groups[key].setdefault(row["participant_id"], {})[condition] = row[
            "human_agreement_utility"
        ]
        conditions[key].add(condition)
    for row in planned:
        if row["practice"]:
            continue
        key = (row["study_id"], row["cohort"], row["domain_sha256"])
        groups[key].setdefault(row["participant_id"], {})
        conditions[key].add(row["label"] + " / " + row["strategy"])
    result = []
    for key, people in groups.items():
        for a, b in combinations(sorted(conditions[key]), 2):
            for person, values in people.items():
                ua, ub = values.get(a), values.get(b)
                complete = ua is not None and ub is not None
                result.append(
                    {
                        "study_id": key[0],
                        "cohort": key[1],
                        "domain_sha256": key[2],
                        "participant_id": person,
                        "condition_a": a,
                        "condition_b": b,
                        "human_utility_a": ua,
                        "human_utility_b": ub,
                        "complete": complete,
                        "human_utility_difference": ub - ua
                        if ub is not None and ua is not None
                        else None,
                        "missing_reason": None if complete else "missing_session_or_no_agreement",
                    }
                )
    return result


def safe_cell(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        value = json.dumps(value, ensure_ascii=False, allow_nan=False)
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def write_tables(output: Path, tables: dict[str, list[dict[str, Any]]]) -> None:
    from openpyxl import Workbook

    book = Workbook()
    book.remove(book.worksheets[0])
    for name, rows in tables.items():
        columns = list(dict.fromkeys(k for row in rows for k in row)) or ["status"]
        sheet = book.create_sheet(name[:31])
        sheet.append(columns)
        sheet.freeze_panes = "A2"
        with (output / f"{name}.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(columns)
            for row in rows:
                values = [safe_cell(row.get(key)) for key in columns]
                writer.writerow(values)
                sheet.append(values)
        sheet.auto_filter.ref = sheet.dimensions
    book.save(output / "records.xlsx")


def html_table(rows: list[dict[str, Any]], fields: list[str]) -> str:
    if not rows:
        return "<p>No eligible observations for this table.</p>"
    return (
        '<div class="scroll"><table><thead><tr>'
        + "".join("<th>" + html.escape(k.replace("_", " ")) + "</th>" for k in fields)
        + "</tr></thead><tbody>"
        + "".join(
            "<tr>"
            + "".join(
                "<td>"
                + html.escape(str(row.get(k) if row.get(k) is not None else "Missing"))
                + "</td>"
                for k in fields
            )
            + "</tr>"
            for row in rows
        )
        + "</tbody></table></div>"
    )


def build_report(
    source: Path,
    output: Path,
    *,
    include_practice: bool = False,
    threshold: float = 0.03,
    plan_id: str | None = None,
) -> Path:
    validate_movement_threshold(threshold)
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError("Report output already exists; choose a new directory to preserve it.")
    root = (
        source
        if source.is_dir()
        else next((p for p in source.parents if (p / "_plans").is_dir()), source.parent)
    )
    study_snapshots: dict[str, bytes] = {}
    planned, answers, selected_ids = study_records(root, plan_id, snapshots=study_snapshots)
    paths = [source] if source.is_file() else sorted(source.glob("*/*/*/events.jsonl"))
    sessions = []
    for path in paths:
        if selected_ids is not None and path.parent.name not in selected_ids:
            continue
        sessions.append(read_session(path, include_practice=include_practice, threshold=threshold))
    if not sessions and not planned:
        raise ValueError("No canonical sessions or planned study records found at this path.")
    if len({s["config"].get("synthetic", False) for s in sessions}) > 1:
        raise ValueError("Analyze synthetic and human study records in separate reports.")
    summaries, participants = aggregate(sessions)
    pairs = pair_records(participants, planned)
    data = {
        "schema_version": 1,
        "framework_version": __version__,
        "python": platform.python_version(),
        "generated_utc": datetime.now(UTC).isoformat(),
        "independent_unit": "participant",
        "include_practice": include_practice,
        "movement_threshold": threshold,
        "movement_definition": MOVEMENT_DEFINITION,
        "metric_definitions": {
            "utility_sum": {"id": "utility-sum-v1", "formula": "U_h + U_a"},
            "utility_product": {"id": "utility-product-v1", "formula": "U_h * U_a"},
            "normalized_utility_product": {
                "id": "normalized-utility-product-v1",
                "formula": "(U_h * U_a) / max_b(U_h(b) * U_a(b))",
                "reference": "all_outcomes_under_recorded_reference_profiles",
                "undefined": "null_with_reason_when_no_agreement_or_denominator_unavailable",
            },
        },
        "sessions": sessions,
        "planned_sessions": planned,
        "study_sources": [
            {
                "plan_id": pid,
                "relative_path": f"studies/{pid}/events.jsonl",
                "sha256": hashlib.sha256(content).hexdigest(),
                "event_count": len(content.splitlines()),
            }
            for pid, content in study_snapshots.items()
        ],
        "questionnaires": answers,
        "condition_summaries": summaries,
        "participant_condition_summaries": participants,
        "paired_participants": pairs,
        "inference": "descriptive_only; repeated offers are not independent participants",
    }
    output.mkdir(parents=True)
    for pid, content in study_snapshots.items():
        target = output / "studies" / pid / "events.jsonl"
        target.parent.mkdir(parents=True)
        target.write_bytes(content)
    offers = [o for s in sessions for o in s["offers"]]
    observations = [o for s in sessions for o in s["observations"]]
    tables = {
        "pairs": pairs,
        "offers": offers,
        "observations": observations,
        "planned_sessions": planned,
        "questionnaires": answers,
        "conditions": summaries,
        "participants": participants,
        "sessions": [
            {
                **s["config"],
                "status": s["status"],
                "reason": (s["outcome"] or {}).get("reason"),
                "included": s["included"],
                "exclusions": s["exclusions"],
                "offers": len(s["offers"]),
                **s["outcome_metrics"],
                "source_sha256": s["source_sha256"],
            }
            for s in sessions
        ],
        "presentations": [p for s in sessions for p in s["presentations"]],
    }
    write_tables(output, tables)
    fragments = []
    for record in sessions:
        directory = output / "sessions" / record["key"]
        directory.mkdir(parents=True)
        (directory / "source-events.jsonl").write_text(
            "".join(canonical_json(e) + "\n" for e in record["source_events"]),
            encoding="utf-8",
            newline="\n",
        )
        (directory / "manifest.json").write_text(
            canonical_json(record["manifest"]) + "\n", encoding="utf-8", newline="\n"
        )
        session_figures(directory, record)
        with (directory / "utility-space.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["human_utility", "agent_utility"])
            writer.writerows(record["utility_space"])
        c = record["config"]
        base = "sessions/" + record["key"] + "/"
        fragments.append(
            "<section><h2>"
            + html.escape(
                c["participant_id"]
                + " · "
                + c["condition"]
                + " · session "
                + str(c["sequence_index"])
            )
            + "</h2><p>"
            + html.escape(
                "Outcome: "
                + str((record["outcome"] or {}).get("reason", "in progress"))
                + " · Exclusions: "
                + (", ".join(record["exclusions"]) or "none")
            )
            + "</p>"
            + html_table(
                [record["outcome_metrics"]],
                ["utility_sum", "utility_product", "normalized_utility_product"],
            )
            + '<p>Agreement measures; the normalized product uses the maximum product in this session’s domain.</p><img alt="Committed offers by actor against elapsed seconds. Full numeric data is in offers.csv." src="'
            + base
            + 'trajectory.svg"><p><a href="'
            + base
            + 'trajectory.pdf">PDF</a> · <a href="'
            + base
            + 'source-events.jsonl">Canonical source snapshot</a></p>'
            + (
                '<img alt="Reference Pareto frontier and agreement in the utility space. Full outcome utilities are available as CSV." src="'
                + base
                + 'utility-space.svg">'
                if record["reference"]
                else ""
            )
            + (
                '<img alt="Separate valence and arousal observations; gaps indicate missing measurements." src="'
                + base
                + 'observations.svg">'
                if record["observations"]
                else ""
            )
            + "</section>"
        )
    (output / "analysis.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8"
    )
    page = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NEGOTIATOR study report</title><style>body{font:16px/1.6 system-ui;color:#183e35;background:#f5f7f3;max-width:1100px;margin:auto;padding:32px}h1,h2{line-height:1.2}section{background:white;border:1px solid #d7e1dc;padding:24px;border-radius:12px;margin:24px 0}a{color:#216c59}table{border-collapse:collapse;min-width:100%}th,td{padding:10px;border-bottom:1px solid #d7e1dc;text-align:left;white-space:nowrap}.scroll{overflow:auto}img{max-width:100%;height:auto}small{color:#4a675e}</style><h1>NEGOTIATOR · study report</h1><p>Descriptive results from canonical records. Independent unit: participant. Synthetic example records are functional checks, not human-study findings.</p><p><a href="records.xlsx">Workbook</a> · <a href="analysis.json">Analysis and provenance</a> · <a href="offers.csv">Offers CSV</a> · <a href="questionnaires.csv">Questionnaires CSV</a></p><p>Practice is excluded by default. Interrupted/operator-ended sessions are excluded from condition summaries. Withdrawals remain outcomes; agreement utility uses agreements only. Condition means average each participant first. Cohorts and domains stay separate. No inferential test is selected automatically.</p>"""
    page += (
        "<section><h2>Condition summaries</h2>"
        + html_table(
            summaries,
            [
                "study_id",
                "cohort",
                "condition",
                "strategy",
                "participants",
                "sessions",
                "mean_participant_agreement_rate",
                "participants_with_agreement",
                "mean_human_agreement_utility",
            ],
        )
        + "</section>"
    )
    page += (
        "<section><h2>Planned and missing sessions</h2>"
        + html_table(
            planned, ["participant_id", "cohort", "sequence_index", "label", "practice", "status"]
        )
        + "</section>"
    )
    page += (
        "<section><h2>Participant pairs</h2>"
        + html_table(
            pairs,
            [
                "participant_id",
                "cohort",
                "condition_a",
                "condition_b",
                "complete",
                "human_utility_difference",
                "missing_reason",
            ],
        )
        + "</section>"
    )
    page += (
        "".join(fragments)
        + "<small>Utility axes are fixed at 0–1. Reference geometry uses assigned/elicited profiles. Maximum utility sum is social welfare; raw-product and reservation-surplus Nash are separate. Original journals are preserved.</small></html>"
    )
    (output / "index.html").write_text(page, encoding="utf-8")
    import base64
    import re

    standalone = re.sub(
        r'src="([^"]+\.svg)"',
        lambda m: (
            'src="data:image/svg+xml;base64,'
            + base64.b64encode((output / m.group(1)).read_bytes()).decode()
            + '"'
        ),
        page,
    )
    standalone = re.sub(
        r'<a href="(?!https?://|data:)[^"]+">([^<]+)</a>',
        r"<span>\1 (in report ZIP)</span>",
        standalone,
    )
    (output / "standalone.html").write_text(standalone, encoding="utf-8")
    return output
