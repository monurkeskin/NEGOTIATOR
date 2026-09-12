"""Loopback web application. Participant access is checked before returning data."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from negotiator.adapters.process import BridgeConfig, BridgeError
from negotiator.application.contracts import (
    AffectRequest,
    CaptureRequest,
    CommandRequest,
    NoteRequest,
    PhaseRequest,
    PreferencesRequest,
    StudySpec,
    SurveyRequest,
    VisibleRequest,
)
from negotiator.application.protocol import (
    ordered_conditions,
    protocol_readiness,
    validate_profiles,
)
from negotiator.application.studies import PhaseError, StudyStore
from negotiator.domain.importers import from_dict, from_json, from_xml, to_dict
from negotiator.events.journal import JournalError
from negotiator.examples import builtin_domain, example_profiles
from negotiator.strategies import strategy_names


def create_app(
    root: Path,
    *,
    conductor_token: str | None = None,
    devices: dict[str, BridgeConfig] | None = None,
) -> FastAPI:
    store = StudyStore(root, conductor_token, devices)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async def clock_loop() -> None:
            while True:
                await asyncio.to_thread(store.tick)
                await asyncio.sleep(0.2)

        task = asyncio.create_task(clock_loop())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            store.shutdown()

    app = FastAPI(
        title="NEGOTIATOR local experiment app", lifespan=lifespan, docs_url=None, redoc_url=None
    )
    app.state.store = store

    @app.exception_handler(PermissionError)
    async def forbidden(request: Request, exc: PermissionError) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.exception_handler(PhaseError)
    async def conflict(request: Request, exc: PhaseError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def invalid(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(BridgeError)
    async def device_error(request: Request, exc: BridgeError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(JournalError)
    async def storage_error(request: Request, exc: JournalError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc), "saved": False})

    @app.exception_handler(KeyError)
    async def missing(request: Request, exc: KeyError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": "Record or field not found."})

    def admin(token: str | None) -> None:
        if store.role(token) != "conductor":
            raise PermissionError("Conductor access is required.")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ready"}

    @app.get("/api/catalog")
    def catalog(x_negotiator_token: str | None = Header(default=None)) -> dict[str, Any]:
        admin(x_negotiator_token)
        return {
            "strategies": strategy_names(),
            "domains": {
                name: to_dict(builtin_domain(name))
                for name in ("holiday", "holiday-b", "fruits", "island")
            },
            "outputs": ["text", "avatar", "nao", "pepper", "qt"],
            "devices": {
                name: {"family": c.family, "capabilities": c.capabilities}
                for name, c in store.devices.items()
            },
        }

    @app.post("/api/import-domain")
    def import_domain(
        body: dict[str, str], x_negotiator_token: str | None = Header(default=None)
    ) -> dict[str, Any]:
        admin(x_negotiator_token)
        if "json" in body:
            return {
                "domain": to_dict(from_json(body["json"])),
                "notes": ["Domain schema validated."],
            }
        imported = from_xml(body.get("xml", ""), name=body.get("name", "Imported domain"))
        return {
            "domain": to_dict(imported.domain),
            "notes": imported.notes,
            "profile": imported.profile.to_dict() if imported.profile else None,
        }

    @app.get("/api/studies")
    def studies(x_negotiator_token: str | None = Header(default=None)) -> list[dict[str, Any]]:
        admin(x_negotiator_token)
        return store.list()

    @app.post("/api/preview-profiles")
    def preview_profiles(
        body: dict[str, Any], x_negotiator_token: str | None = Header(default=None)
    ) -> dict[str, Any]:
        admin(x_negotiator_token)
        data = body["domain"]
        domain = builtin_domain(data) if isinstance(data, str) else from_dict(data)
        human, agent = example_profiles(domain)
        return {"human": human.to_dict(), "agent": agent.to_dict()}

    @app.post("/api/preview-study")
    def preview_study(
        spec: StudySpec, x_negotiator_token: str | None = Header(default=None)
    ) -> dict[str, Any]:
        admin(x_negotiator_token)
        conditions = ordered_conditions(spec)
        validate_profiles(spec, conditions)
        return {
            "configuration": spec.model_dump(),
            "conditions": conditions,
            "readiness": protocol_readiness(spec, verify_hashes=False),
        }

    @app.post("/api/studies/{pid}/preview-offer")
    def preview_offer(
        pid: str, body: dict[str, Any], x_negotiator_token: str | None = Header(default=None)
    ) -> dict[str, Any]:
        store.role(x_negotiator_token, pid)
        return store.preview_offer(pid, body["values"])

    @app.post("/api/studies")
    def create(
        spec: StudySpec, x_negotiator_token: str | None = Header(default=None)
    ) -> dict[str, Any]:
        admin(x_negotiator_token)
        return store.create(spec)

    @app.get("/api/studies/{pid}")
    def get(pid: str, x_negotiator_token: str | None = Header(default=None)) -> dict[str, Any]:
        role = store.role(x_negotiator_token, pid)
        return store.snapshot(pid, role)

    @app.patch("/api/studies/{pid}")
    def edit(
        pid: str, body: dict[str, Any], x_negotiator_token: str | None = Header(default=None)
    ) -> dict[str, Any]:
        admin(x_negotiator_token)
        return store.update(pid, body)

    @app.post("/api/studies/{pid}/preferences")
    def preferences(
        pid: str, body: PreferencesRequest, x_negotiator_token: str | None = Header(default=None)
    ) -> dict[str, Any]:
        role = store.role(x_negotiator_token, pid)
        store.preferences(pid, body)
        return store.snapshot(pid, role)

    @app.post("/api/studies/{pid}/start")
    def start(pid: str, x_negotiator_token: str | None = Header(default=None)) -> dict[str, Any]:
        admin(x_negotiator_token)
        store.start(pid)
        return store.snapshot(pid)

    @app.post("/api/studies/{pid}/command")
    def command(
        pid: str, body: CommandRequest, x_negotiator_token: str | None = Header(default=None)
    ) -> dict[str, Any]:
        role = store.role(x_negotiator_token, pid)
        result = store.command(pid, body)
        return {**result, "state": store.snapshot(pid, role)}

    @app.post("/api/studies/{pid}/next")
    def next_phase(
        pid: str, body: PhaseRequest, x_negotiator_token: str | None = Header(default=None)
    ) -> dict[str, Any]:
        role = store.role(x_negotiator_token, pid)
        store.next(pid, body.request_id, body.phase_id)
        return store.snapshot(pid, role)

    @app.post("/api/studies/{pid}/survey")
    def survey(
        pid: str, body: SurveyRequest, x_negotiator_token: str | None = Header(default=None)
    ) -> dict[str, Any]:
        role = store.role(x_negotiator_token, pid)
        store.survey(pid, body)
        return store.snapshot(pid, role)

    @app.post("/api/studies/{pid}/note")
    def note(
        pid: str, body: NoteRequest, x_negotiator_token: str | None = Header(default=None)
    ) -> dict[str, Any]:
        admin(x_negotiator_token)
        store.note(pid, body.text, body.request_id, phase_id=body.phase_id)
        return store.snapshot(pid)

    @app.post("/api/studies/{pid}/terminate")
    def terminate(
        pid: str, body: NoteRequest, x_negotiator_token: str | None = Header(default=None)
    ) -> dict[str, Any]:
        admin(x_negotiator_token)
        store.terminate(pid, body.text, body.request_id, phase_id=body.phase_id)
        return store.snapshot(pid)

    @app.post("/api/studies/{pid}/preflight")
    def preflight(
        pid: str, x_negotiator_token: str | None = Header(default=None)
    ) -> dict[str, Any]:
        admin(x_negotiator_token)
        return store.preflight(pid)

    @app.post("/api/studies/{pid}/visible")
    def visible(
        pid: str, body: VisibleRequest, x_negotiator_token: str | None = Header(default=None)
    ) -> dict[str, bool]:
        if store.role(x_negotiator_token, pid) != "participant":
            raise PermissionError("Only the participant display can acknowledge visibility.")
        store.visible(pid, body.session_id, body.event_id)
        return {"saved": True}

    @app.post("/api/studies/{pid}/affect")
    def affect(
        pid: str, body: AffectRequest, x_negotiator_token: str | None = Header(default=None)
    ) -> dict[str, bool]:
        store.role(x_negotiator_token, pid)
        store.affect(pid, body.session_id, body.values, body.request_id)
        return {"saved": True}

    @app.post("/api/studies/{pid}/capture")
    def capture(
        pid: str, body: CaptureRequest, x_negotiator_token: str | None = Header(default=None)
    ) -> dict[str, Any]:
        store.role(x_negotiator_token, pid)
        return store.capture(pid, body.session_id, body.kind, body.request_id)

    @app.post("/api/studies/{pid}/report")
    def report(pid: str, x_negotiator_token: str | None = Header(default=None)) -> dict[str, Any]:
        admin(x_negotiator_token)
        if store.snapshot(pid)["phase"] == "active":
            raise PhaseError("End the active session before running offline analysis.")
        from uuid import uuid4

        from negotiator.analysis.report import build_report

        rid = uuid4().hex
        directory = build_report(store.root, store.root / "_reports" / rid, plan_id=pid)
        return {
            "report_id": rid,
            "html": (directory / "standalone.html").read_text(encoding="utf-8"),
        }

    @app.get("/api/reports/{rid}/download")
    def download(rid: str, x_negotiator_token: str | None = Header(default=None)) -> FileResponse:
        admin(x_negotiator_token)
        import re
        import shutil

        if not re.fullmatch(r"[0-9a-f]{32}", rid):
            raise ValueError("Invalid report ID.")
        directory = store.root / "_reports" / rid
        if not directory.is_dir():
            raise KeyError("Report not found.")
        archive = directory.with_suffix(".zip")
        if not archive.exists():
            shutil.make_archive(str(directory), "zip", directory)
        return FileResponse(archive, media_type="application/zip", filename="negotiator-report.zip")

    static = Path(__file__).with_name("static")
    if (static / "assets").exists():
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        if not (static / "index.html").exists():
            raise HTTPException(
                503, "GUI assets are missing. Build the frontend or install a release wheel."
            )
        return FileResponse(static / "index.html")

    return app
