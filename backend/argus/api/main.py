"""FastAPI + WebSocket server for the ARGUS console.

Run from backend/:  uvicorn argus.api.main:app --reload --port 8000
"""
import asyncio
import contextlib
import json
import logging
import os
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from argus import settings
from argus.access import for_duty_officer, pin_required, require_supervisor, role_of
from argus.audit import AuditLog
from argus.brief.llm import MODEL, brief_for, cache_key
from argus.config import profiles, site
from argus.fusion.engine import FusionEngine
from argus.ingest import demo_window, load_all_events
from argus.replay.clock import Replay
from argus.schema import Event, Incident

logger = logging.getLogger("argus")
TICK_S = 0.25
RECENT_MAX = 500


class Runtime:
    def __init__(self):
        self.profile = os.environ.get("ARGUS_PROFILE") or profiles().get("default")
        self.cfg = site().with_profile(self.profile)
        self.events = load_all_events(self.cfg)
        start, end = demo_window(self.cfg)
        self.engine = FusionEngine(self.cfg)
        self.replay = Replay(self.events, self.engine, start, end, speed=10.0)
        self.audit = AuditLog()
        self.clients: set[WebSocket] = set()
        self.recent: list[Event] = []
        self._briefing: set[str] = set()
        self._brief_keys: dict[str, str] = {}      # incident -> the evidence its current brief was written for
        self._tasks: set[asyncio.Task] = set()     # strong refs, or the event loop may drop running tasks

    def remember(self, events: list[Event]) -> None:
        self.recent.extend(events)
        del self.recent[:-RECENT_MAX]

    def snapshot(self) -> dict:
        return {
            "type": "snapshot",
            "profile": self.profile,
            "clock": self.clock(),
            "summary": self.engine.summary(),
            "incidents": [i.model_dump() for i in self.engine.ranked(include_candidates=True)],
            "recent_events": [e.model_dump() for e in self.recent[-200:]],
        }

    def set_profile(self, name: str) -> None:
        """Re-score everything seen so far under another security profile (same events, same replay position)."""
        at, playing, speed = self.replay.sim_t, self.replay.playing, self.replay.speed
        self.profile = name
        self.cfg = site().with_profile(name)
        self.engine = FusionEngine(self.cfg)
        start, end = demo_window(self.cfg)
        self.replay = Replay(self.events, self.engine, start, end, speed=speed)
        self.recent.clear()
        new_events, _ = self.replay.seek(at)
        self.remember(new_events)
        for ev in getattr(self, "live_events", []):      # live-camera alerts survive a profile switch
            self.engine.ingest(ev)
        self.replay.playing = playing

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
        try:
            new_events, changed = rt.replay.advance(TICK_S)
            await _publish(new_events, changed)
        except Exception:                       # one bad tick must never stop the replay for the rest of the demo
            logger.exception("replay tick failed")


async def _publish(new_events: list[Event], changed: list[Incident]):
    if new_events:
        rt.remember(new_events)
    for inc in changed:
        _ensure_brief(inc)
    await _broadcast({
        "type": "tick", "clock": rt.clock(), "summary": rt.engine.summary(),
        "events": [e.model_dump() for e in new_events],
        "incidents": [i.model_dump() for i in changed],
    })


def _ensure_brief(inc: Incident):
    """Keep the brief in step with the evidence. When the evidence changes (a bag left is then taken), the brief for
    the new evidence comes at once from the cache (briefs are keyed by evidence and pre-warmed by brief/warm.py for
    every state of the replay), else the template; a language-model brief then replaces the template when it can."""
    if inc.status not in ("open", "ack", "escalated"):
        return
    key = cache_key(inc)
    if inc.brief is None or rt._brief_keys.get(inc.incident_id) != key:
        inc.brief = brief_for(inc, rt.engine.evidence(inc.incident_id), rt.cfg, allow_llm=False)
        rt._brief_keys[inc.incident_id] = key
    if inc.brief.generated_by == "template" and inc.incident_id not in rt._briefing:
        rt._briefing.add(inc.incident_id)
        task = asyncio.create_task(_upgrade_brief(inc))
        rt._tasks.add(task)
        task.add_done_callback(rt._tasks.discard)


