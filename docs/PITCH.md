# ARGUS: pitch pack (deck, 5-minute script, demo run-sheet, 2-minute video, Q&A)

**Format (from the rules):** 5 min pitch + 2 min Q&A · live demo mandatory (backup video allowed) · **all four
members speak** · final deck **max 8 slides** · judged 25% each on Innovation, Technical Implementation,
Presentation & Storytelling, Business Impact & Market Potential.

**Fill in before 07:00** from `python -m argus.eval.evaluate` on the demo laptop (numbers marked `[…]`):

| Placeholder | Where it comes from | Measured (Fri, vision README) |
|---|---|---|
| `[CAUGHT]` staged incidents caught | `ground_truth_alerted / ground_truth_total` | **4/5** (2 cafe thefts, bus theft + abandonment; miss: black purse on black bench) |
| `[FALSE]` false incidents in the 30-min window | incidents with no ground truth nearby | **0** (2 camera-level bag alerts, absorbed by fusion) |
| `[RAW] → [SILO] → [INC]` | `reduction` block | **1,242 → 20 → 3** (99.8% never reach an operator) |
| `[DOOR_P] / [DOOR_R]` door detection precision / recall | `door_detection` | **0.54 / 0.75** indoor (0.21 / 0.52 all cameras) |
| `[LAT]` median seconds from first signal to incident | `latency_s` | not on the slides |
| `[FPS]` live inference fps on the RTX 5060 | live tile stats | **30 fps** (13–23 ms per frame) |

**Speakers:** A = Tanush (lead: opens and closes) · B = demo driver · C = vision/technical (the teammate who built
the pipeline) · D = business. Swap names as you like; every member must speak.

## 0. Answering "very little innovation" (Sat 26 Sep)

The feedback was that ARGUS reads as a dashboard with detection on top. The answer is **one new layer of reasoning
above incidents**, shown on screens the judges already look at (full audit and research in
[INNOVATION.md](INNOVATION.md)):

| Beat | What the judge sees | The line |
|---|---|---|
| **Patterns, not rows** | Incident panel "Part of a pattern": a chain of incidents in time; the site map draws arcs between areas; the queue tags "pattern 2/3" | "Every dashboard shows you incidents. ARGUS notices when three of them are one pattern: same behaviour, and it checks whether one person could even have walked between them." |
| **Honest about who** | A link marked *too soon to walk* (dashed amber) | "These two thefts are two minutes and 219 metres apart. Nobody walks that in time, so ARGUS says: at least two people. It never recognises a face; it links behaviour, place and time." |
| **Forecasts the site** | "Watch next: Bus station (G331) and Parking" with the window counting down; the map outlines them | "After a theft, crime clusters nearby for a while: criminologists call it near-repeat. So ARGUS tells the operator where to look next, and admits the parking lot has no camera at all." |
| **Knows where it's blind** | "What could agree here" in *Why this score*; hatched areas on the map; visibility % | "A one-camera area can't corroborate itself. ARGUS says how much evidence each place can give, instead of pretending." |
| **Cover the camera (live)** | Hand over the stage webcam for 2 s: red border, "Camera view lost" opens at once; the live area goes blind on the map until the view is back | "Attackers blind cameras first. A monitoring system that doesn't notice its own eyes going dark reports a quiet scene." |
| **Hands over the case** | **Case report**: timeline, pattern, blind spots, forecast, decisions with hashes; print or copy | "When the shift ends, the case is already written, and every line traces back to a signal or a logged decision." |

**Run-sheet inserts** (add to section 3): after opening the bus-station incident, scroll to *Part of a pattern*
(15 s), point at the map arcs and *watch next* (10 s); in *Why this score* read *What could agree here* (10 s); at
the end, **Case report** (10 s). With the stage camera: cover the lens for 3 s after the bag demo (10 s).

