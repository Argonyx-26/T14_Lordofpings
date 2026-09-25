"""Filesystem locations. Override the data root with the ARGUS_DATA environment variable."""
import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

DATA_DIR = Path(os.environ.get("ARGUS_DATA", REPO_ROOT / "data"))
MEVA_DIR = DATA_DIR / "meva"
ANNOTATION_DIR = MEVA_DIR / "ann"
GPS_DIR = MEVA_DIR / "gps"
WEB_VIDEO_DIR = MEVA_DIR / "web"
EVENTS_DIR = DATA_DIR / "events"   # cctv.jsonl written by the vision pipeline
TRACKS_DIR = DATA_DIR / "tracks"   # per-clip YOLO track caches
CACHE_DIR = DATA_DIR / "cache"     # LLM briefs, metrics, audit log

CONFIG_DIR = Path(__file__).resolve().parent / "config"
