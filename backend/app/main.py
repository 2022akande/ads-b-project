"""FastAPI application: REST + WebSocket for the ADS-B defense demo (TDD §5.2)."""

from __future__ import annotations

import asyncio
import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger("ai-sysdef")

from .schema import AttackType
from .scenario import ScenarioEngine

engine = ScenarioEngine()


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine.start()  # auto-start the live stream for the demo
    yield
    engine.stop()


app = FastAPI(title="ai-sysdef — ADS-B Injection Defense", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # demo; tighten for any real deployment
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return unhandled errors as JSON (not a bare 'Internal Server Error' string) and
    log the full traceback to stderr so it is visible without CloudWatch.

    The `error`/`trace` fields make the real cause visible in the browser Network tab;
    drop them (keep the logging) once the deployment is debugged.
    """
    tb = traceback.format_exc()
    logger.error("Unhandled error on %s %s\n%s", request.method, request.url.path, tb)
    return JSONResponse(
        status_code=500,
        content={"error": f"{type(exc).__name__}: {exc}", "trace": tb.splitlines()[-8:]},
    )


class InjectRequest(BaseModel):
    attack_type: AttackType
    target_icao: str | None = None
    severity: float = Field(0.8, ge=0.0, le=1.0)


# --------------------------------- REST ----------------------------------- #
@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "running": engine._running}


@app.get("/api/model")
def model_info() -> dict:
    meta = dict(engine.detector.model_meta)
    meta["decision_threshold"] = engine.detector.DECISION_THRESHOLD
    return meta


@app.get("/api/tracks")
def tracks() -> dict:
    return {"tracks": list(engine.latest_tracks.values())}


@app.get("/api/detections")
def detections() -> dict:
    return {"detections": [d.model_dump(mode="json") for d in engine.detections_log]}


@app.post("/api/inject")
def inject(req: InjectRequest) -> dict:
    if req.attack_type == AttackType.NONE:
        return {"error": "attack_type must be path_mod, velocity_drift, or ghost"}
    return engine.inject(req.attack_type, req.target_icao, req.severity)


@app.post("/api/clear")
def clear() -> dict:
    return {"cleared": engine.clear_attacks()}


@app.post("/api/scenario/start")
def scenario_start() -> dict:
    engine.start()
    return {"running": True}


@app.post("/api/scenario/stop")
def scenario_stop() -> dict:
    engine.stop()
    return {"running": False}


# ------------------------------ WebSocket --------------------------------- #
@app.websocket("/ws/stream")
async def ws_stream(ws: WebSocket) -> None:
    await ws.accept()
    q = engine.subscribe()
    # Send a snapshot immediately so a fresh client isn't blank for a second.
    await ws.send_json({
        "type": "snapshot",
        "tracks": list(engine.latest_tracks.values()),
        "stats": engine.stats(list(engine.latest_tracks.values())),
    })
    try:
        while True:
            frame = await q.get()
            await ws.send_json(frame)
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:  # pragma: no cover
        pass
    finally:
        engine.unsubscribe(q)
