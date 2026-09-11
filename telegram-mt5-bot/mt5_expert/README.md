# TelegramBridgeEA

Companion Expert Advisor for the Python bot. Only needed if placing orders
straight from Python (`mt5.order_send()`) gets rejected with
`retcode=10027 "AutoTrading disabled by client"` even though Algo Trading
is on in the terminal and manual trades work fine - a restriction some
brokers/terminal builds apply specifically to the external Python API.
The EA trades from inside the terminal instead (same path as clicking
"New Order" manually), which isn't affected.

Python still does everything else: reads Telegram, parses signals, plans
the entry/SL/TP grid, watches prices/positions for the 1:1 average-SL
logic. It only hands the EA a plain-text instruction file for the actual
trade calls - see `TelegramBridgeEA.mq5`'s header comment for the exact
format.

## Install

1. Open MT5 → **Narzędzia (Tools) → MetaEditor** (or press F4).
2. In MetaEditor's Navigator (left panel), right-click **Experts** → **New Folder**
   is not needed - just right-click **Experts** → **Open Folder** to see
   where files go, or simpler: in Windows Explorer, copy
   `TelegramBridgeEA.mq5` into your MT5 data folder's `MQL5\Experts\`
   subfolder (in MT5: **File → Open Data Folder** to find it).
3. Back in MetaEditor, open `TelegramBridgeEA.mq5` from the Navigator and
   press **F7** (Compile). It should say "0 error(s), 0 warning(s)" at the
   bottom. This creates `TelegramBridgeEA.ex5` next to it.
4. Switch to MT5. In the **Navigator** panel (Ctrl+N), under **Doradcy
   (Expert Advisors)**, you should now see `TelegramBridgeEA`.
5. Drag it onto **any one chart** (the XAUUSD chart is fine, but it doesn't
   actually matter which symbol - the EA trades whatever symbol each
   command file tells it to).
6. In the properties dialog that opens:
   - Tab **Common (Ogólne)**: check **"Allow live trading" / "Zezwól na
     handel na żywo"**.
   - Tab **Inputs (Wejścia)**: defaults are fine (`BridgeSubfolder=tg_bridge`,
     `PollSeconds=1`, `MagicRangeStart=990000` - must match `MAGIC_BASE` in
     `.env`, `ScreenshotWidth`/`ScreenshotHeight=1024x600`).
   - Click OK.
7. Make sure the global **"Algo Trading"** button in the MT5 toolbar is on
   (green) - the EA needs it too, same as any automated trading.
