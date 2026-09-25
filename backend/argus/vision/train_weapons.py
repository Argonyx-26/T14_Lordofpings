"""Weapon detector: YOLO11s fine-tuned on real CCTV footage of a staged armed attack, tested on a camera it never saw.

Data: "Mock attack dataset" from Salazar-Gonzalez et al., Real-time gun detection in CCTV: an open problem,
Neural Networks 2020 (CC BY-NC 4.0; https://huggingface.co/datasets/jsalazar/US-Real-time-gun-detection-in-CCTV-An-
open-problem-dataset). Three university CCTV cameras at 1920x1080, annotated at 2 fps: Handgun, Short_rifle, Knife.

Split by camera, so the test score is on a viewpoint the model never trained on:
  train  Cam5 (entrance) + Cam1 (corridor): 1,638 frames, 1,102 of them with a weapon
  test   Cam7 (the other corridor):         3,511 frames, 432 with a weapon (542 boxes), 3,079 without
Frames with no weapon stay in both splits: the 3,079 clean test frames measure the false-alarm rate.
Training runs a fixed number of epochs with no validation on the test camera, and keeps the last weights, so nothing
is tuned on the test set.

Usage (from the repo root):
  python backend/argus/vision/train_weapons.py prepare   # data/train/weapons_raw/Images -> data/train/weapons_yolo
  python backend/argus/vision/train_weapons.py train     # fine-tune -> models/weapons_yolo11s.pt (~40 min on the RTX 5060)
  python backend/argus/vision/train_weapons.py test      # scores on Cam7 -> data/cache/weapons_eval.json
"""
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "train" / "weapons_raw" / "Images"
OUT = ROOT / "data" / "train" / "weapons_yolo"
RUNS = ROOT / "data" / "train" / "runs"
WEIGHTS = ROOT / "models" / "weapons_yolo11s.pt"
CLASSES = ["handgun", "knife", "rifle"]
NAME_TO_ID = {"Handgun": 0, "Knife": 1, "Short_rifle": 2}
TEST_CAMERAS = ("Cam7",)
IMGSZ = 960


def prepare() -> None:
    counts = {"train": [0, 0], "test": [0, 0]}          # images, boxes
    for split in ("train", "test"):
        for sub in ("images", "labels"):
            (OUT / sub / split).mkdir(parents=True, exist_ok=True)
    for xml in sorted(RAW.glob("*.xml")):
        img = xml.with_suffix(".jpg")
        if not img.exists():
            continue
        split = "test" if xml.name.startswith(TEST_CAMERAS) else "train"
        root = ET.parse(xml).getroot()
        w, h = float(root.findtext("size/width")), float(root.findtext("size/height"))
        lines = []
        for obj in root.iter("object"):
            cls = NAME_TO_ID.get(obj.findtext("name"))
            b = obj.find("bndbox")
            if cls is None or b is None:
                continue
            x1, y1, x2, y2 = (float(b.findtext(k)) for k in ("xmin", "ymin", "xmax", "ymax"))
            lines.append(f"{cls} {(x1 + x2) / 2 / w:.6f} {(y1 + y2) / 2 / h:.6f} {(x2 - x1) / w:.6f} {(y2 - y1) / h:.6f}")
        dst = OUT / "images" / split / img.name
        if not dst.exists():
            shutil.copyfile(img, dst)
        (OUT / "labels" / split / f"{img.stem}.txt").write_text("\n".join(lines), encoding="utf-8")
        counts[split][0] += 1
        counts[split][1] += len(lines)
    (OUT / "data.yaml").write_text(
        f"path: {OUT.as_posix()}\ntrain: images/train\nval: images/test\nnames: {dict(enumerate(CLASSES))}\n",
        encoding="utf-8")
    print(f"train {counts['train'][0]} images / {counts['train'][1]} boxes, "
          f"test ({'+'.join(TEST_CAMERAS)}) {counts['test'][0]} images / {counts['test'][1]} boxes")


def train(epochs: int = 30) -> None:
    from ultralytics import YOLO
    model = YOLO(str(ROOT / "models" / "yolo11s.pt"))      # COCO-pretrained: people and objects already learnt
    model.train(data=str(OUT / "data.yaml"), epochs=epochs, imgsz=IMGSZ, batch=8, workers=4, val=False,
                project=str(RUNS), name="weapons", exist_ok=True, plots=False, seed=0, verbose=False)
    best = RUNS / "weapons" / "weights" / "last.pt"
    WEIGHTS.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(best, WEIGHTS)
    print(f"-> {WEIGHTS}")


def test() -> None:
    """Box-level P / R / mAP50 per class, and frame-level alarm rates at the confidence the rule uses."""
    from ultralytics import YOLO
    model = YOLO(str(WEIGHTS))
    m = model.val(data=str(OUT / "data.yaml"), split="val", imgsz=IMGSZ, batch=8, conf=0.001, plots=False,
                  verbose=False)
    per_class = {CLASSES[c]: {"precision": round(float(m.box.p[i]), 3), "recall": round(float(m.box.r[i]), 3),
                              "map50": round(float(m.box.ap50[i]), 3)} for i, c in enumerate(m.box.ap_class_index)}
    # frame level at the operating point: does a frame with a weapon raise one, and does a clean frame stay quiet?
    conf = 0.5
    imgs = sorted((OUT / "images" / "test").glob("*.jpg"))
    tp = fn = fp = tn = 0
    for i in range(0, len(imgs), 16):
        batch = imgs[i:i + 16]
        for img, r in zip(batch, model.predict([str(p) for p in batch], imgsz=IMGSZ, conf=conf, verbose=False)):
            has = bool((OUT / "labels" / "test" / f"{img.stem}.txt").read_text(encoding="utf-8").strip())
            hit = len(r.boxes) > 0
            tp, fn, fp, tn = tp + (has and hit), fn + (has and not hit), fp + (hit and not has), tn + (not has and not hit)
    out = {
        "test_camera": list(TEST_CAMERAS), "images": len(imgs), "imgsz": IMGSZ,
        "box_map50": round(float(m.box.map50), 3), "box_precision": round(float(m.box.mp), 3),
        "box_recall": round(float(m.box.mr), 3), "per_class": per_class,
        "frame_level_at_conf": conf,
        "frames_with_weapon": tp + fn, "frames_with_weapon_flagged": tp,
        "frames_clean": fp + tn, "frames_clean_flagged": fp,
        "frame_recall": round(tp / max(tp + fn, 1), 3), "frame_false_alarm_rate": round(fp / max(fp + tn, 1), 3),
    }
    dest = ROOT / "data" / "cache" / "weapons_eval.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    {"prepare": prepare, "train": train, "test": test}[sys.argv[1]]()
