import './style.css';
import { Game } from './core/Game';
import type { ClassId } from './types';

const app = document.querySelector<HTMLDivElement>('#app')!;
const classSelectOverlay = document.querySelector<HTMLDivElement>('#class-select-overlay')!;

function startGame(classId: ClassId): void {
  classSelectOverlay.classList.add('hidden');
  const game = new Game(app, app, classId);
  game.start();

  if (import.meta.env.DEV) {
    (window as unknown as { __game: Game }).__game = game;
  }
}

for (const card of classSelectOverlay.querySelectorAll<HTMLButtonElement>('.class-card')) {
  card.addEventListener('click', () => startGame(card.dataset.class as ClassId));
}
