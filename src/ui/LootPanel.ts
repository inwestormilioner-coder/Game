import { ITEMS } from '../data/items';
import type { LootDrop } from '../systems/loot';

/**
 * The corpse-contents window (GDD Section 12): opening a corpse doesn't
 * vacuum everything into the backpack — each item sits here until the
 * player taps it, at which point the game checks carry capacity.
 */
export class LootPanel {
  private root: HTMLElement;
  private title: HTMLElement;
  private itemsEl: HTMLElement;
  private closeBtn: HTMLElement;
  private onPick: ((itemId: string) => void) | null = null;
  private onPickGold: (() => void) | null = null;

  constructor(root: HTMLElement) {
    this.root = root.querySelector('#loot-panel')!;
    this.title = root.querySelector('#loot-panel-title')!;
    this.itemsEl = root.querySelector('#loot-panel-items')!;
    this.closeBtn = root.querySelector('#loot-panel-close')!;
    this.closeBtn.addEventListener('click', () => this.hide());
  }

  get isOpen(): boolean {
    return !this.root.classList.contains('hidden');
  }

  /** Gold sits in the loot list like any other pickup now (GDD Section 12) — opening a
   * corpse no longer vacuums it straight into the wallet, tapping it does. */
  show(title: string, items: LootDrop[], gold: number, onPick: (itemId: string) => void, onPickGold: () => void): void {
    this.title.textContent = title;
    this.onPick = onPick;
    this.onPickGold = onPickGold;
    this.render(items, gold);
    this.root.classList.remove('hidden');
  }

  render(items: LootDrop[], gold: number): void {
    this.itemsEl.innerHTML = '';
    if (gold > 0) {
      const btn = document.createElement('button');
      btn.className = 'loot-item loot-item-gold';
      const name = document.createElement('span');
      name.textContent = `🪙 ${gold} złota`;
      btn.append(name);
      btn.addEventListener('click', () => this.onPickGold?.());
      this.itemsEl.appendChild(btn);
    }

    if (items.length === 0 && gold <= 0) {
      const empty = document.createElement('div');
      empty.className = 'loot-empty';
      empty.textContent = 'Puste';
      this.itemsEl.appendChild(empty);
      return;
    }

    for (const drop of items) {
      const def = ITEMS[drop.itemId];
      const btn = document.createElement('button');
      btn.className = 'loot-item';

      const name = document.createElement('span');
      name.textContent = drop.qty > 1 ? `${def.name} x${drop.qty}` : def.name;

      const weight = document.createElement('span');
      weight.className = 'loot-item-weight';
      weight.textContent = `${(def.weight * drop.qty).toFixed(1)} kg`;

      btn.append(name, weight);
      btn.addEventListener('click', () => this.onPick?.(drop.itemId));
      this.itemsEl.appendChild(btn);
    }
  }

  hide(): void {
    this.root.classList.add('hidden');
    this.onPick = null;
  }
}
