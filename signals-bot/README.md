# XAUUSD Signal Bot

Bot śledzi złoto (domyślnie M30). Po zamknięciu każdej świecy szuka setupu Smart Money:
**BOS/CHOCH → retest strefy → odrzucenie**. Gdy go znajdzie:

1. rysuje wykres ze strefą, BOS/CHOCH, retestem, wejściem, SL i TP,
2. pisze post. Liczby wstawia kod, a AI (Claude) dopisuje krótkie uzasadnienie „dlaczego”,
3. publikuje na **Telegram**, **Threads** i **X**,
4. pilnuje sygnału i po trafieniu TP albo SL odpisuje pod postem z wynikiem w R.

## Zasady setupu (SELL; BUY to lustrzane odbicie)

| Element | Skąd się bierze |
|---|---|
| **BOS / CHOCH** | Zamknięcie świecy poniżej ostatniego swing low. Jeśli wcześniej były wyższe szczyty i dołki, to CHOCH (zmiana trendu), w przeciwnym razie BOS (kontynuacja). |
| **Strefa podaży** | Od przebitego poziomu do szczytu ruchu, który go przebił (maks. 2,5 ATR). |
| **TP** | Dołek impulsu po przebiciu, czyli wsparcie ze struktury. |
| **Retest** | Cena wraca do przebitego poziomu. |
| **SL** | Szczyt retestu + 0,2 ATR, czyli też ze struktury. |
| **Wejście** | Pierwsza spadkowa świeca, która zamyka się z powrotem pod poziomem. |
| **Unieważnienie** | Zamknięcie nad strefą albo brak retestu w ciągu 48 świec. |
| **Filtry** | RR ≥ `MIN_RR` (1,5), impuls ≥ 2 ATR. |

**Konfluencje** liczone przy każdym setupie, rysowane na wykresie i opisywane w poście:

| Konfluencja | Znaczenie |
|---|---|
| **Fibo 0.5–0.786** | Retest sięgnął strefy premium/discount impulsu (OTE). |
| **FVG** | Retest wszedł w lukę (Fair Value Gap) zostawioną przez impuls. |
| **Sweep (BSL/SSL)** | Retest wybił wcześniejszy szczyt lub dołek, czyli zebrał płynność, i wrócił. |
| **Volume Profile** | Strefa pokrywa się z POC albo węzłem dużego wolumenu (HVN) z ostatnich 200 świec. Wymaga wolumenu (tick volume z MT5); z Twelve Data może go nie być. |
| **Liquidity target** | Następna pula płynności za TP. Przy `TP_MODE=liquidity` staje się celem. |

`MIN_SCORE=0..4` pozwala publikować tylko setupy z określoną liczbą konfluencji.

### Porównanie wariantów

```bash
python -m signalbot.compare XAUUSD_M30.csv --tf M30   # CSV: time/datetime,open,high,low,close
```

Skrypt liczy każdy wariant (bazowy, +Fibo, +FVG, +sweep, min. 1 lub 2 konfluencje, TP na płynności)
osobno dla 1. i 2. połowy danych, z kosztem spreadu.

Parametry są w `signalbot/strategy.py` (`Params`). Detektor nie zagląda w przyszłość
(test `test_no_lookahead`), więc wyniki backtestu odpowiadają temu, co bot zrobiłby na żywo.

## Dane: MT5 czy Exness?

To to samo. Exness to broker, a MT5 to platforma, przez którą bot czyta ceny z Twojego konta.
Do wyboru są dwie drogi:

- **`DATA_SOURCE=mt5`** daje dokładnie te ceny, które widzisz u Exness (`SYMBOL=XAUUSDm`).
  Pakiet `MetaTrader5` działa jednak **tylko na Windows** z uruchomionym terminalem MT5,
  więc potrzebujesz komputera albo Windows VPS włączonego 24/5.
- **`DATA_SOURCE=twelvedata`** działa na dowolnym tanim serwerze z Linuxem. Wystarczy darmowy
  klucz z twelvedata.com (`SYMBOL=XAU/USD`). Ceny spot mogą różnić się od Exness o ułamki dolara.

Na start polecam Twelve Data, bo hosting jest prostszy i tańszy. Na MT5 można przejść później
zmianą jednej linijki w `.env`.

## Instalacja

```bash
cd signals-bot
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env    # uzupełnij klucze
```

## Użycie

```bash
python -m signalbot.main demo                 # przykładowy wykres + post (dane syntetyczne)
python -m signalbot.main backtest --charts 10 # statystyki na historii + 10 wykresów w data/backtest/
python -m signalbot.main once                 # jedno sprawdzenie rynku
python -m signalbot.main run                  # praca ciągła (sprawdza 20 s po zamknięciu świecy)
python -m pytest -q                           # testy
```

Dopóki `DRY_RUN=true`, bot nic nie wysyła i tylko wypisuje posty w konsoli.

## Kolejność wdrażania

1. **Backtest.** Najlepiej na kilku miesiącach M30, np. eksport z MT5 do CSV (`DATA_SOURCE=csv`).
   Jeśli suma R wychodzi ujemna, najpierw dostrajamy `Params`.
2. **Telegram, prywatna grupa testowa.** `DRY_RUN=false`, `TELEGRAM_ENABLED=true`, przez 2–4 tygodnie.
3. **Kanał publiczny.** Potem Threads i X.

