"""FastAPI + WebSocket server for the ARGUS console.

Run from backend/:  uvicorn argus.api.main:app --reload --port 8000
"""
import asyncio
import contextlib
import json
from typing import Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from argus import settings
from argus.audit import AuditLog
from argus.brief.llm import MODEL, brief_for, template_brief
from argus.config import site
from argus.fusion.engine import FusionEngine
from argus.ingest import demo_window, load_all_events
from argus.replay.clock import Replay
from argus.schema import Event, Incident

TICK_S = 0.25


class Runtime:
    def __init__(self):
        self.cfg = site()
        self.events = load_all_events(self.cfg)
        start, end = demo_window(self.cfg)
        self.engine = FusionEngine(self.cfg)
        self.replay = Replay(self.events, self.engine, start, end, speed=10.0)
        self.audit = AuditLog()
        self.clients: set[WebSocket] = set()
        self.recent: list[Event] = []
        self._briefing: set[str] = set()

    def snapshot(self) -> dict:
        return {
            "type": "snapshot",
            "clock": self.clock(),
            "summary": self.engine.summary(),
            "incidents": [i.model_dump() for i in self.engine.ranked(include_candidates=True)],
            "recent_events": [e.model_dump() for e in self.recent[-200:]],
        }

    def clock(self) -> dict:
        r = self.replay
        return {"sim_t": r.sim_t, "local": self.cfg.epoch_to_local(r.sim_t), "playing": r.playing,
                "speed": r.speed, "start_t": r.start_t, "end_t": r.end_t, "finished": r.finished}


rt: Runtime | None = None


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    global rt
    rt = Runtime()
    task = asyncio.create_task(_loop())
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


app = FastAPI(title="ARGUS", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
settings.WEB_VIDEO_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.WEB_VIDEO_DIR), name="media")


# ---- background replay loop ---------------------------------------------------------------
async def _loop():
    while True:
        await asyncio.sleep(TICK_S)
        new_events, changed = rt.replay.advance(TICK_S)
        await _publish(new_events, changed)


async def _publish(new_events: list[Event], changed: list[Incident]):
    if new_events:
        rt.recent.extend(new_events)
        del rt.recent[:-500]
    for inc in changed:
        _ensure_brief(inc)
    await _broadcast({
        "type": "tick", "clock": rt.clock(), "summary": rt.engine.summary(),
        "events": [e.model_dump() for e in new_events],
        "incidents": [i.model_dump() for i in changed],
    })


def _ensure_brief(inc: Incident):
    if inc.status not in ("open", "ack", "escalated"):
        return
    if inc.brief is None:
        inc.brief = template_brief(inc, rt.engine.evidence(inc.incident_id), rt.cfg)
    if inc.brief.generated_by == "template" and inc.incident_id not in rt._briefing:
        rt._briefing.add(inc.incident_id)
        asyncio.create_task(_upgrade_brief(inc))


async def _upgrade_brief(inc: Incident):
    try:
        brief = await asyncio.to_thread(brief_for, inc, rt.engine.evidence(inc.incident_id), rt.cfg)
        if rt.engine.incidents.get(inc.incident_id) is inc:     # still the same replay run
            inc.brief = brief
            await _broadcast({"type": "tick", "clock": rt.clock(), "summary": rt.engine.summary(),
                              "events": [], "incidents": [inc.model_dump()]})
    finally:
        rt._briefing.discard(inc.incident_id)


