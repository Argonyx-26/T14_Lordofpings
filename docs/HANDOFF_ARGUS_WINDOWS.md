# ARGUS: handoff for the Windows GPU laptop

**From:** Tanush (team lead) · **Written:** Fri 25 Sep, ~12:40 IST · **Hackathon ends:** Sat 26 Sep, 14:30 IST
**Your role:** you own the laptop with the **RTX 5060**, so you own the **vision pipeline** and the **data**. Everyone else builds on what you produce.

---

## 0. TL;DR: what changed and what you do right now

We are **not** demoing on synthetic data. The demo runs on **MEVA**: real, multi-camera, 1080p CCTV from one facility (a school, cafe, plaza, bus station and parking lot at the Muscatatuck Urban Training Center, USA). It's licensed CC-BY-4.0 and comes with human ground-truth annotations and real GPS tracks from people on site.

In our 30-minute window (**15 Mar 2018, 14:50–15:20**), the whole facility has about 351 door openings, 386 building entries and 365 vehicle stops. Among them are only **4 thefts and 1 abandoned package**. Our pitch is "thousands of signals, a handful of real incidents", and that window proves it with real data.

**No model training.** COCO-pretrained YOLO is enough (people, vehicles, backpacks, handbags, suitcases). The rest is tracking plus rules.

**Your next 2 hours:**
1. Set up the Windows environment and **prove the GPU works** (§2)
2. Verify the downloaded videos and fetch the small extra files (§3)
3. Watch the 5 ground-truth incidents in the footage (§4). This is critical.
4. Draw zone polygons for each camera (§5)
5. Start the offline tracking run over all clips (§6)

**15:00 checkpoint:** tracking events file exists for at least G421.

---

## 1. Hard rules (these protect us from judges and disqualification)

1. **Theft and abandonment annotations are ground truth only. They are never inputs to ARGUS.** We use them only to score ourselves. If we fed them in, the demo would be fake.
2. **The door-open annotations are the only annotation we use as an input.** They stand in for a door-contact sensor. They're labelled on screen as `door sensor (derived from MEVA annotations)`.
3. **Say "staged, real-world footage".** MEVA incidents were acted by people among ordinary passers-by.
4. **Put the attribution on screen:** "MEVA dataset, Kitware Inc. / IARPA, CC-BY-4.0".
5. **Never commit video, model weights or API keys to git.** `data/`, `*.avi`, `*.mp4`, `*.pt` and `.env` all go in `.gitignore`.
6. The solution must be built on-site. Commit small and often. **Tanush coordinates pushes** to `Argonyx-26/Team-21`.

---

## 2. Windows setup (about 30 min)

