/**
 * Site-wide configuration. The CTA destination is set in one place:
 * `VITE_CTA_URL` in website/.env (a Telegram invite or the app URL).
 */
function safeUrl(raw: string | undefined): string | null {
  const value = raw?.trim();
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' || url.protocol === 'http:' || url.protocol === 'tg:' ? url.href : null;
  } catch {
    return null;
  }
}

export const CONFIG = {
  brand: 'Ninja Trading Group',
  ctaLabel: 'Enter Ninja Trading',
  /** null until a destination is configured. */
  ctaUrl: safeUrl(import.meta.env.VITE_CTA_URL),
  /** Fallback target for CTAs when no destination is configured yet. */
  ctaFallbackHash: '#enter',
} as const;
