# Telegram -> MT5 signal bot

Nasłuchuje kanału Telegram z sygnałami w stylu "PREMIUM SIGNALS (TAKE PROFIT)"
i automatycznie wystawia w MT5 siatkę zleceń oczekujących pokrywającą całą
podaną strefę, po 0.01 lota co `ZONE_STEP` (domyślnie 0.5$), z drabinką TP
rosnącą co 10 pipsów od najniższej ceny w strefie (60 / 70 / 80 / 90 / 100 /
110 / ... pipsów, wg liczby zleceń w strefie). SL jest **jeden, wspólny dla
całej siatki** - odległość z sygnału (np. 60 pips) liczona od najgorszego
(najniższego dla BUY, najwyższego dla SELL) entry w strefie, nie osobno od
ceny wejścia każdego zlecenia.

## Jak bot faktycznie wystawia zlecenia

Python (ten kod) robi wszystko oprócz samego kliknięcia "kup/sprzedaj":
czyta kanał, parsuje sygnał, liczy siatkę cen/SL/TP, pilnuje 1:1 do
przesunięcia SL. Same zlecenia i zmiany SL są jednak wystawiane przez
**Expert Advisora działającego wewnątrz MT5** (`mt5_expert/TelegramBridgeEA.mq5`)
- Python zapisuje polecenie do pliku, EA je odczytuje i wykonuje. Powód:
  na części kont/buildów MT5 wywołania `order_send()` z zewnętrznego API
  Pythona są odrzucane (`retcode=10027 "AutoTrading disabled by client"`)
  mimo że przycisk Algo Trading jest włączony i ręczne zlecenia działają -
  EA handlujący "od środka" terminala nie ma tego problemu. Zobacz
  **`mt5_expert/README.md`** - instalacja jest wymagana, bez tego bot
  policzy zlecenia, ale nic się nie wystawi w MT5.

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
- **Powiadomienia na Telegram** (`NOTIFY_ENABLED=true`, domyślnie włączone,
  wymaga `DRY_RUN=false`): gdy zlecenie oczekujące faktycznie się wypełni
  (nie w momencie wystawienia - dopiero gdy cena je złapie), bot wysyła na
  Telegram (tą samą sesją co czyta kanał - `TELEGRAM_NOTIFY_CHAT`, domyślnie
  "me" czyli własne Zapisane Wiadomości) zrzut wykresu z EA + kierunek/
  entry/SL/TP/lot. Do tego raz dziennie o `DAILY_SUMMARY_TIME` (domyślnie
  23:55) wysyła podsumowanie: ile entry faktycznie złapaliśmy danego dnia
  (i ile lotów), ile pozycji się zamknęło i jaki łączny wynik (pipsy + $) -
  liczone z historii transakcji MT5, niezależnie od tego kiedy sygnał
  przyszedł. Zobacz **`mt5_expert/README.md`** sekcję "Powiadomienia..." -
  wymaga zaktualizowanego EA.

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
5. Zainstaluj `TelegramBridgeEA` w MT5 - patrz **`mt5_expert/README.md`**.
   Bez tego kroku bot nie wystawi żadnego zlecenia.

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

## Backtest na historii kanału i cenach z MT5

```bash
python backtest.py                       # wszystkie sygnały ZONE z historii kanału
python backtest.py --since 2026-06-01     # tylko sygnały od tej daty (UTC)
python backtest.py --csv wyniki.csv       # dodatkowo zapisz raport per-zlecenie do CSV
```

Ściąga CAŁĄ historię wiadomości kanału (Telethon), parsuje z niej sygnały
ZONE, i dla każdego symuluje - tym samym `plan_orders()` co live bot i
Twoimi aktualnymi ustawieniami z `.env` (loty, TP_MODE, EXIT_MODE,
zone extend...) - na prawdziwych świecach M1 dla `SYMBOL` ściągniętych z
Twojego terminala MT5 (`mt5.copy_rates_range`). Wymaga więc tego samego co
`main.py` na żywo: uruchomienia na Windows przy zalogowanym MT5. Nic nie
wystawia na MT5 i nic nie wysyła na Telegram - czysto analityczne, offline.

Wypisuje log per-sygnał (ile zleceń się wypełniło, ile zamknęło, wynik w
pipsach/$) i podsumowanie na końcu (win rate, suma pipsów/wyniku). Z
`--csv` dodatkowo zapisuje jedną linię per zlecenie (czas wypełnienia,
cena zamknięcia, powód: tp/sl/breakeven/trailing) do otwarcia w Excelu.

To jest **przybliżenie**, nie 1:1 z tym co by się stało live - świece M1
nie mówią co się działo w środku minuty, więc: zlecenie "wypełnia się" w
pierwszej świecy, której zakres dotknie ceny entry (bez spreadu/slippage);
jeśli SL i TP wypadają w tej samej świecy, SL wygrywa (bezpieczniejsze
założenie, nie przecenia wyniku); moment przesunięcia SL na BE / kroku
trailing liczony jest raz na świecę z jej ceny zamknięcia. Zobacz nagłówek
`backtester.py` po szczegóły.

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
mt5_executor.py        - czyta ceny/pozycje przez API, zlecenia/SL zleca
                          EA pisząc polecenia do wspólnego folderu (tylko Windows)
telegram_listener.py   - nasłuch kanału (Telethon)
notifier.py             - wysyłka powiadomień (screeny wypełnień, dzienne
                          podsumowanie) tą samą sesją Telethon
backtester.py            - czysta logika symulacji sygnał+świece -> wynik
                          (bez importów MT5/Telegram, testowalna tutaj)
backtest.py              - CLI: ściąga historię kanału + świece z MT5,
                          woła backtester.py, wypisuje raport/CSV
main.py                - spina wszystko, tryb live i --replay
list_chats.py           - jednorazowa pomoc: wypisuje Twoje czaty z ID
                          (do znalezienia ID prywatnego kanału bez usernamu)
login_qr.py             - alternatywne logowanie przez zeskanowanie kodu QR,
                          gdy przepisywanie kodu SMS/z Telegrama nie działa
mt5_expert/              - TelegramBridgeEA.mq5 + instrukcja instalacji -
                          EA w MT5, który faktycznie wystawia zlecenia
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
