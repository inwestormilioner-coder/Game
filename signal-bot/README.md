# Signal Pips Bot

Bot Telegram, który śledzi Twój kanał/grupę z sygnałami i wysyła podsumowania zdobytych pipsów:

- **dzienne** – codziennie o `REPORT_TIME`
- **tygodniowe** – w niedzielę (pon–ndz)
- **miesięczne** – ostatniego dnia miesiąca

Z każdego sygnału liczony jest **tylko najwyższy osiągnięty TP** (TP1 → TP2 → TP3 daje pipsy za TP3, a nie sumę wszystkich). Wynik jest rozbity na **Strategię nr 1, nr 2 i nr 3**.

## Jak bot rozpoznaje wiadomości

**Sygnał** to post z symbolem, kierunkiem, TP i SL/ceną wejścia, np.:

```
Strategia nr 1
XAUUSD BUY 2350
SL: 2340
TP1: 2353
TP2: 2356
TP3: 2365
```

Strategię rozpoznaje po tekście `Strategia 1`, `Strategia nr 2`, `Strategy #3`, `#S1` (można zmienić `STRATEGY_REGEX`).
TP mogą być cenami (pipsy liczone od wejścia) albo od razu w pipsach (`TP1: 30 pips`).

**Trafienie TP/SL** bot wyłapuje na 3 sposoby:
1. **Odpowiedź (reply) na sygnał**: `TP2 ✅`, `TP3 hit +150 pips`, `✅ TP1 zaliczone`, `All TP hit`, `SL hit ❌`
2. **Edycja sygnału** – dopisanie ✅ przy TP
3. Zwykły post z symbolem, np. `XAUUSD TP2 ✅` → przypisuje do ostatniego sygnału na tym symbolu

Jeśli w wiadomości o TP są podane pipsy (`+150 pips`), bot bierze większą z wartości (podanej / wyliczonej).
SL po trafionym TP nie jest liczony jako strata (stop na BE). Domyślnie raport pokazuje tylko zdobyte pipsy; `INCLUDE_SL_LOSSES=true` odejmuje straty z SL.

Pipsy przypisywane są do dnia **wystawienia sygnału**.

Wielkość pipsa: pary walutowe 0.0001, pary z JPY 0.01, XAUUSD 0.1, indeksy 1. Możesz to nadpisać przez `PIP_SIZES`.

## Instalacja

1. Utwórz bota u [@BotFather](https://t.me/BotFather) i skopiuj token.
2. Dodaj bota do kanału jako **administratora** (wystarczy prawo do publikowania wiadomości, jeśli raporty mają iść na kanał).
   Jeśli to grupa, a nie kanał: w BotFather `/setprivacy` → `Disable`, albo zrób bota adminem.
3. Na serwerze / VPS (Python 3.10+):

```bash
cd signal-bot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # uzupełnij BOT_TOKEN
.venv/bin/python bot.py
```

4. Napisz coś na kanale – w logach pojawi się jego ID (np. `-1001234567890`). Wpisz je jako `SOURCE_CHAT_ID` i zrestartuj bota.
5. Napisz do bota `/start` w prywatnej wiadomości – pokaże Twoje ID. Wpisz je w `ADMIN_IDS`, a jeśli raporty mają przychodzić do Ciebie prywatnie, także w `REPORT_CHAT_IDS`.

Bot musi działać cały czas (VPS, Raspberry Pi, itp.). Przykład usługi systemd:

```ini
[Unit]
Description=Signal Pips Bot
After=network-online.target

[Service]
WorkingDirectory=/opt/signal-bot
ExecStart=/opt/signal-bot/.venv/bin/python bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

## Komendy (prywatnie do bota)

| Komenda | Działanie |
|---|---|
| `/dzis`, `/wczoraj` | raport dzienny |
| `/tydzien`, `/poprzedni_tydzien` | raport tygodniowy |
| `/miesiac`, `/poprzedni_miesiac` | raport miesięczny |
| `/tp <id> <nr>` | ręcznie ustaw najwyższy TP sygnału |
| `/pips <id> <pipsy>` | ręcznie ustaw pipsy |
| `/sl <id>` | oznacz sygnał jako SL |
| `/usun <id>` | usuń sygnał ze statystyk |

`<id>` to numer wiadomości z sygnałem (ostatnia liczba w linku do posta: `t.me/c/123456/`**`789`**).

## Ograniczenia

- Bot widzi tylko wiadomości wysłane **po** dodaniu go do kanału (Bot API nie daje dostępu do historii).
- Jeśli Twoje sygnały mają inny format niż powyżej, sprawdź logi – bot loguje każdy rozpoznany sygnał i aktualizację. Brakujące przypadki można poprawić komendami lub dopasować wzorce w `signal_parser.py`.

## Testy

```bash
.venv/bin/pip install pytest
.venv/bin/pytest -q tests
```
