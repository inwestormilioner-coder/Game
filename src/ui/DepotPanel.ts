import { ITEMS } from '../data/items';
import type { Stats } from '../types';

/**
 * The Depot screen (GDD Section 18): a per-city personal stash, separate from the
 * backpack — unlimited slots at MVP (tiered expansion is a later gold-sink pass).
 */
export class DepotPanel {
  private root: HTMLElement;
  private backpackEl: HTMLElement;
  private depotEl: HTMLElement;
  private closeBtn: HTMLElement;
  private onDeposit: ((itemId: string) => void) | null = null;
  private onWithdraw: ((itemId: string) => void) | null = null;

  constructor(root: HTMLElement) {
    this.root = root.querySelector('#depot-panel')!;
    this.backpackEl = root.querySelector('#depot-backpack-items')!;
    this.depotEl = root.querySelector('#depot-stored-items')!;
    this.closeBtn = root.querySelector('#depot-panel-close')!;
    this.closeBtn.addEventListener('click', () => this.hide());
  }

  get isOpen(): boolean {
    return !this.root.classList.contains('hidden');
  }

  show(stats: Stats, onDeposit: (itemId: string) => void, onWithdraw: (itemId: string) => void): void {
    this.onDeposit = onDeposit;
    this.onWithdraw = onWithdraw;
    this.render(stats);
    this.root.classList.remove('hidden');
  }

  render(stats: Stats): void {
    this.renderList(this.backpackEl, stats.inventory, 'Plecak pusty', 'Wpłać', (id) => this.onDeposit?.(id));
    this.renderList(this.depotEl, stats.depot, 'Depozyt pusty', 'Wypłać', (id) => this.onWithdraw?.(id));
  }

  private renderList(
    container: HTMLElement,
    entries: Record<string, number>,
    emptyText: string,
    actionLabel: string,
    onAction: (itemId: string) => void,
  ): void {
    container.innerHTML = '';
    const items = Object.entries(entries);
    if (items.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'loot-empty';
      empty.textContent = emptyText;
      container.appendChild(empty);
      return;
    }

    for (const [itemId, qty] of items) {
      const def = ITEMS[itemId];
      const row = document.createElement('div');
      row.className = 'inventory-row';

      const name = document.createElement('span');
      name.textContent = qty > 1 ? `${def.name} x${qty}` : def.name;
      row.appendChild(name);

      const btn = document.createElement('button');
      btn.className = 'slot-action';
      btn.textContent = actionLabel;
      btn.addEventListener('click', () => onAction(itemId));
      row.appendChild(btn);

      container.appendChild(row);
    }
  }

  hide(): void {
    this.root.classList.add('hidden');
    this.onDeposit = null;
    this.onWithdraw = null;
  }
}
