"""Two-line incident brief. The LLM explains; it never detects, scores or creates incidents.

Output is schema-constrained, the recommended action must come from the playbook, every cited
evidence id must belong to the incident, and any failure (no key, no network, refusal, invalid
output) falls back to a deterministic template. Results are cached so replays are instant offline.
"""
import hashlib
import json
import os
import threading

from pydantic import BaseModel

from argus import settings
from argus.config import SiteConfig
from argus.fusion.engine import headline, story_action
from argus.schema import Brief, Event, Incident

CLAUDE_MODEL = os.environ.get("ARGUS_LLM_MODEL", "claude-opus-5")
GEMINI_MODEL = os.environ.get("ARGUS_GEMINI_MODEL", "gemini-flash-latest")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
# Claude when its key is set, else Gemini when its key is set, else template only.
PROVIDER = "claude" if os.environ.get("ANTHROPIC_API_KEY") else "gemini" if GEMINI_KEY else None
MODEL = GEMINI_MODEL if PROVIDER == "gemini" else CLAUDE_MODEL
TIMEOUT_S = float(os.environ.get("ARGUS_LLM_TIMEOUT", "12"))
CACHE_FILE = settings.CACHE_DIR / "briefs.json"

SYSTEM = (
    "You write incident briefs for a security control-room operator. You receive an incident that a "
    "deterministic engine has already detected and scored, with its evidence. Explain it; do not add facts. "
    "Mention only areas, sensors and observations that appear in the evidence. Use plain, calm language. "
    "Write for a guard, not an engineer: never use internal type names or jargon such as crowding, dispersal, "
    "exodus, telemetry or custody change. Describe device-location evidence as people's phones, for example "
    "'phones show a crowd gathering at the bus station' or 'phones show people suddenly leaving the school "
    "building'; describe a custody change as 'a bag changed hands'. Camera names such as G331 are fine. "
    "summary: one sentence saying what happened where. why: one sentence on why it deserves attention now, "
    "referring to how the independent sources agree. action_id: pick exactly one id from the playbook. "
    "evidence_ids: the ids of the evidence items you relied on."
)


class _LLMBrief(BaseModel):
    summary: str
    why: str
    action_id: str
    evidence_ids: list[str]


_lock = threading.Lock()


def _cache() -> dict:
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _store(key: str, brief: Brief) -> None:
    with _lock:
        data = _cache()
        data[key] = brief.model_dump()
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(data, indent=1), encoding="utf-8")


def cache_key(inc: Incident) -> str:
    """Stable across replays: same area, same evidence, same brief."""
    return hashlib.sha1(f"{inc.area}|{'|'.join(sorted(inc.event_ids))}".encode()).hexdigest()[:16]


def _evidence_lines(evidence: list[Event], cfg: SiteConfig) -> list[dict]:
    return [{
        "id": e.event_id, "time": cfg.epoch_to_local(e.t)[11:], "source": e.source, "sensor": e.sensor_id,
        "zone": e.zone, "type": e.type, "severity": round(e.severity, 2), "confidence": round(e.confidence, 2),
        "provenance": e.provenance, "details": e.attrs,
    } for e in evidence]


def template_brief(inc: Incident, evidence: list[Event], cfg: SiteConfig) -> Brief:
    defaults = cfg.playbook["defaults"]
    top = max(evidence, key=lambda e: e.severity) if evidence else None
    what = headline(inc.signal_types, evidence, cfg) if top else "Activity"
    where = cfg.area_name(inc.area)
    srcs = ", ".join(inc.sources)
    action = (story_action(inc.signal_types, cfg) or defaults.get(top.type, defaults["default"])) if top \
        else defaults["default"]
    return Brief(
        summary=f"{what} in {where} at {cfg.epoch_to_local(inc.first_signal_at)[11:]}.",
        why=(f"{len(inc.sources)} independent source{'s' if len(inc.sources) != 1 else ''} ({srcs}) "
             f"{'point' if len(inc.sources) != 1 else 'points'} at this area within {int(cfg.fusion['window_s'])} s; "
             f"score {inc.score}/100."),
        action_id=action, evidence_ids=[e.event_id for e in evidence[:5]], generated_by="template",
    )


