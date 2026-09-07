/**
 * Touch-first virtual joystick + attack button. Falls back to mouse drag
 * (left button) so the controls are also testable on desktop/in a headless
 * browser without a touchscreen.
 */
export class InputController {
  moveX = 0;
  moveY = 0;
  attackRequested = false;
  loadoutSwitchRequested = false;

  private zone: HTMLElement;
  private base: HTMLElement;
  private stick: HTMLElement;
  private attackBtn: HTMLElement;
  private abilityButtons: HTMLElement[];
  private loadoutBtn: HTMLElement;
  private abilityRequested = [false, false, false, false, false];

  private dragging = false;
  private pointerId: number | null = null;
  private originX = 0;
  private originY = 0;
  private readonly radius = 38;

  constructor(root: HTMLElement) {
    this.zone = root.querySelector('#joystick-zone')!;
    this.base = root.querySelector('#joystick-base')!;
    this.stick = root.querySelector('#joystick-stick')!;
    this.attackBtn = root.querySelector('#attack-btn')!;
    this.abilityButtons = Array.from(root.querySelectorAll('.ability-btn'));
    this.loadoutBtn = root.querySelector('#loadout-switch')!;

    this.zone.addEventListener('pointerdown', this.onPointerDown);
    window.addEventListener('pointermove', this.onPointerMove);
    window.addEventListener('pointerup', this.onPointerUp);
    window.addEventListener('pointercancel', this.onPointerUp);

    this.attackBtn.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      this.attackRequested = true;
    });

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
      if (e.key === ' ') this.attackRequested = true;
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

  /** Call once per frame after the game has consumed the attack request. */
  consumeAttack(): boolean {
    const v = this.attackRequested;
    this.attackRequested = false;
    return v;
  }

  /** The single action button is fully context-sensitive: "ATAK" on a monster, "SZUKAJ" on a
   * corpse, "Kop"/"Rąb"/"Łów" on a gathering node, "Rozmawiaj"/"Depozyt" on an NPC — one button
   * for every targetable thing, on purpose (Game.ts.updateTargets picks the nearest one). */
  setActionLabel(text: string): void {
    this.attackBtn.textContent = text;
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