> Keep the project **outside OneDrive-synced folders** (Desktop and Documents are often synced). Use `C:\argus\`. OneDrive syncing 1.2 GB of video and locking files will hurt.

**2.1 Driver and tools** (PowerShell):
```powershell
nvidia-smi                      # Driver Version must be >= 580. If lower, update the NVIDIA driver first.
winget install -e --id Gyan.FFmpeg
winget install -e --id OpenJS.NodeJS.LTS
winget install -e --id Git.Git
winget install -e --id Python.Python.3.12
```
Close and reopen PowerShell afterwards so the PATH updates.

**2.2 Laptop settings (do these now; they matter on stage):**
- Plug in the charger. Set Settings → System → Power → Power mode to **Best performance**.
- In NVIDIA Control Panel, go to Manage 3D settings → Program settings. Add `C:\argus\.venv\Scripts\python.exe` and set it to **High-performance NVIDIA processor**.
- Set Settings → System → Power → Screen and sleep to **Never** while plugged in.

**2.3 Python environment.** Torch must be installed **before** ultralytics, and it must come from the **cu130** index. The RTX 50-series (sm_120) does not work with CPU-only or older CUDA wheels, and plain `pip install torch` on Windows gives you the CPU-only build.
```powershell
mkdir C:\argus; cd C:\argus
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130 --no-cache-dir
.\.venv\Scripts\python -m pip install ultralytics supervision opencv-python pyyaml numpy pandas scikit-learn shapely gpxpy fastapi "uvicorn[standard]" pydantic anthropic python-dotenv
```

**2.4 Prove the GPU works:**
```powershell
.\.venv\Scripts\python -c "import torch;print(torch.__version__, torch.cuda.get_device_name(0), torch.cuda.get_arch_list());print(torch.randn(2,device='cuda')*2)"
```
✅ You should see `RTX 5060`, the arch list should contain `sm_120`, and the tensor op should print without errors.
❌ If you see `no kernel image is available` or `sm_120 is not compatible`, you got the wrong wheel. Run `pip uninstall torch torchvision -y` and repeat the cu130 install.

**2.5 Get the detector weights now,** while the Wi-Fi still works:
```powershell
.\.venv\Scripts\python -c "from ultralytics import YOLO; YOLO('yolo11s.pt'); YOLO('yolo11m.pt')"
```
Use `yolo11s.pt` by default. It's the same kind of COCO model as your YOLOv8, but more accurate at the same speed. Your YOLOv8-COCO weights are a fine fallback. The YOLO-World buildings/trees model is **not needed**.

---

## 3. Data: verify what you downloaded and fetch the small extras

Put everything in `C:\argus\data\meva\`. If your videos are elsewhere, move them into `C:\argus\data\meva\video\`.

**3.1 Expected video files** (10 files, about 1.18 GB, sizes checked against the S3 bucket today):

| # | Clip (file stem) | Camera: what it sees | Bytes |
|---|---|---|---|
| 1 | `2018-03-15.14-50-00.14-55-00.school.G421` | School cafe interior. **2 thefts** | 142880030 |
| 2 | `2018-03-15.14-50-00.14-55-00.school.G419` | School doors (interior) | 78883804 |
| 3 | `2018-03-15.14-50-01.14-55-01.school.G420` | School doors (interior) | 66614110 |
| 4 | `2018-03-15.14-50-00.14-55-00.school.G638` | Plaza (exterior), doors | 190112066 |
| 5 | `2018-03-15.14-50-00.14-55-00.school.G336` | School exterior / vehicle lot | 260260028 |
| 6 | `2018-03-15.14-50-00.14-55-00.school.G474` | Infrared pair of G336 (low-res, no annotations) | 5987886 |
| 7 | `2018-03-15.14-50-00.14-55-00.bus.G331` | Bus station | 112414584 |
| 8 | `2018-03-15.14-55-00.15-00-00.bus.G331` | Bus station. **1 theft** | 108866912 |
| 9 | `2018-03-15.15-10-00.15-15-00.bus.G331` | Bus station. **1 theft** | 108593042 |
| 10 | `2018-03-15.15-15-00.15-20-00.bus.G331` | Bus station. **1 abandoned package** | 103333370 |

Source URL pattern: `https://mevadata-public-01.s3.amazonaws.com/drops-123-r13/2018-03-15/<HH>/<stem>.r13.avi`. `<HH>` is the hour the clip **ends** in: `14` for clips 1–7, and `15` for clips 8–10, including the 14:55–15:00 clip.

**3.2 Run this script.** It verifies the videos, downloads any missing or incomplete ones, and fetches the annotations, GPS, site map and clip table. Save it as `C:\argus\scripts\get_meva.ps1` and run it with `powershell -ExecutionPolicy Bypass -File C:\argus\scripts\get_meva.ps1`.

