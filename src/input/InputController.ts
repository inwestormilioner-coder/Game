/** A tap vs. a real drag-and-release on the attack joystick (InputController.consumeAttack). */
export type AttackRelease = 'tap' | 'aimed';

/**
 * Touch-first virtual joystick + attack button. Falls back to mouse drag
 * (left button) so the controls are also testable on desktop/in a headless
 * browser without a touchscreen.
 */
export class InputController {
  moveX = 0;
  moveY = 0;
  loadoutSwitchRequested = false;

  /** True for every frame the attack joystick is held down — Game.ts reads this to
   * show/hide the ground range+cone reticle (GDD Section 28 aimed-attack joystick). */
  aiming = false;
  /** Normalized screen-space drag vector of the attack joystick, same convention as
   * moveX/moveY (Game.ts negates both axes the same way to get a world direction). */
  aimX = 0;
  aimY = 0;

  private zone: HTMLElement;
  private base: HTMLElement;
  private stick: HTMLElement;
  private attackBtn: HTMLElement;
  private attackAimDot: HTMLElement;
  private abilityButtons: HTMLElement[];
  private loadoutBtn: HTMLElement;
  private abilityRequested = [false, false, false, false, false];

  private dragging = false;
  private pointerId: number | null = null;
  private originX = 0;
  private originY = 0;
  private readonly radius = 38;

  private attackPointerId: number | null = null;
  private attackOriginX = 0;
  private attackOriginY = 0;
  private attackMaxDist = 0;
  private pendingAttackRelease: AttackRelease | null = null;
  private readonly attackAimRadius = 60;
  /** A drag shorter than this (px) counts as a plain tap — attacks the auto-picked
   * target exactly like before, rather than requiring a deliberate aim. */
  private readonly tapThresholdPx = 12;

