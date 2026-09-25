"""CCTV analytics events written by the vision pipeline (data/events/cctv.jsonl, one Event per line)."""
import json
from pathlib import Path

from argus.config import SiteConfig
from argus.schema import Event


def load_cctv_events(path: Path, cfg: SiteConfig) -> list[Event]:
    if not path.exists():
        return []
    events = []
    for line_no, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            ev = Event.model_validate(json.loads(line))
        except Exception as exc:  # a bad line must not take the demo down
            print(f"[cctv] skipping line {line_no}: {exc}")
            continue
        if not ev.area:
            cam = cfg.camera(ev.sensor_id)
            ev.area = cam["area"]
            ev.zone = ev.zone or cam["zone"]
        events.append(ev)
    return sorted(events, key=lambda e: e.t)