async def _upgrade_brief(inc: Incident):
    key = cache_key(inc)
    current = False
    try:
        brief = await asyncio.to_thread(brief_for, inc, rt.engine.evidence(inc.incident_id), rt.cfg)
        current = rt.engine.incidents.get(inc.incident_id) is inc      # still the same replay run
        if current and cache_key(inc) == key:                           # and nothing new arrived while it was written
            inc.brief = brief
            rt._brief_keys[inc.incident_id] = key
            await _broadcast({"type": "tick", "clock": rt.clock(), "summary": rt.engine.summary(),
                              "events": [], "incidents": [inc.model_dump()]})
    finally:
        rt._briefing.discard(inc.incident_id)
        if current and cache_key(inc) != key:
            _ensure_brief(inc)                                         # brief the evidence it has now


async def _broadcast(msg: dict):
    if not rt.clients:
        return
    data = json.dumps(msg)
    dead = []
    for ws in list(rt.clients):
        try:
            await ws.send_text(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        rt.clients.discard(ws)


# ---- REST ---------------------------------------------------------------------------------
@app.get("/api/health")
async def health():
    by_source = {}
    for e in rt.events:
        by_source[e.source] = by_source.get(e.source, 0) + 1
    return {"ok": True, "events": len(rt.events), "by_source": by_source, "llm_model": MODEL}


@app.get("/api/config")
async def config():
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
        "profile": rt.profile,
        "profiles": [{"id": k, "label": v["label"], "description": v.get("description", "")}
                     for k, v in profiles()["profiles"].items()],
        "geometry": _area_geometry(),
        "supervisor_pin_required": pin_required(),
        "attribution": "MEVA dataset, Kitware Inc. / IARPA, CC-BY-4.0. Incidents are staged by actors.",
    }


def _area_geometry() -> dict[str, list[list[float]]]:
    """Outer ring [lon, lat] of every fusion area, for the console's site map."""
    geo = json.loads((settings.CONFIG_DIR / "areas.geojson").read_text(encoding="utf-8"))
    return {f["properties"]["area"]: f["geometry"]["coordinates"][0] for f in geo["features"]}


@app.get("/api/state")
async def state():
    return rt.snapshot()


@app.get("/api/role")
async def whoami(request: Request):
    """The caller's role as the backend sees it (checks the supervisor PIN when one is set)."""
    return {"role": role_of(request), "pin_required": pin_required()}


@app.get("/api/incidents/{incident_id}")
async def incident(incident_id: str, request: Request):
    """An incident and its evidence. A duty officer gets the evidence without detector internals; a supervisor gets
    it whole, plus `internals`: how each signal was weighted and what each source contributed to the score."""
    inc = rt.engine.incidents.get(incident_id)
    if inc is None:
        raise HTTPException(404, "unknown incident")
    role = role_of(request)
    evidence = [e.model_dump() for e in rt.engine.evidence(incident_id)]
    if role != "supervisor":
        return {"incident": inc.model_dump(), "evidence": [for_duty_officer(e) for e in evidence], "role": role}
    return {"incident": inc.model_dump(), "evidence": evidence, "role": role, "internals": _internals(inc)}


def _internals(inc: Incident) -> dict:
    """Detector internals for supervisors: every signal's raw strength and the profile's weighting of it, the
    strongest signal of each source (the ones the score uses), and each source's marginal contribution: the score
    with that source's evidence removed, re-run through the real scorer."""
    from argus.fusion.score import score_incident, strongest_per_source
    signals = rt.engine.evidence(inc.incident_id)
    feedback = min((rt.engine._feedback[(inc.area, t)] for t in inc.signal_types), default=1.0)
    damping = rt.cfg.fusion["burst"]["damping"] if inc.common_cause else 1.0
    best = {e.event_id for e in strongest_per_source(signals).values()}
    rows = []
    for e in signals:
        raw = e.attrs.get("raw_severity", e.severity)
        rows.append({"event_id": e.event_id, "t": e.t, "type": e.type, "source": e.source, "sensor_id": e.sensor_id,
                     "severity": e.severity, "raw_severity": raw, "profile_weight": round(e.severity / raw, 3) if raw else None,
                     "confidence": e.confidence, "entity": e.entity.model_dump() if e.entity else None,
                     "media": e.media.model_dump() if e.media else None, "attrs": e.attrs, "provenance": e.provenance,
                     "counts_for_source": e.event_id in best})
    contributions = []
    for src in inc.sources:
        rest = [e for e in signals if e.source != src]
        without = score_incident(rest, inc.area, inc.updated_at, rt.cfg, feedback, damping).score if rest else 0
        contributions.append({"source": src, "score_without": without, "adds": inc.score - without})
    return {"profile": rt.profile, "signals": rows, "contributions": contributions,
            "feedback": {"factor": round(feedback, 3),
                         "from": [x for x in rt.engine.learned() if x["area"] == inc.area and x["type"] in inc.signal_types]},
            "burst_damping": damping}


