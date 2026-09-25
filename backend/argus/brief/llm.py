"""Two-line incident brief. The LLM explains; it never detects, scores or creates incidents.

Output is schema-constrained, the recommended action must come from the playbook, every cited
evidence id must belong to the incident, and any failure (no key, no network, refusal, invalid
output) falls back to a deterministic template. Results are cached so replays are instant offline.
"""
import hashlib
import json
import os
import threading
from typing import Literal

from pydantic import BaseModel

from argus import settings
from argus.config import SiteConfig
from argus.schema import Brief, Event, Incident

MODEL = os.environ.get("ARGUS_LLM_MODEL", "claude-opus-5")
TIMEOUT_S = float(os.environ.get("ARGUS_LLM_TIMEOUT", "12"))
CACHE_FILE = settings.CACHE_DIR / "briefs.json"

SYSTEM = (
    "You write incident briefs for a security control-room operator. You receive an incident that a "
    "deterministic engine has already detected and scored, with its evidence. Explain it; do not add facts. "
    "Mention only areas, sensors and observations that appear in the evidence. Use plain, calm language. "
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
    titles, defaults = cfg.playbook["titles"], cfg.playbook["defaults"]
    top = max(evidence, key=lambda e: e.severity) if evidence else None
    what = titles.get(top.type, top.type) if top else "Activity"
    where = cfg.area_name(inc.area)
    srcs = ", ".join(inc.sources)
    action = defaults.get(top.type, defaults["default"]) if top else defaults["default"]
    return Brief(
        summary=f"{what} in {where} at {cfg.epoch_to_local(inc.first_signal_at)[11:]}.",
        why=(f"{len(inc.sources)} independent sources ({srcs}) point at the same area within "
             f"{int(cfg.fusion['window_s'])} s; score {inc.score}/100."),
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
                 evidence_ids=ids, generated_by="llm")


def llm_brief(inc: Incident, evidence: list[Event], cfg: SiteConfig) -> Brief | None:
    """Returns None on any failure; callers fall back to the template."""
    try:
        import anthropic
    except ImportError:
        return None
    if os.environ.get("ARGUS_LLM", "on").lower() == "off":
        return None
    payload = {
        "incident": {"id": inc.incident_id, "area": cfg.area_name(inc.area), "score": inc.score,
                     "score_breakdown": inc.score_breakdown.model_dump(), "sources": inc.sources,
                     "common_cause_suspected": inc.common_cause},
        "evidence": _evidence_lines(evidence[:12], cfg),
        "playbook": cfg.playbook["actions"],
    }
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


def brief_for(inc: Incident, evidence: list[Event], cfg: SiteConfig, allow_llm: bool = True) -> Brief:
    key = cache_key(inc)
    cached = _cache().get(key)
    if cached:
        return Brief.model_validate(cached)
    brief = (llm_brief(inc, evidence, cfg) if allow_llm else None) or template_brief(inc, evidence, cfg)
    if brief.generated_by == "llm":
        _store(key, brief)
    return brief