```powershell
$ErrorActionPreference = "Stop"
$root = "C:\argus\data\meva"
$vid  = "$root\video"; $ann = "$root\ann"; $gps = "$root\gps"
New-Item -ItemType Directory -Force -Path $vid,$ann,$gps | Out-Null
$S3  = "https://mevadata-public-01.s3.amazonaws.com/drops-123-r13/2018-03-15"
$GL  = "https://gitlab.kitware.com/meva/meva-data-repo/-/raw/master"
$A   = "$GL/annotation/DIVA-phase-2/MEVA"

# stem, S3 hour folder, annotation set ('' = no annotation), expected bytes
$clips = @(
 @("2018-03-15.14-50-00.14-55-00.school.G421","14","kitware/2018-03-15/14",142880030),
 @("2018-03-15.14-50-00.14-55-00.school.G419","14","kitware-meva-training/2018-03-15/14",78883804),
 @("2018-03-15.14-50-01.14-55-01.school.G420","14","kitware/2018-03-15/14",66614110),
 @("2018-03-15.14-50-00.14-55-00.school.G638","14","kitware-meva-training/2018-03-15/14",190112066),
 @("2018-03-15.14-50-00.14-55-00.school.G336","14","kitware-meva-training/2018-03-15/14",260260028),
 @("2018-03-15.14-50-00.14-55-00.school.G474","14","",5987886),
 @("2018-03-15.14-50-00.14-55-00.bus.G331","14","kitware-meva-training/2018-03-15/14",112414584),
 @("2018-03-15.14-55-00.15-00-00.bus.G331","15","kitware-meva-training/2018-03-15/15",108866912),
 @("2018-03-15.15-10-00.15-15-00.bus.G331","15","kitware-meva-training/2018-03-15/15",108593042),
 @("2018-03-15.15-15-00.15-20-00.bus.G331","15","kitware-meva-training/2018-03-15/15",103333370)
)

foreach ($c in $clips) {
  $stem,$hh,$aset,$size = $c
  # accept either <stem>.avi or <stem>.r13.avi that you may already have
  $existing = @("$vid\$stem.avi","$vid\$stem.r13.avi") | Where-Object { Test-Path $_ } | Select-Object -First 1
  if ($existing -and (Get-Item $existing).Length -eq $size) {
    if ($existing -ne "$vid\$stem.avi") { Rename-Item $existing "$stem.avi" }
    Write-Host "OK      $stem"
  } else {
    Write-Host "FETCH   $stem"
    curl.exe -fL --retry 3 -C - -o "$vid\$stem.avi" "$S3/$hh/$stem.r13.avi"
    if ((Get-Item "$vid\$stem.avi").Length -ne $size) { throw "Size mismatch: $stem" }
  }
  if ($aset -ne "") { curl.exe -fsL -o "$ann\$stem.activities.yml" "$A/$aset/$stem.activities.yml" }
}

# GPS (small zip). Keep only the 14:50–15:20 slots.
curl.exe -fL -o "$root\gps.zip" "$GL/metadata/gps/gps-for-released-meva-data.zip"
Expand-Archive -Force "$root\gps.zip" "$root\gps_all"
Get-ChildItem "$root\gps_all" -Recurse -Filter "2018-03-15.1*.gpx" |
  Where-Object { $_.Name -match '2018-03-15\.(14-5|15-[01])' } | Copy-Item -Destination $gps

# Site map (named zones and camera placement) and clip timing table
curl.exe -fL -o "$root\site-map.pdf" "https://mevadata-public-01.s3.amazonaws.com/phase2-known-facility-site-map.pdf"
curl.exe -fL -o "$root\clip-table.txt" "$GL/metadata/meva-clip-camera-and-time-table.txt"
Write-Host "DONE. Videos:" (Get-ChildItem $vid).Count " Annotations:" (Get-ChildItem $ann).Count " GPX:" (Get-ChildItem $gps).Count
```
✅ Expected at the end: `Videos: 10  Annotations: 9  GPX: 6` (14:50, 14:55, 15:00, 15:05, 15:10, 15:15).