8. Check the **Eksperci (Experts)** tab at the bottom of MT5: you should
   see `TelegramBridgeEA started, watching Common\Files\tg_bridge\` and,
   every 60s, an "alive" heartbeat line. If you see a smiling face in the
   corner of the chart the EA is on, it's active.

That's it - leave that chart open (can be minimized) while the Python bot
runs. No changes needed to `.env`; `mt5_executor.py` finds the same shared
`Common\Files\tg_bridge` folder automatically via the MT5 connection.

## Updating after this first install

Whenever `TelegramBridgeEA.mq5` changes (e.g. after `git pull`), you need
to copy the new source over the old one and recompile. Two ways:

- **`update_ea.bat`** (in this folder) does both in one double-click - it
  copies the file into your MT5 data folder and compiles it via
  MetaEditor's command-line mode, then prints the compile result. The two
  paths at the top of the script are already filled in for this install;
  only edit them if you reinstall MT5 or move it elsewhere.
- Or do it manually: repeat steps 2-3 above (copy the file, open it in
  MetaEditor, press F7).

Either way, check MT5's **Eksperci** tab afterwards - the EA should keep
running with the new code (MT5 usually hot-reloads a recompiled EA
automatically), or remove and re-drag it onto the chart if it doesn't.

## How to tell it's working

- MT5 **Eksperci** tab logs every order it places/fails and every SL move,
  e.g. `Bridge: placed PENDING BUY @ 4469.00 (requested 4469.00) sl=4463.00
  tp=4475.00 ticket=123456`. An entry that's within the broker's minimum
  stop/freeze distance of the current price fills at MARKET instead (same
  line, but `MARKET` and a fill price that may differ slightly from the
  requested one) rather than being rejected/skipped for being too close.
- The Python bot logs `queued N orders for EA bridge (campaign ...) -> ...`
  when it hands off a zone signal, then you'll see the resulting positions
  show up in MT5's **Handel (Trade)** tab a moment later.
- If the Python bot's own log ever shows a warning about "command file(s)
  ... still unprocessed" - the EA isn't attached/running; redo steps 4-6.

## Powiadomienia na Telegram przy realnym wypełnieniu zlecenia

Poza wystawianiem/modyfikowaniem zleceń ten EA robi jeszcze jedną rzecz:
gdy jedno z naszych zleceń oczekujących faktycznie się wypełni (nie w
momencie wystawienia, tylko dopiero gdy cena je faktycznie złapie), robi
zrzut wykresu (`ChartScreenShot`) i zapisuje go razem z małym plikiem
tekstowym (numer transakcji/pozycji/magic/symbol) do
`Common\Files\<BridgeSubfolder>\fills\`. Rozpoznaje "nasze" zlecenia po
magic number - każda transakcja z magic `>= MagicRangeStart` (domyślnie
990000, musi się zgadzać z `MAGIC_BASE` w `.env`) liczy się jako nasza,
niezależnie od tego, kiedy EA został uruchomiony/zrestartowany.

Stronę Python odbiera te pliki (`mt5_executor.take_pending_fill_notifications`,
wołane z `main.py`'s `Bot.watch_fills`) i wysyła screenshot + szczegóły
zlecenia na Telegram tą samą sesją, która czyta kanał z sygnałami - zobacz
`NOTIFY_ENABLED`/`TELEGRAM_NOTIFY_CHAT`/`DAILY_SUMMARY_TIME` w
`.env.example`. Zamknięcia pozycji i dzienne podsumowanie pipsów/wyniku EA
w ogóle nie liczy - to Python robi z historii transakcji MT5, do której ma
dostęp przez zwykłe (read-only, więc nieobjęte retcode 10027) wywołania
API.

Żeby zrzuty ekranu były sensowne (pokazywały realny wykres złota, nie
przypadkowy inny symbol), EA musi być podpięty do wykresu tego samego
symbolu co handluje (u nas: XAUUSD) - dokładnie tak, jak jest to opisane w
kroku 5 powyżej.

## Panel ręcznego wystawiania zleceń - `ManualZonePanelEA.mq5`

Osobny, samodzielny EA (nie ma nic wspólnego z `TelegramBridgeEA.mq5` -
inny plik, inny magic range, żadnych wspólnych folderów/plików) - wrzucasz
go na **dowolny inny wykres** (może być na tym samym terminalu co bridge
EA, może być na zupełnie innym), niezależnie od Pythona/Telegrama.

Instalacja - te same kroki co dla `TelegramBridgeEA.mq5` (patrz sekcja
**Install** wyżej), tylko z plikiem `ManualZonePanelEA.mq5`: skopiuj do
`MQL5\Experts\`, otwórz w MetaEditor, **F7** (kompilacja), przeciągnij na
wykres, zaznacz **"Allow live trading"**, upewnij się że **Algo Trading**
jest włączony globalnie.

Panel jest **w pełni obsługiwany klikaniem** - żadnego wpisywania tekstu,
żadnego przeciągania obiektów (oba okazały się niepewne w niektórych
konfiguracjach/motywach MT5, więc panel ich w ogóle nie używa):

1. Klikasz **"ZAZNACZ STREFE"**.
2. Klikasz na wykresie **dwa punkty** (dowolna kolejność) - to są granice
   strefy. Po pierwszym kliknięciu widzisz od razu szarą kropkowaną linię
   na tej cenie; po drugim - całą strefę wyrysowaną na złoto (prostokąt +
   etykieta z cenami) i pole "Strefa" uzupełnione - widzisz dokładnie co
   zamierzasz otworzyć, zanim jeszcze wybierzesz kierunek.
3. **SL (pips)**, **Trailing (pips)**, **Blokada zysku (pips)**, **Krok
   siatki ($)** ustawiasz przyciskami `-`/`+` obok każdej wartości
   (SL/Trailing: co 5 pipsów, Blokada zysku: co 1 pips, Krok siatki: co
   $0.10).
4. Klikasz **BUY** albo **SELL**.

EA liczy siatkę wejść co "Krok siatki" w zaznaczonej strefie, jeden
wspólny SL (tyle pipsów od gorszego brzegu strefy), lot ze skalowaniem
mirrorującym `LOT_SIZE`/`LOT_TIER_ORDERS`/`LOT_SCALING_MODE`/
`LOT_MULTIPLIER` (Inputs: `PanelLotBase`/`PanelLotTierOrders`/
`PanelLotScalingMode`/`PanelLotMultiplier`), i wystawia zlecenia (z
fallbackiem na MARKET dla entry zbyt blisko ceny, tak jak bridge EA).
Zlecenia z panelu nie dostają TP - wychodzą wyłącznie przez ten sam
**trailing stop** co `EXIT_MODE=trailing_stop` w Pythonie: co "Trailing
(pips)" zysku SL przeskakuje o kolejne "Trailing (pips)", ale zamiast
lądować dokładnie na BE/poprzednim progu, zawsze zostawia dodatkowo
"Blokada zysku (pips)" zablokowanego zysku (domyślnie 12 - ustaw 0 dla
starego czysto-BE zachowania). SL nigdy nie wraca w dół. Wartości brane są
w momencie kliknięcia BUY/SELL. Po wystawieniu zlecenia zaznaczona strefa
się czyści (żółty podgląd znika, zastępuje go docelowy
niebieski/pomarańczowy rysunek strefy) - kolejne zlecenie wymaga ponownego
"ZAZNACZ STREFE".

**"ZAMKNIJ ZLECENIA OCZEKUJACE"** anuluje od razu wszystkie jeszcze
niewypełnione zlecenia oczekujące wystawione przez ten EA (magic
`>= PanelMagicBase`) - otwartych już pozycji nie rusza, tylko czyści
"zawieszone" zlecenia z siatki, które jeszcze się nie złapały.

**Siatka wszystko-albo-nic**: jeśli jedno zlecenie oczekujące z danej
siatki zniknie BEZ fillu (np. ręcznie usunięte w terminalu, wygasłe,
odrzucone), EA automatycznie usuwa resztę jeszcze niewypełnionych zleceń
z tej samej siatki (magic) - sprawdzane co tick timera
(`PanelDetectAbandonedGrids`). Już otwartych pozycji to nie dotyka, tylko
pozostałych zleceń oczekujących - niekompletna siatka przestaje
reprezentować zakładaną wielkość/ryzyko strefy. Zlecenie, które zniknęło
bo się wypełniło (normalny przypadek - jeden poziom siatki złapał cenę),
zostaje bez zmian, razem z resztą siatki.

`PanelMagicBase` (domyślnie 500000+) jest celowo poza zakresem
`MAGIC_BASE` (990000+) używanym przez Pythona - zlecenia z panelu nigdy
się nie pomieszają z kampaniami sterowanymi sygnałami z kanału, nawet
jeśli oba EA działają na tym samym koncie. `PanelPipSize` musi się
zgadzać z `PIP_SIZE` w `.env`/Twoim brokerem.

Każde kliknięcie BUY/SELL rysuje też samą strefę na wykresie - prostokąt
od dołu do góry strefy (niebieski dla BUY, pomarańczowy dla SELL),
przerywaną czerwoną linię na SL i etykietę z kierunkiem/cenami - dokładnie
jak w botach "ZONES". Rysunek dla danej strefy znika automatycznie, gdy
nie ma już dla niej żadnych zleceń oczekujących ani otwartych pozycji.

Panel jest teraz większy i domyślnie doku­je się w **prawym górnym rogu**
wykresu (`PanelOnRight=true`, odległość od prawej krawędzi liczona z
`PanelRightMargin`, domyślnie 20px - pozycja liczona automatycznie z
szerokości wykresu, więc działa niezależnie od rozdzielczości). Żeby
wrócić do starego zachowania (lewy górny róg, ręczne `PanelX`/`PanelY`),
ustaw `PanelOnRight=false` w Inputs. Jeśli mimo to panel zasłania Ci
pasek narzędzi/OHLC, dostrój `PanelRightMargin`/`PanelY` (albo
`PanelX`/`PanelY` gdy `PanelOnRight=false`) i przeciągnij EA na wykres
ponownie (albo zmień Inputs w już podpiętym EA: prawy klik na wykres →
Właściwości → Wejścia).

Ograniczenie: który trailing należy do której pozycji EA pamięta tylko w
pamięci (nie w pliku) - restart EA/terminala zeruje to dla już otwartych
pozycji z panelu (nowe kliknięcia po restarcie działają normalnie od
razu).

## Uninstalling / going back to direct API calls

Not supported as a toggle right now - the bridge is the only way
`mt5_executor.py` places orders. If your account doesn't have the
retcode-10027 restriction, the EA is a compatible, working alternative
either way (it doesn't hurt to leave it running).
