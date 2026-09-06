import { ITEMS } from '../data/items';
import { CAPE_UNLOCK_LEVEL, type EquipSlot, type Stats } from '../types';

// Display order top to bottom. Cape is last and only shown once unlocked.
const SLOT_LABELS: Array<[EquipSlot, string]> = [
  ['helmet', 'Hełm'],
  ['amulet', 'Amulet'],
  ['armor', 'Pancerz'],
  ['gloves', 'Rękawice'],
  ['legs', 'Spodnie'],
  ['boots', 'Buty'],
  ['weapon', 'Broń'],
  ['shield', 'Tarcza'],
  ['ammo', 'Kołczan / Esencja'],
  ['cape', 'Peleryna'],
];

/** The backpack + equipped-gear screen (GDD Section 26). */
export class InventoryPanel {
  private root: HTMLElement;
  private equippedEl: HTMLElement;
  private itemsEl: HTMLElement;
  private closeBtn: HTMLElement;
  private onEquip: ((itemId: string) => void) | null = null;
  private onUnequip: ((slot: EquipSlot) => void) | null = null;
  private onEat: ((itemId: string) => void) | null = null;

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

  toggle(
    stats: Stats,
    onEquip: (itemId: string) => void,
    onUnequip: (slot: EquipSlot) => void,
    onEat: (itemId: string) => void,
  ): void {
    if (this.isOpen) {
      this.hide();
      return;
    }
    this.onEquip = onEquip;
    this.onUnequip = onUnequip;
    this.onEat = onEat;
    this.render(stats);
    this.root.classList.remove('hidden');
  }

  render(stats: Stats): void {
    this.equippedEl.innerHTML = '';
    for (const [slot, label] of SLOT_LABELS) {
      if (slot === 'cape' && stats.level < CAPE_UNLOCK_LEVEL) continue; // slot itself isn't unlocked yet

      const itemId = stats.equipment[slot];
      const row = document.createElement('div');
      row.className = 'equip-slot';

      const labelEl = document.createElement('span');
      labelEl.className = 'equip-slot-label';
      labelEl.textContent = label;

      const name = document.createElement('span');
      name.className = 'equip-slot-name';
      name.textContent = itemId ? ITEMS[itemId].name : '— puste —';
      row.append(labelEl, name);

      if (itemId) {
        const btn = document.createElement('button');
        btn.className = 'slot-action';
        btn.textContent = 'Zdejmij';
        btn.addEventListener('click', () => this.onUnequip?.(slot));
        row.appendChild(btn);
      }
      this.equippedEl.appendChild(row);
    }

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
      } else if (def.food) {
        const btn = document.createElement('button');
        btn.className = 'slot-action';
        btn.textContent = def.food.poisonTicks ? 'Zjedz ⚠️' : 'Zjedz';
        btn.addEventListener('click', () => this.onEat?.(itemId));
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
    this.onEat = null;
  }
}
