"""What ARGUS can see, and what it can't (after DeTT&CT's visibility scoring for security operations).

A monitoring system that does not know where it is blind reports a one-camera area with the same confidence as a
four-camera one. For every area this computes:

- streams      which streams cover it: cameras (and whether each one is recording right now), door sensors, phone
               counts. Recording comes from MEVA's clip table (what the dataset actually recorded) or, without it,
               from the browser clips on disk; with neither, a camera is assumed to be recording.
- behaviours   which kinds of behaviour it can see at all (playbook `visibility`): bags left or taken, weapons and
               fights, crowds, door traffic. A behaviour no stream there can produce is a blind spot.
- ceiling      the most independent sources that could ever agree there, and the corroboration factor that caps
               (fusion `corroboration_factors`): a single-source incident in a one-stream area is not weak evidence,
               it is all the evidence that area can give.

And one site figure, visibility: the share of (area x behaviour) cells some stream can see, weighted by area
criticality. Its parts are returned with it.
"""
from functools import lru_cache

from argus import settings
from argus.config import SiteConfig
from argus.ingest.clips import parse_clip
from argus.schema import Event

DEFAULT_BEHAVIOURS = [
    {"id": "bags", "label": "Bags left or taken", "needs": ["cctv"]},
    {"id": "violence", "label": "Weapons, fights, falls", "needs": ["cctv"]},
    {"id": "crowds", "label": "Crowds and people leaving", "needs": ["device", "cctv"]},
    {"id": "doors", "label": "Door traffic", "needs": ["door"]},
]
STREAM_LABEL = {"cctv": "cameras", "door": "door sensors", "device": "phone counts"}


@lru_cache(maxsize=4)
def _recordings(cameras: tuple[str, ...], utc_offset_h: float) -> dict[str, list[tuple[float, float]]] | None:
    stems: list[str] = []
    table = settings.MEVA_DIR / "clip-table.txt"
    if table.exists():
        stems = [ln.split()[0] for ln in table.read_text(encoding="utf-8").splitlines() if ln.strip()]
    elif settings.WEB_VIDEO_DIR.exists():
        stems = [p.stem for p in settings.WEB_VIDEO_DIR.glob("*.mp4")]
    if not stems:
        return None
    from argus.config import site
    cfg = site()
    out: dict[str, list[tuple[float, float]]] = {c: [] for c in cameras}
    for stem in stems:
        parts = stem.split(".")
        if len(parts) < 5 or parts[4] not in out:
            continue
        try:
            c = parse_clip(stem, cfg)
        except ValueError:
            continue
        out[c.camera].append((c.start_t, c.end_t))
    return out


def recording(camera: str, t: float, cfg: SiteConfig) -> bool | None:
    """Was this camera recording at t? None when ARGUS has no record of recordings at all."""
    if camera == "LIVE":
        return True
    rec = _recordings(tuple(sorted(cfg.raw["cameras"])), cfg.raw["utc_offset_hours"])
    if rec is None:
        return None
    # MEVA clips are 5 min and abut with up to 2 s between them: a gap that small is not a blind spot
    return any(s - 2 <= t < e + 2 for s, e in rec.get(camera, []))


def coverage(cfg: SiteConfig, log: list[Event], now: float, live: bool = False) -> dict:
    behaviours = cfg.playbook.get("visibility") or DEFAULT_BEHAVIOURS
    door_areas = {e.area for e in log if e.source == "door"}
    factors = cfg.fusion["corroboration_factors"]
    areas, seen_by = [], {}
    num = den = 0.0
    for area, meta in cfg.raw["areas"].items():
        if area == "upload" or (area == "live" and not live):
            continue
        cams = [c for c, m in cfg.raw["cameras"].items() if m.get("area") == area and (c != "LIVE" or live)]
        cam_rows = [{"id": c, "label": cfg.raw["cameras"][c].get("label", c), "recording": recording(c, now, cfg)} for c in cams]
        up = [c["id"] for c in cam_rows if c["recording"] is not False]
        streams = {"cctv": bool(up), "door": area in door_areas, "device": area in cfg.area_shapes}
        installed = {"cctv": bool(cams), "door": streams["door"], "device": streams["device"]}
        seen = [b["id"] for b in behaviours if any(streams.get(s) for s in b["needs"])]
        blind = [b["label"] for b in behaviours if b["id"] not in seen]
        n = sum(streams.values())
        crit = meta.get("criticality", 0.5)
        num += crit * len(seen) / len(behaviours)
        den += crit
        seen_by[area] = up
        areas.append({
            "area": area, "name": meta.get("name", area), "criticality": crit, "cameras": cam_rows,
            "streams": streams, "installed": installed, "sees": seen, "blind": blind,
            "ceiling": {"sources": n, "corroboration": factors[min(max(n, 1), len(factors)) - 1] if n else None},
            "offline": [c["id"] for c in cam_rows if c["recording"] is False],
            "note": _note(meta.get("name", area), streams, installed, blind, cam_rows),
        })
    vis = round(100 * num / den) if den else None
    worst = sorted((a for a in areas if a["blind"]), key=lambda a: -a["criticality"] * len(a["blind"]))
    return {
        "as_of": now, "behaviours": [{"id": b["id"], "label": b["label"]} for b in behaviours], "areas": areas,
        "visibility": vis, "seen_by": seen_by,
        "visibility_basis": ("share of area x behaviour cells some stream can see, weighted by area criticality"
                             + (f"; the largest gap: {worst[0]['name']} ({', '.join(worst[0]['blind']).lower()})" if worst else "")),
    }


def _note(name: str, streams: dict, installed: dict, blind: list[str], cams: list[dict]) -> str:
    have = [STREAM_LABEL[s] for s, on in streams.items() if on]
    off = [c["id"] for c in cams if c["recording"] is False]
    parts = [f"{name}: " + (", ".join(have) if have else "no sensors")]
    if off:
        parts.append(f"{', '.join(off)} not recording now")
    if blind:
        parts.append("cannot see " + ", ".join(b.lower() for b in blind))
    return "; ".join(parts)