**Before the slot, on the demo laptop:** `python -m argus.eval.patterns_eval` for the pattern and near-repeat numbers
(say them as counts with the chance level, e.g. "3 of 4 later staged events were in a watch-next area; chance was
half"), and `python -m argus.export_snapshot` so the hosted console shows the same.

**Q&A for this layer**

| Question | Answer |
|---|---|
| Isn't linking incidents just a guess? | "It's a stated rule: same crime script, the same act, inside 30 minutes, and a walking-time check from the site map. ARGUS calls it a working hypothesis on screen, and it never changes a score or opens an incident." |
| Could it link innocent people? | "It links incidents, not people: no faces, no phone IDs. A link says the behaviour repeated; a person decides what that means." |
| Does the watch actually predict anything? | "On the staged events in our window, [WATCH] later events were in a watch-next area, where chance was half. Five events is tiny and we say so; it's a prompt for attention, not a prediction of a crime." |
| Why is the parking lot 'blind'? | "It has no camera, only phone counts. ARGUS can count people there but cannot see a bag or a fight, and it says so on the map and in every score." |

---

## 1. The deck (8 slides)

Keep the console's look: near-black, one serif for headlines (Instrument Serif), Geist for text, no clip art,
one idea per slide, numbers big.

| # | Slide | On screen | Speaker · time |
|---|---|---|---|
| 1 | **Title** | "Argus" wordmark · *We don't watch more. We notice sooner.* · PS5 Intelligent Threat Detection & Situational Awareness · team names | A · 0:00–0:10 |
| 2 | **The problem** | Big: **4,484 alerts a day · 67% never looked at** (Vectra 2023, 2,000 SOC analysts). Small: physical security teams report the same wall of false alarms (ServiceNow cut 94% with alarm triage, Ambient.ai 2026). Photo-free: a sketch of five screens, one tired operator. If you got a quote from RV University campus security, put it here. | A · 0:10–0:35 |
| 3 | **The insight** | *The threat lives between the screens.* One camera flag is noise; a camera flag + a crowd forming on phones + a door opening in the same place and minute is an incident. Visual: the funnel `[RAW] events → [SILO] per-stream alerts → [INC] incidents`. | A · 0:35–1:00 |
| 4 | **Live** | One word: "Live". Switch to the console. | B (+C) · 1:00–3:15 |
| 5 | **How it works** | Left to right: *Real streams* (MEVA CCTV · door sensor · device location) → *Detect* (YOLO11 + ByteTrack, rules, causal baselines; no training, no labels) → *Fuse* (same area within 120 s, strongest signal per source, corroboration, common-cause damping) → *Score* (transparent 0–100) → *Explain* (Gemini writes the brief; it can't create, hide or re-rank incidents; every sentence checked against evidence) → *Human decides* (acknowledge / escalate / dismiss, hash-chained audit). | C · 3:15–3:40 |
| 6 | **Measured on real footage** | **[CAUGHT] staged incidents caught** · **[FALSE] false incidents** in 30 min across 6 cameras · **[RAW] → [INC]** · door detection P `[DOOR_P]` R `[DOOR_R]` · `[LAT]` s to an explained incident · `[FPS]` fps live on one laptop GPU. Footnote: *MEVA dataset (Kitware/IARPA), staged incidents among real passers-by; door stream derived from annotations (stands in for access control); video door sensor scored against them; the miss was a black purse on a black bench.* | C · 3:40–3:55 |
| 7 | **Why us, who pays** | 2×2: *camera-only vs multi-stream* × *enterprise-priced vs campus-priced*. Genetec / Milestone PSIM (physical, enterprise) · Splunk / Sentinel (cyber, enterprise) · Ambient.ai (camera-first, US enterprise) · **Argus: multi-stream, software-only, explainable, runs on one GPU**. Beachhead: Indian university and hospital campuses with 2–5-person control rooms. Model: per-site SaaS by stream count + on-prem licence (assumption to state: ₹[X] per site per month). PSIM market ≈ $4.3B by 2029 (MarketsandMarkets). | D · 3:55–4:40 |
| 8 | **What comes next** | Any footage: upload a clip and Argus analyses it on the spot. Connectors (Milestone/Genetec video, access control, Wi-Fi and security logs). One GPU box per site with a DPDP-ready audit trail. Close line. | A · 4:40–5:00 |

Slide 5 and 6 are the technical-implementation marks; slide 7 is the business marks; slides 2–3 plus the demo
carry storytelling. Do not add a slide for the tech stack list or "future features".

---

## 2. The 5-minute script

Aim for ~650 spoken words. Rehearse with a timer; cut words, not the demo.

**A: Problem (0:00–1:00)**
> "Security control rooms aren't short of cameras. They're drowning in them. One survey of two thousand security
> analysts found four and a half thousand alerts a day, and two thirds never get looked at. On a campus the control
> room is two people and a wall of screens. The threat is rarely on one screen. It's *between* them: a bag changing
> hands on one camera, a crowd forming at the bus station on people's phones, a door opening at the wrong moment.
> Each alone is noise. Together they're an incident. That's what Argus finds. We don't watch more. We notice sooner."

**B: Demo (1:00–3:15)** see the run-sheet below. C adds one or two technical sentences where marked.

**C: How it works + results (3:15–3:55)**
> "Every stream is real: multi-camera footage and GPS from the MEVA dataset, a real facility with staged incidents
> among ordinary passers-by. YOLO11 and ByteTrack run on this laptop's GPU; rules turn tracks into events with no
> training and no labels. The fusion engine groups signals by place and time, counts each *source* once so one noisy
> camera can't shout louder, and rewards independent corroboration. The score is transparent: you just saw every
> factor. Gemini writes the brief, but it can't create or hide an incident, and we reject any sentence that isn't
> backed by the evidence. Measured against the ground truth: we caught [CAUGHT] staged incidents with [FALSE] false
> alarms in half an hour of six cameras, out of [RAW] raw events."

**D: Business (3:55–4:40)**
> "Big sites buy Genetec or Milestone for physical security and Splunk for cyber: enterprise products, separate
> silos, enterprise prices. Ambient.ai does AI on cameras for US enterprises. Nobody serves the Indian campus: a
> university or a hospital with a two-person control room and cameras they already own. Argus is software on one
> GPU box that reads the feeds they already have. We'd sell it per site by number of streams, with an on-prem
> licence for sites that can't use the cloud, and every decision is explainable and audited, which matters under
> India's DPDP rules."

**A: Close (4:40–5:00)**
> "What comes next: first, any footage. Hand us a clip and Argus analyses it on the spot with the same detectors
> and fusion. Then connectors for the video, access-control and network systems campuses already run, and one GPU box
> per site with an audit trail ready for India's DPDP rules. Argus: we don't watch more, we notice sooner. Thank you."

---

## 3. Live demo run-sheet (B drives, 2 min 15 s)

**Before the slot:** `scripts\run_demo.ps1` running (add `-Live` for the live tile), console at
http://localhost:8000, **Reset** pressed, speed **10×** (the camera wall stutters above 10× until the seek fix lands), Duty officer role, browser full-screen (F11), Wi-Fi off
if the venue network is shaky. Backup video on the desktop and on a USB stick.

| Time | Do | Say |
|---|---|---|
| 1:00 | Press **Play** (10×) | "This is thirty minutes of real footage and sensor data from one facility, sped up." |
| 1:10 | Point at the funnel band | "Events pour in from every stream; the per-stream alerts pile up; incidents stay near zero." |
| 1:20 | Open **Raw signals** under the cameras and toggle **Siloed alerts** | "This is what each system would page on its own. This is what operators ignore." |
| 1:35 | Click the **Bus station** diamond on the timeline | "Let's go to the bus station." |
| 1:45 | The incident "Possible theft: unattended object taken" rises to the top; click it | "A bag was left unattended, then someone else carried it off, and phones show a crowd forming in the same minute: independent sources agree." |
| 2:05 | Point at **Why this score** | "No black box: severity, confidence, how critical the place is, and the corroboration bonus." |
| 2:20 | Click the **camera evidence** row | "One click replays the moment." (that camera moves to the main view, red box on the object) |
| 2:35 | C: one sentence | "That box comes from YOLO11 tracking, running on this laptop, no training." |
| 2:45 | Switch role to **Supervisor**, **Respond → Escalate to a supervisor** | "A human decides, and every decision goes into a tamper-evident log." |
| 2:55 | (optional) **Live inference** toggle for 5 s | "And this is the detector running live, [FPS] frames a second." |
| 3:10 | Back to slides | |

**If something breaks:** say "let me show you the recording" and play the backup video from the matching moment.
Never debug on stage.

---

## 4. The 2-minute demo video (deliverable + stage backup)

> The full, record-ready version (prep checklist, shot list, editing steps) is **[DEMO_VIDEO_SCRIPT.md](DEMO_VIDEO_SCRIPT.md)**. Use that one; the table below is the summary.

Record on the Windows laptop with **Xbox Game Bar** (`Win + Alt + R` starts/stops; saves to
`Videos\Captures`) or OBS. Trim in **Clipchamp** (built into Windows 11). 1920×1080, console full-screen (F11),
voice-over recorded separately and laid over, or recorded live with a headset mic. Add burned-in captions (Clipchamp
auto-captions), because judges may watch it muted.

| Time | Picture | Voice-over |
|---|---|---|
| 0:00–0:08 | Title card: "Argus" · tagline · PS5 | "Argus: we don't watch more, we notice sooner." |
| 0:08–0:25 | Console playing at 10×, funnel numbers climbing; then the Siloed alerts view | "A security control room gets thousands of signals. Here are thirty minutes of real multi-camera footage and GPS from one facility. Every stream on its own would page constantly." |
| 0:25–0:50 | Jump to the bus-station scenario; incident rises; open it | "Argus fuses signals by place and time. At the bus station, a camera sees an object change hands while phones show a crowd forming: two independent sources, one incident, ranked first." |
| 0:50–1:10 | Zoom on Why this score and the brief | "The score is transparent. Gemini writes the brief, but it cannot create or hide incidents, and every sentence is checked against the evidence." |
| 1:10–1:30 | Click the evidence: that camera takes the main view with the red box; then the live inference view | "One click replays the moment. Detection is YOLO11 with tracking, running live on a single laptop GPU, with no training." |
| 1:30–1:45 | Supervisor escalates; audit log | "A human makes every call, and every call is recorded in a tamper-evident log." |
| 1:45–2:00 | Results card: [CAUGHT] caught · [FALSE] false alarms · [RAW] → [INC] | "On real footage we caught [CAUGHT] staged incidents with [FALSE] false alarms. And you can hand Argus any clip to analyse on the spot." |

Export as MP4 ≤ 2:00. Keep one copy on the demo laptop desktop and one on a USB stick.

---

## 5. Q&A bank (2 minutes: answer in one or two sentences, then stop)

| Likely question | Answer |
|---|---|
| Isn't it tuned on the data you tested on? | "We tuned on one 30-minute window, then ran the unchanged pipeline on footage it never saw: a different day and a later window. Those held-out numbers are on the results slide [fill from docs/HOLDOUT_RESULTS.md]." |
| Five incidents is a tiny sample. | "It is, and we say so. MEVA only stages six thefts and abandonments in the whole public set; five are in our window and the sixth is in our held-out day. That's why we also count false incidents over every hour of unseen footage." |
| Isn't the data staged? | "The incidents are staged by actors, but among real passers-by, on real multi-camera footage and real GPS from one facility (the MEVA dataset). We score against its human ground truth, including the miss." |
| Why not just use Splunk, Genetec or Ambient? | "They're enterprise products and each covers one silo. Argus fuses streams from different vendors, runs on one GPU box, and explains every score: built for a two-person campus control room." |
| What about the one you missed? | "A black purse on a black bench: the detector can't see it. We added an experimental static-change detector for exactly that case; it's the next thing we'd harden." |
| Does the LLM hallucinate threats? | "It can't: detection and scoring are deterministic; Gemini only writes the explanation, we reject anything not backed by the evidence, and there's a template fallback if it's offline." |
| Corroboration assumes independent sensors. What if a power cut trips everything? | "Bursts of the same alert are treated as one likely common cause and damped, and each source counts once, however noisy it is." |
| Where does the door stream come from on a real campus? | "The access-control system. In the demo it's derived from MEVA's human door annotations as a stand-in, and separately our video door sensor (door-leaf motion) detects the same openings on its own: precision [DOOR_P] against those annotations." |
| Your door sensor is 0.21 precision across all cameras. | "Indoors, where a camera faces the door, it's 0.54 precision at 0.75 recall. Outdoors it's a motion heuristic: at the bus station most false openings come from the queue in front of the ATM back door. We tried a stricter pass-through rule and it lost more real openings than it removed false ones, so we kept the simpler rule and report both numbers. On a real site the access-control system gives the exact signal." |
| GPS on a campus? | "On a real campus that stream is Wi-Fi access-point associations: where devices are, not who they are. We fuse by place and time, never identity." |
| Privacy / DPDP? | "No face recognition, no identity inference; people are track numbers; every operator action is logged in a tamper-evident audit trail." |
| Does it scale to 1,000 cameras? | "Detection is per camera on edge GPUs; fusion only sees small events, so it's cheap: thousands of events per second on one CPU." |
| How would you make money? | "Per site, priced by number of streams, plus an on-prem licence for sites that can't use the cloud." |
| What did you build during the hackathon? | "All of it: the repo history is public and timestamped from 11:00 on Friday." |

---

## 6. Honesty rules for the pitch

- Say "staged, real-world footage", never "real crimes".
- Door stream: "derived from MEVA's human door annotations, standing in for access control". The video door sensor
  is a separate camera detector, scored against those annotations. Device location: "recorded GPS", standing in
  for Wi-Fi on a campus.
- Report the miss and the false alarms with the hits.
- Credit: "MEVA dataset, Kitware Inc. / IARPA, CC-BY-4.0" on the results slide.
- Every statistic on slide 2 cites its source on the slide.
