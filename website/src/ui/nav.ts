import type { ScrubFrame } from '../scrub/types.ts';

/**
 * Masthead behaviour (hide on scroll down, reveal on scroll up), the
 * full-screen chapter menu, and the chapter indicator.
 */
export function initNav() {
  const root = document.documentElement;
  const head = document.querySelector<HTMLElement>('.masthead');
  const toggle = document.querySelector<HTMLButtonElement>('.menu-toggle');
  const menu = document.querySelector<HTMLElement>('#menu');
  const rail = [...document.querySelectorAll<HTMLAnchorElement>('[data-rail] a')];
  const menuLinks = menu ? [...menu.querySelectorAll<HTMLAnchorElement>('a')] : [];
  const bar = document.querySelector<HTMLElement>('.progress-line');
  const label = document.querySelector<HTMLElement>('[data-chapter-label]');

  let lastY = scrollY;
  let open = false;

  const setOpen = (next: boolean) => {
    if (!toggle || !menu) return;
    open = next;
    toggle.setAttribute('aria-expanded', String(next));
    toggle.setAttribute('aria-label', next ? 'Close menu' : 'Open menu');
    menu.hidden = false;
    root.classList.toggle('menu-open', next);
    if (next) {
      requestAnimationFrame(() => menu.classList.add('is-open'));
      menuLinks[0]?.focus({ preventScroll: true });
    } else {
      menu.classList.remove('is-open');
      toggle.focus({ preventScroll: true });
      // Hide after the fade; the timer covers browsers that skip transitionend.
      setTimeout(() => !open && (menu.hidden = true), 600);
    }
  };

  toggle?.addEventListener('click', () => setOpen(!open));
  menu?.addEventListener('transitionend', (e) => {
    if (!open && e.target === menu) menu.hidden = true;
  });
  menuLinks.forEach((a) => a.addEventListener('click', () => open && setOpen(false)));
  addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && open) setOpen(false);
    if (e.key === 'Tab' && open && menu && toggle) {
      const items = [toggle, ...menuLinks];
      const i = items.indexOf(document.activeElement as HTMLAnchorElement);
      if (e.shiftKey && i <= 0) {
        e.preventDefault();
        items[items.length - 1].focus();
      } else if (!e.shiftKey && i === items.length - 1) {
        e.preventDefault();
        items[0].focus();
      }
    }
  });

  addEventListener(
    'scroll',
    () => {
      const y = scrollY;
      if (!open && head) head.classList.toggle('is-hidden', y > lastY && y > 120);
      head?.classList.toggle('is-solid', y > 40);
      lastY = y;
    },
    { passive: true },
  );

  let current = -1;
  return (frame: ScrubFrame) => {
    if (bar) bar.style.transform = `scaleX(${frame.overall.toFixed(4)})`;
    if (frame.active === current) return;
    current = frame.active;
    rail.forEach((a, i) => (i === current ? a.setAttribute('aria-current', 'step') : a.removeAttribute('aria-current')));
    menuLinks.forEach((a, i) => (i === current ? a.setAttribute('aria-current', 'step') : a.removeAttribute('aria-current')));
    if (label) label.textContent = rail[current]?.dataset.name ?? '';
  };
}
