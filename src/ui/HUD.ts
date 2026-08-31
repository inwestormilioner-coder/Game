import type { Stats } from '../types';

export class HUD {
  private hpFill: HTMLElement;
  private xpFill: HTMLElement;
  private levelLabel: HTMLElement;
  private goldLabel: HTMLElement;
  private toast: HTMLElement;
  private flash: HTMLElement;
  private toastTimeout: number | undefined;

  constructor(root: HTMLElement) {
    this.hpFill = root.querySelector('#hp-fill')!;
    this.xpFill = root.querySelector('#xp-fill')!;
    this.levelLabel = root.querySelector('#level-label')!;
    this.goldLabel = root.querySelector('#gold-label')!;
    this.toast = root.querySelector('#toast')!;
    this.flash = root.querySelector('#level-up-flash')!;
  }

  update(stats: Stats): void {
    this.hpFill.style.width = `${(stats.hp / stats.maxHp) * 100}%`;
    this.xpFill.style.width = `${(stats.exp / stats.expToNext) * 100}%`;
    this.levelLabel.textContent = `Lvl ${stats.level}`;
    this.goldLabel.textContent = String(stats.gold);
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
