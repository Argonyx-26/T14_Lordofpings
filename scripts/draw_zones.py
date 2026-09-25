"""Overlay cameras.yaml polygons on each camera's reference frame -> data/meva/zones_check/<cam>.jpg"""
import pathlib
import sys

import cv2
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from argus.vision.common import MEVA_DIR, camera_cfg  # noqa: E402

COLORS = [(0, 0, 255), (0, 200, 0), (255, 0, 0), (0, 200, 255), (255, 0, 255), (255, 255, 0)]

out_dir = MEVA_DIR / "zones_check"
out_dir.mkdir(parents=True, exist_ok=True)
for jpg in sorted((MEVA_DIR / "frames").glob("*.jpg")):
    cam = jpg.stem.split(".")[-1]
    polys = camera_cfg(cam).get("polygons") or {}
    img = cv2.imread(str(jpg))
    for i, (name, pts) in enumerate(polys.items()):
        p = np.array(pts, np.int32)
        cv2.polylines(img, [p], True, COLORS[i % len(COLORS)], 4)
        cv2.putText(img, name, tuple(p[0]), cv2.FONT_HERSHEY_SIMPLEX, 1.4, COLORS[i % len(COLORS)], 3)
    for name, (x1, y1, x2, y2) in (camera_cfg(cam).get("door_leaf") or {}).items():
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 255), 3)
        cv2.putText(img, f"leaf:{name}", (x1, y2 + 30), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 255, 255), 3)
    cv2.imwrite(str(out_dir / f"{cam}.jpg"), cv2.resize(img, (960, 536)))
    print(cam, list(polys))
