# Telegram -> MT5 signal bot

Nasłuchuje kanału Telegram z sygnałami w stylu "PREMIUM SIGNALS (TAKE PROFIT)"
i automatycznie wystawia w MT5 siatkę zleceń oczekujących pokrywającą całą
podaną strefę, po 0.01 lota co `ZONE_STEP` (domyślnie 0.5$), z SL z sygnału
i drabinką TP rosnącą co 10 pipsów od najniższej ceny w strefie
(60 / 70 / 80 / 90 / 100 / 110 / ... pipsów, wg liczby zleceń w strefie).

## Ograniczenia, o których musisz wiedzieć

- **Pakiet `MetaTrader5` działa tylko na Windows**, obok uruchomionego i
  zalogowanego terminala MT5. Bota (część, która realnie handluje) trzeba
  uruchomić na Twoim Windowsie z zainstalowanym MT5 - nie w tym środowisku
  ani na Macu/Linuksie. Parser i planer zleceń są platformowo-niezależne i
  mają testy jednostkowe, które przechodzą tutaj.
- **`PIP_SIZE` w `.env` musisz zweryfikować u swojego brokera.** Wiele
  brokerów kwotuje XAUUSD z 2 miejscami po przecinku i nazywa ruch o 0.10
  "1 pipsem" (stąd domyślne `PIP_SIZE=0.1`, czyli SL 60 pips = $6). Jeśli
  Twój broker liczy inaczej, zmień tę wartość - inaczej SL/TP wylądują w
  złym miejscu.
- **Kanał Telegram nie ma ID sygnału.** Wiadomości typu "SL na BE" czy
  "Zamykam całość" nie mówią, której strefy dotyczą. Bot zakłada, że
  dotyczą wszystkich aktualnie aktywnych ("otwartych") kampanii dla danego
  symbolu - jeśli w tym samym czasie masz otwarte dwie różne strefy, update
  zadziała na obie. Zobacz `campaign_store.py`, jeśli chcesz to zawęzić
  (np. tylko do najnowszej).
- Wiadomości typu "Zbieram malutką część zysków" (częściowe zamknięcie bez
  podanego %) są tylko logowane - **nie zamykają automatycznie części
  pozycji**, bo sygnał nie mówi ile. To świadome uproszczenie, nie bug.
- **Domyślnie `DRY_RUN=true`** - bot parsuje wiadomości i loguje, co BY
  wysłał do MT5, ale nic nie wysyła. Włącz realne zlecenia (`DRY_RUN=false`)
  dopiero gdy przejrzysz logi z kilku prawdziwych sygnałów.

## Instalacja (na Windows, obok MT5)

```bash
cd telegram-mt5-bot
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Uzupełnij `.env`:

1. `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` - z https://my.telegram.org
   ("API development tools"). To dane Twojego konta Telegram (nie bota) -
   tylko zwykłe konto może czytać wiadomości z kanału, do którego jesteś
   dopisany.
2. `TELEGRAM_CHANNEL` - @username kanału albo jego numeryczne ID.
3. `MT5_LOGIN` / `MT5_PASSWORD` / `MT5_SERVER` - zostaw puste, jeśli MT5
   jest już otwarty i zalogowany na koncie, na którym ma handlować bot.
4. Sprawdź `SYMBOL` (np. `XAUUSD`, czasem `XAUUSD.a` / `GOLD` zależnie od
   brokera) i `PIP_SIZE`.

Pierwsze uruchomienie (`python main.py`) poprosi o numer telefonu i kod z
Telegrama - to jednorazowe logowanie, zapisze się w pliku sesji
(`*.session`, nie commituj go).

## Uruchomienie

```bash
python main.py
```

Nasłuchuje kanał i na żywo przetwarza wiadomości. Zatrzymaj Ctrl+C.

## Test offline (bez Telegrama i MT5)

```bash
python main.py --replay tests/sample_signals.txt
```

Odtwarza przykładowe wiadomości z ekranu (dokładnie te z zapytania) przez
parser -> planer zleceń i loguje wynik w trybie DRY RUN.

## Testy jednostkowe

```bash
pip install pytest
pytest tests/
```

Pokrywają parser (rozbijanie "Strefa: 4425-20", rozpoznawanie BE / zamknij
całość, polskie znaki) i planer zleceń (siatka co 0.5$, drabinka TP).

## Struktura

```
config.py            - wczytywanie .env
signal_parser.py      - tekst wiadomości -> ZONE / BREAKEVEN / CLOSE_ALL / ...
order_planner.py       - strefa -> lista zleceń (cena wejścia, SL, TP, lot)
campaign_store.py      - który magic/ticket należy do której strefy
mt5_executor.py        - właściwe wywołania MetaTrader5 (tylko Windows)
telegram_listener.py   - nasłuch kanału (Telethon)
main.py                - spina wszystko, tryb live i --replay
```
