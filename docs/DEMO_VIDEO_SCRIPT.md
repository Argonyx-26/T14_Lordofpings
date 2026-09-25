# Argus: 2-minute demo video script

**What it is for:** a required deliverable (the "2-minute demo video"), and the **backup** if the live demo fails on
stage. **Length:** 2:00 or less. **Format:** 1920×1080 MP4 with burned-in captions (judges often watch muted).
**Record on:** the Windows demo laptop, with the full MEVA replay loaded. **Due:** 07:00 Saturday.

The script is about 250 spoken words, a calm pace for 2 minutes. Numbers are the measured ones (vision README,
`HANDOFF.md`); don't round them up.

---

## 1. Before recording (10 minutes)

- [ ] `scripts\run_demo.ps1 -Live` is running; the console is at http://localhost:8000 and the live tile at :8001.
- [ ] Charger in, **Best performance**, **Energy Saver off**, notifications off (Focus assist → Alarms only).
- [ ] Browser full-screen (**F11**), zoom 100%, nothing else on screen. Close the dev tools.
- [ ] Console: **Reset**, speed **10×**, role **Duty officer**, event stream on **All events**.
- [ ] One upload already analysed (for shot H): the bus-station clip from `HANDOFF_TO_JACK.md` §3.
- [ ] A quiet room and a headset mic. Record the voice-over separately if the room is noisy.
- [ ] **Title and results cards:** export the deck's cover slide and results slide as PNGs (Download → PNG/PDF), or make them in Clipchamp as white text on `#0c0d0f`.

## 2. How to record

Record **short separate clips** (shots A–H below) with **Xbox Game Bar**: `Win + Alt + R` starts and stops;
clips land in `Videos\Captures`. OBS works too. Then assemble them in **Clipchamp** (built into Windows 11):

1. Put the shots on the timeline in order and trim each to its time in the table.
2. Add the title card (0:00) and the results card (1:50).
3. Record the voice-over in Clipchamp (**Record & create → Audio**) or import it. Read the lines from §3.
4. **Captions → Auto captions** (English). Fix any misheard words: Argus, MEVA, YOLO, Gemini.
5. Where the table says "zoom", use Clipchamp's crop or zoom so the incident panel is readable at 1080p.
6. Export **1080p MP4**. Name it `Argus_demo_2min.mp4`, check it's 2:00 or less, and save copies to the desktop, a USB stick and the team chat.

## 3. Shot list and voice-over

| Time | Shot | On screen / what to do | Voice-over |
|---|---|---|---|
| 0:00–0:07 | **Title card** | "Argus" · *We don't watch more. We notice sooner.* · ARGONYX '26 · PS5 | "This is Argus. We don't watch more. We notice sooner." |
| 0:07–0:22 | **A. The flood** | Press **Play** at 10×. Hold on the camera wall and the funnel band as the event count climbs. | "A security control room gets thousands of signals. This is thirty minutes of real footage, door activity and phone location from one facility, replayed at ten times speed." |
| 0:22–0:32 | **B. Siloed view** | Switch the event stream to **Siloed alerts**, let it fill, then switch back to **All events**. | "On their own, every system pages constantly. Operators learn to ignore it, and real threats get buried." |
| 0:32–0:55 | **C. The incident** | Click the **Bus station** diamond on the timeline (hover shows the label). Play on until the bus-station incident tops the queue, then click it. **Zoom** on the queue and the score. | "Argus looks for agreement instead. At the bus station, a camera sees a bag left unattended, then carried off by someone else, while people's phones show a crowd forming in the same minute. Independent sources agree, so Argus ranks it first." |
| 0:55–1:12 | **D. Why this score** | Scroll the incident panel slowly: the brief, the recommended action, then **Why this score**. **Zoom** on the factor bars. | "The score shows its working: severity, confidence, how critical the place is, and a bonus because independent sources agree. Gemini writes the brief, but it can't create or hide an incident, and every line is checked against the evidence." |
| 1:12–1:25 | **E. Replay the moment** | Click the **camera** evidence row: the camera enlarges with the red box on the bag. Let it play 3–4 seconds. | "One click replays the moment, on the camera that saw it. Detection is YOLO11 with tracking, running on this laptop, with no training." |
| 1:25–1:33 | **F. Live** | Toggle **Live inference** for about 5 seconds; the fps counter is visible. Toggle back. | "And it runs live, at thirty frames a second, on a single laptop GPU." |
| 1:33–1:42 | **G. A human decides** | Switch the role to **Supervisor**, press **Escalate**. | "A person makes every call, and every call goes into a tamper-evident log." |
| 1:42–1:50 | **H. Any footage** | Header: **Analyse a video** → open the finished bus-station analysis; play 3 seconds with boxes on. | "Any clip can be uploaded and analysed the same way." |
| 1:50–2:00 | **Results card** | "4 of 5 staged incidents caught · 0 false incidents · 1,242 events → 3 incidents · 30 fps live" · small line: "MEVA dataset, Kitware / IARPA. Incidents staged by actors." | "On real footage, Argus caught four of five staged incidents with zero false incidents. We don't watch more. We notice sooner." |

**Check before recording shot C:** the bus-station incident is now titled **"Possible theft: unattended object taken"**
(its evidence holds both the unattended bag and the bag changing hands, plus phones showing a crowd). If the evidence on
screen differs, adjust the shot C line to describe only what the evidence shows.

## 4. Honesty rules (the video is judged too)

- Say "real footage" and "staged incidents"; never "real crimes".
- Every number on screen and in the voice-over must match the measured results. No "95%" or other round-ups.
- Keep the dataset credit on the results card.
- Don't cut anything that makes the system look faster than it is. Speed-ramping the replay is fine; it already runs at 10×, and the voice-over says so.

## 5. If you're short on time

Drop shot H (the voice-over line goes with it) and give its 8 seconds to shot C. Shots A, C, D and E and the results
card are the essential ones.
