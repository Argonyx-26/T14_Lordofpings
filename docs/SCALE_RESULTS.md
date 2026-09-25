# Large-sample results (MEVA, outside every tuning and held-out window)

20 five-minute clips (1.67 camera-hours) on G419, G420, G421 and G638, from seven days. 0 clips were skipped because the camera had been re-aimed. Produced by `python -m argus.eval.scale`.

| Detector | Annotated events | Detected | Precision | Recall |
|---|---|---|---|---|
| Door opening (video door sensor) | 73 | 106 | 0.255 | 0.37 |
| Hand-to-hand exchange | 16 | 599 | 0.08 | 0.938 |

False threat events on this ordinary footage (MEVA has no weapons, fights or dealing): weapon_visible 26, violence 0, person_down 0, dealing_pattern 130.

| Camera | Clips | Doors (truth / detected / correct) | Hand-offs (truth / found / detected) |
|---|---|---|---|
| G419 | 5 | 8 / 6 / 5 | 0 / 0 / 6 |
| G420 | 5 | 4 / 4 / 0 | 0 / 0 / 0 |
| G421 | 5 | 15 / 39 / 6 | 16 / 15 / 592 |
| G638 | 5 | 46 / 57 / 16 | 0 / 0 / 1 |

Re-scored from the cached detections with the rules as of 26 Sep 03:50 (only meetings feed the dealing pattern; a
fall must start upright): dealing_pattern 130 → **18**, person_down 0, violence 0. The 26 weapon alerts are before the
vision-model verifier, which runs on uploads and needs the frames (these videos were deleted after processing); on
149 ordinary clips elsewhere it removed 66 of 72 false weapon alerts (`docs/MODEL_SCORES.md`).