**3.3 Make browser-playable copies** (the web console can't play AVI). This writes 960-px-wide MP4s for the UI; the originals stay for YOLO.
```powershell
New-Item -ItemType Directory -Force C:\argus\data\meva\web | Out-Null
Get-ChildItem C:\argus\data\meva\video\*.avi | ForEach-Object {
  ffmpeg -y -loglevel error -i $_.FullName -vf "scale=960:-2" -c:v libx264 -preset veryfast -crf 26 -an -movflags +faststart "C:\argus\data\meva\web\$($_.BaseName).mp4"
}
```

---

## 4. Watch the ground-truth moments (about 20 min, **do not skip**)

Before we design any rule, we need to see what the thefts and the abandonment actually look like on camera. **Frame ÷ 30 = seconds into the clip.**

| Event | Clip | Frames | Time into clip | Wall-clock (local) |
|---|---|---|---|---|
| Theft 1 | G421 cafe, 14:50 clip | 6544–6684 | **3:38–3:43** | 14:53:38 |
| Theft 2 | G421 cafe, 14:50 clip | 7748–7880 | **4:18–4:23** | 14:54:18 |
| Theft 3 | G331 bus, 14:55 clip | 3434–3582 | **1:54–1:59** | 14:56:54 |
| Theft 4 | G331 bus, 15:10 clip | 6319–6444 | **3:30–3:35** | 15:13:30 |
| Abandoned package | G331 bus, 15:15 clip | 5629–5740 | **3:07–3:11** | 15:18:07 |

For each one, write one line in our team chat:
- **What object?** Is it a COCO class (backpack=24, handbag=26, suitcase=28)? Or a phone or something small?
- **Is it big enough to detect?**
- **What visible pattern could a rule catch?** For example: the bag was put down by person A and carried away by person B; the bag was left alone for 30 s and then the owner walked out the door.

This tells us which incidents our video rules can **honestly** catch. Some may not be detectable (for example, stealing a phone). That's fine: we'll report recall honestly (e.g. "3/5").

---

## 5. Zones (about 30 min)

We need **pixel polygons per camera** (for YOLO rules) and **lat/lon polygons per area** (for GPS).

**5.1 Grab one frame per camera:**
```powershell
New-Item -ItemType Directory -Force C:\argus\data\meva\frames | Out-Null
Get-ChildItem C:\argus\data\meva\video\*.avi | ForEach-Object {
  ffmpeg -y -loglevel error -ss 5 -i $_.FullName -frames:v 1 "C:\argus\data\meva\frames\$($_.BaseName).jpg"
}
```

**5.2 Draw pixel polygons.** Upload each frame to https://polygonzone.roboflow.com and copy the coordinates into `C:\argus\backend\argus\config\cameras.yaml`. Coordinates are in the **original 1920×1072** resolution:
```yaml
G421:
  zone: school_cafe            # physical zone this camera belongs to
  criticality: 0.6             # 0..1 asset criticality of the area
  polygons:
    door:      [[x,y],[x,y],[x,y],[x,y]]   # doorway region (validates door sensor)
    seating:   [[...]]
    counter:   [[...]]
G331:
  zone: bus_station
  criticality: 0.7
  polygons:
    platform:  [[...]]
    walkway:   [[...]]         # pedestrian-only (for vehicle-in-pedestrian-zone)
# ...same for G419, G420, G638, G336 (G474 = same zone as G336)
```
Use `site-map.pdf` to check which named zone each camera covers.

**5.3 GPS zones.** Open https://geojson.io, search for `39.0498, -85.5292` (the MUTC site origin) and switch to satellite. Draw polygons for the same zone names as `cameras.yaml` (the school building, cafe side, plaza, school parking, bus station), following the site map. Save the result as `C:\argus\backend\argus\config\zones.geojson`, with a `zone` property on each feature.

---

## 6. Vision pipeline: your main build (14:30 → 22:00)

**Architecture decision: do the offline run first, and use live inference only as a proof.** The demo replays 30 minutes of 6 cameras at 10–20× speed, and no GPU can run live YOLO at that rate. So:

1. **`vision/run_tracks.py` (offline):** YOLO + ByteTrack over every clip → `data/tracks/<stem>.jsonl` with one line per frame per track.
2. **`vision/rules.py`:** tracks + polygons → **CCTV events** in the shared schema (§8) → `data/events/cctv.jsonl`.
3. **The UI** plays the MP4s and draws boxes from the cached tracks. This is smooth and can't crash on stage.
4. **`vision/live.py`:** one camera running **real-time YOLO** in a "LIVE INFERENCE" tile, so judges see real inference. If it misbehaves on stage, turn the tile off; nothing else depends on it.

**6.1 Tracking run.** Always use `stream=True` so frames aren't kept in memory. On Windows, put the entry point under `if __name__ == "__main__":`.
```python
from ultralytics import YOLO
import json, pathlib
CLASSES = [0, 2, 3, 5, 7, 24, 26, 28]   # person, car, motorcycle, bus, truck, backpack, handbag, suitcase
def run(clip: pathlib.Path, out: pathlib.Path):
    model = YOLO("yolo11s.pt")           # one model instance per clip/process
    with out.open("w") as f:
        for i, r in enumerate(model.track(source=str(clip), stream=True, persist=True, tracker="bytetrack.yaml",
                                          classes=CLASSES, conf=0.3, imgsz=960, half=True, vid_stride=2, verbose=False)):
            frame = i * 2                # vid_stride=2 -> original frame index
            if r.boxes.id is None: continue
            for box, tid, cls, cf in zip(r.boxes.xyxy.tolist(), r.boxes.id.int().tolist(),
                                         r.boxes.cls.int().tolist(), r.boxes.conf.tolist()):
                f.write(json.dumps({"frame": frame, "tid": tid, "cls": cls, "conf": round(cf, 3),
                                    "xyxy": [round(v, 1) for v in box]}) + "\n")
if __name__ == "__main__":
    import sys; run(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]))
```
Expected speed is roughly 60–120 fps on the 5060, so all 10 clips take about 10–20 min. **Run G421 first** and hand its output to the backend person immediately.
If people's IDs keep switching, try `tracker="botsort.yaml"`. Try `imgsz=1280` only if small bags are missed; it's slower.

**6.2 Rules** (each emits CCTV events; start with the first three):

| Rule | Logic | Maps to |
|---|---|---|
| `door_activity` | person track enters a `door` polygon | Checked against annotated door opens (our **precision/recall metric**) |
| `abandoned_object` | bag (24/26/28) stationary for more than 20 s with no person within 3× the bag's box height | Abandoned package |
| `custody_change` | bag first seen near person A; later the bag moves while its nearest person is B ≠ A, for more than 1 s | Possible theft. Experimental: tune on thefts 1–4 from §4 |
| `vehicle_in_ped_zone` | vehicle box centre inside a `walkway` polygon | Vehicle intrusion |
| `loitering` | person track inside a polygon longer than T seconds (T set per zone) | Loitering |
| `running` | track speed (px/s ÷ box height) above a threshold | Running / chase |
| `occupancy` | person count per polygon every 10 s; emit only when it changes a lot (z-score vs a rolling mean) | Crowding / baseline |

Converting time: `t = clip_start_local + frame/30`. The clip start comes from the filename; the clip-table offsets matter only for exact cross-camera sync, so skip them at first. Store `t` as **UTC epoch seconds**. Filenames are local time, EDT, which is **UTC−4**. GPX times are already UTC (`...T18:50:06Z` = 14:50:06 local).

---

## 7. The other two real streams (the backend person builds these, from your files)

- **Door sensor:** parse `ann/*.activities.yml` and keep **only** `person_opens_facility_door` (plus `person_enters/exits_scene_through_structure` as entry/exit). Each record looks like `{'act': {'act2': {'person_opens_facility_door': 1.0}, 'timespan': [{'tsr0': [start, end]}], ...}}`. Load with `yaml.load(f, Loader=yaml.CSafeLoader)` (fast). Set `provenance = "annotation_derived"`.
- **Device location:** GPX files with 88 tracks per 5-minute slot, one fix every 10 s, named by logger ID (e.g. `G528`). Map each fix to a zone via `zones.geojson` (shapely point-in-polygon). This produces presence and flow events per zone. **GPS devices cannot be linked to the people on camera**, so fusion is by **zone and time**, never by identity. On a real campus this stream would be **Wi-Fi access-point associations**; say that in the pitch.

**Cyber stream (decision: not in the MVP).** No real dataset shares a site with this footage. If we're ahead at the 22:00 checkpoint, we add LANL's real enterprise login logs with red-team labels, replayed onto the admin building. Every incident that uses them gets a visible **"composed link"** badge. **Someone submits the short access form at https://csr.lanl.gov/data/cyber1/ today** (a form only we can fill in) so the files are available if we get there.

---

## 8. The shared contract (everyone codes against this; don't change it without telling the team)

**Event** (one JSON line per event; all streams write this format):
```json
{
  "event_id": "cctv-G421-000123",
  "t": 1521140018.0,
  "source": "cctv | door | device | auth",
  "sensor_id": "G421",
  "zone": "school_cafe",
  "type": "abandoned_object | custody_change | door_activity | door_open | entry | exit | vehicle_in_ped_zone | loitering | running | occupancy | device_presence | device_flow",
  "severity": 0.0,
  "confidence": 0.0,
  "entity": {"kind": "track | device | door", "id": "G421:t145"},
  "provenance": "computed | annotation_derived | recorded",
  "media": {"clip": "2018-03-15.14-50-00.14-55-00.school.G421", "frame": 6544, "bbox": [0,0,0,0]},
  "attrs": {}
}
```

**Incident** (produced by the fusion engine):
```json
{
  "incident_id": "INC-0007", "zone": "bus_station", "status": "open | ack | escalated | dismissed",
  "opened_at": 0.0, "updated_at": 0.0,
  "score": 0, "score_breakdown": {"severity": 0, "confidence": 0, "criticality": 0, "corroboration": 0, "time_factor": 0},
  "sources": ["cctv", "device"], "event_ids": ["..."], "title": "Unattended bag, owner left zone",
  "brief": {"summary": "", "why": "", "action_id": "", "evidence_ids": []},
  "composed": false
}
```

**Folder layout** (repo root = `C:\argus`):
```
backend/argus/{schema.py, config/, ingest/(doors.py, gps.py), vision/(run_tracks.py, rules.py, live.py),
               fusion/(engine.py, score.py), brief/(llm.py, playbook.yaml), replay/clock.py, api/main.py, eval/evaluate.py}
frontend/            React + Vite + Tailwind console
scripts/             get_meva.ps1, transcode.ps1
data/                (gitignored) meva/, tracks/, events/, cache/
```

---

## 9. Whole-team plan and owners (Tanush assigns names)

| Owner | Builds |
|---|---|
| **You (GPU laptop): Vision + Data** | §2–§6: env, data, zones, tracks, CCTV rules, live tile, door metric |
| **Backend / fusion** | schema, door + GPS ingest (§7), replay clock (merges all streams by `t`, speed 1–20×, jump-to-bookmark), fusion engine, scoring, FastAPI + WebSocket |
| **Frontend** | one excellent console screen: camera wall (MP4 + box overlay), ranked incident queue, incident detail (evidence timeline, score breakdown, brief, Ack/Escalate/Dismiss), site map with zones, metrics strip, **"siloed view" toggle** (raw per-stream alerts), attribution footer |
| **AI brief + eval + pitch** | schema-bound LLM brief (Claude API, with cached briefs for demo incidents and a template fallback when offline), `eval/evaluate.py`, 2-min video, ≤8-slide deck, README, project site + Raah + LinkedIn |

**Fusion engine in one paragraph.** Signals that share a **zone** inside a **120 s window** are grouped. The score is severity × confidence × zone criticality × corroboration, times a time-of-day factor, scaled to 0–100. Corroboration counts **distinct independent sources** (cctv / door / device), not event counts. **Common-cause rollup:** bursts of the same routine type from one source (e.g. 40 door opens at a class change) become one low-priority "routine activity" roll-up, never 40 alerts. An incident opens above the threshold (tuned; start at 60).

**Metrics we will show (all measured on real data):**
1. **Door detection:** video `door_activity` vs annotated door opens, matched within ±2 s, on G419/G420/G421/G638. Report precision and recall.
2. **Incident recall:** how many of the 5 ground-truth incidents (4 thefts + 1 abandonment) appear among ARGUS incidents, and at what rank. Say "k/5" honestly.
3. **Reduction:** raw events (all streams) → incidents above threshold.
4. **Latency:** signal → incident, in replay time.

---

## 10. Timeline (IST) and checkpoints

| Time | Goal |
|---|---|
| **13:00–13:45** | §2 env and GPU check, §3 data script, MP4 transcode running |
| **13:45–14:30** | §4 watch the 5 incidents, §5 zones |
| **14:30–15:00** | §6.1 tracking run starts (G421 first) |
| **15:00 ✅ CHECKPOINT** | `data/tracks/G421...jsonl` exists and is shared with the backend |
| 15:00–17:00 | rules `door_activity`, `abandoned_object`, `custody_change` → `events/cctv.jsonl` |
| **17:00 ✅ CHECKPOINT** | end-to-end: CCTV + door + GPS events → fusion → at least 1 incident on screen |
| 17:00–22:00 | remaining rules, door metric, live inference tile, tune on the 5 ground-truth incidents |
| **22:00 ✅ FEATURE FREEZE** | full 30-min replay works; metrics computed; decide go/no-go on the cyber stream |
| 22:00–02:00 | should-haves only if stable; bug fixes |
| 02:00–06:00 | sleep in shifts |
| **07:00** | 2-minute demo video recorded (also our backup if the live demo fails) |
| **09:00 🔒 CODE FREEZE** | rehearse 5×; **test with Wi-Fi OFF** |

---

## 11. If something breaks

| Problem | Do this |
|---|---|
| `no kernel image` / `sm_120` error | Wrong torch wheel. Reinstall from `--index-url .../whl/cu130` (§2.3) |
| Driver < 580 | Update the NVIDIA driver (GeForce app or nvidia.com) before anything else |
| Python runs on the integrated GPU / slow | NVIDIA Control Panel → python.exe → High-performance processor; laptop on charger |
| RAM grows during tracking | You forgot `stream=True` |
| IDs switch a lot | `botsort.yaml`; lower `vid_stride` to 1 for that clip |
| Small bags missed | `imgsz=1280` or `yolo11m.pt` for that clip only |
| `curl` behaves oddly in PowerShell | Use `curl.exe` (plain `curl` is an alias for Invoke-WebRequest) |
| Script blocked by execution policy | `powershell -ExecutionPolicy Bypass -File <script>` |
| Venue Wi-Fi dies | Everything runs on localhost; LLM briefs are cached, with a template fallback; phone hotspot as last resort |
| Live tile stutters on stage | Turn it off; the cached-tracks camera wall keeps running |

## 12. Do NOT spend time on
Training any model · YOLO-World / buildings model · Redis, Docker or DuckDB · a login system · fancy graph visualisations · more cameras than the 6 above · TensorRT export (only if everything else is done) · downloading more MEVA data.

---

**Questions → Tanush.** Once §2 and §3 pass, post "✅ GPU + data OK" in the team chat with the output of the §2.4 command and the counts from §3.2.
