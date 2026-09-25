"""MEVA clip names: '2018-03-15.14-50-01.14-55-01.school.G420' (local start/end, site, camera)."""
from dataclasses import dataclass
from datetime import datetime, timezone

from argus.config import SiteConfig


@dataclass(frozen=True)
class Clip:
    stem: str
    start_t: float   # UTC epoch
    end_t: float
    site: str
    camera: str


def parse_clip(stem: str, cfg: SiteConfig) -> Clip:
    stem = stem.removesuffix(".r13").removesuffix(".avi").removesuffix(".activities.yml")
    date, start, end, site_name, camera = stem.split(".")[:5]

    def epoch(hms: str) -> float:
        naive = datetime.strptime(f"{date} {hms}", "%Y-%m-%d %H-%M-%S")
        return (naive - cfg.utc_offset).replace(tzinfo=timezone.utc).timestamp()

    return Clip(stem=stem, start_t=epoch(start), end_t=epoch(end), site=site_name, camera=camera)