@app.get("/api/incidents/{incident_id}/forecast")
async def incident_forecast(incident_id: str):
    """Where the incident is heading and what each response would do (argus/forecast.py). Uses only what has been
    seen up to the replay clock."""
    from argus.forecast import forecast
    inc = rt.engine.incidents.get(incident_id)
    if inc is None:
        raise HTTPException(404, "unknown incident")
    now = rt.replay.sim_t
    log = [e for e in rt.events if e.t <= now]
    feedback = min((rt.engine._feedback[(inc.area, t)] for t in inc.signal_types), default=1.0)
    return await asyncio.to_thread(forecast, inc, rt.engine.evidence(incident_id), rt.cfg, now, log=log, feedback=feedback)


@app.get("/api/intel")
async def intel():
    """The layer above incidents (argus/intel.py): pattern links between incidents, series, the near-repeat watch
    and what ARGUS can and cannot see. Read-only, as of the replay clock."""
    from argus.intel import build_intel
    now = rt.replay.sim_t
    live = getattr(rt, "live_events", [])
    log = [e for e in rt.events if e.t <= now] + live
    return await asyncio.to_thread(build_intel, list(rt.engine.incidents.values()), rt.engine.evidence, rt.cfg, now, log,
                                   bool(live))


# Supervisor-only decisions. Dismissing lowers how similar alerts score in that area (policy, not handling), and
# calling the police commits outside resources; a duty officer escalates instead. Enforced here, not only in the UI.
SUPERVISOR_NOTES = {"notify_police", "false_alarm"}


class ActionIn(BaseModel):
    action: Literal["ack", "escalate", "dismiss", "reopen"]
    role: Literal["duty_officer", "supervisor"] = "duty_officer"
    note: str = ""


