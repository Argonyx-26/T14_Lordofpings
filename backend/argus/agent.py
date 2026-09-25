"""ARGUS investigator: an agent that works a case the way a control-room analyst would, with the site's own sensors.

Given a question ("What happened at the bus station?") or an incident to investigate, the model plans and calls
read-only tools in a loop:
  list_incidents      what ARGUS has raised so far
  get_incident        one incident: score breakdown and every piece of evidence
  search_signals      the sensor log (cameras, door contacts, people's phones), filtered by area / type / time
  look_at_camera      pull the real frame from a camera at a moment (or at a piece of evidence, box drawn) and
                      ask a vision model a specific question about it: the agent checks the footage itself
  phones_in_area      how many phones were in an area around a moment, and how many now (counts only: ARGUS never
                      follows an individual phone)
  forecast            where the incident is heading and what each response would do (argus/forecast.py)
  finish              the case file: verdict, answer, confidence, next step, cited ids

Guard rails (the same rules as the briefs):
  * every tool sees only what has happened up to the replay clock: no future, no ground truth
  * the agent recommends; only the operator acts (acknowledge / escalate / dismiss stay audit-logged buttons)
  * cited ids that are not in the log are dropped; the run stops after MAX_STEPS tool calls or MAX_LOOKS frames
  * every step (tool, arguments, what came back, how long it took) is kept and shown, so the reasoning is visible
  * no key or no network: a deterministic investigation (the incident, its evidence, the forecast) is returned;
    successful runs are cached, so a rehearsed investigation replays offline on stage

Usage:  python -m argus.agent "2018-03-15 15:19:30" "What happened at the bus station?"   (warm the cache)
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import threading
import time
from collections import Counter
from typing import Callable

from argus import settings
from argus.brief.llm import GEMINI_KEY, GEMINI_MODEL
from argus.config import SiteConfig
from argus.schema import Event, Incident

CACHE_FILE = settings.CACHE_DIR / "agent.json"
FRAMES_DIR = settings.WEB_VIDEO_DIR / "agent"          # served at /media/agent/<name>.jpg
MAX_STEPS, MAX_LOOKS = 10, 3
STEP_TIMEOUT_S = float(os.environ.get("ARGUS_AGENT_TIMEOUT", "30"))
SURFACED = ("watch", "open", "ack", "escalated", "dismissed")
_lock = threading.Lock()

SYSTEM = (
    "You are the ARGUS investigator, working for a security control-room operator at a site with CCTV cameras, "
    "door sensors and anonymous phone counts per area (ARGUS never follows an individual). Investigate the operator's request with your tools, like a careful "
    "analyst: start from what ARGUS has raised, pull the evidence, and CHECK the footage yourself with "
    "look_at_camera before you trust a camera alert (ask it a specific question, e.g. 'Is anyone standing with "
    "the backpack?'). Use phones_in_area when it matters how crowded an area was. Do not repeat a call. "
    "You only know what your tools return; they only cover the past up to the current time. Never invent facts. "
    "When you have enough (usually 3-6 calls), call finish. The answer is for a guard: two to four short, calm "
    "sentences with local times (HH:MM), what the sensors show and what you saw on camera. Say plainly when the "
    "footage does not confirm an alert. Mention incidents by title, never by internal type names. The verdict is "
    "one of: confirmed, likely, unclear, false_alarm, nothing_found. The next step is one concrete action for the "
    "operator (you never act yourself).\n"
    "How much to trust each source (measured on this site): the camera rules follow every person and bag across "
    "hundreds of frames, so details such as owner_left_scene or unattended_s outweigh what a few frames show. A "
    "vision model looking at a few low-resolution frames missed 4 of 6 real staged thefts and abandonments here: "
    "a person sitting next to a bag may be a bystander, and a hand-over can fall between frames. So footage can "
    "CONFIRM an alert when it clearly shows the act, but footage that does not show it means 'not visible on "
    "camera', never 'false alarm'. Use false_alarm only when the footage clearly shows the flagged thing is not "
    "what the detector claims (the box is on a wall, a plant, an empty floor), and even then leave the dismissal "
    "to the operator. Confidence above 0.85 needs the footage to show the act."
)

TOOLS = [
    {"name": "list_incidents", "description": "Incidents ARGUS has raised so far, strongest first.",
     "parameters": {"type": "OBJECT", "properties": {}}},
    {"name": "get_incident", "description": "One incident: status, score and why, and every piece of evidence.",
     "parameters": {"type": "OBJECT", "properties": {"incident_id": {"type": "STRING"}}, "required": ["incident_id"]}},
    {"name": "search_signals",
     "description": "Search the sensor log up to now. All filters optional. Sources: cctv, door, device (phones). "
                    "Returns at most 30 signals, most severe first, plus counts of everything that matched.",
     "parameters": {"type": "OBJECT", "properties": {
         "area": {"type": "STRING", "description": "area name or id, e.g. 'Bus station'"},
         "source": {"type": "STRING", "enum": ["cctv", "door", "device"]},
         "type": {"type": "STRING", "description": "signal type, e.g. abandoned_object, custody_change, door_open"},
         "since": {"type": "STRING", "description": "local time HH:MM[:SS]"},
         "until": {"type": "STRING", "description": "local time HH:MM[:SS]"},
         "min_severity": {"type": "NUMBER"}}}},
    {"name": "look_at_camera",
     "description": "Look at real footage and ask a vision model one specific question about it. With event_id you "
                    "get three frames of that piece of camera evidence (8 s before, the moment, 4 s after) with the "
                    "detector's box; with camera + time, the whole frame at that moment.",
     "parameters": {"type": "OBJECT", "properties": {
         "question": {"type": "STRING"},
         "event_id": {"type": "STRING"},
         "camera": {"type": "STRING", "description": "camera id, e.g. G331"},
         "time": {"type": "STRING", "description": "local time HH:MM:SS"},
         "offset_s": {"type": "NUMBER", "description": "seconds after the event (negative = before); default 0"}},
         "required": ["question"]}},
    {"name": "phones_in_area",
     "description": "How many phones were inside an area within window_s seconds of a moment, and how many are there "
                    "now. Counts only: individual phones are never identified or followed.",
     "parameters": {"type": "OBJECT", "properties": {
         "area": {"type": "STRING"}, "time": {"type": "STRING", "description": "local time HH:MM[:SS]"},
         "window_s": {"type": "NUMBER"}}, "required": ["area", "time"]}},
    {"name": "forecast", "description": "Where an incident is heading and the ranked responses.",
     "parameters": {"type": "OBJECT", "properties": {"incident_id": {"type": "STRING"}}, "required": ["incident_id"]}},
    {"name": "finish", "description": "Close the investigation with the case file.",
     "parameters": {"type": "OBJECT", "properties": {
         "answer": {"type": "STRING"},
         "verdict": {"type": "STRING", "enum": ["confirmed", "likely", "unclear", "false_alarm", "nothing_found"]},
         "confidence": {"type": "NUMBER", "description": "0-1"},
         "next_step": {"type": "STRING"},
         "cited_ids": {"type": "ARRAY", "items": {"type": "STRING"}}},
         "required": ["answer", "verdict", "confidence", "next_step", "cited_ids"]}},
]


class Case:
    """The world as the operator knows it at sim_t, and the tools over it."""

    def __init__(self, events: list[Event], incidents: list[Incident], sim_t: float, cfg: SiteConfig,
                 evidence: Callable[[str], list[Event]] | None = None, feedback: Callable[[Incident], float] | None = None):
        self.cfg, self.now = cfg, sim_t
        self.log = [e for e in events if e.t <= sim_t]
        self.by_id = {e.event_id: e for e in self.log}
        self.incidents = {i.incident_id: i for i in incidents if i.status in SURFACED and i.first_signal_at <= sim_t}
        self._evidence = evidence or (lambda iid: [self.by_id[x] for x in self.incidents[iid].event_ids
                                                   if x in self.by_id])
        self._feedback = feedback or (lambda inc: 1.0)
        self.looks = 0
        self.frames: list[str] = []

    # --- helpers -------------------------------------------------------------------------------------------------
    def local(self, t: float, seconds: bool = True) -> str:
        return self.cfg.epoch_to_local(t)[11:19 if seconds else 16]

    def at(self, hms: str) -> float:
        hms = hms.strip()
        if re.fullmatch(r"\d{1,2}:\d{2}", hms):
            hms += ":00"
        day = self.cfg.epoch_to_local(self.now)[:10]
        return self.cfg.local_to_epoch(f"{day} {hms}")

    def area_id(self, name: str | None) -> str | None:
        if not name:
            return None
        key = name.strip().lower()
        for aid in self.cfg.raw["areas"]:
            if key in (aid.lower(), self.cfg.area_name(aid).lower()) or key.replace(" ", "_") == aid:
                return aid
        for aid in self.cfg.raw["areas"]:
            if key in self.cfg.area_name(aid).lower():
                return aid
        return key

    def signal(self, e: Event) -> dict:
        d = {"id": e.event_id, "time": self.local(e.t), "area": self.cfg.area_name(e.area), "sensor": e.sensor_id,
             "source": e.source, "type": e.type, "severity": round(e.severity, 2), "confidence": round(e.confidence, 2)}
        attrs = {k: v for k, v in e.attrs.items() if isinstance(v, (str, int, float, bool)) and k not in ("live",)}
        if attrs:
            d["details"] = dict(list(attrs.items())[:6])
        return d

    # --- tools ---------------------------------------------------------------------------------------------------
    def list_incidents(self) -> dict:
        rows = sorted(self.incidents.values(), key=lambda i: -i.peak_score)
        return {"now": self.local(self.now), "incidents": [{
            "id": i.incident_id, "title": i.title.split(" — ")[0], "area": self.cfg.area_name(i.area),
            "status": i.status, "score": i.score, "peak_score": i.peak_score, "since": self.local(i.first_signal_at, False),
            "sources": i.sources, "signals": len(i.event_ids)} for i in rows]}

    def get_incident(self, incident_id: str) -> dict:
        inc = self.incidents.get(incident_id)
        if inc is None:
            return {"error": f"no incident {incident_id}; call list_incidents"}
        b = inc.score_breakdown
        return {
            "id": inc.incident_id, "title": inc.title.split(" — ")[0], "area": self.cfg.area_name(inc.area),
            "status": inc.status, "score": inc.score, "peak_score": inc.peak_score,
            "since": self.local(inc.first_signal_at), "opened_at": inc.opened_at and self.local(inc.opened_at),
            "opened_by_decisive_signal": inc.decisive, "common_cause": inc.common_cause,
            "why_this_score": {"severity": round(b.severity, 2), "confidence": round(b.confidence, 2),
                               "area_criticality": round(b.criticality, 2), "corroboration": round(b.corroboration, 2),
                               "recency": round(b.time_factor, 2)},
            "brief": inc.brief.summary if inc.brief else None,
            "evidence": [self.signal(e) for e in self._evidence(incident_id)][:25],
        }

    def search_signals(self, area=None, source=None, type=None, since=None, until=None, min_severity=None) -> dict:
        aid = self.area_id(area)
        lo = self.at(since) if since else float("-inf")
        hi = min(self.at(until), self.now) if until else self.now
        hits = [e for e in self.log if lo <= e.t <= hi and (not aid or e.area == aid) and (not source or e.source == source)
                and (not type or e.type == type) and (min_severity is None or e.severity >= float(min_severity))]
        top = sorted(hits, key=lambda e: (-e.severity, e.t))[:30]
        return {"matched": len(hits), "by_type": dict(Counter(e.type for e in hits).most_common(12)),
                "signals": [self.signal(e) for e in sorted(top, key=lambda e: e.t)]}

    def look_at_camera(self, question: str, event_id=None, camera=None, time=None, offset_s=0.0) -> dict:
        if self.looks >= MAX_LOOKS:
            return {"error": f"frame budget used ({MAX_LOOKS}); decide with what you have"}
        img, where = self._frame(event_id, camera, time, float(offset_s or 0))
        if img is None:
            return {"error": where}
        self.looks += 1
        import cv2
        name = hashlib.sha1(f"{where}|{question}".encode()).hexdigest()[:12] + ".jpg"
        FRAMES_DIR.mkdir(parents=True, exist_ok=True)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        (FRAMES_DIR / name).write_bytes(buf.tobytes())
        self.frames.append(f"/media/agent/{name}")
        seen = _vision(buf.tobytes(), question, where)
        return {"frame": where, "image": f"/media/agent/{name}", **seen}

    def _frame(self, event_id, camera, hms, offset_s):
        import cv2
        box = etype = None
        if event_id:
            e = self.by_id.get(event_id)
            if e is None or e.source != "cctv":
                return None, f"{event_id} is not a camera event in the log"
            if e.media and e.media.clip == "live":
                thumb = settings.WEB_VIDEO_DIR / "thumbs" / f"{e.event_id}.jpg"
                img = cv2.imread(str(thumb)) if thumb.exists() else None
                return (img, f"stage camera still at {self.local(e.t)}") if img is not None else (None, "no still saved")
            camera, t, box, etype = e.sensor_id, e.t + offset_s, e.media.bbox if e.media else None, e.type
            if box:
                strip = [self._grab(camera, t + dt, box, etype) for dt in (-8.0, 0.0, 4.0)]
                if all(x is not None for x in strip):
                    for img, dt in zip(strip, ("8 s before", "the alert", "4 s after")):
                        (tw, th), _ = cv2.getTextSize(dt, cv2.FONT_HERSHEY_SIMPLEX, 1.3, 3)
                        cv2.rectangle(img, (0, 0), (tw + 28, th + 26), (20, 20, 20), -1)
                        cv2.putText(img, dt, (14, th + 12), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (255, 255, 255), 3, cv2.LINE_AA)
                    label = (f"camera {camera} ({self.cfg.camera(camera).get('label', '')}), three frames around "
                             f"{self.local(t)}: 8 s before, the alert, 4 s after")
                    return cv2.hconcat([cv2.resize(x, (640, 360), interpolation=cv2.INTER_AREA) for x in strip]), label
        elif camera and hms:
            t = self.at(hms) + offset_s
        else:
            return None, "give event_id, or camera and time"
        if t > self.now + 0.5:
            return None, "that moment is in the future"
        img = self._grab(camera, t, box, etype)
        if img is None:
            return None, f"no footage from camera {camera} at {self.local(t)}"
        return img, f"camera {camera} ({self.cfg.camera(camera).get('label', '')}) at {self.local(t)}"

    def _grab(self, camera, t, box=None, etype=None):
        """The frame at t (never after now), with the detector's box drawn and cropped around it when given."""
        import cv2
        from argus.ingest.clips import parse_clip
        from argus.vision.thumbs import COLOR, DEFAULT_COLOR, crop_box
        t = min(t, self.now)
        for path in sorted((settings.MEVA_DIR / "video").glob(f"*{camera}.avi")):
            clip = parse_clip(path.stem, self.cfg)
            if clip.start_t <= t < clip.end_t:
                cap = cv2.VideoCapture(str(path))
                cap.set(cv2.CAP_PROP_POS_FRAMES, int((t - clip.start_t) * self.cfg.fps))
                ok, img = cap.read()
                cap.release()
                if not ok:
                    return None
                if box:                          # the detector's box drawn on the frame, cropped around it
                    h, w = img.shape[:2]
                    bx = [int(v) for v in box]
                    cv2.rectangle(img, (bx[0] - 4, bx[1] - 4), (bx[2] + 4, bx[3] + 4),
                                  COLOR.get(etype, DEFAULT_COLOR), 3, cv2.LINE_AA)
                    x1, y1, x2, y2 = crop_box(box, w, h, context=6.0)
                    return cv2.resize(img[y1:y2, x1:x2], (960, 540), interpolation=cv2.INTER_AREA)
                return cv2.resize(img, (1280, int(1280 * img.shape[0] / img.shape[1])))
        return None

    def phones_in_area(self, area: str, time: str, window_s=60) -> dict:
        """How many phones were in an area around a moment, and how many are there now. Counts only: the tool never
        returns a device id or follows a phone (see ingest/gps.py)."""
        aid, t = self.area_id(area), self.at(time)
        if t > self.now:
            return {"error": "that moment is in the future"}
        w = float(window_s or 60)
        from argus.ingest.gps import phones_in_area
        then, now = phones_in_area(self.cfg, aid, t, w) or 0, phones_in_area(self.cfg, aid, self.now, w) or 0
        return {"area": self.cfg.area_name(aid), "moment": self.local(t), "window_s": w, "phones_then": then,
                "phones_now": now, "change": now - then}

    def forecast(self, incident_id: str) -> dict:
        from argus.forecast import forecast
        inc = self.incidents.get(incident_id)
        if inc is None:
            return {"error": f"no incident {incident_id}"}
        f = forecast(inc, self._evidence(incident_id), self.cfg, self.now, log=self.log, feedback=self._feedback(inc))
        return _trim(f)

    def call(self, name: str, args: dict) -> dict:
        fn = {"list_incidents": self.list_incidents, "get_incident": self.get_incident,
              "search_signals": self.search_signals, "look_at_camera": self.look_at_camera,
              "phones_in_area": self.phones_in_area, "forecast": self.forecast}.get(name)
        if fn is None:
            return {"error": f"unknown tool {name}"}
        try:
            return fn(**args)
        except TypeError as exc:
            return {"error": f"bad arguments: {exc}"}
        except Exception as exc:                                  # a tool failing must not end the case
            return {"error": f"{type(exc).__name__}: {exc}"}


