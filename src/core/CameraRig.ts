import * as THREE from 'three';

/**
 * Touch camera controls (GDD Section 28): pinch to zoom, drag on empty
 * screen space to orbit around the player. Listens directly on the canvas
 * element, so it never sees pointers that land on HUD controls (joystick,
 * attack button, ability ring) — those are separate DOM elements stacked
 * above the canvas and swallow their own pointer events.
 */
const MIN_DISTANCE = 6;
const MAX_DISTANCE = 15;
const DEFAULT_DISTANCE = 9.55;
const ELEVATION = 0.749; // radians; fixed camera pitch, matches the original static offset
const ROTATE_SENSITIVITY = 0.006; // radians of yaw per pixel of horizontal drag
const ZOOM_SENSITIVITY = 0.02; // world units of distance per pixel of pinch delta
const WHEEL_SENSITIVITY = 0.01; // desktop-testing fallback

function clamp(v: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, v));
}

export class CameraRig {
  distance = DEFAULT_DISTANCE;
  yaw = 0;

  private pointers = new Map<number, { x: number; y: number }>();
  private dragPointerId: number | null = null;
  private lastDragX = 0;
  private lastPinchDist: number | null = null;

  constructor(el: HTMLElement) {
    el.addEventListener('pointerdown', this.onPointerDown);
    window.addEventListener('pointermove', this.onPointerMove);
    window.addEventListener('pointerup', this.onPointerUp);
    window.addEventListener('pointercancel', this.onPointerUp);
    el.addEventListener('wheel', this.onWheel, { passive: false });
  }

  /** World-space offset to add to the player's position to place the camera. */
  getOffset(): THREE.Vector3 {
    const horizontal = this.distance * Math.cos(ELEVATION);
    const height = this.distance * Math.sin(ELEVATION);
    return new THREE.Vector3(
      Math.sin(this.yaw) * horizontal,
      height,
      -Math.cos(this.yaw) * horizontal,
    );
  }

  private onPointerDown = (e: PointerEvent): void => {
    this.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });

    if (this.pointers.size === 1) {
      this.dragPointerId = e.pointerId;
      this.lastDragX = e.clientX;
    } else if (this.pointers.size === 2) {
      this.dragPointerId = null;
      this.lastPinchDist = this.pinchDistance();
    }
  };

  private onPointerMove = (e: PointerEvent): void => {
    if (!this.pointers.has(e.pointerId)) return;
    this.pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });

    if (this.pointers.size >= 2) {
      const dist = this.pinchDistance();
      if (this.lastPinchDist !== null && dist !== null) {
        this.distance = clamp(
          this.distance - (dist - this.lastPinchDist) * ZOOM_SENSITIVITY,
          MIN_DISTANCE,
          MAX_DISTANCE,
        );
      }
      this.lastPinchDist = dist;
      return;
    }

    if (this.dragPointerId === e.pointerId) {
      const dx = e.clientX - this.lastDragX;
      this.yaw -= dx * ROTATE_SENSITIVITY;
      this.lastDragX = e.clientX;
    }
  };

  private onPointerUp = (e: PointerEvent): void => {
    this.pointers.delete(e.pointerId);
    if (e.pointerId === this.dragPointerId) this.dragPointerId = null;
    if (this.pointers.size < 2) this.lastPinchDist = null;

    // if a pinch just ended and one finger is still down, resume orbit with it
    if (this.pointers.size === 1 && this.dragPointerId === null) {
      const [[id, pos]] = this.pointers;
      this.dragPointerId = id;
      this.lastDragX = pos.x;
    }
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
