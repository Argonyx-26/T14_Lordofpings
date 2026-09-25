# Argus project website

Static pages (`index.html`, `judges.html`, `motion.js`, `assets/`, `fonts/`), no build step and no internet needed:
the fonts are bundled.

**Live:** https://argus-lordofpings.vercel.app (with the judges' page at `/judges.html` and the console's offline
demo at `/console/`), published with `scripts/deploy_site.sh`, which also adds Raah analytics. The copies served on
the demo laptop never load analytics or anything else from the internet.

## Open it on the demo laptop

- With the demo running (`scripts\run_demo.ps1`): **http://localhost:8000/site/** (the backend serves it
  next to the console at http://localhost:8000).
- Without the demo: double-click `site\index.html`.

## Before showing it

- `assets/console-preview.jpg` is a real capture of the console (done). Retake it if the console changes a lot.
- After changing anything under `site/`, run `scripts/deploy_site.sh` so the live site matches.

## LinkedIn post (optional draft)

Tag: **Studio1**, **School of Computer Science and Engineering, RV University**, **Viksha – The Coding Club**,
**ECell, RV University**, **IEEE RVU**, and your teammates.

> We built Argus in 24 hours at #ARGONYX26.
>
> Security control rooms don't miss threats for lack of cameras; they miss them because every system raises its own
> alarms on its own screen. Argus fuses camera analytics, door activity and device location, and only raises an
> incident when independent signals agree about the same place and the same minute.
>
> Measured on real multi-camera footage (the MEVA dataset): 4 of 5 staged incidents caught, 0 false incidents, and
> 314 raw events reduced to 3 explained incidents. Detection runs live at 30 fps on one laptop GPU, every score
> shows its working, and you can upload any video to analyse it on the spot.
>
> Code: https://github.com/Argonyx-26/T14_Lordofpings
>
> With [teammates] · @Studio1 · @RV University SoCSE · @Viksha · @ECell RVU · @IEEE RVU
> #hackathon #computervision #security #ai
