import { CLASSES, type Stats } from '../types';

export class HUD {
  private hpFill: HTMLElement;
  private resourceFill: HTMLElement;
  private resourceLabel: HTMLElement;
  private xpFill: HTMLElement;
  private levelLabel: HTMLElement;
  private classLabel: HTMLElement;
  private goldLabel: HTMLElement;
  private capacityLabel: HTMLElement;
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
    this.toast = root.querySelector('#toast')!;
    this.flash = root.querySelector('#level-up-flash')!;
  }

  update(stats: Stats, carriedWeight: number): void {
    this.hpFill.style.width = `${(stats.hp / stats.maxHp) * 100}%`;
    this.resourceFill.style.width = `${(stats.resource / stats.maxResource) * 100}%`;
    this.resourceLabel.textContent = stats.resourceName;
    this.xpFill.style.width = `${(stats.exp / stats.expToNext) * 100}%`;
    this.levelLabel.textContent = `Lvl ${stats.level}`;
    this.classLabel.textContent = CLASSES[stats.classId].name;
    this.goldLabel.textContent = String(stats.gold);
    this.capacityLabel.textContent = `${carriedWeight.toFixed(1)} / ${stats.maxCapacity}`;
    this.capacityLabel.parentElement!.classList.toggle('over-limit', carriedWeight >= stats.maxCapacity);
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
