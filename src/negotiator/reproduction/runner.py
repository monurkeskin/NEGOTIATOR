"""Verify identities, compute independently, compare references, export auditable artifacts."""

import csv
import hashlib
import html
import json
import math
import platform
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from negotiator import __version__
from negotiator.software import runtime_identity

from .operations import OPERATIONS, Computation
from .schema import ReproductionSpec


def save_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8"
    )


def tex(value: Any) -> str:
    special = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    text = "--" if value is None else f"{value:.6g}" if isinstance(value, float) else str(value)
    return "".join(special.get(char, char) for char in text)


def export_computation(output: Path, computed: Computation) -> None:
    columns = list(computed.rows[0]) if computed.rows else ["no_available_rows"]
    with (output / "results.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(computed.rows)
    # A compact table of scalar summaries; CSV retains all computed rows and precision.
    scalar = [
        (key, value)
        for key, value in computed.results.items()
        if not isinstance(value, (list, dict))
    ]
    lines = [r"\begin{tabular}{lr}", r"Measure & Value \\ \hline"]
    lines += [f"{tex(key)} & {tex(value)} " + r"\\" for key, value in scalar]
    if "groups" in computed.results:
        keys = ["cohort", "domain", "complete_pairs", "mean_difference", "ci_lower", "ci_upper"]
        lines = [r"\begin{tabular}{llrrrr}", " & ".join(tex(k) for k in keys) + r" \\ \hline"]
        lines += [" & ".join(tex(row[key]) for key in keys) + r" \\" for row in computed.rows]
    lines += [r"\end{tabular}"]
    (output / "table.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if computed.points is not None or "groups" in computed.results:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        figure, axis = plt.subplots(figsize=(5.5, 4.5), layout="constrained")
        if computed.points is None:
            plt.close(figure)
            export_paired_plot(output, computed)
            return
        human, agent = zip(*computed.points, strict=True)
        axis.scatter(human, agent, s=15, alpha=0.65, color="#0072B2", edgecolors="none")
        axis.set(
            xlabel="Human additive utility",
            ylabel="Agent additive utility",
            title="Computed outcome space",
            xlim=(-0.02, 1.02),
            ylim=(-0.02, 1.02),
        )
        for suffix in ("svg", "pdf"):
            figure.savefig(output / f"outcome-space.{suffix}")
        plt.close(figure)


def export_paired_plot(output: Path, computed: Computation) -> None:
    import matplotlib.pyplot as plt

    groups = computed.results["groups"]
    figure, axis = plt.subplots(figsize=(7, max(2.8, 0.65 * len(groups) + 1)), layout="constrained")
    for index, group in enumerate(groups):
        mean, ci = group["mean_difference"], group["ci"]
        if mean is None:
            axis.text(0, index, "No complete pairs", va="center")
        else:
            axis.plot(mean, index, "o", color="#0072B2")
            if ci is not None:
                axis.hlines(index, ci[0], ci[1], color="#0072B2", linewidth=2)
    axis.axvline(0, color="#777777", linestyle="--", linewidth=0.8)
    axis.set_yticks(
        range(len(groups)),
        [
            f"{g['study_id']} / {g['cohort']} / {g['domain']} (n={g['complete_pairs']})"
            for g in groups
        ],
    )
    axis.set_xlabel("Mean paired utility difference (first condition minus second)")
    axis.set_title("Participant-level contrasts; percentile bootstrap intervals")
    for suffix in ("svg", "pdf"):
        figure.savefig(output / f"paired-contrasts.{suffix}")
    plt.close(figure)


def crate(output: Path, report: dict[str, Any]) -> None:
    files = []
    for path in sorted(output.iterdir()):
        if path.is_file() and path.name != "ro-crate-metadata.json":
            files.append(
                {
                    "@id": path.name,
                    "@type": "File",
                    "name": path.name,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    inputs = [
        {
            "@id": "urn:sha256:" + entry["sha256"],
            "@type": "File",
            "name": entry["id"],
            "sha256": entry["sha256"],
        }
        for entry in report["inputs"]
        if entry.get("sha256")
    ]
    save_json(
        output / "ro-crate-metadata.json",
        {
            "@context": "https://w3id.org/ro/crate/1.1/context",
            "@graph": [
                {
                    "@id": "ro-crate-metadata.json",
                    "@type": "CreativeWork",
                    "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
                    "about": {"@id": "./"},
                },
                {
                    "@id": "./",
                    "@type": "Dataset",
                    "name": report["result_id"],
                    "datePublished": report["generated_at_utc"],
                    "license": {"@id": "#rights"},
                    "description": f"{report['claim_scope']}; computation status: {report['status']}",
                    "hasPart": [{"@id": entry["@id"]} for entry in files],
                },
                {
                    "@id": "#calculation",
                    "@type": "CreateAction",
                    "actionStatus": "http://schema.org/PotentialActionStatus"
                    if report["status"] == "unavailable"
                    else "http://schema.org/CompletedActionStatus",
                    "instrument": {"@id": "#software"},
                    "object": [{"@id": entry["@id"]} for entry in inputs],
                    "result": {"@id": "report.json"},
                },
                {
                    "@id": "#software",
                    "@type": "SoftwareApplication",
                    "name": "NEGOTIATOR",
                    "softwareVersion": report["software"]["version"],
                },
                {
                    "@id": "#rights",
                    "@type": "CreativeWork",
                    "name": "Input and software rights remain separate",
                    "description": "This manifest grants no new rights to input data. Consult the input owners and the GPL-3.0-only software license before redistribution.",
                },
                *files,
                *inputs,
            ],
        },
    )


def run_reproduction(manifest: Path, output: Path) -> dict[str, Any]:
    manifest, output = Path(manifest).resolve(), Path(output)
    raw_manifest = manifest.read_bytes()
    spec = ReproductionSpec.model_validate_json(raw_manifest)
    if spec.environment.framework != __version__:
        raise ValueError(
            f"Framework mismatch: requires {spec.environment.framework}, running {__version__}."
        )
    if spec.environment.python and platform.python_version() != spec.environment.python:
        raise ValueError("Python version differs from the pinned reproduction environment.")
    if output.exists():
        raise FileExistsError("Choose a new output directory; existing evidence is preserved.")
    inputs, unavailable = [], []
    contents = []
    for item in spec.inputs:
        inputs.append(item.model_dump())
        if item.missing_reason:
            unavailable.append({"id": item.id, "reason": item.missing_reason})
            continue
        assert item.path is not None
        path = (manifest.parent / item.path).resolve()
        if not path.is_relative_to(manifest.parent):
            raise ValueError("Reproduction inputs must reside inside the manifest directory.")
        if not path.is_file():
            unavailable.append({"id": item.id, "reason": "Manifest input file is unavailable."})
            continue
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != item.sha256:
            raise ValueError(f"Input hash mismatch: {item.id}.")
        contents.append(json.loads(raw))
    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "paper_id": spec.paper_id,
        "result_id": spec.result_id,
        "claim_scope": spec.claim_scope,
        "analysis": spec.analysis,
        "parameters": spec.parameters,
        "manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
        "software": runtime_identity(),
        "inputs": inputs,
        "unavailable": unavailable,
        "results": None,
        "comparisons": [],
        "status": "unavailable",
    }
    computed = None
    if not unavailable:
        if len(contents) != 1:
            raise ValueError("This analysis requires exactly one input document.")
        computed = OPERATIONS[spec.analysis](contents[0], spec.parameters)
        report["results"] = computed.results
        for expected in spec.expected:
            actual = computed.results.get(expected.key)
            passed = (
                isinstance(actual, (int, float))
                and not isinstance(actual, bool)
                and math.isclose(
                    actual, expected.value, rel_tol=expected.rtol, abs_tol=expected.atol
                )
            )
            report["comparisons"].append(
                {**expected.model_dump(), "actual": actual, "passed": passed}
            )
        report["status"] = (
            ("verified" if all(c["passed"] for c in report["comparisons"]) else "mismatch")
            if spec.expected
            else "computed-unchecked"
        )
    # Check serialization before creating output, so nonfinite results cannot become a report.
    json.dumps(report, allow_nan=False)
    output.mkdir(parents=True)
    if computed is not None:
        export_computation(output, computed)
    save_json(output / "report.json", report)
    details = html.escape(json.dumps(report, indent=2, ensure_ascii=False))
    title = html.escape(spec.result_id)
    (output / "index.html").write_text(
        f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title} — reproduction</title>
<style>body{{font:16px system-ui;max-width:1000px;margin:3em auto;padding:1em}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}img{{max-width:100%}}</style>
<h1>{title}</h1><p>Status: <strong>{report["status"]}</strong> · Scope: {spec.claim_scope}</p>
<p>Reference scores are compared after independent computation. Synthetic validation does not reproduce human-study findings.</p>
<p><a href="report.json">Full precision JSON and evidence</a></p>
{('<p><a href="results.csv">Computed CSV</a> · <a href="table.tex">LaTeX summary</a></p>' if computed else "")}
{('<img src="outcome-space.svg" alt="Computed human and agent utilities for every allocation">' if computed and computed.points else "")}
<details open><summary>Calculation and comparison details</summary><pre>{details}</pre></details></html>""",
        encoding="utf-8",
    )
    crate(output, report)
    return report
