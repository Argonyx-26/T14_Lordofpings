# Argus project website

One static page (`index.html` + `assets/`), no build step. It's the public showcase for the ARGONYX '26
bonus points: hosted site + Raah analytics + LinkedIn post.

## 1. Deploy (5 minutes, pick one)

**Vercel:** vercel.com → Add New → Project → import `Argonyx-26/T14_Lordofpings` → **Root Directory: `site`** →
Framework preset: **Other** → Deploy. You get `https://<name>.vercel.app`.

**Cloudflare Pages:** dash.cloudflare.com → Workers & Pages → Create → Pages → connect the repo →
Build command: *(empty)* → **Build output directory: `site`** → Deploy.

Every push to `main` redeploys automatically.

## 2. Turn on Raah analytics

1. Sign up at https://raah.dev, create a project with the domain Vercel/Cloudflare gave you.
2. In `site/index.html`, replace `RAAH_PROJECT_ID` with the project ID and `YOUR-DOMAIN` with that domain
   (the `<script ... src="https://t.raah.dev/script.js">` line in `<head>`).
3. If Raah's dashboard offers an official badge snippet, paste it in place of the "Analytics by Raah" link in
   the footer.
4. Also make `og:image` an absolute URL (`https://<your-domain>/assets/detections-bus-station.jpg`) so the
   LinkedIn post shows the preview image. Commit and push; the site redeploys.

## 3. Before posting

- Replace `assets/console-preview.jpg` with a real screenshot of the console on the demo laptop (full replay
  loaded, an incident open), `Win + Shift + S`, saved at about 1536 px wide. Then remove "This preview uses
  the console's sample-data mode" from the caption under it.
- Check the team roles in the Team section.

## 4. LinkedIn post (draft)

Tag: **Studio1** (Raah's LinkedIn), **School of Computer Science and Engineering, RV University**,
**Viksha – The Coding Club**, **ECell, RV University**, **IEEE RVU**, and your teammates.

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
> Project: https://<your-domain>
> Code: https://github.com/Argonyx-26/T14_Lordofpings
>
> With [teammates] · @Studio1 · @RV University SoCSE · @Viksha · @ECell RVU · @IEEE RVU
> #hackathon #computervision #security #ai
