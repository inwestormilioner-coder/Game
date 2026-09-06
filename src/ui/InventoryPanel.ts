import { ITEMS } from '../data/items';
import type { EquipSlot, Stats } from '../types';

const SLOT_LABELS: Record<EquipSlot, string> = { weapon: 'Broń', armor: 'Zbroja' };

/** The backpack + equipped-gear screen (GDD Section 26). */
export class InventoryPanel {
  private root: HTMLElement;
  private equippedEl: HTMLElement;
  private itemsEl: HTMLElement;
  private closeBtn: HTMLElement;
  private onEquip: ((itemId: string) => void) | null = null;
  private onUnequip: ((slot: EquipSlot) => void) | null = null;

  constructor(root: HTMLElement) {
    this.root = root.querySelector('#inventory-panel')!;
    this.equippedEl = root.querySelector('#inventory-equipped')!;
    this.itemsEl = root.querySelector('#inventory-items')!;
    this.closeBtn = root.querySelector('#inventory-panel-close')!;
    this.closeBtn.addEventListener('click', () => this.hide());
  }

  get isOpen(): boolean {
    return !this.root.classList.contains('hidden');
  }

  toggle(stats: Stats, onEquip: (itemId: string) => void, onUnequip: (slot: EquipSlot) => void): void {
    if (this.isOpen) {
      this.hide();
      return;
    }
    this.onEquip = onEquip;
    this.onUnequip = onUnequip;
    this.render(stats);
    this.root.classList.remove('hidden');
  }

  render(stats: Stats): void {
    this.equippedEl.innerHTML = '';
    (Object.keys(SLOT_LABELS) as EquipSlot[]).forEach((slot) => {
      const itemId = stats.equipment[slot];
      const row = document.createElement('div');
      row.className = 'equip-slot';

      const label = document.createElement('span');
      label.className = 'equip-slot-label';
      label.textContent = SLOT_LABELS[slot];

      const name = document.createElement('span');
      name.className = 'equip-slot-name';
      name.textContent = itemId ? ITEMS[itemId].name : '— puste —';
      row.append(label, name);

      if (itemId) {
        const btn = document.createElement('button');
        btn.className = 'slot-action';
        btn.textContent = 'Zdejmij';
        btn.addEventListener('click', () => this.onUnequip?.(slot));
        row.appendChild(btn);
      }
      this.equippedEl.appendChild(row);
    });

    this.itemsEl.innerHTML = '';
    const entries = Object.entries(stats.inventory);
    if (entries.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'loot-empty';
      empty.textContent = 'Plecak pusty';
      this.itemsEl.appendChild(empty);
      return;
    }

    for (const [itemId, qty] of entries) {
      const def = ITEMS[itemId];
      const row = document.createElement('div');
      row.className = 'inventory-row';

      const name = document.createElement('span');
      name.textContent = qty > 1 ? `${def.name} x${qty}` : def.name;

      row.appendChild(name);

      if (def.equip) {
        const btn = document.createElement('button');
        btn.className = 'slot-action';
        btn.textContent = 'Załóż';
        btn.addEventListener('click', () => this.onEquip?.(itemId));
        row.appendChild(btn);
      } else {
        const weight = document.createElement('span');
        weight.className = 'loot-item-weight';
        weight.textContent = `${(def.weight * qty).toFixed(1)} kg`;
        row.appendChild(weight);
      }

      this.itemsEl.appendChild(row);
    }
  }

  hide(): void {
    this.root.classList.add('hidden');
    this.onEquip = null;
    this.onUnequip = null;
  }
}
