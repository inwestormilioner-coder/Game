export interface Beat {
  /** Eased 0→1 as the beat enters. */
  in: number;
  /** Eased 0→1 as the beat leaves. */
  out: number;
  /** Raw entry range start/end and exit start (fractions of scene progress). */
  start: number;
  end: number;
  exit: number;
}

export interface DrawEnv {
  ctx: CanvasRenderingContext2D;
  w: number;
  h: number;
  /** Seconds since start; frozen when motion is reduced. */
  t: number;
  /** Seconds since the previous frame; 0 when motion is reduced. */
  dt: number;
  /** Scene progress 0→1. */
  p: number;
  wide: boolean;
  /** True when scroll animation is off (reduced motion). */
  still: boolean;
  stage: HTMLElement;
  beats: Beat[];
}

export interface ChapterRenderer {
  /** Called when the canvas size changes. */
  resize?(w: number, h: number, wide: boolean): void;
  draw(env: DrawEnv): void;
}
