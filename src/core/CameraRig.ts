import * as THREE from 'three';

/**
 * Touch camera zoom (GDD Section 28): the camera angle is fixed for every
 * player — no player-controlled rotation — so everyone reads the map, the
 * minimap and incoming threats from the same orientation and sees the same
 * amount of the world around them. Pinch (or mouse wheel, for desktop
 * testing) is the only adjustable axis. Listens directly on the canvas
 * element, so it never sees pointers that land on HUD controls (joystick,
 * attack button, ability ring) — those are separate DOM elements stacked
 * above the canvas and swallow their own pointer events.
 */
const MIN_DISTANCE = 6;
const MAX_DISTANCE = 15;
const DEFAULT_DISTANCE = 9.55;
const ELEVATION = 0.749; // radians; fixed camera pitch, matches the original static offset
const ZOOM_SENSITIVITY = 0.02; // world units of distance per pixel of pinch delta
const WHEEL_SENSITIVITY = 0.01; // desktop-testing fallback

function clamp(v: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, v));
}

export class CameraRig {
  distance = DEFAULT_DISTANCE;

  private pointers = new Map<number, { x: number; y: number }>();
  private lastPinchDist: number | null = null;

  constructor(el: HTMLElement) {
    el.addEventListener('pointerdown', this.onPointerDown);
    window.addEventListener('pointermove', this.onPointerMove);
    window.addEventListener('pointerup', this.onPointerUp);
    window.addEventListener('pointercancel', this.onPointerUp);
    el.addEventListener('wheel', this.onWheel, { passive: false });
  }

  /** World-space offset to add to the player's position to place the camera. Angle never changes. */
  getOffset(): THREE.Vector3 {
    const horizontal = this.distance * Math.cos(ELEVATION);
    const height = this.distance * Math.sin(ELEVATION);
    return new THREE.Vector3(0, height, -horizontal);
  }

  private onPointerDown = (e: PointerEvent): void => {
    this.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (this.pointers.size === 2) this.lastPinchDist = this.pinchDistance();
  };

  private onPointerMove = (e: PointerEvent): void => {
    if (!this.pointers.has(e.pointerId)) return;
    this.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (this.pointers.size < 2) return;

    const dist = this.pinchDistance();
    if (this.lastPinchDist !== null && dist !== null) {
      this.distance = clamp(
        this.distance - (dist - this.lastPinchDist) * ZOOM_SENSITIVITY,
        MIN_DISTANCE,
        MAX_DISTANCE,
      );
    }
    this.lastPinchDist = dist;
  };

  private onPointerUp = (e: PointerEvent): void => {
    this.pointers.delete(e.pointerId);
    if (this.pointers.size < 2) this.lastPinchDist = null;
  };

  private onWheel = (e: WheelEvent): void => {
    e.preventDefault();
    this.distance = clamp(this.distance + e.deltaY * WHEEL_SENSITIVITY, MIN_DISTANCE, MAX_DISTANCE);
  };

  private pinchDistance(): number | null {
    if (this.pointers.size < 2) return null;
    const [a, b] = [...this.pointers.values()];
    return Math.hypot(a.x - b.x, a.y - b.y);
  }
}
