# Open World RPG — prototyp

Gra 3D w przeglądarce (mobile-first) łącząca klimat Tibii (open world, exp,
potwory, loot) z prostotą sterowania rodem z Mobile Legends (wirtualny
joystick + przycisk ataku). Napisana w TypeScript + [Three.js](https://threejs.org/),
budowana przez [Vite](https://vitejs.dev/).

## Uruchomienie

```bash
npm install
npm run dev
```

Otwórz wyświetlony adres na telefonie (w tej samej sieci) albo w przeglądarce
desktopowej — działa też na klawiaturze (WASD/strzałki + spacja do ataku,
przydatne przy szybkim testowaniu).

## Co już działa (prototyp)

- Otwarty świat 3D (okrągła mapa z drzewami/skałami rozrzuconymi proceduralnie).
- Postać gracza sterowana wirtualnym joystickiem (dotyk) lub klawiaturą.
- Kamera trzecioosobowa podążająca za graczem.
- Jeden typ potwora („Slime”): błądzi losowo, agresuje gracza z bliska,
  atakuje w zwarciu, ma HP, umiera i odradza się po czasie.
- System walki: przycisk ataku, zasięg, cooldown, automatyczne namierzanie
  najbliższego potwora w zasięgu.
- System progresji: EXP, poziomy, rosnące HP/atak, pasek EXP/HP w HUD.
- Prosty "loot": złoto za zabicie potwora (widoczne w HUD).
- Śmierć i respawn gracza.

## Struktura kodu

```
src/
  core/Game.ts        – pętla gry, scena, kamera, spinanie systemów
  entities/Player.ts   – ruch, staty, atak, exp/level
  entities/Monster.ts  – AI wędrówki/agresji, HP, loot, respawn
  input/InputController.ts – wirtualny joystick + przycisk ataku (dotyk/mysz/klawiatura)
  world/World.ts       – teren, dekoracje, granice mapy
  ui/HUD.ts            – paski HP/EXP, poziom, złoto, powiadomienia
  types.ts             – wspólne typy (Stats) i formuły progresji
```

Architektura jest celowo modularna (encje / systemy / świat / UI oddzielone),
żeby kolejne systemy (ekwipunek, gildie, multiplayer) dało się dopiąć bez
przepisywania rdzenia.

## Plan rozwoju (kolejne etapy)

1. **Ekwipunek i przedmioty** — inwentarz, sloty (broń/zbroja), staty z
   przedmiotów, dropy z różnych potworów, prosty crafting/handel.
2. **Więcej treści świata** — różne typy potworów i poziomy trudności per
   strefa, questy, NPC, dungeony/bossowie.
3. **Umiejętności/klasy** — drzewko umiejętności, cooldowny specjalnych
   ataków (bliżej klimatu Mobile Legends).
4. **Multiplayer** — serwer (np. Node + WebSocket/Colyseus), synchronizacja
   pozycji i walki, wspólny świat.
5. **Gildie** — zakładanie/dołączanie, czat gildyjny, wspólne cele
   (rajdy, terytoria), ranking.
6. **PvP** — areny lub otwarte strefy PvP, ranking/sezony.
7. **Wydanie na telefon jako appka** — np. przez Capacitor (opakowanie tej
   samej bazy webowej w natywną appkę na Android/iOS, z dostępem do
   powiadomień push itp.), gdy prototyp będzie gotowy do dalszej rozbudowy.

## Uwaga deweloperska

W `src/main.ts` w trybie dev (`import.meta.env.DEV`) instancja gry jest
wystawiana jako `window.__game` — to hak do automatycznych smoke-testów
(np. Playwright), nieobecny w buildzie produkcyjnym.
