export interface DialogueOption {
  label: string;
  onClick: () => void;
}

/**
 * NPC conversation window (GDD Section 17): interactive, response-option dialogue —
 * never a single "press to skip" wall of text — used for quest offers/progress/turn-in
 * and any other diegetic NPC talk.
 */
export class DialoguePanel {
  private root: HTMLElement;
  private nameEl: HTMLElement;
  private textEl: HTMLElement;
  private optionsEl: HTMLElement;
  private closeBtn: HTMLElement;

  constructor(root: HTMLElement) {
    this.root = root.querySelector('#dialogue-panel')!;
    this.nameEl = root.querySelector('#dialogue-name')!;
    this.textEl = root.querySelector('#dialogue-text')!;
    this.optionsEl = root.querySelector('#dialogue-options')!;
    this.closeBtn = root.querySelector('#dialogue-panel-close')!;
    this.closeBtn.addEventListener('click', () => this.hide());
  }

  get isOpen(): boolean {
    return !this.root.classList.contains('hidden');
  }

  show(npcName: string, text: string, options: DialogueOption[]): void {
    this.nameEl.textContent = npcName;
    this.textEl.textContent = text;
    this.optionsEl.innerHTML = '';

    for (const opt of options) {
      const btn = document.createElement('button');
      btn.className = 'dialogue-option';
      btn.textContent = opt.label;
      btn.addEventListener('click', () => opt.onClick());
      this.optionsEl.appendChild(btn);
    }

    this.root.classList.remove('hidden');
  }

  hide(): void {
    this.root.classList.add('hidden');
  }
}
