"""Load every input stream for the demo window into one time-ordered list of Events."""
from argus import settings
from argus.config import SiteConfig, site
from argus.ingest.cctv import load_cctv_events
from argus.ingest.doors import load_door_events
from argus.ingest.gps import load_device_events
from argus.schema import Event

WINDOW_LOCAL = ("2018-03-15 14:50:00", "2018-03-15 15:20:00")


def demo_window(cfg: SiteConfig) -> tuple[float, float]:
    return cfg.local_to_epoch(WINDOW_LOCAL[0]), cfg.local_to_epoch(WINDOW_LOCAL[1])


def load_all_events(cfg: SiteConfig | None = None) -> list[Event]:
    cfg = cfg or site()
    start, end = demo_window(cfg)
    events: list[Event] = []
    if settings.ANNOTATION_DIR.exists():
        events += load_door_events(settings.ANNOTATION_DIR, cfg)
    if settings.GPS_DIR.exists():
        events += load_device_events(settings.GPS_DIR, cfg, start, end)
    events += load_cctv_events(settings.EVENTS_DIR / "cctv.jsonl", cfg)
    return sorted((e for e in events if start <= e.t <= end), key=lambda e: (e.t, e.event_id))
