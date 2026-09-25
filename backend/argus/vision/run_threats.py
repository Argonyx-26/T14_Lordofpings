"""Threat passes for the demo clips: pose (violence, person down, hand-offs), weapons, and the VideoMAE violence
score, each skipped when its output already exists or its model is missing. Run before rules.py.

Usage:  python backend/argus/vision/run_threats.py [clip.avi ...]     (default: every clip in data/meva/video)
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from argus.settings import MEVA_DIR, TRACKS_DIR  # noqa: E402
from argus.vision import run_pose, run_weapons, violence_videomae  # noqa: E402


def main(clips: list[pathlib.Path]) -> int:
    TRACKS_DIR.mkdir(parents=True, exist_ok=True)
    for clip in clips:
        pose = TRACKS_DIR / f"{clip.stem}.pose.jsonl"
        if run_pose.WEIGHTS.exists() and not pose.exists():
            run_pose.run(clip, pose)
        weapons = TRACKS_DIR / f"{clip.stem}.weapons.jsonl"
        if run_weapons.available() and not weapons.exists():
            run_weapons.run(clip, weapons)
        vmae = TRACKS_DIR / f"{clip.stem}.vmae.jsonl"
        if violence_videomae.available() and pose.exists() and not vmae.exists():
            violence_videomae.run(clip, pose, vmae)
    return 0


if __name__ == "__main__":
    args = [pathlib.Path(a) for a in sys.argv[1:]] or sorted((MEVA_DIR / "video").glob("*.avi"))
    sys.exit(main(args))
