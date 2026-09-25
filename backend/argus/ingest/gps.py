"""Device-location stream from real MEVA GPS tracks (one fix every ~10 s per logger).

On a real campus this stream would be Wi-Fi access-point associations. GPS loggers are not linked
to the people seen on camera, so fusion uses these events by area and time, never by identity.
"""
import math
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from argus.config import SiteConfig
from argus.ingest.rates import group_times, rate_anomalies
from argus.schema import Entity, Event

NS = {"g": "http://www.topografix.com/GPX/1/0"}
FAST_EXIT_MPS = 2.5   # faster than a brisk walk (~1.4 m/s)


def _epoch(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def _metres(lat1, lon1, lat2, lon2) -> float:
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


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


def load_device_events(gps_dir: Path, cfg: SiteConfig, start_t: float | None = None,
                       end_t: float | None = None) -> list[Event]:
    fixes = load_fixes(gps_dir, start_t, end_t)
    events: list[Event] = []
    presence: list[tuple[str, float, str]] = []   # (area, t, device)
    exits: list[tuple[str, float]] = []            # (area, t)

    for dev, pts in fixes.items():
        areas = _debounced_areas([cfg.area_at(lat, lon) for _, lat, lon in pts])
        prev_area, prev = None, None
        for (t, lat, lon), area in zip(pts, areas):
            if area:
                presence.append((area, t, dev))
            if prev is not None and area != prev_area:
                speed = _metres(prev[1], prev[2], lat, lon) / max(t - prev[0], 1.0)
                if prev_area:
                    exits.append((prev_area, t))
                    # A single fast exit is context only: people drive and GPS jitters. Unusual exit
                    # *rates* per area become signals via _rate_signals below.
                    events.append(Event(
                        event_id=f"dev-{dev}-{t:.0f}-exit",
                        t=t, source="device", sensor_id="gps", zone=prev_area, area=prev_area,
                        type="device_fast_exit" if speed >= FAST_EXIT_MPS else "device_exit",
                        severity=0.08 if speed >= FAST_EXIT_MPS else 0.02, confidence=0.6,
                        entity=Entity(kind="device", id=dev), provenance="recorded",
                        attrs={"speed_mps": round(speed, 2), "to": area or "outside"},
                    ))
                if area:
                    events.append(Event(
                        event_id=f"dev-{dev}-{t:.0f}-enter",
                        t=t, source="device", sensor_id="gps", zone=area, area=area,
                        type="device_enter", severity=0.02, confidence=0.6,
                        entity=Entity(kind="device", id=dev), provenance="recorded",
                        attrs={"from": prev_area or "outside"},
                    ))
            prev_area, prev = area, (t, lat, lon)

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

