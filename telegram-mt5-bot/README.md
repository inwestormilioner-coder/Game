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
- **Kanał steruje tylko wejściami (nowe strefy). Wszystko po wejściu -
  SL, TP, zamykanie - robi bot sam, wg Twoich zasad, nie wg tego co pisze
  kanał:**
  - **"SL na BE"** z kanału jest **ignorowane**. Bot sam pilnuje SL:
    dopiero gdy pływający zysk całej strefy (mierzony od średniej ważonej
    ceny wejścia wszystkich otwartych zleceń tej strefy) osiągnie
    `RISK_REWARD_TRIGGER` (domyślnie 1.0, czyli 1:1) razy pierwotne ryzyko
    (odległość SL w pipsach z sygnału), przesuwa SL wszystkich otwartych
    pozycji tej strefy na **średnią cenę wejścia całego koszyka** (nie na
    cenę wejścia każdego zlecenia z osobna). Robi to raz na strefę
    (`breakeven_applied` w `state/campaigns.json`).
  - **"Zamykam całość"** z kanału też jest **ignorowane**. Bot nigdy nie
    zamyka pozycji na słowo kanału - jedyne wyjścia to TP każdego zlecenia
    (drabinka 60/70/80/... pipsów) albo SL (najpierw ten z sygnału, potem
    przesunięty na średnią po 1:1 jak wyżej). Kampania jest oznaczana jako
    zakończona sama, gdy MT5 pokaże, że nie ma już dla niej żadnych zleceń
    oczekujących ani otwartych pozycji (magic number) - nie na skutek
    wiadomości z kanału.
  - Oba powyższe są sprawdzane co `MONITOR_INTERVAL_SECONDS` sekund
    (domyślnie 5), tylko gdy `DRY_RUN=false` (wymaga żywego połączenia z
    MT5) - w DRY_RUN pętla monitorująca się nie uruchamia.
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
2. `TELEGRAM_CHANNEL` - @username kanału, albo jego numeryczne ID jeśli
   kanał jest prywatny (bez publicznego usernamu - większość kanałów z
   sygnałami tak ma). Żeby znaleźć ID:
   ```bash
   python list_chats.py premium
   ```
   (Pierwsze uruchomienie poprosi o numer telefonu i kod z Telegrama -
   jednorazowe logowanie, zapisuje się w pliku sesji `*.session`, nie
   commituj go.) Wypisze listę Twoich czatów pasujących do słowa "premium" z
   ID - skopiuj ID interesującego Cię kanału (razem ze znakiem "-", jeśli
   jest) do `TELEGRAM_CHANNEL`. Bez argumentu (`python list_chats.py`)
   wypisze wszystkie czaty.
3. `MT5_LOGIN` / `MT5_PASSWORD` / `MT5_SERVER` - zostaw puste, jeśli MT5
   jest już otwarty i zalogowany na koncie, na którym ma handlować bot.
4. Sprawdź `SYMBOL` (np. `XAUUSD`, czasem `XAUUSD.a` / `GOLD` zależnie od
   brokera) i `PIP_SIZE`.

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
list_chats.py           - jednorazowa pomoc: wypisuje Twoje czaty z ID
                          (do znalezienia ID prywatnego kanału bez usernamu)
login_qr.py             - alternatywne logowanie przez zeskanowanie kodu QR,
                          gdy przepisywanie kodu SMS/z Telegrama nie działa
```

## Logowanie do Telegrama nie działa (kod nieprawidłowy / nie przychodzi)

Jeśli `list_chats.py` albo `main.py` przy logowaniu ciągle piszą "Invalid
code" albo kod w ogóle nie przychodzi, zaloguj się zamiast tego przez kod
QR - omija to całkowicie wpisywanie kodu:

```bash
python login_qr.py
```

Wyświetli w terminalu kod QR (ASCII-art). Zeskanuj go telefonem: w
aplikacji Telegram wejdź w **Ustawienia -> Urządzenia -> Połącz biurkowe
urządzenie ("Link Desktop Device")** i zeskanuj kod aparatem w aplikacji
(nie zwykłym aparatem telefonu). Po zeskanowaniu logowanie kończy się
automatycznie i zapisuje się w tej samej sesji, której używają
`list_chats.py` i `main.py` - nie trzeba się logować drugi raz.

Częsta przyczyna błędu przy zwykłym logowaniu (numer + kod): w oknie cmd
komendy/tekst wpisane wcześniej "doklejają się" do kolejnych pytań, jeśli
wkleja się kilka linijek naraz. Wpisuj/wklejaj tylko jedną odpowiedź na raz
i czekaj na kolejne pytanie.
