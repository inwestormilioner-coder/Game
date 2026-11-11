import { CONFIG } from '../config.ts';

/**
 * Wires every `[data-cta]` link to the configured destination.
 *
 * - With `VITE_CTA_URL` set: links open the community / app in a new tab.
 * - Without it: links lead to the final scene, and the final button
 *   (`data-cta="final"`) explains that access opens soon instead of
 *   pointing nowhere.
 */
export function initCta() {
  const links = document.querySelectorAll<HTMLAnchorElement>('a[data-cta]');
  const note = document.querySelector<HTMLElement>('[data-cta-note]');

  for (const a of links) {
    if (CONFIG.ctaUrl) {
      a.href = CONFIG.ctaUrl;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      continue;
    }
    if (a.dataset.cta === 'final') {
      a.removeAttribute('href');
      a.setAttribute('role', 'button');
      a.setAttribute('tabindex', '0');
      a.setAttribute('aria-describedby', 'cta-note');
      const reveal = () => {
        if (note) note.hidden = false;
      };
      a.addEventListener('click', reveal);
      a.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          reveal();
        }
      });
    } else {
      a.href = CONFIG.ctaFallbackHash;
    }
  }
}
