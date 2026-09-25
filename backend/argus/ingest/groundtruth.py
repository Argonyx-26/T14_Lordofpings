"""Ground-truth incidents for EVALUATION ONLY. Never import this from the live pipeline."""
from dataclasses import dataclass
from pathlib import Path

from argus.config import SiteConfig
from argus.ingest.clips import parse_clip
from argus.ingest.doors import _activities

GT_ACTIVITIES = {"person_steals_object": "theft", "person_abandons_package": "abandoned_package"}


@dataclass(frozen=True)
class GroundTruth:
    kind: str
    camera: str
    area: str
    t_start: float
    t_end: float
    clip: str
    frames: tuple[int, int]


def load_ground_truth(ann_dir: Path, cfg: SiteConfig) -> list[GroundTruth]:
    out = []
    for path in sorted(ann_dir.glob("*.activities.yml")):
        clip = parse_clip(path.name.removesuffix(".activities.yml"), cfg)
        for _, label, start, end in _activities(path):
            if label in GT_ACTIVITIES:
                out.append(GroundTruth(
                    kind=GT_ACTIVITIES[label], camera=clip.camera, area=cfg.camera(clip.camera)["area"],
                    t_start=clip.start_t + start / cfg.fps, t_end=clip.start_t + end / cfg.fps,
                    clip=clip.stem, frames=(start, end),
                ))
    return sorted(out, key=lambda g: g.t_start)


def load_door_truth(ann_dir: Path, cfg: SiteConfig) -> dict[str, list[float]]:
    """Annotated door-open times per camera, to score the video door detector."""
    out: dict[str, list[float]] = {}
    for path in sorted(ann_dir.glob("*.activities.yml")):
        clip = parse_clip(path.name.removesuffix(".activities.yml"), cfg)
        for _, label, start, _end in _activities(path):
            if label == "person_opens_facility_door":
                out.setdefault(clip.camera, []).append(clip.start_t + start / cfg.fps)
    return {k: sorted(v) for k, v in out.items()}
