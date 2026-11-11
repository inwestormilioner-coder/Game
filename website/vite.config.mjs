// Vite config for the Ninja Trading Group marketing website.
// The website is its own Vite root so it builds and deploys independently
// of the game prototype that lives at the repository root.
import { defineConfig, loadEnv } from 'vite';

/**
 * Canonical and social-share URLs must be absolute. When VITE_SITE_URL is
 * set (website/.env) they are written into the page at build time; when it
 * is empty the page keeps the relative share image and omits the rest.
 */
function siteUrlMeta(siteUrl) {
  const origin = siteUrl.replace(/\/+$/, '');
  return {
    name: 'ntg-site-url-meta',
    transformIndexHtml(html) {
      if (!origin) return html;
      return {
        html: html.replaceAll('content="/og.jpg"', `content="${origin}/og.jpg"`),
        tags: [
          { tag: 'link', attrs: { rel: 'canonical', href: `${origin}/` }, injectTo: 'head' },
          { tag: 'meta', attrs: { property: 'og:url', content: `${origin}/` }, injectTo: 'head' },
        ],
      };
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, import.meta.dirname, 'VITE_');
  return {
    root: import.meta.dirname,
    publicDir: 'public',
    envDir: import.meta.dirname,
    plugins: [siteUrlMeta(env.VITE_SITE_URL ?? '')],
    build: {
      outDir: '../dist-website',
      emptyOutDir: true,
      assetsInlineLimit: 0,
    },
  };
});
