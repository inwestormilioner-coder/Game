import './styles/tokens.css';
import './styles/base.css';
import './styles/chrome.css';
import './styles/chapters.css';

import { ScrollScrub } from './scrub/ScrollScrub.ts';
import { SCENES } from './scrub/scenes.ts';
import { Backdrop } from './backdrop/Backdrop.ts';
import { initNav } from './ui/nav.ts';
import { initCta } from './ui/cta.ts';

const root = document.documentElement;

/** Lifts the opening curtain once fonts are ready (or after a short cap). */
function reveal() {
  const fonts = document.fonts?.ready ?? Promise.resolve();
  const cap = new Promise((r) => setTimeout(r, 2200));
  Promise.race([fonts, cap]).then(() =>
    requestAnimationFrame(() => {
      root.classList.remove('is-loading');
      root.classList.add('is-ready');
    }),
  );
}

function boot() {
  initCta();
  const onFrame = initNav();
  const scrub = new ScrollScrub(SCENES);
  const backdrop = Backdrop.create(document.querySelector<HTMLCanvasElement>('.backdrop'));
  scrub.subscribe((frame) => {
    onFrame(frame);
    backdrop?.update(frame);
  });
  document.querySelectorAll('[data-year]').forEach((el) => (el.textContent = String(new Date().getFullYear())));
  reveal();
}

try {
  boot();
} catch (err) {
  // Never leave visitors behind the curtain: fall back to the static page.
  console.error('[ntg] boot failed', err);
  root.classList.remove('is-loading', 'scrub');
  root.classList.add('is-ready', 'no-canvas');
}
