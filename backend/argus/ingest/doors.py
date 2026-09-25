"""Door-sensor stream derived from MEVA human annotations.

Only door/entry/exit activities are used. They stand in for a door-contact sensor, which reports
exactly these events. Theft and abandonment labels are NOT read here (see groundtruth.py).
"""
from pathlib import Path

import yaml

from argus.config import SiteConfig
from argus.ingest.clips import parse_clip
from argus.ingest.rates import group_times, rate_anomalies
from argus.schema import Entity, Event, Media

DOOR_ACTIVITIES = {
    "person_opens_facility_door": ("door_open", 0.05),
    "person_enters_scene_through_structure": ("entry", 0.03),
    "person_exits_scene_through_structure": ("exit", 0.03),
}

try:
    _Loader = yaml.CSafeLoader
except AttributeError:  # libyaml not available
    _Loader = yaml.SafeLoader


def _activities(path: Path):
    for item in yaml.load(path.read_text(encoding="utf-8"), Loader=_Loader) or []:
        act = item.get("act") if isinstance(item, dict) else None
        if not act:
            continue
        label = next(iter(act["act2"]))
        start, end = act["timespan"][0]["tsr0"]
        yield act["id2"], label, start, end


def load_door_events(ann_dir: Path, cfg: SiteConfig) -> list[Event]:
    events: list[Event] = []
    for path in sorted(ann_dir.glob("*.activities.yml")):
        clip = parse_clip(path.name.removesuffix(".activities.yml"), cfg)
        cam = cfg.camera(clip.camera)
        for act_id, label, start, end in _activities(path):
            if label not in DOOR_ACTIVITIES:
                continue
            etype, severity = DOOR_ACTIVITIES[label]
            events.append(Event(
                event_id=f"door-{clip.camera}-{clip.start_t:.0f}-{act_id}",
                t=clip.start_t + start / cfg.fps,
                source="door", sensor_id=f"{clip.camera}-door", zone=cam["zone"], area=cam["area"],
                type=etype, severity=severity, confidence=0.9,
                entity=Entity(kind="door", id=f"{clip.camera}-door"),
                provenance="annotation_derived",
                media=Media(clip=clip.stem, frame=start),
                attrs={"frames": [start, end]},
            ))
    events.extend(_door_surges(events, cfg))
    return sorted(events, key=lambda e: e.t)


def _door_surges(door_events: list[Event], cfg: SiteConfig) -> list[Event]:
    r = cfg.rates
    opens = [e for e in door_events if e.type == "door_open"]
    out = []
    # Baselines are per clip: clips of one camera can be non-contiguous and gaps must not read as silence.
    for stem in sorted({e.media.clip for e in opens}):
        clip = parse_clip(stem, cfg)
        mine = [e for e in opens if e.media.clip == stem]
        ref = mine[0]
        times = group_times((ref.sensor_id, e.t) for e in mine)
        for sensor, bucket_t, count, z in rate_anomalies(times, r["bucket_s"], r["min_history"], r["z_threshold"],
                                                         start_t=clip.start_t, end_t=clip.end_t):
            if z <= 0:
                continue
            out.append(_surge(sensor, ref, bucket_t, count, z, r))
    return out


def _surge(sensor: str, ref: Event, bucket_t: float, count: int, z: float, r: dict) -> Event:
    return Event(
        event_id=f"doorsurge-{sensor}-{bucket_t:.0f}",
        t=bucket_t + r["bucket_s"], source="door", sensor_id=sensor, zone=ref.zone, area=ref.area,
        type="door_surge", severity=min(0.5, 0.15 + 0.07 * z), confidence=0.7,
        provenance="computed", attrs={"count": count, "z": round(z, 2), "bucket_s": r["bucket_s"]},
    )