  constructor(root: HTMLElement) {
    this.zone = root.querySelector('#joystick-zone')!;
    this.base = root.querySelector('#joystick-base')!;
    this.stick = root.querySelector('#joystick-stick')!;
    this.attackBtn = root.querySelector('#attack-btn')!;
    this.attackAimDot = root.querySelector('#attack-aim-dot')!;
    this.abilityButtons = Array.from(root.querySelectorAll('.ability-btn'));
    this.loadoutBtn = root.querySelector('#loadout-switch')!;

    this.zone.addEventListener('pointerdown', this.onPointerDown);
    window.addEventListener('pointermove', this.onPointerMove);
    window.addEventListener('pointerup', this.onPointerUp);
    window.addEventListener('pointercancel', this.onPointerUp);

    this.attackBtn.addEventListener('pointerdown', this.onAttackPointerDown);
    window.addEventListener('pointermove', this.onAttackPointerMove);
    window.addEventListener('pointerup', this.onAttackPointerUp);
    window.addEventListener('pointercancel', this.onAttackPointerUp);

    this.abilityButtons.forEach((btn, slot) => {
      btn.addEventListener('pointerdown', (e) => {
        e.preventDefault();
        this.abilityRequested[slot] = true;
      });
    });

    this.loadoutBtn.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      this.loadoutSwitchRequested = true;
    });

    // keyboard fallback for quick iteration on desktop
    const keys = new Set<string>();
    window.addEventListener('keydown', (e) => {
      keys.add(e.key.toLowerCase());
      if (e.key === ' ') this.pendingAttackRelease = 'tap';
      this.updateFromKeys(keys);
    });
    window.addEventListener('keyup', (e) => {
      keys.delete(e.key.toLowerCase());
      this.updateFromKeys(keys);
    });
  }

  private updateFromKeys(keys: Set<string>) {
    if (this.dragging) return;
    let x = 0;
    let y = 0;
    if (keys.has('a') || keys.has('arrowleft')) x -= 1;
    if (keys.has('d') || keys.has('arrowright')) x += 1;
    if (keys.has('w') || keys.has('arrowup')) y -= 1;
    if (keys.has('s') || keys.has('arrowdown')) y += 1;
    this.moveX = x;
    this.moveY = y;
  }

  private onPointerDown = (e: PointerEvent) => {
    if (this.pointerId !== null) return;
    this.pointerId = e.pointerId;
    this.dragging = true;
    // The base is a fixed HUD element (always visible, MOBA-style) — the
    // stick reacts relative to its center, not to where the touch landed.
    const rect = this.base.getBoundingClientRect();
    this.originX = rect.left + rect.width / 2;
    this.originY = rect.top + rect.height / 2;
    this.updateStick(e.clientX, e.clientY);
  };

  private onPointerMove = (e: PointerEvent) => {
    if (!this.dragging || e.pointerId !== this.pointerId) return;
    this.updateStick(e.clientX, e.clientY);
  };

  private onPointerUp = (e: PointerEvent) => {
    if (e.pointerId !== this.pointerId) return;
    this.dragging = false;
    this.pointerId = null;
    this.stick.style.transform = 'translate(-50%, -50%)';
    this.moveX = 0;
    this.moveY = 0;
  };

  private updateStick(clientX: number, clientY: number) {
    const dx = clientX - this.originX;
    const dy = clientY - this.originY;
    const dist = Math.min(Math.hypot(dx, dy), this.radius);
    const angle = Math.atan2(dy, dx);
    const sx = Math.cos(angle) * dist;
    const sy = Math.sin(angle) * dist;
    this.stick.style.transform = `translate(calc(-50% + ${sx}px), calc(-50% + ${sy}px))`;
    this.moveX = sx / this.radius;
    this.moveY = sy / this.radius;
  }

  private onAttackPointerDown = (e: PointerEvent) => {
    if (this.attackPointerId !== null) return;
    e.preventDefault();
    this.attackPointerId = e.pointerId;
    this.aiming = true;
    this.attackMaxDist = 0;
    const rect = this.attackBtn.getBoundingClientRect();
    this.attackOriginX = rect.left + rect.width / 2;
    this.attackOriginY = rect.top + rect.height / 2;
    this.updateAttackAim(e.clientX, e.clientY);
  };

  private onAttackPointerMove = (e: PointerEvent) => {
    if (!this.aiming || e.pointerId !== this.attackPointerId) return;
    this.updateAttackAim(e.clientX, e.clientY);
  };

  private onAttackPointerUp = (e: PointerEvent) => {
    if (e.pointerId !== this.attackPointerId) return;
    this.aiming = false;
    this.attackPointerId = null;
    this.attackAimDot.style.transform = 'translate(-50%, -50%)';
    this.pendingAttackRelease = this.attackMaxDist > this.tapThresholdPx ? 'aimed' : 'tap';
  };

  private updateAttackAim(clientX: number, clientY: number) {
    const dx = clientX - this.attackOriginX;
    const dy = clientY - this.attackOriginY;
    const dist = Math.hypot(dx, dy);
    this.attackMaxDist = Math.max(this.attackMaxDist, dist);
    const clamped = Math.min(dist, this.attackAimRadius);
    const angle = Math.atan2(dy, dx);
    const sx = Math.cos(angle) * clamped;
    const sy = Math.sin(angle) * clamped;
    this.attackAimDot.style.transform = `translate(calc(-50% + ${sx}px), calc(-50% + ${sy}px))`;
    // Keep the last real drag direction even past the button's own radius, not clamped to
    // it — the ground reticle (Game.ts) is a separate, larger radius than this little dot.
    if (dist > 0.001) {
      this.aimX = dx / dist;
      this.aimY = dy / dist;
    }
  }

  /** Call once per frame: null if nothing happened, else whether the attack button was
   * released as a quick 'tap' (attack the auto-picked target, exactly like before) or
   * released after a real 'aimed' drag (attack whatever's in the aimed direction instead —
   * Game.ts reads aimX/aimY and the `aiming` flag to know which and to draw the reticle). */
  consumeAttack(): AttackRelease | null {
    const v = this.pendingAttackRelease;
    this.pendingAttackRelease = null;
    return v;
  }

  /** The single action button is fully context-sensitive: "ATAK" on a monster, "SZUKAJ" on a
   * corpse, "Kop"/"Rąb"/"Łów" on a gathering node, "Rozmawiaj"/"Depozyt" on an NPC — one button
   * for every targetable thing, on purpose (Game.ts.updateTargets picks the nearest one). */
  setActionLabel(text: string): void {
    this.attackBtn.querySelector('.attack-label')!.textContent = text;
  }

  consumeAbility(slot: number): boolean {
    const v = this.abilityRequested[slot];
    this.abilityRequested[slot] = false;
    return v;
  }

  consumeLoadoutSwitch(): boolean {
    const v = this.loadoutSwitchRequested;
    this.loadoutSwitchRequested = false;
    return v;
  }

  /** Icon/cooldown text and disabled look for one ability slot; called every frame from Game.ts. */
  setAbilityDisplay(slot: number, icon: string, cooldownText: string, disabled: boolean): void {
    const btn = this.abilityButtons[slot];
    if (!btn) return;
    btn.querySelector('.ability-icon')!.textContent = icon;
    btn.querySelector('.ability-cd')!.textContent = cooldownText;
    btn.classList.toggle('on-cooldown', disabled);
  }

  setLoadoutLabel(text: string): void {
    this.loadoutBtn.textContent = text;
  }
}
