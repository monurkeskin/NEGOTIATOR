"""Command-line entrypoints share the application services used by the GUI."""

import argparse
import json
import os
import platform
import sys
import webbrowser
from pathlib import Path
from typing import Any

from negotiator import __version__
from negotiator.events.journal import Journal, JournalError
from negotiator.events.projection import replay
from negotiator.examples import builtin_domain, run_demo


def output(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False))


def main(argv: list[str] | None = None) -> int:
    # File and pipe output use the same encoding as exported research records.
    for stream in (sys.stdout, sys.stderr):
        configure = getattr(stream, "reconfigure", None)
        if callable(configure):
            configure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="NEGOTIATOR: local human-agent negotiation studies"
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Run a synthetic session without devices or network")
    demo.add_argument("--output", type=Path, default=Path("demo-output"))
    playback = commands.add_parser("replay", help="Read a journal without changing the original")
    playback.add_argument("journal", type=Path)
    commands.add_parser("doctor", help="Check the local installation without connecting to devices")
    gui = commands.add_parser("gui", help="Open the local conductor and participant application")
    gui.add_argument("--data-dir", type=Path, default=Path("local-data"))
    gui.add_argument("--port", type=int, default=8765)
    gui.add_argument(
        "--devices", type=Path, help="Local JSON file describing installed device bridges"
    )
    gui.add_argument("--no-browser", action="store_true")
    bridge_files = commands.add_parser(
        "bridge-files", help="Export standalone legacy bridge scripts for a separate runtime"
    )
    bridge_files.add_argument("--output", type=Path, required=True)
    gui.add_argument("--study", type=Path, help="Create a study from a JSON configuration")
    report = commands.add_parser(
        "report", help="Export offline HTML, CSV, XLSX and figures from canonical records"
    )
    report.add_argument("source", type=Path)
    report.add_argument("--output", type=Path, required=True)
    report.add_argument("--include-practice", action="store_true")
    reproduction = commands.add_parser(
        "reproduce", help="Recompute a pinned method/result recipe and compare references"
    )
    reproduction.add_argument("manifest", type=Path)
    reproduction.add_argument("--output", type=Path, required=True)
    citation = commands.add_parser(
        "cite", help="Cite the papers and software used by verified session records"
    )
    citation.add_argument("run_dir", type=Path)
    citation.add_argument("--format", choices=("bibtex", "json"), default="bibtex")
    recovery = commands.add_parser(
        "recover", help="Recover a verified prefix to a new copy, preserving the damaged source"
    )
    recovery.add_argument("journal", type=Path)
    recovery.add_argument("--output", type=Path, required=True)
    run = commands.add_parser(
        "run", help="Execute a bounded, explicitly synthetic study configuration"
    )
    run.add_argument("configuration", type=Path)
    run.add_argument("--synthetic", action="store_true", required=True)
    run.add_argument("--output", type=Path, required=True)
    legacy = commands.add_parser(
        "import-legacy",
        help="Map legacy CSV observations without modifying or inferring source data",
    )
    legacy.add_argument("source", type=Path)
    legacy.add_argument("--mapping", type=Path, required=True)
    legacy.add_argument("--output", type=Path, required=True)
    legacy.add_argument("--arousal-overwritten", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "cite":
            from negotiator.citations import run_citations, to_bibtex

            citations = run_citations(args.run_dir)
            if args.format == "bibtex":
                print(to_bibtex(citations))
            else:
                output(citations)
        elif args.command == "reproduce":
            from negotiator.reproduction import run_reproduction

            result = run_reproduction(args.manifest, args.output)
            output({"status": result["status"], "report": str(args.output / "index.html")})
            return {"verified": 0, "computed-unchecked": 0, "mismatch": 2, "unavailable": 3}[
                result["status"]
            ]
        elif args.command == "bridge-files":
            import shutil

            source = Path(__file__).with_name("bridges")
            args.output.mkdir(parents=True, exist_ok=False)
            for name in ("protocol.py", "naoqi_legacy.py", "qt_legacy.py"):
                shutil.copyfile(source / name, args.output / name)
            output({"bridge_files": str(args.output.resolve()), "hardware_connected": False})
        elif args.command == "import-legacy":
            from negotiator.analysis.legacy import import_legacy

            output(
                {
                    "imported": str(
                        import_legacy(
                            args.source,
                            json.loads(args.mapping.read_text(encoding="utf-8")),
                            args.output,
                            arousal_overwritten=args.arousal_overwritten,
                        )
                    )
                }
            )
        elif args.command == "report":
            from negotiator.analysis.report import build_report

            output(
                {
                    "report": str(
                        build_report(
                            args.source, args.output, include_practice=args.include_practice
                        )
                        / "index.html"
                    )
                }
            )
        elif args.command == "recover":
            from negotiator.events.recovery import recover_copy

            output({"recovered_copy": str(recover_copy(args.journal, args.output))})
        elif args.command == "run":
            from negotiator.application.contracts import StudySpec
            from negotiator.application.synthetic import run_study

            output(
                run_study(
                    StudySpec.model_validate_json(args.configuration.read_text(encoding="utf-8")),
                    args.output,
                )
            )
        elif args.command == "demo":
            session = run_demo(args.output)
            output(
                {
                    "synthetic": True,
                    "journal": str(session.journal.path.resolve()),
                    "outcome": session.snapshot()["outcome"],
                }
            )
        elif args.command == "replay":
            output(replay(Journal(args.journal).read()).to_dict())
        elif args.command == "doctor":
            domains = {
                name: builtin_domain(name).size
                for name in ("holiday", "holiday-b", "fruits", "island")
            }
            output(
                {
                    "version": __version__,
                    "python": platform.python_version(),
                    "offline_demo_ready": True,
                    "domains": domains,
                    "hardware_validation": "not_performed",
                }
            )
        elif args.command == "gui":
            import uvicorn

            from negotiator.adapters.process import load_devices
            from negotiator.web.app import create_app

            app = create_app(
                args.data_dir,
                conductor_token=os.environ.get("NEGOTIATOR_ACCESS_TOKEN"),
                devices=load_devices(args.devices),
            )
            plan_query = ""
            if args.study:
                from negotiator.application.contracts import StudySpec

                plan = app.state.store.create(
                    StudySpec.model_validate_json(args.study.read_text(encoding="utf-8"))
                )
                plan_query = "?plan=" + plan["plan_id"]
            url = (
                f"http://127.0.0.1:{args.port}/{plan_query}#token={app.state.store.conductor_token}"
            )
            print(f"Conductor: {url}", flush=True)
            if not args.no_browser:
                webbrowser.open(url)
            uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    except (ValueError, OSError, JournalError) as exc:
        print(f"NEGOTIATOR: {exc}", file=sys.stderr)
        return 1
    return 0
