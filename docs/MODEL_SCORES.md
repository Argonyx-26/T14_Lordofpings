# ARGUS model scores

Every number below is measured, with its test set, its size and how it was split. Sources are the JSON files in
`data/cache/` on the demo laptop (not in git; the scripts that produce them are). Updated 26 Sep 2026, 03:00 IST.

## Detection and fusion on real multi-sensor footage (MEVA, 15 Mar 2018, 14:50-15:20)

| What | Score | n and method | Source |
|---|---|---|---|
| Staged thefts / abandonments caught | **4 of 5**, **0 false incidents** | Every staged theft and abandonment MEVA annotates in the window. This is the window the rules were tuned on. | `metrics.json` (`argus.eval.evaluate`) |
| Signal reduction | 1,242 raw events → 20 siloed alerts → **3 incidents** (99.8 % fewer than raw) | same 30 min, 6 cameras + door sensors + GPS | `metrics.json` |
| Security profiles | Airport 4/5 (+6 on watch), Campus 4/5, Park 2/5; **0 false incidents in all three** | same 30 min | `profiles_eval.json` |
| Video door sensor, demo window | indoor precision **0.54**, recall **0.75**; all cameras P 0.21 / R 0.52 (the bus-station camera over-fires: 64 detections, 1 door opening) | 42 annotated door openings, ±2 s | `metrics.json` |
| Video door sensor, unseen clips | G419 **5/8** found (precision 5/6); G420 0/4 (running: 10 of 20 clips so far) | MEVA clips outside every tuning window, ±2 s | `data_scale/results.json` (`argus.eval.scale`) |

## Threat detectors (public datasets, tested on data the model never trained on)

| Model | Score | n and method | Source |
|---|---|---|---|
| **Fight detection** (pose + VideoMAE, random forest) | accuracy **76.7 %**, ROC-AUC **0.854**; at the pipeline threshold 0.7: **87/150 fights caught, 12/150 false** (precision 0.88) | 300 CCTV clips (Akti et al. 2019), 5-fold CV **grouped by source recording** (74 recordings). The dataset's authors reported 72 % on a random split. | `violence_eval.json` |
| Fight detection, pose only | accuracy 74.7 %, AUC 0.821; at 0.7: 80/150 caught, 17 false | same | `violence_eval.json` |
| VideoMAE alone (pretrained, no training here) | accuracy 74.0 %, AUC 0.805 | same 300 clips, external test | `violence_eval.json` |
| **Weapon detector v2** (in use) | **46/84 weapon appearances alerted, 7 false alerts in 29 min**; box mAP50 0.311 (handgun 0.37, rifle 0.51, knife 0.05) | 3,511 frames from a camera **never trained on** (Univ. Seville mock attack, Cam7); trained on Cam1 + Cam5 + 2,500 synthetic frames, fixed 30 epochs | `weapons_v1_v2.json` |
| Weapon detector v1 | 42/84 alerted, 14 false alerts in 29 min; box mAP50 **0.376** (handgun 0.51, rifle 0.54, knife 0.09) | same test camera, real frames only | `weapons_v1_v2.json`, `weapons_eval.json` |
| Public gun/knife YOLO11n (for comparison) | 3/84 alerted at 0.5; handgun AP50 0.04 | same test camera | `weapons_compare.json` |
| Person down, hand-off, dealing pattern | **no measured score yet**; hand-offs are being scored at scale (0 annotated in the first 10 clips) | | |

## Live and GenAI

| What | Score | n and method | Source |
|---|---|---|---|
| Live unattended-bag rule | fires **once**, 0.3 s from the offline rule, owner-left; no alert for the other bags on the platform | the staged MEVA abandonment (G331 15:18), streamed as if live; 4 unit tests | `tests/test_live_rules.py` |
| **Investigator agent** (Gemini, tool use) | real alerts kept **12/12** (11 confirmed or likely); the false alert (a bush) called a false alarm **2/2**; the 3 staged incidents kept **6/6** | the 7 camera bag alerts and 3 incidents in the demo window, 2 runs each, scored against MEVA annotations it never sees | `agent_eval.json` (`argus.eval.agent_eval`) |
| Vision model alone as a second opinion (baseline) | kept **2/6** real alerts, removed 1/1 false | same 7 alerts, 3 frames each | `vlm_check.json` |
| All models load and run | **8/8** | a real positive and negative per model | `models_check.json` (`argus.eval.models_check`) |

## Speed (RTX 5060 laptop)

| What | Speed |
|---|---|
| Live tile (YOLO11s + ByteTrack + bag rule) | ~30 fps, 13-16 ms per frame |
| Investigator | 24 s per case on average (6.3 tool calls, 1.6 camera looks); cached cases replay in ~4 s offline |
| One-pass analysis (tracks + valuables + pose + weapons) | 1.37× faster than four separate passes (not yet used by default) |

## Honest limits

- The 4/5 is on the window the rules were tuned on; the held-out and at-scale runs are the evidence against
  overfitting, and they are small (MEVA publishes few staged crimes).
- The agent's n is small: the window has 6 staged camera alerts and 1 false one.
- Knife detection is weak (AP50 ≤ 0.09): knives are small in 1080p CCTV and rare in the training cameras.
- The bus-station camera's door sensor over-fires; the indoor cameras are the reliable ones.
