"""Ask ARGUS: a question in plain words, answered only from what the system has seen so far.

The model gets the surfaced incidents and the non-routine signals up to the replay clock (never the future,
never ground truth) and must cite the incident and event ids it used. Citations that are not in that log are
dropped, and the console turns the rest into clickable evidence. With no key or no network the answer falls
back to a plain list of what is open. Answers are cached so a rehearsed question also works offline.
"""
import hashlib
import json
import os
import re
import threading
from collections import Counter

from pydantic import BaseModel

from argus import settings
from argus.brief.llm import GEMINI_KEY, GEMINI_MODEL, TIMEOUT_S
from argus.config import SiteConfig
from argus.schema import Event, Incident

CACHE_FILE = settings.CACHE_DIR / "ask.json"
MAX_SIGNALS = 150
SURFACED = ("watch", "open", "ack", "escalated", "dismissed")

SYSTEM = (
    "You are ARGUS, the assistant in a security control room. Answer the operator's question using ONLY the log "
    "you are given: the incidents ARGUS has raised and the signals from its sensors, up to the current time. "
    "If the log does not answer the question, say so plainly; never guess and never describe anything that is not "
    "in the log. Write two to four short sentences in calm, plain language for a guard: say what happened, where "
    "and when (local times as HH:MM), and how sure the sensors are. Describe device-location evidence as people's "
    "phones, a custody change as a bag changing hands, and never use internal type names. Mention incidents by "
    "their title, not their id. cited_ids: the incident ids and event ids you relied on, most important first."
)


class _Answer(BaseModel):
    answer: str
    cited_ids: list[str]


_GEMINI_SCHEMA = {
    "type": "OBJECT",
    "properties": {"answer": {"type": "STRING"}, "cited_ids": {"type": "ARRAY", "items": {"type": "STRING"}}},
    "required": ["answer", "cited_ids"],
}

_lock = threading.Lock()


def context(events: list[Event], incidents: list[Incident], sim_t: float, cfg: SiteConfig) -> dict:
    """What the operator could know at sim_t: surfaced incidents, non-routine signals, routine counts per area."""
    seen = [e for e in events if e.t <= sim_t]
    routine_max = cfg.fusion["context_max_severity"]
    signals = sorted((e for e in seen if e.severity > routine_max), key=lambda e: -e.severity)[:MAX_SIGNALS]
    routine = Counter((cfg.area_name(e.area), e.type) for e in seen if e.severity <= routine_max)
    return {
        "site": cfg.raw["site_name"],
        "now": cfg.epoch_to_local(sim_t),
        "incidents": [{
            "id": i.incident_id, "title": i.title.split(" — ")[0], "area": cfg.area_name(i.area), "status": i.status,
            "score": i.score, "peak_score": i.peak_score, "since": cfg.epoch_to_local(i.first_signal_at)[11:16],
            "sources": i.sources, "evidence_ids": i.event_ids[:12],
            "brief": i.brief.summary if i.brief else None,
        } for i in incidents if i.status in SURFACED and i.first_signal_at <= sim_t],
        "signals": [{
            "id": e.event_id, "time": cfg.epoch_to_local(e.t)[11:19], "area": cfg.area_name(e.area),
            "sensor": e.sensor_id, "source": e.source, "type": e.type, "severity": round(e.severity, 2),
            "confidence": round(e.confidence, 2),
        } for e in sorted(signals, key=lambda e: e.t)],
        "routine_counts": [{"area": a, "type": t, "count": n} for (a, t), n in sorted(routine.items())],
    }


def _cache_key(question: str, ctx: dict) -> str:
    q = re.sub(r"\s+", " ", question.strip().lower())
    ids = ",".join(i["id"] + str(i["peak_score"]) for i in ctx["incidents"]) + str(len(ctx["signals"]))
    return hashlib.sha1(f"{q}|{ids}".encode()).hexdigest()[:16]


