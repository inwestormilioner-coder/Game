/**
 * Scene configuration for the scroll-scrub engine.
 *
 * A scene is a tall <section data-scene="id"> containing one sticky
 * `.stage`. While the stage is pinned, scrolling through the section
 * drives a progress value from 0 to 1 that the engine writes to CSS
 * (`--p`, plus `--in` / `--out` / `--v` on `[data-in]`/`[data-out]`
 * elements) and hands to subscribers such as the canvas backdrop.
 */
export interface SceneConfig {
  /** Matches the `data-scene` attribute of the section. */
  id: string;
  /** Section height in viewport heights, phones first, wide screens optional. */
  length: { base: number; wide?: number };
  /**
   * Optional video to scrub with scroll (frame = progress × duration).
   * Leave undefined when no footage exists: the scene then relies on the
   * canvas backdrop. Only reference files that really ship with the site.
   */
  media?: SceneMedia;
}

export interface SceneMedia {
  /** URL of an all-intra or short-GOP encoded video, e.g. imported from src/assets. */
  src: string;
  poster?: string;
  type?: string;
}

export interface SceneState {
  id: string;
  index: number;
  el: HTMLElement;
  stage: HTMLElement;
  /** 0 → 1 while the stage is pinned. */
  progress: number;
  /** Share of the viewport the stage currently covers, 0 → 1. */
  visibility: number;
}

export interface ScrubFrame {
  scenes: readonly SceneState[];
  /** Index of the scene covering most of the viewport. */
  active: number;
  /** Whole-document scroll progress, 0 → 1. */
  overall: number;
  /** True when scrubbing is off (reduced motion or unsupported). */
  static: boolean;
}

export type ScrubListener = (frame: ScrubFrame) => void;
