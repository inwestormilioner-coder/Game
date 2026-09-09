import { CLASSES, type Stats } from '../types';

function formatMinSec(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = Math.floor(totalSeconds % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

// Resource-bar color per class (Section 28 HUD art): Mana gets the blue variant, every
// other resource (Fervor, Focus, Momentum) shares the green "energy" variant. Rage/yellow
// is prepared in the art but unused until a class/mechanic actually needs it.
const RESOURCE_COLOR_CLASS: Record<string, string> = { Mana: 'mana' };
function resourceColorClass(resourceName: string): string {
  return RESOURCE_COLOR_CLASS[resourceName] ?? 'energy';
}

export class HUD {
  private hpFill: HTMLElement;
  private resourceFill: HTMLElement;
  private resourceLabel: HTMLElement;
  private xpFill: HTMLElement;
  private levelLabel: HTMLElement;
  private classLabel: HTMLElement;
  private skillLabel: HTMLElement;
  private capacityLabel: HTMLElement;
  private satietyIndicator: HTMLElement;
  private satietyLabel: HTMLElement;
  private poisonIndicator: HTMLElement;
  private poisonLabel: HTMLElement;
  private toast: HTMLElement;
  private flash: HTMLElement;
  private toastTimeout: number | undefined;

  constructor(root: HTMLElement) {
    this.hpFill = root.querySelector('#hp-fill')!;
    this.resourceFill = root.querySelector('#resource-fill')!;
    this.resourceLabel = root.querySelector('#resource-label')!;
    this.xpFill = root.querySelector('#xp-fill')!;
    this.levelLabel = root.querySelector('#level-label')!;
    this.classLabel = root.querySelector('#class-label')!;
    this.skillLabel = root.querySelector('#skill-label')!;
    this.capacityLabel = root.querySelector('#capacity-label')!;
    this.satietyIndicator = root.querySelector('#satiety-indicator')!;
    this.satietyLabel = root.querySelector('#satiety-label')!;
    this.poisonIndicator = root.querySelector('#poison-indicator')!;
    this.poisonLabel = root.querySelector('#poison-label')!;
    this.toast = root.querySelector('#toast')!;
    this.flash = root.querySelector('#level-up-flash')!;
  }

  update(
    stats: Stats,
    derived: { carriedWeight: number; maxResource: number; skillName: string; skillLevel: number },
  ): void {
    this.hpFill.style.width = `${(stats.hp / stats.maxHp) * 100}%`;
    this.resourceFill.style.width = `${(stats.resource / derived.maxResource) * 100}%`;
    this.resourceFill.classList.remove('energy', 'mana', 'rage');
    this.resourceFill.classList.add(resourceColorClass(stats.resourceName));
    this.resourceLabel.textContent = stats.resourceName;
    this.xpFill.style.width = `${(stats.exp / stats.expToNext) * 100}%`;
    this.levelLabel.textContent = `Lvl ${stats.level}`;
    this.classLabel.textContent = CLASSES[stats.classId].name;
    this.skillLabel.textContent = `${derived.skillName} ${derived.skillLevel}`;
    this.capacityLabel.textContent = `${derived.carriedWeight.toFixed(1)} / ${stats.maxCapacity}`;
    this.capacityLabel.parentElement!.classList.toggle('over-limit', derived.carriedWeight >= stats.maxCapacity);

    const fed = stats.satietySeconds > 0;
    this.satietyLabel.textContent = fed ? formatMinSec(stats.satietySeconds) : 'Głodny';
    this.satietyIndicator.classList.toggle('hungry', !fed);

    const poisoned = stats.poisonTicksRemaining > 0;
    this.poisonIndicator.classList.toggle('hidden', !poisoned);
    if (poisoned) this.poisonLabel.textContent = `Zatrucie x${stats.poisonTicksRemaining}`;
  }

  showToast(text: string): void {
    this.toast.textContent = text;
    this.toast.classList.add('show');
    window.clearTimeout(this.toastTimeout);
    this.toastTimeout = window.setTimeout(() => this.toast.classList.remove('show'), 900);
  }

  flashLevelUp(): void {
    this.flash.classList.remove('show');
    // force reflow so the animation can restart
    void this.flash.offsetWidth;
    this.flash.classList.add('show');
  }
}