def validate(candidate: _LLMBrief, inc: Incident, cfg: SiteConfig) -> Brief | None:
    if candidate.action_id not in cfg.playbook["actions"]:
        return None
    ids = [i for i in candidate.evidence_ids if i in set(inc.event_ids)]
    if not ids or len(ids) != len(candidate.evidence_ids):
        return None
    text = f"{candidate.summary} {candidate.why}".lower()
    other_areas = [cfg.area_name(a).lower() for a in cfg.raw["areas"] if a != inc.area]
    if any(name in text for name in other_areas):
        return None                     # mentions a place that is not in the evidence
    return Brief(summary=candidate.summary.strip(), why=candidate.why.strip(), action_id=candidate.action_id,
                 evidence_ids=ids, generated_by="llm", model=MODEL)


def llm_brief(inc: Incident, evidence: list[Event], cfg: SiteConfig) -> Brief | None:
    """Returns None on any failure; callers fall back to the template."""
    if os.environ.get("ARGUS_LLM", "on").lower() == "off" or PROVIDER is None:
        return None
    payload = {
        "incident": {"id": inc.incident_id, "area": cfg.area_name(inc.area), "score": inc.score,
                     "score_breakdown": inc.score_breakdown.model_dump(), "sources": inc.sources,
                     "common_cause_suspected": inc.common_cause},
        "evidence": _evidence_lines(evidence[:12], cfg),
        "playbook": cfg.playbook["actions"],
    }
    if PROVIDER == "gemini":
        return _gemini_brief(payload, inc, cfg)
    try:
        import anthropic
    except ImportError:
        return None
    try:
        client = anthropic.Anthropic(timeout=TIMEOUT_S, max_retries=1)
        response = client.beta.messages.parse(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM,
            output_config={"effort": "low"},
            output_format=_LLMBrief,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": json.dumps(payload)}],
        )
    except anthropic.APIConnectionError:
        return None                     # offline venue Wi-Fi: template takes over
    except anthropic.APIStatusError as exc:
        print(f"[brief] API error {exc.status_code}: {exc.message}")
        return None
    except Exception as exc:            # missing credentials, parse errors, anything else
        print(f"[brief] {type(exc).__name__}: {exc}")
        return None
    if response.stop_reason == "refusal" or response.parsed_output is None:
        return None
    return validate(response.parsed_output, inc, cfg)


_GEMINI_SCHEMA = {  # _LLMBrief in Gemini's response-schema format
    "type": "OBJECT",
    "properties": {"summary": {"type": "STRING"}, "why": {"type": "STRING"}, "action_id": {"type": "STRING"},
                   "evidence_ids": {"type": "ARRAY", "items": {"type": "STRING"}}},
    "required": ["summary", "why", "action_id", "evidence_ids"],
}


def _gemini_brief(payload: dict, inc: Incident, cfg: SiteConfig) -> Brief | None:
    """Gemini REST generateContent with a JSON response schema (plain httpx, no SDK). Same validation."""
    import httpx

    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": json.dumps(payload)}]}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": _GEMINI_SCHEMA,
                             "temperature": 0.2},
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    try:
        r = httpx.post(url, json=body, headers={"x-goog-api-key": GEMINI_KEY}, timeout=TIMEOUT_S)
    except httpx.TransportError:
        return None                     # offline venue Wi-Fi: template takes over
    if r.status_code != 200:
        print(f"[brief] Gemini error {r.status_code}: {r.text[:200]}")
        return None
    try:
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        candidate = _LLMBrief.model_validate_json(text)
    except Exception as exc:            # blocked, empty or malformed output
        print(f"[brief] Gemini output rejected: {type(exc).__name__}")
        return None
    return validate(candidate, inc, cfg)


def brief_for(inc: Incident, evidence: list[Event], cfg: SiteConfig, allow_llm: bool = True) -> Brief:
    key = cache_key(inc)
    cached = _cache().get(key)
    if cached:
        return Brief.model_validate(cached)
    brief = (llm_brief(inc, evidence, cfg) if allow_llm else None) or template_brief(inc, evidence, cfg)
    if brief.generated_by == "llm":
        _store(key, brief)
    return brief
