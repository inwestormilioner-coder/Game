import './style.css';
import { Game } from './core/Game';

const app = document.querySelector<HTMLDivElement>('#app')!;
const game = new Game(app, app);
game.start();

if (import.meta.env.DEV) {
  (window as unknown as { __game: Game }).__game = game;
}
