from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from agentflow.loader import load_pipeline_from_text
from agentflow.orchestrator import Orchestrator
from agentflow.specs import PipelineSpec
from agentflow.store import RunStore


def create_app(*, store: RunStore | None = None, orchestrator: Orchestrator | None = None) -> FastAPI:
    store = store or RunStore()
    orchestrator = orchestrator or Orchestrator(store=store)
    app = FastAPI(title="AgentFlow", version="0.1.0")
    app.state.store = store
    app.state.orchestrator = orchestrator

    base_dir = Path(__file__).resolve().parent / "web"
    templates = Jinja2Templates(directory=str(base_dir / "templates"))
    app.mount("/static", StaticFiles(directory=str(base_dir / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        example_path = Path("examples/pipeline.yaml")
        example = example_path.read_text(encoding="utf-8") if example_path.exists() else "name: example\nnodes: []\n"
        return templates.TemplateResponse("index.html", {"request": request, "example": example})

    @app.get("/api/examples/default")
    async def default_example() -> JSONResponse:
        return JSONResponse({"yaml": Path("examples/pipeline.yaml").read_text(encoding="utf-8")})

    @app.post("/api/runs")
    async def create_run(request: Request) -> JSONResponse:
        payload = await request.json()
        if "yaml" in payload:
            pipeline = load_pipeline_from_text(payload["yaml"])
        else:
            pipeline = PipelineSpec.model_validate(payload["pipeline"] if "pipeline" in payload else payload)
        run = await app.state.orchestrator.submit(pipeline)
        return JSONResponse(run.model_dump(mode="json"))

    @app.get("/api/runs")
    async def list_runs() -> JSONResponse:
        return JSONResponse([run.model_dump(mode="json") for run in app.state.store.list_runs()])

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str) -> JSONResponse:
        try:
            run = app.state.store.get_run(run_id)
        except KeyError as exc:  # pragma: no cover - exercised by API callers only
            raise HTTPException(status_code=404, detail="run not found") from exc
        return JSONResponse(run.model_dump(mode="json"))

    @app.get("/api/runs/{run_id}/events")
    async def get_events(run_id: str) -> JSONResponse:
        return JSONResponse([event.model_dump(mode="json") for event in app.state.store.get_events(run_id)])

    @app.get("/api/runs/{run_id}/stream")
    async def stream_run(run_id: str):
        queue = await app.state.store.subscribe(run_id)

        async def event_stream():
            try:
                for cached in app.state.store.get_events(run_id):
                    yield f"data: {cached.model_dump_json()}\n\n"
                while True:
                    event = await asyncio.to_thread(queue.get)
                    yield f"data: {event.model_dump_json()}\n\n"
                    run = app.state.store.get_run(run_id)
                    if run.status.value in {"completed", "failed"} and event.type == "run_completed":
                        break
            finally:
                await app.state.store.unsubscribe(run_id, queue)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.get("/api/health")
    async def health() -> JSONResponse:
        return JSONResponse({"ok": True})

    return app
