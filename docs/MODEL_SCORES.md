# ARGUS model scores

Every number below is measured, with its test set, its size and how it was split. Sources are the JSON files in
`data/cache/` on the demo laptop (not in git; the scripts that produce them are). Updated 26 Sep 2026, 03:30 IST.

## Detection and fusion on real multi-sensor footage (MEVA, 15 Mar 2018, 14:50-15:20)

| What | Score | n and method | Source |
|---|---|---|---|
| Staged thefts / abandonments caught | **4 of 5**, **0 false incidents** | Every staged theft and abandonment MEVA annotates in the window. This is the window the rules were tuned on. | `metrics.json` (`argus.eval.evaluate`) |
| Signal reduction | 325 raw events → 21 siloed alerts → **3 incidents** (99 % fewer than raw; 1,242 before phones were reduced to per-area counts) | same 30 min, 7 cameras + door sensors + GPS | `metrics.json` |
| Security profiles | Airport 4/5 (+6 on watch), Campus 4/5, Park 2/5; **0 false incidents in all three** | same 30 min | `profiles_eval.json` |
| Video door sensor, demo window | indoor precision **0.54**, recall **0.75**; all cameras P 0.21 / R 0.52 (the bus-station camera over-fires: 64 detections, 1 door opening) | 42 annotated door openings, ±2 s | `metrics.json` |
| Video door sensor, unseen clips | precision **0.26**, recall **0.37** (73 door openings); best camera G419 5/8 found, precision 5/6 | 20 MEVA clips, 1.67 camera-hours on 4 cameras, 7 days, outside every tuning window, ±2 s | `docs/SCALE_RESULTS.md` (`argus.eval.scale`) |
| False threat alerts on ordinary footage (unseen clips) | violence **0**, person down **0**, dealing pattern **18** (130 before the meeting rule), weapons 26 before the verifier | same 1.67 camera-hours (MEVA has no weapons, fights or dealing) | `docs/SCALE_RESULTS.md` |

## Threat detectors (public datasets, tested on data the model never trained on)

| Model | Score | n and method | Source |
|---|---|---|---|
| **Fight detection** (pose + VideoMAE, random forest) | accuracy **76.7 %**, ROC-AUC **0.854**; at the pipeline threshold 0.7: **87/150 fights caught, 12/150 false** (precision 0.88) | 300 CCTV clips (Akti et al. 2019), 5-fold CV **grouped by source recording** (74 recordings). The dataset's authors reported 72 % on a random split. | `violence_eval.json` |
| Fight detection, pose only | accuracy 74.7 %, AUC 0.821; at 0.7: 80/150 caught, 17 false | same | `violence_eval.json` |
| VideoMAE alone (pretrained, no training here) | accuracy 74.0 %, AUC 0.805 | same 300 clips, external test | `violence_eval.json` |
| **Weapons: v2 detector + vision-model verifier** (in use for uploads) | real alerts kept **33/37**; false alerts on the unseen camera **4 → 0**; ordinary CCTV clips with a false weapon alarm **72 → 6 of 149** | detector as below; each alert's close crop checked by Gemini, dropped only on a clear "no" | `weapons_vlm.json` (`argus.eval.weapons_vlm`) |
| Weapon detector v2 alone | **46/84 weapon appearances alerted, 7 false alerts in 29 min** on the unseen camera; box mAP50 0.311 (handgun 0.37, rifle 0.51, knife 0.05); but a false alarm on **145/300** ordinary CCTV clips | 3,511 frames from a camera **never trained on** (Univ. Seville mock attack, Cam7); trained on Cam1 + Cam5 + 2,500 synthetic frames. Ordinary clips: the 300-clip fight dataset (no weapons) | `weapons_v1_v2.json`, `weapons_fp.json` |
| Weapon detector v1 | 42/84 alerted, 14 false alerts in 29 min; box mAP50 **0.376** (handgun 0.51, rifle 0.54, knife 0.09); false alarm on 137/300 ordinary clips | same | `weapons_v1_v2.json`, `weapons_eval.json`, `weapons_fp.json` |
| Public pretrained weapon models (4 tested) | best: 15/84 alerted, 22 false alerts in 29 min, 33/149 ordinary clips flagged; gun-knife YOLO11n 3/84 | the same two tests | `weapons_public.json` (`argus.eval.weapons_public`) |
| **Hand-offs** (pose: wrists meet) | recall **15/16** annotated transfers (demo clips), **9/10** (unseen clips); precision low (12-16 %): hands touch a lot, so it is a weak context signal that never opens an incident | MEVA `person_transfers_object`, ±2 s | `threats_eval.json`, `handoff_heldout.json` |
| Dealing pattern (repeated hand-offs) | false patterns on ordinary footage: **51 → 7** in 65 unseen camera-minutes after requiring meetings (one person walks up or away) | MEVA, no dealing in the footage: every pattern is false | `handoff_heldout.json` |
| **Person down** | **unvalidated**: 0/30 falls on UR Fall (the clips end ~1.5 s after the fall; the rule needs 3 s down), **0/40** false on everyday activities incl. lying on a bed. False alarms on MEVA **6 → 1** after requiring the person to have been standing just before | UR Fall Detection (30 falls, 40 activities); MEVA 90 camera-min. A variant tuned on half of UR Fall caught 11/15 there but 1/15 on the other half, so it was not adopted | `threats_eval.json`, `person_down_curve.json`, `person_down_tuning.json` |

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
- The weapon verifier needs the network; offline, weapon alerts stay but are marked unverified.
- Person down is not proven on real falls; treat it as experimental.
- The bus-station camera's door sensor over-fires; the indoor cameras are the reliable ones.
