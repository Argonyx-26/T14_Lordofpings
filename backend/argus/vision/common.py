"""Vision-side helpers on top of the shared site config (site.yaml) and clip naming."""
import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from argus.config import site  # noqa: E402
from argus.ingest.clips import parse_clip as _parse  # noqa: E402
from argus.settings import DATA_DIR, EVENTS_DIR, MEVA_DIR, TRACKS_DIR  # noqa: E402

FPS = 30.0
ZONES_FILE = pathlib.Path(__file__).resolve().parent / "zones.yaml"


def clip_info(stem: str):
    """Track/bag file stem or clip stem -> Clip(stem, start_t, end_t, site, camera)."""
    return _parse(stem.removesuffix(".bags"), site())


def frame_to_t(stem: str, frame: int) -> float:
    return clip_info(stem).start_t + frame / FPS


def camera_cfg(cam: str) -> dict:
    """site.yaml camera entry (zone/area/label) merged with this camera's pixel polygons."""
    with ZONES_FILE.open(encoding="utf-8") as f:
        polys = yaml.safe_load(f).get(cam) or {}
    return {**site().camera(cam), **polys}


__all__ = ["DATA_DIR", "EVENTS_DIR", "MEVA_DIR", "TRACKS_DIR", "FPS", "clip_info", "frame_to_t", "camera_cfg"]
