# Ninja Trading Group — website

Mobile-first marketing site for Ninja Trading Group, told as six scroll-driven
chapters: Introduction, Philosophy, The Market, Community, Intelligence and
the final invitation. It is a presentation site. The trading tools described in
chapter 05 live in the separate Ninja Trading application.

The site is its own Vite root inside this repository, separate from the game
prototype at the repository root.

```bash
npm install
npm run dev:website        # local dev server
npm run typecheck:website  # TypeScript check
npm run build:website      # production build → dist-website/
npm run preview:website    # serve the production build
```

## Configuration — `website/.env`

| Variable        | Purpose |
| --------------- | ------- |
| `VITE_CTA_URL`  | Destination of every “Enter Ninja Trading” button (Telegram invite or app URL). While empty, buttons lead to the final chapter and the final button says access opens soon. |
| `VITE_SITE_URL` | Public origin, e.g. `https://ninjatrading.group`. When set, the build adds the canonical link, `og:url`, and absolute share-image URLs. |

## How it is built

```
src/
  main.ts               boot: CTA wiring, navigation, scroll engine, backdrop, curtain
  config.ts             CTA destination and brand constants
  scrub/
    ScrollScrub.ts      scroll-scrub engine (pinned stages → progress → CSS vars)
    scenes.ts           chapter list and pinned lengths
    media.ts            optional video scrubbing per scene (unused until footage exists)
    types.ts
  backdrop/
    Backdrop.ts         one fixed canvas, chapters cross-dissolve by visibility
    chapters.ts         one renderer per chapter
  ui/nav.ts, ui/cta.ts  masthead, menu, chapter rail, CTA behaviour
  styles/               tokens, base, chrome (masthead/menu/footer), chapters
```

**Scroll-scrub.** Each chapter is a tall `<section data-scene>` with a sticky
`.stage`. `ScrollScrub` turns the pinned travel into progress `0 → 1` (`--p`).
Elements opt in with `data-in="start end"` / `data-out="start end"` and receive
`--in`, `--out` and `--v`. Classes such as `fx-lift`, `fx-wipe` and `fx-blur`
in `chapters.css` turn those values into motion. Elements marked `data-beat`
are also passed to the chapter's canvas renderer, so text and visuals stay in
sync from a single source.

**Video.** No footage ships with the site, so every chapter is drawn by the
canvas renderer. To scrub real video in a chapter, add the file to
`src/assets`, import it in `scenes.ts` and set `media: { src, type }`. If the
file fails to load, the stage falls back to the canvas.

**Fallbacks.** With `prefers-reduced-motion: reduce`, chapters are not pinned,
all content is shown statically and the backdrop stops animating. Without
canvas support, each chapter gets CSS lighting instead. The opening curtain
lifts on its own after a few seconds even if scripts fail.
