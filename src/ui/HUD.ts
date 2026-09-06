import { CLASSES, type Stats } from '../types';

function formatMinSec(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = Math.floor(totalSeconds % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

export class HUD {
  private hpFill: HTMLElement;
  private resourceFill: HTMLElement;
  private resourceLabel: HTMLElement;
  private xpFill: HTMLElement;
  private levelLabel: HTMLElement;
  private classLabel: HTMLElement;
  private goldLabel: HTMLElement;
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
    this.goldLabel = root.querySelector('#gold-label')!;
    this.capacityLabel = root.querySelector('#capacity-label')!;
    this.satietyIndicator = root.querySelector('#satiety-indicator')!;
    this.satietyLabel = root.querySelector('#satiety-label')!;
    this.poisonIndicator = root.querySelector('#poison-indicator')!;
    this.poisonLabel = root.querySelector('#poison-label')!;
    this.toast = root.querySelector('#toast')!;
    this.flash = root.querySelector('#level-up-flash')!;
  }

  update(stats: Stats, derived: { carriedWeight: number; maxResource: number }): void {
    this.hpFill.style.width = `${(stats.hp / stats.maxHp) * 100}%`;
    this.resourceFill.style.width = `${(stats.resource / derived.maxResource) * 100}%`;
    this.resourceLabel.textContent = stats.resourceName;
    this.xpFill.style.width = `${(stats.exp / stats.expToNext) * 100}%`;
    this.levelLabel.textContent = `Lvl ${stats.level}`;
    this.classLabel.textContent = CLASSES[stats.classId].name;
    this.goldLabel.textContent = String(stats.gold);
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