## Konfiguracja kanałów

**Telegram.** Dodaj bota do grupy lub kanału jako administratora. `TELEGRAM_CHAT_ID` znajdziesz,
wysyłając wiadomość w grupie i otwierając
`https://api.telegram.org/bot<TOKEN>/getUpdates`. ID grupy zaczyna się od `-100`.

**Threads.**
1. Utwórz aplikację w developers.facebook.com, dodaj produkt *Threads API* z uprawnieniami
   `threads_basic` i `threads_content_publish`.
2. Wygeneruj long-lived token (ważny 60 dni, trzeba go odświeżać) i wpisz go razem z `THREADS_USER_ID`.
3. Threads pobiera obrazek z publicznego URL, więc katalog `data/` musi być dostępny
   z internetu (np. nginx) pod adresem z `PUBLIC_IMAGE_BASE_URL`. Bez tego bot publikuje sam tekst.

**X.**
1. Utwórz projekt w developer.x.com i ustaw uprawnienia aplikacji na *Read and Write*.
2. Wygeneruj 4 klucze OAuth 1.0a.
3. Publikowanie przez API jest płatne. Sprawdź aktualny plan.
4. Moduł X nie był jeszcze testowany na prawdziwych kluczach, więc pierwszy post najlepiej zrobić ręcznie.

**AI.** Potrzebny jest `ANTHROPIC_API_KEY` z console.anthropic.com. Koszt to ułamek centa za sygnał.
Bez klucza (albo przy `USE_AI=false`) bot używa gotowego szablonu tekstu.

## Uruchomienie 24/5 na serwerze (Linux, systemd)

```ini
# /etc/systemd/system/signalbot.service
[Service]
WorkingDirectory=/opt/signals-bot
ExecStart=/opt/signals-bot/.venv/bin/python -m signalbot.main run
Restart=always
[Install]
WantedBy=multi-user.target
```

Na Windows z MT5 możesz użyć Harmonogramu zadań albo po prostu `python -m signalbot.main run`.

## Ważne

- Każdy post zawiera disclaimer. Publiczne rekomendacje inwestycyjne mogą podlegać przepisom
  (KNF, rozporządzenie MAR). Przy płatnej grupie lub linkach afiliacyjnych skonsultuj to z prawnikiem.
- Wyniki (✅ TP / ❌ SL) są publikowane automatycznie, także te przegrane. To buduje wiarygodność.
- Stan sygnałów jest w `data/state.json`, wykresy w `data/charts/`.

## Wskaźnik TradingView

`tradingview/smc_zones.pine` to ta sama logika co bot, do porównania na wykresie:

- **Strefy** SELL ZONE / BUY ZONE z siłą Weak / Medium / Strong. Siła to liczba spełnionych warunków:
  - impuls ≥ 3 ATR,
  - impuls zostawił FVG,
  - wolumen świecy przebicia ≥ 1,5× średniej.
- **BOS / CHoCH** oraz FVG.
- **Sygnały bota** z Entry / SL / TP i konfluencjami Fibo i FVG, z alertami.
- **Tabela trendu** na 5 interwałach (M5, M15, H1, H4, D1).

Instalacja: TradingView → Pine Editor → wklej plik → *Add to chart*.
Alert: ⏰ → warunek „SMC Zones” → *Any alert() function call*.

`tradingview/tpz_zones.pine` to wersja w stylu TPZ: węższe strefy z jednej świecy order blocka,
paski wolumenu kupna i sprzedaży, siła jako ranking wolumenu (Strong / Medium / Weak) i maks. 3 strefy na stronę.

## Strategia „strefa + Fibo” (domyślna, posty po angielsku)

Działanie strategii:
1. Cena dotyka strefy (order block). Fibo idzie od dołka (dla SELL: szczytu) reakcji (0) do poprzedniego swingu (1).
2. Zlecenie BUY/SELL STOP stoi na 0.1272, SL na -0.1272. Domyślnie jest 5 celów (`TP_LEVELS`): 0.382 (= 1:1 RR), 0.618, 1.0, 1.272 i 1.618. Pozycję zamykamy częściami, a SL idzie na wejście po TP1.
3. Post wychodzi, gdy zlecenie się aktywuje: wykres, poziomy i uzasadnienie „Why” od AI.
4. Odpowiedź pod postem pojawia się tylko po zaliczeniu 1:1 RR, a potem na zamknięciu, jeśli wynik ≥ +1R.

Test na historii, odtwarzany świeca po świecy (przy `DRY_RUN=false` naprawdę wysyła):

```bash
python -m signalbot.main fibtest --csv XAUUSD_M15.csv --at "2026-07-08 15:45"
```

### Tryb podglądu: tylko Twój prywatny Telegram

W `.env` ustaw:
- `TELEGRAM_ENABLED=true`, `THREADS_ENABLED=false`, `X_ENABLED=false`, `DRY_RUN=false`,
- `TELEGRAM_CHAT_ID` = Twoje ID.

Żeby poznać ID, napisz cokolwiek do swojego bota i otwórz `https://api.telegram.org/bot<TOKEN>/getUpdates`.
ID jest w polu `"chat":{"id": ...}`.
