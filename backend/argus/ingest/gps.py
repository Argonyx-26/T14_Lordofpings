"""Device-location stream from real MEVA GPS tracks (one fix every ~10 s per logger).

On a real campus this stream would be Wi-Fi access-point associations. GPS loggers are not linked
to the people seen on camera, so fusion uses these events by area and time, never by identity.
"""
import xml.etree.ElementTree as ET
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from argus import settings
from argus.config import SiteConfig
from argus.ingest.rates import group_times, rate_anomalies
from argus.schema import Event

NS = {"g": "http://www.topografix.com/GPX/1/0"}


def _epoch(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def load_fixes(gps_dir: Path, start_t: float | None = None, end_t: float | None = None) -> dict[str, list[tuple]]:
    """{device_id: [(t, lat, lon), ...]} sorted by time, merged across 5-minute GPX files."""
    fixes: dict[str, list[tuple]] = {}
    for path in sorted(gps_dir.glob("*.gpx")):
        root = ET.parse(path).getroot()
        for trk in root.findall("g:trk", NS):
            dev = trk.findtext("g:name", default="?", namespaces=NS)
            for pt in trk.iterfind(".//g:trkpt", NS):
                t = _epoch(pt.findtext("g:time", namespaces=NS))
                if (start_t is not None and t < start_t) or (end_t is not None and t > end_t):
                    continue
                fixes.setdefault(dev, []).append((t, float(pt.get("lat")), float(pt.get("lon"))))
    for dev in fixes:
        fixes[dev].sort()
    return fixes


@lru_cache(maxsize=2)
def _cached_fixes(gps_dir: str) -> dict[str, list[tuple]]:
    return load_fixes(Path(gps_dir))


def phones_in_area(cfg: SiteConfig, area: str, t: float, window_s: float = 60.0, gps_dir: Path | None = None) -> int | None:
    """How many phones had a fix inside `area` within `window_s` of t: a count and nothing else (no id, no route).
    None when there is no GPS, or the area has no outline to count in (an uploaded clip, the stage camera)."""
    d = gps_dir or settings.GPS_DIR
    if area not in cfg.area_shapes or not d.exists():
        return None
    fixes = _cached_fixes(str(d))
    if not fixes:
        return None
    return sum(any(abs(p[0] - t) <= window_s and cfg.area_at(p[1], p[2]) == area for p in pts) for pts in fixes.values())


def load_device_events(gps_dir: Path, cfg: SiteConfig, start_t: float | None = None,
                       end_t: float | None = None) -> list[Event]:
    """Privacy by design: ARGUS never follows a phone. Positions are reduced, in memory, to how many phones are in
    each area per time bucket and how many left it; only unusual COUNTS become events (crowding, dispersal, exodus),
    and no event carries a device id. No per-phone arrival, departure or route is stored, shown or sent to a model."""
    fixes = load_fixes(gps_dir, start_t, end_t)
    events: list[Event] = []
    presence: list[tuple[str, float, str]] = []   # (area, t, device)
    exits: list[tuple[str, float]] = []            # (area, t)

    for dev, pts in fixes.items():
        areas = _debounced_areas([cfg.area_at(lat, lon) for _, lat, lon in pts])
        prev_area = None
        for (t, _lat, _lon), area in zip(pts, areas):
            if area:
                presence.append((area, t, dev))
            if area != prev_area and prev_area:
                exits.append((prev_area, t))
            prev_area = area

    events.extend(_occupancy_anomalies(presence, cfg, start_t, end_t))
    events.extend(_exodus_anomalies(exits, cfg, start_t, end_t))
    return sorted(events, key=lambda e: e.t)


def _debounced_areas(raw: list[str | None]) -> list[str | None]:
    """Accept an area change only when the next fix agrees (suppresses GPS jitter at area edges)."""
    out: list[str | None] = []
    current = raw[0] if raw else None
    for i, a in enumerate(raw):
        if a != current and (i + 1 == len(raw) or raw[i + 1] == a):
            current = a
        out.append(current)
    return out


def _exodus_anomalies(exits, cfg: SiteConfig, start_t, end_t) -> list[Event]:
    r = cfg.rates
    out = []
    for area, bucket_t, count, z in rate_anomalies(group_times(exits), r["bucket_s"], r["min_history"],
                                                   r["z_threshold"], start_t=start_t, end_t=end_t):
        if z <= 0:
            continue
        out.append(Event(
            event_id=f"exodus-{area}-{bucket_t:.0f}",
            t=bucket_t + r["bucket_s"], source="device", sensor_id="gps", zone=area, area=area,
            type="device_exodus", severity=min(0.55, 0.15 + 0.08 * z), confidence=0.6, provenance="computed",
            attrs={"exits": count, "z": round(z, 2), "bucket_s": r["bucket_s"]},
        ))
    return out


def _occupancy_anomalies(presence, cfg: SiteConfig, start_t, end_t) -> list[Event]:
    """Unique devices per area per bucket vs a causal rolling baseline."""
    r = cfg.rates
    bucket = r["bucket_s"]
    seen: dict[tuple[str, int], set] = {}
    for area, t, dev in presence:
        seen.setdefault((area, int(t // bucket)), set()).add(dev)
    # rate_anomalies counts timestamps, so emit one pseudo-timestamp per unique device in each bucket
    times = group_times((area, b * bucket + 0.5) for (area, b), devs in seen.items() for _ in devs)
    out = []
    for area, bucket_t, count, z in rate_anomalies(times, bucket, r["min_history"], r["z_threshold"],
                                                   start_t=start_t, end_t=end_t):
        crowding = z > 0
        out.append(Event(
            event_id=f"occ-{area}-{bucket_t:.0f}",
            t=bucket_t + bucket, source="device", sensor_id="gps", zone=area, area=area,
            type="device_crowding" if crowding else "device_dispersal",
            severity=min(0.55, 0.15 + 0.08 * abs(z)), confidence=0.6, provenance="computed",
            attrs={"devices": count, "z": round(z, 2), "bucket_s": bucket},
        ))
    return out