async def _broadcast(msg: dict):
    if not rt.clients:
        return
    data = json.dumps(msg)
    dead = []
    for ws in rt.clients:
        try:
            await ws.send_text(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        rt.clients.discard(ws)


# ---- REST ---------------------------------------------------------------------------------
@app.get("/api/health")
def health():
    by_source = {}
    for e in rt.events:
        by_source[e.source] = by_source.get(e.source, 0) + 1
    return {"ok": True, "events": len(rt.events), "by_source": by_source, "llm_model": MODEL}


@app.get("/api/config")
def config():
    cfg = rt.cfg
    clips = sorted(p.stem for p in settings.WEB_VIDEO_DIR.glob("*.mp4"))
    return {
        "site_name": cfg.raw["site_name"],
        "areas": cfg.raw["areas"], "cameras": cfg.raw["cameras"],
        "bookmarks": cfg.bookmarks(), "playbook": cfg.playbook["actions"],
        "thresholds": {k: cfg.fusion[k] for k in ("watch_threshold", "open_threshold", "siloed_alert_severity",
                                                   "context_max_severity")},
        "window": {"start_t": rt.replay.start_t, "end_t": rt.replay.end_t},
        "clips": clips, "fps": cfg.fps,
        "attribution": "MEVA dataset, Kitware Inc. / IARPA, CC-BY-4.0. Incidents are staged by actors.",
    }


@app.get("/api/state")
def state():
    return rt.snapshot()


@app.get("/api/incidents/{incident_id}")
def incident(incident_id: str):
    inc = rt.engine.incidents.get(incident_id)
    if inc is None:
        raise HTTPException(404, "unknown incident")
    return {"incident": inc.model_dump(), "evidence": [e.model_dump() for e in rt.engine.evidence(incident_id)]}


class ActionIn(BaseModel):
    action: Literal["ack", "escalate", "dismiss"]
    role: Literal["duty_officer", "supervisor"] = "duty_officer"
    note: str = ""


@app.post("/api/incidents/{incident_id}/action")
async def act(incident_id: str, body: ActionIn):
    if incident_id not in rt.engine.incidents:
        raise HTTPException(404, "unknown incident")
    inc = rt.engine.act(incident_id, body.action)
    entry = rt.audit.append(incident_id=incident_id, action=body.action, role=body.role, note=body.note,
                            sim_t=rt.replay.sim_t, score=inc.score)
    await _broadcast({"type": "tick", "clock": rt.clock(), "summary": rt.engine.summary(), "events": [],
                      "incidents": [inc.model_dump()]})
    return {"incident": inc.model_dump(), "audit": entry}


class ReplayIn(BaseModel):
    cmd: Literal["play", "pause", "speed", "seek", "reset"]
    value: float | None = None


@app.post("/api/replay")
async def replay_control(body: ReplayIn):
    r = rt.replay
    if body.cmd == "play":
        r.playing = True
    elif body.cmd == "pause":
        r.playing = False
    elif body.cmd == "speed" and body.value:
        r.speed = max(0.25, min(body.value, 60.0))
    elif body.cmd == "reset":
        r.playing = False
        r.reset()
        rt.recent.clear()
    elif body.cmd == "seek" and body.value is not None:
        rewound = body.value < r.sim_t
        new_events, changed = r.seek(body.value)
        if rewound:
            rt.recent = list(new_events)
        else:
            rt.recent.extend(new_events)
        for inc in changed:
            _ensure_brief(inc)
    snap = rt.snapshot()
    await _broadcast(snap)
    return snap["clock"]


@app.get("/api/audit")
def audit():
    return {"verified": rt.audit.verify(), "entries": rt.audit.entries()}


@app.get("/api/metrics")
def metrics():
    path = settings.CACHE_DIR / "metrics.json"
    if not path.exists():
        return {"available": False}
    return {"available": True, **json.loads(path.read_text(encoding="utf-8"))}


@app.get("/api/tracks/{stem}")
def tracks(stem: str):
    path = settings.TRACKS_DIR / f"{stem}.jsonl"
    if not path.exists() or path.resolve().parent != settings.TRACKS_DIR.resolve():
        raise HTTPException(404, "no tracks for this clip yet")
    return FileResponse(path, media_type="application/x-ndjson")


# ---- WebSocket ----------------------------------------------------------------------------
@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    rt.clients.add(websocket)
    await websocket.send_text(json.dumps(rt.snapshot()))
    try:
        while True:
            await websocket.receive_text()     # client pings; commands go through REST
    except WebSocketDisconnect:
        pass
    finally:
        rt.clients.discard(websocket)
