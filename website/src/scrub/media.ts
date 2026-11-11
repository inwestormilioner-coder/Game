import type { SceneMedia } from './types.ts';

/**
 * Video scrubbing for scenes that ship real footage.
 *
 * The video is placed behind the stage content and its `currentTime`
 * follows scroll progress. If the file cannot be loaded the element is
 * removed and the stage is marked `data-media="fallback"`, so the canvas
 * backdrop remains the visual. No scene in this build has footage yet:
 * `scenes.ts` leaves `media` undefined everywhere.
 */
export function attachSceneMedia(stage: HTMLElement, media: SceneMedia, progress: () => number) {
  const video = document.createElement('video');
  video.className = 'stage-media';
  video.muted = true;
  video.playsInline = true;
  video.preload = 'auto';
  video.setAttribute('aria-hidden', 'true');
  if (media.poster) video.poster = media.poster;

  const source = document.createElement('source');
  source.src = media.src;
  if (media.type) source.type = media.type;
  video.append(source);

  let ready = false;
  let pending = false;
  const seek = () => {
    pending = false;
    if (!ready || !video.duration) return;
    const target = progress() * (video.duration - 0.05);
    if (Math.abs(video.currentTime - target) > 1 / 60) video.currentTime = target;
  };
  const queue = () => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(seek);
  };

  const fail = () => {
    video.remove();
    stage.dataset.media = 'fallback';
    removeEventListener('scroll', queue);
  };

  video.addEventListener('loadedmetadata', () => {
    ready = true;
    stage.dataset.media = 'video';
    queue();
  });
  source.addEventListener('error', fail);
  video.addEventListener('error', fail);
  addEventListener('scroll', queue, { passive: true });

  stage.dataset.media = 'loading';
  stage.prepend(video);
}