def _cached(key: str) -> dict | None:
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8")).get(key)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _store(key: str, value: dict) -> None:
    with _lock:
        try:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        data[key] = value
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(data, indent=1), encoding="utf-8")


def _gemini(question: str, ctx: dict) -> _Answer | None:
    import httpx

    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps({"question": question, "log": ctx})}]}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": _GEMINI_SCHEMA,
                             "temperature": 0.1},
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    try:
        r = httpx.post(url, json=body, headers={"x-goog-api-key": GEMINI_KEY}, timeout=TIMEOUT_S + 8)
    except httpx.TransportError:
        return None
    if r.status_code != 200:
        print(f"[ask] Gemini error {r.status_code}: {r.text[:200]}")
        return None
    try:
        return _Answer.model_validate_json(r.json()["candidates"][0]["content"]["parts"][0]["text"])
    except Exception as exc:
        print(f"[ask] Gemini output rejected: {type(exc).__name__}")
        return None


def fallback(ctx: dict) -> _Answer:
    """No model: say what is open, strongest first. Honest and always available."""
    live = sorted((i for i in ctx["incidents"] if i["status"] != "dismissed"), key=lambda i: -i["peak_score"])
    if not live:
        return _Answer(answer=f"Nothing has been raised so far (as of {ctx['now'][11:16]}). "
                              f"{len(ctx['signals'])} sensor signals were seen, none strong enough for an incident.",
                       cited_ids=[])
    lines = [f"{i['title']} at {i['area']} since {i['since']} (score {i['peak_score']})"
             for i in live[:4]]
    return _Answer(answer=f"As of {ctx['now'][11:16]}, {len(live)} incident{'s' if len(live) != 1 else ''} "
                          f"raised: " + "; ".join(lines) + ". (Automatic summary: the language model is offline.)",
                   cited_ids=[i["id"] for i in live[:4]])


def ask(question: str, events: list[Event], incidents: list[Incident], sim_t: float, cfg: SiteConfig) -> dict:
    ctx = context(events, incidents, sim_t, cfg)
    key = _cache_key(question, ctx)
    cached = _cached(key)
    if cached:
        return cached
    use_llm = os.environ.get("ARGUS_LLM", "on").lower() != "off" and GEMINI_KEY
    answer = (_gemini(question, ctx) if use_llm else None)
    generated_by = "llm" if answer else "template"
    answer = answer or fallback(ctx)
    known_incidents = {i["id"] for i in ctx["incidents"]}
    known_events = {s["id"] for s in ctx["signals"]} | {e for i in ctx["incidents"] for e in i["evidence_ids"]}
    cited = list(dict.fromkeys(c for c in answer.cited_ids if c in known_incidents | known_events))
    out = {
        "question": question, "answer": answer.answer, "as_of": ctx["now"],
        "cited_incidents": [c for c in cited if c in known_incidents],
        "cited_events": [e.model_dump() for e in events if e.event_id in set(cited) - known_incidents],
        "generated_by": generated_by, "model": GEMINI_MODEL if generated_by == "llm" else None,
    }
    if generated_by == "llm":
        _store(key, out)
    return out


def warm(question: str, at_local: str) -> dict:
    """Answer a rehearsed question at a replay moment ahead of time, so it is served from the cache on stage."""
    from argus.config import site
    from argus.fusion.engine import FusionEngine
    from argus.ingest import demo_window, load_all_events
    from argus.replay.clock import Replay

    cfg = site()
    events = load_all_events(cfg)
    engine = FusionEngine(cfg)
    replay = Replay(events, engine, *demo_window(cfg))
    replay.seek(cfg.local_to_epoch(at_local))
    return ask(question, events, list(engine.incidents.values()), replay.sim_t, cfg)


if __name__ == "__main__":
    # python -m argus.ask "2018-03-15 15:19:00" "What happened at the bus station?"   (run on Wi-Fi before the pitch)
    import sys
    out = warm(sys.argv[2], sys.argv[1])
    print(f"[{out['generated_by']}] {out['answer']}")