@app.post("/api/incidents/{incident_id}/action")
async def act(incident_id: str, body: ActionIn, request: Request):
    if incident_id not in rt.engine.incidents:
        raise HTTPException(404, "unknown incident")
    role = role_of(request, "supervisor" if body.role == "supervisor" else None)
    if role != "supervisor" and (body.action in ("dismiss", "reopen") or body.note in SUPERVISOR_NOTES):
        raise HTTPException(403, "Only a supervisor can do that: escalate it to them")
    try:
        inc = rt.engine.act(incident_id, body.action)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if inc.status == "open":
        _ensure_brief(inc)
    entry = rt.audit.append(incident_id=incident_id, action=body.action, role=role, note=body.note,
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
            rt.recent.clear()
        rt.remember(new_events)
        for inc in changed:
            _ensure_brief(inc)
    snap = rt.snapshot()
    await _broadcast(snap)
    return snap["clock"]


class ProfileIn(BaseModel):
    name: str
    role: Literal["duty_officer", "supervisor"] = "duty_officer"


@app.post("/api/profile")
async def set_profile(body: ProfileIn, request: Request):
    """Switch the site's security profile (profiles.yaml) and re-score the replay so far."""
    if body.name not in profiles()["profiles"]:
        raise HTTPException(400, f"unknown profile {body.name}")
    if role_of(request, "supervisor" if body.role == "supervisor" else None) != "supervisor":
        raise HTTPException(403, "Only a supervisor can change how strict the site is")
    rt.set_profile(body.name)
    rt.audit.append(incident_id="-", action="profile", role=body.role, note=body.name, sim_t=rt.replay.sim_t, score=0)
    for inc in rt.engine.incidents.values():
        _ensure_brief(inc)
    snap = rt.snapshot()
    await _broadcast(snap)
    return {"profile": rt.profile, "thresholds": {k: rt.cfg.fusion[k] for k in ("watch_threshold", "open_threshold")}}


class LiveEventIn(BaseModel):
    type: Literal["abandoned_object", "weapon_visible", "violence", "camera_obstructed", "camera_restored"]
    severity: float
    confidence: float
    bbox: list[float]
    track: int
    attrs: dict = {}
    still_jpeg_b64: str | None = None


@app.post("/api/live/event")
async def live_event(body: LiveEventIn):
    """An alert from the live camera (vision/live.py --rules). It joins the replay at the current moment, in the
    'Stage camera (live)' area, so it is fused, scored, briefed and shown like any other signal."""
    import base64
    import time as _time

    from argus.schema import Entity, Media
    rt.live_seq = getattr(rt, "live_seq", 0) + 1
    ev = Event(event_id=f"live-{int(_time.time())}-{rt.live_seq}", t=rt.replay.sim_t, source="cctv",
               sensor_id="LIVE", zone="stage", area="live", type=body.type, severity=body.severity,
               confidence=body.confidence, entity=Entity(kind="track", id=f"LIVE:t{body.track}"),
               provenance="computed", media=Media(clip="live", frame=0, bbox=body.bbox),
               attrs={**body.attrs, "live": True})
    if body.still_jpeg_b64:
        thumbs = settings.WEB_VIDEO_DIR / "thumbs"
        thumbs.mkdir(parents=True, exist_ok=True)
        (thumbs / f"{ev.event_id}.jpg").write_bytes(base64.b64decode(body.still_jpeg_b64))
    rt.live_events = getattr(rt, "live_events", []) + [ev]
    changed = rt.engine.ingest(ev)
    rt.remember([ev])
    for inc in changed:
        _ensure_brief(inc)
    await _broadcast({"type": "tick", "clock": rt.clock(), "summary": rt.engine.summary(),
                      "events": [ev.model_dump()], "incidents": [i.model_dump() for i in changed]})
    return {"event_id": ev.event_id, "incidents": [i.incident_id for i in changed],
            "status": [i.status for i in changed]}


class AskIn(BaseModel):
    question: str


@app.post("/api/ask")
async def ask_argus(body: AskIn):
    """Ask ARGUS (argus/ask.py): answered only from what has been seen up to the replay clock."""
    from argus.ask import ask
    q = body.question.strip()[:300]
    if not q:
        raise HTTPException(400, "empty question")
    from argus.intel import build_intel
    incidents = list(rt.engine.incidents.values())
    now = rt.replay.sim_t
    try:
        intel = build_intel(incidents, rt.engine.evidence, rt.cfg, now, [e for e in rt.events if e.t <= now])
    except Exception:                          # the intel layer is context; a failure there must not break Ask
        logger.exception("intel for ask failed")
        intel = None
    return await asyncio.to_thread(ask, q, rt.events, incidents, now, rt.cfg, intel)


class InvestigateIn(BaseModel):
    question: str | None = None
    incident_id: str | None = None


def _case_and_question(question: str | None, incident_id: str | None):
    from argus.agent import Case
    if incident_id:
        inc = rt.engine.incidents.get(incident_id)
        if inc is None:
            raise HTTPException(404, "unknown incident")
        question = question or f"Investigate {incident_id} ({inc.title.split(' — ')[0]}): is it real, and what should we do?"
    question = (question or "").strip()[:300]
    if not question:
        raise HTTPException(400, "empty question")
    events = rt.events + getattr(rt, "live_events", [])
    case = Case(events, list(rt.engine.incidents.values()), rt.replay.sim_t, rt.cfg, evidence=rt.engine.evidence,
                feedback=lambda inc: min((rt.engine._feedback[(inc.area, t)] for t in inc.signal_types), default=1.0))
    return case, question


@app.post("/api/agent")
async def agent(body: InvestigateIn):
    """The ARGUS investigator (argus/agent.py): a tool-using agent that works the case and returns a case file with
    its verdict, the steps it took and the frames it looked at."""
    from argus.agent import investigate
    case, question = _case_and_question(body.question, body.incident_id)
    return await asyncio.to_thread(investigate, question, case, None, 0)


@app.get("/api/agent/stream")
async def agent_stream(q: str | None = None, incident: str | None = None):
    """The same, as server-sent events: one 'step' event per tool call as it happens, then 'done' with the case
    file. EventSource('/api/agent/stream?incident=INC-0009')."""
    from fastapi.responses import StreamingResponse

    from argus.agent import investigate
    case, question = _case_and_question(q, incident)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def work():
        try:
            out = investigate(question, case, lambda s: loop.call_soon_threadsafe(queue.put_nowait, ("step", s)))
        except Exception as exc:                                  # the stream must always end
            out = {"question": question, "error": f"{type(exc).__name__}: {exc}"}
        loop.call_soon_threadsafe(queue.put_nowait, ("done", out))

    async def events():
        yield f"event: start\ndata: {json.dumps({'question': question, 'as_of': rt.cfg.epoch_to_local(case.now)})}\n\n"
        task = asyncio.create_task(asyncio.to_thread(work))
        rt._tasks.add(task)
        task.add_done_callback(rt._tasks.discard)
        while True:
            kind, data = await queue.get()
            yield f"event: {kind}\ndata: {json.dumps(data)}\n\n"
            if kind == "done":
                break
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/api/audit")
async def audit(request: Request, incident: str | None = None):
    """The hash-chained decision log. A duty officer reads the decisions on one incident (?incident=INC-0007); the
    whole log is a supervisor's. The chain is verified over the whole log either way."""
    role = role_of(request)
    entries = rt.audit.entries()
    if role != "supervisor":
        if not incident:
            raise HTTPException(403, "The full decision log is supervisor-only: ask for one incident's decisions")
        entries = [e for e in entries if e.get("incident_id") == incident]
    elif incident:
        entries = [e for e in entries if e.get("incident_id") == incident]
    return {"verified": rt.audit.verify(), "entries": entries, "scope": "incident" if incident else "all"}


@app.get("/api/audit/export")
async def audit_export(request: Request):
    """The whole decision log as JSON Lines, as written (supervisor). Anyone can re-verify the chain from it."""
    from fastapi.responses import PlainTextResponse
    require_supervisor(request, "Exporting the decision log")
    path = rt.audit.path
    body = path.read_text(encoding="utf-8") if path.exists() else ""
    return PlainTextResponse(body, media_type="application/x-ndjson",
                             headers={"Content-Disposition": 'attachment; filename="argus-decision-log.jsonl"'})


@app.get("/api/learning")
async def learning(request: Request):
    """What ARGUS has learned from dismissals (supervisor): each area and signal whose future scores are damped, by
    how much, and the dismissals that taught it."""
    require_supervisor(request, "What ARGUS has learned")
    dismissals = [e for e in rt.audit.entries() if e.get("action") == "dismiss"]
    out = []
    for x in rt.engine.learned():
        taught = [d for d in dismissals if (inc := rt.engine.incidents.get(d["incident_id"])) is not None
                  and inc.area == x["area"] and x["type"] in inc.signal_types and inc.status == "dismissed"]
        out.append({**x, "area_name": rt.cfg.area_name(x["area"]), "penalty": rt.cfg.fusion["dismiss_penalty"],
                    "dismissals": [{"incident_id": d["incident_id"], "sim_t": d["sim_t"], "role": d["role"]} for d in taught]})
    return {"rules": out, "penalty": rt.cfg.fusion["dismiss_penalty"]}


class LearningResetIn(BaseModel):
    area: str
    type: str


@app.post("/api/learning/reset")
async def learning_reset(body: LearningResetIn, request: Request):
    """Forget what dismissals taught for one area and signal (supervisor); audit-logged, live incidents re-scored."""
    require_supervisor(request, "Resetting what ARGUS has learned")
    changed = rt.engine.reset_learning(body.area, body.type)
    entry = rt.audit.append(incident_id="-", action="reset_learning", role="supervisor", note=f"{body.area}:{body.type}",
                            sim_t=rt.replay.sim_t, score=0)
    await _broadcast({"type": "tick", "clock": rt.clock(), "summary": rt.engine.summary(), "events": [],
                      "incidents": [i.model_dump() for i in changed]})
    return {"audit": entry, "rescored": [i.incident_id for i in changed]}


@app.get("/api/dismissed")
async def dismissed(request: Request):
    """Incidents dismissed as false alarms, with who dismissed them and when (supervisor): the oversight view of
    what the floor chose to ignore. Each can be reopened (POST .../action {"action": "reopen"})."""
    require_supervisor(request, "Reviewing dismissals")
    by = {e["incident_id"]: e for e in rt.audit.entries() if e.get("action") == "dismiss"}
    return {"incidents": [{**i.model_dump(), "dismissed_by": by.get(i.incident_id)} for i in rt.engine.incidents.values()
                          if i.status == "dismissed"]}


@app.get("/api/metrics")
async def metrics():
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


# ---- Analyse any uploaded video ------------------------------------------------------------
def _job_or_404(job_id: str):
    from argus.uploads import manager
    job = manager().get(job_id)
    if job is None:
        raise HTTPException(404, "unknown upload")
    return job


@app.post("/api/uploads")
def upload_video(file: UploadFile = File(...), thorough: bool = Form(True)):
    from argus.uploads import manager
    try:
        job = manager().submit(file.file, file.filename or "", thorough=thorough)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return job.__dict__


@app.get("/api/uploads")
def list_uploads():
    from argus.uploads import manager
    return [j.__dict__ for j in manager().list()]


@app.get("/api/uploads/{job_id}")
def get_upload(job_id: str):
    from argus.uploads import manager
    job = _job_or_404(job_id)
    return {**job.__dict__, "result": manager().result(job) if job.status == "done" else None}


@app.get("/api/uploads/{job_id}/assess")
def assess_upload(job_id: str, profile: str | None = None):
    """Threat assessment of an analysed clip under a security profile: verdict, risk over time, incidents with their
    evidence and forecasts. Re-fuses the clip's stored events, so switching profile is instant."""
    from argus.uploads import assess, manager
    job = _job_or_404(job_id)
    result = manager().result(job) if job.status == "done" else None
    if result is None:
        raise HTTPException(409, "analysis not finished")
    if profile is not None and profile not in profiles()["profiles"]:
        raise HTTPException(400, f"unknown profile {profile}")
    return assess([Event(**e) for e in result["events"]], profile or rt.profile)


@app.get("/api/uploads/{job_id}/video")
def upload_video_file(job_id: str):
    job = _job_or_404(job_id)
    web = job.dir / "web.mp4"
    if web.exists() and web.stat().st_size > 0:
        return FileResponse(web, media_type="video/mp4")
    return FileResponse(job.dir / job.meta["original"])


@app.get("/api/uploads/{job_id}/thumbs/{event_id}.jpg")
def upload_still(job_id: str, event_id: str):
    job = _job_or_404(job_id)
    path = job.dir / "thumbs" / f"{event_id}.jpg"
    if not event_id.replace("-", "").isalnum() or not path.exists():
        raise HTTPException(404, "no still for this event")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/uploads/{job_id}/tracks")
def upload_tracks(job_id: str):
    job = _job_or_404(job_id)
    path = job.dir / f"{job.meta.get('stem', '')}.jsonl"
    if not job.meta.get("stem") or not path.exists():
        raise HTTPException(404, "not tracked yet")
    return FileResponse(path, media_type="application/x-ndjson")


@app.get("/api/uploads/{job_id}/weapons")
def upload_weapons(job_id: str):
    """The weapon detector's raw per-frame boxes (run_weapons.py), so the review overlay follows the weapon."""
    job = _job_or_404(job_id)
    path = job.dir / f"{job.meta.get('stem', '')}.weapons.jsonl"
    if not job.meta.get("stem") or not path.exists():
        raise HTTPException(404, "no weapon pass for this clip")
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


# ---- Console (built frontend) -------------------------------------------------------------
# `npm run build` in frontend/ produces frontend/dist; serving it here makes the whole demo one process
# at http://localhost:8000. Mounted last so every /api, /media and /ws route above wins.
_SITE = settings.REPO_ROOT / "site"            # project website, at http://localhost:8000/site/
if _SITE.is_dir():
    app.mount("/site", StaticFiles(directory=_SITE, html=True), name="site")
_CONSOLE = settings.REPO_ROOT / "frontend" / "dist"
if _CONSOLE.is_dir():
    app.mount("/", StaticFiles(directory=_CONSOLE, html=True), name="console")
