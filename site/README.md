# Argus project website

One static page (`index.html` + `assets/` + `fonts/`), no build step and no internet needed: the fonts are
bundled. It is not deployed anywhere; it runs on the demo laptop.

## Open it on the demo laptop

- With the demo running (`scripts\run_demo.ps1`): **http://localhost:8000/site/** (the backend serves it
  next to the console at http://localhost:8000).
- Without the demo: double-click `site\index.html`.

## Before showing it

- Replace `assets/console-preview.jpg` with a real screenshot of the console on the demo laptop (full replay
  loaded, an incident open): `Win + Shift + S`, saved at about 1536 px wide. Then remove "This preview uses the
  console's sample-data mode" from the caption under it in `index.html`.
- Check the team roles in the Team section.

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
> 1,242 raw events reduced to 3 explained incidents. Detection runs live at 30 fps on one laptop GPU, every score
> shows its working, and you can upload any video to analyse it on the spot.
>
> Code: https://github.com/Argonyx-26/T14_Lordofpings
>
> With [teammates] · @Studio1 · @RV University SoCSE · @Viksha · @ECell RVU · @IEEE RVU
> #hackathon #computervision #security #ai