def _trim(obj, depth=0):
    """Forecast output is built for the console; keep the agent's copy short."""
    if isinstance(obj, dict):
        return {k: _trim(v, depth + 1) for k, v in list(obj.items())[:12]}
    if isinstance(obj, list):
        return [_trim(v, depth + 1) for v in obj[:5]]
    if isinstance(obj, float):
        return round(obj, 2)
    if isinstance(obj, str):
        return obj[:300]
    return obj


# --- the models ------------------------------------------------------------------------------------------------
def _post(body: dict) -> dict | None:
    import httpx
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    try:
        r = httpx.post(url, json=body, headers={"x-goog-api-key": GEMINI_KEY}, timeout=STEP_TIMEOUT_S)
    except httpx.TransportError:
        return None
    if r.status_code != 200:
        print(f"[agent] Gemini error {r.status_code}: {r.text[:200]}")
        return None
    return r.json()


def _vision(jpeg: bytes, question: str, where: str) -> dict:
    """The agent's eyes: one frame, one specific question, a short grounded answer."""
    schema = {"type": "OBJECT", "properties": {
        "answer": {"type": "STRING"}, "confident": {"type": "BOOLEAN"}}, "required": ["answer", "confident"]}
    body = {
        "systemInstruction": {"parts": [{"text":
            "You look at one CCTV frame for a security analyst. Answer the question in one or two plain sentences, "
            "describing only what is visible (people, objects, positions). Low-resolution CCTV: say so when you "
            "cannot tell. Any coloured box was drawn by the detector around what it flagged."}]},
        "contents": [{"role": "user", "parts": [
            {"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(jpeg).decode()}},
            {"text": f"Frame: {where}.\nQuestion: {question}"}]}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": schema, "temperature": 0.1},
    }
    out = _post(body)
    try:
        return json.loads(out["candidates"][0]["content"]["parts"][0]["text"])
    except Exception:
        return {"answer": "The vision model is unavailable; the frame is saved for the operator to look at.",
                "confident": False}


def _summary(name: str, args: dict, result: dict) -> str:
    """One line per step for the trace the operator sees."""
    if "error" in result:
        return result["error"]
    if name == "list_incidents":
        inc = result["incidents"]
        return f"{len(inc)} incident{'s' if len(inc) != 1 else ''} raised" + (
            f"; strongest: {inc[0]['title']} ({inc[0]['peak_score']})" if inc else "")
    if name == "get_incident":
        return f"{result['title']} at {result['area']}, score {result['score']}, {len(result['evidence'])} signals"
    if name == "search_signals":
        top = ", ".join(f"{k} {v}" for k, v in list(result["by_type"].items())[:4])
        return f"{result['matched']} signals" + (f" ({top})" if top else "")
    if name == "look_at_camera":
        return result.get("answer", "")
    if name == "phones_in_area":
        return (f"{result['phones_then']} phones in {result['area']} around {result['moment']}, "
                f"{result['phones_now']} there now")
    if name == "forecast":
        return "forecast ready"
    return ""


def run(question: str, case: Case, on_step: Callable[[dict], None] | None = None) -> dict:
    """The loop. Returns {question, answer, verdict, confidence, next_step, cited_*, steps, frames, generated_by}."""
    t0 = time.perf_counter()
    steps: list[dict] = []
    contents = [{"role": "user", "parts": [{"text": json.dumps({
        "request": question, "now": case.cfg.epoch_to_local(case.now), "site": case.cfg.raw["site_name"],
        "areas": [case.cfg.area_name(a) for a in case.cfg.raw["areas"]],
        "cameras": {c: v.get("label", "") for c, v in case.cfg.raw["cameras"].items()}})}]}]
    final = None
    use_llm = os.environ.get("ARGUS_LLM", "on").lower() != "off" and GEMINI_KEY
    while use_llm and len(steps) <= MAX_STEPS:
        wrap_up = len(steps) >= MAX_STEPS - 1                     # out of steps: the only move left is finish
        calling = {"mode": "ANY", **({"allowedFunctionNames": ["finish"]} if wrap_up else {})}
        body = {"systemInstruction": {"parts": [{"text": SYSTEM}]}, "contents": contents,
                "tools": [{"functionDeclarations": TOOLS}], "toolConfig": {"functionCallingConfig": calling},
                "generationConfig": {"temperature": 0.2}}
        out = _post(body)
        try:
            content = out["candidates"][0]["content"]
            calls = [p["functionCall"] for p in content["parts"] if "functionCall" in p]
        except Exception:
            break
        if not calls:
            break
        contents.append(content)
        responses = []
        for c in calls:
            name, args = c["name"], c.get("args") or {}
            if name == "finish":
                final = args
                break
            s0 = time.perf_counter()
            result = case.call(name, args)
            step = {"n": len(steps) + 1, "tool": name, "args": args, "summary": _summary(name, args, result),
                    "ms": round((time.perf_counter() - s0) * 1000)}
            if name == "look_at_camera" and "image" in result:
                step["image"] = result["image"]
            steps.append(step)
            if on_step:
                on_step(step)
            responses.append({"functionResponse": {"name": name, "response": {"result": result}}})
        if final is not None:
            break
        contents.append({"role": "user", "parts": responses})
    generated_by = "agent" if final else "template"
    if final is None:
        final = _fallback(question, case, steps, on_step)
    known_inc = set(case.incidents)
    cited = list(dict.fromkeys(c for c in final.get("cited_ids", []) if c in known_inc or c in case.by_id))
    return {
        "question": question, "as_of": case.cfg.epoch_to_local(case.now),
        "answer": final.get("answer", ""), "verdict": final.get("verdict", "unclear"),
        "confidence": round(float(final.get("confidence", 0.5)), 2), "next_step": final.get("next_step", ""),
        "cited_incidents": [c for c in cited if c in known_inc],
        "cited_events": [case.by_id[c].model_dump() for c in cited if c in case.by_id],
        "steps": steps, "frames": case.frames, "generated_by": generated_by,
        "model": GEMINI_MODEL if generated_by == "agent" else None,
        "seconds": round(time.perf_counter() - t0, 1),
    }


def _fallback(question: str, case: Case, steps: list, on_step) -> dict:
    """No model: the same first moves an analyst makes, done deterministically, and said plainly."""
    def do(name, args):
        result = case.call(name, args)
        step = {"n": len(steps) + 1, "tool": name, "args": args, "summary": _summary(name, args, result), "ms": 0}
        steps.append(step)
        if on_step:
            on_step(step)
        return result
    inc = do("list_incidents", {})["incidents"]
    live = [i for i in inc if i["status"] != "dismissed"]
    if not live:
        return {"answer": f"Nothing has been raised as of {case.local(case.now, False)}.", "verdict": "nothing_found",
                "confidence": 0.5, "next_step": "Keep watching.", "cited_ids": []}
    top = do("get_incident", {"incident_id": live[0]["id"]})
    return {"answer": f"{top['title']} at {top['area']} since {top['since'][:5]}, score {top['score']} from "
                      f"{len(top['evidence'])} signals. (Automatic summary: the language model is offline, so the "
                      f"footage was not checked.)",
            "verdict": "unclear", "confidence": 0.4, "next_step": "Look at the evidence stills and decide.",
            "cited_ids": [top["id"]] + [e["id"] for e in top["evidence"][:4]]}


# --- cache, so a rehearsed investigation also works with the Wi-Fi off ---------------------------------------
def cache_key(question: str, case: Case) -> str:
    q = re.sub(r"\s+", " ", question.strip().lower())
    # which incidents are on the board, not the exact second: a rehearsed question matches on stage wherever the
    # replay is, as long as the same incidents are showing (the console marks such answers "replayed")
    sig = ",".join(sorted(case.incidents))
    brain = hashlib.sha1((SYSTEM + json.dumps(TOOLS) + GEMINI_MODEL).encode()).hexdigest()[:8]   # a new prompt: new runs
    return hashlib.sha1(f"{q}|{sig}|{brain}".encode()).hexdigest()[:16]


def cached(key: str) -> dict | None:
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8")).get(key)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def store(key: str, value: dict) -> None:
    with _lock:
        try:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        data[key] = value
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(data, indent=1), encoding="utf-8")


def investigate(question: str, case: Case, on_step: Callable[[dict], None] | None = None,
                replay_delay_s: float = 0.6) -> dict:
    """Cached runs are replayed step by step (so the console shows the same trace), then returned."""
    key = cache_key(question, case)
    hit = cached(key)
    if hit:
        for step in hit["steps"]:
            if on_step:
                time.sleep(replay_delay_s)
                on_step(step)
        return {**hit, "cached": True}
    out = run(question, case, on_step)
    if out["generated_by"] == "agent":
        store(key, out)
    return out


def warm(question: str, at_local: str) -> dict:
    from argus.config import site
    from argus.fusion.engine import FusionEngine
    from argus.ingest import demo_window, load_all_events
    from argus.replay.clock import Replay

    cfg = site()
    events = load_all_events(cfg)
    engine = FusionEngine(cfg)
    replay = Replay(events, engine, *demo_window(cfg))
    replay.seek(cfg.local_to_epoch(at_local))
    case = Case(events, list(engine.incidents.values()), replay.sim_t, cfg, evidence=engine.evidence)
    return investigate(question, case, on_step=lambda s: print(f"  {s['n']}. {s['tool']}({json.dumps(s['args'])[:90]})"
                                                                 f"\n     -> {s['summary'][:160]}", flush=True),
                       replay_delay_s=0)


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv(settings.REPO_ROOT / ".env")
    out = warm(sys.argv[2], sys.argv[1])
    print(f"\n[{out['generated_by']}, {out['seconds']} s] {out['verdict']} ({out['confidence']})\n{out['answer']}\n"
          f"Next: {out['next_step']}\nCited: {out['cited_incidents']} {[e['event_id'] for e in out['cited_events']]}")
