"""Ustawienia bota bez ręcznej edycji .env (tylko biblioteka standardowa - działa przed instalacją).

    python -m signalbot.setup_env migrate     # znajdź stary folder bota, przenieś .env, strefy, historię, TV
    python -m signalbot.setup_env telegram    # wpisz token i chat ID Telegrama (chat ID może znaleźć sam)
    python -m signalbot.setup_env check       # co jest w .env (tokeny zamaskowane) + wiadomość testowa

Tokeny zostają tylko w pliku .env na tym komputerze.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent          # folder bota (tam gdzie .env)
ENV = HERE / ".env"

NEW_KEYS = {
    "PATTERNS_ENABLED": "true", "PATTERN_KINDS": "all", "PATTERN_DEPTHS": "2,4", "PATTERN_MIN_SCORE": "2",
    "PATTERN_AI_FILTER": "true", "PATTERN_MIN_CONFIDENCE": "60", "ZONES_FILE": "zones.json",
    "RISK_MODE": "atr", "SL_ATR": "2.0", "TP_R": "1,2,3,4,5",
}


def read_text(path: Path) -> str:
    """Notatnik potrafi zapisać .env jako UTF-8 z BOM, UTF-16 albo ANSI - czytamy każdy z nich."""
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    for enc in ("utf-8-sig", "cp1250", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def find_env(folder: Path) -> Path | None:
    """.env albo .env.txt (Notatnik często dopisuje .txt)."""
    for name in (".env", ".env.txt", "env.txt"):
        if (folder / name).is_file():
            return folder / name
    return None


def parse(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def set_keys(path: Path, values: dict) -> None:
    """Podmienia wartości kluczy w .env (zachowuje komentarze), brakujące dopisuje na końcu."""
    lines = read_text(path).splitlines() if path.exists() else []
    done = set()
    for i, line in enumerate(lines):
        k = line.split("=", 1)[0].strip()
        if "=" in line and not line.lstrip().startswith("#") and k in values:
            lines[i] = f"{k}={values[k]}"
            done.add(k)
    missing = [k for k in values if k not in done]
    if missing:
        lines += ["", "# ===== dopisane automatycznie ====="] + [f"{k}={values[k]}" for k in missing]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def mask(v: str) -> str:
    return "(PUSTE)" if not v else f"...{v[-4:]} ({len(v)} znaków)"


def _candidates() -> list[Path]:
    """Foldery z botem (signalbot/main.py) i plikiem .env - poza tym folderem."""
    home = Path.home()
    roots = [HERE.parent, home / "Desktop", home / "Pulpit", home / "Downloads", home / "Documents",
             home / "OneDrive" / "Desktop", home / "OneDrive" / "Pulpit", home / "OneDrive" / "Documents", home]
    drives = [Path(f"{d}:\\") for d in "CDEF" if os.name == "nt" and Path(f"{d}:\\").exists()]
    found, seen = [], set()
    for root in roots + drives:
        if not root.exists():
            continue
        for depth in range(0, 3 if root in drives else 4):
            for main in root.glob("/".join(["*"] * depth + ["signalbot", "main.py"])):
                folder = main.parent.parent.resolve()
                if folder == HERE or folder in seen:
                    continue
                seen.add(folder)
                env = find_env(folder)
                if env:
                    found.append(env)
    return sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)


def migrate(old: str | None = None) -> None:
    print("=== Przenoszę ustawienia ze starego bota ===")
    if old:
        env = find_env(Path(old.strip().strip('"')))
        cands = [env] if env else []
    else:
        print("Szukam starego folderu bota na dysku (może to potrwać chwilę)...")
        cands = _candidates()
    cands = [c for c in cands if parse(read_text(c)).get("TELEGRAM_BOT_TOKEN")] or cands
    if not cands:
        print("Nie znalazłem starego pliku .env z ustawieniami.")
        path = input("Wklej ścieżkę do STAREGO folderu bota (albo Enter, żeby wpisać token Telegrama ręcznie): ")
        if path.strip():
            return migrate(path)
        return telegram()
    for i, c in enumerate(cands, 1):
        v = parse(read_text(c))
        print(f"  {i}. {c}  (Telegram token {mask(v.get('TELEGRAM_BOT_TOKEN', ''))}, "
              f"chat {v.get('TELEGRAM_CHAT_ID') or '(PUSTE)'})")
    pick = input("Który przenieść? [1]: ").strip() or "1"
    src = cands[int(pick) - 1]
    old_dir = src.parent
    if ENV.exists():
        shutil.copy2(ENV, HERE / ".env.bak")
    ENV.write_text(read_text(src), encoding="utf-8")
    for name in ("zones.json",):
        if (old_dir / name).exists():
            shutil.copy2(old_dir / name, HERE / name)
    for name in ("data", "tv_profile"):
        if (old_dir / name).is_dir():
            shutil.copytree(old_dir / name, HERE / name, dirs_exist_ok=True)
    have = parse(read_text(ENV))
    add = {k: v for k, v in NEW_KEYS.items() if k not in have}
    if add:
        set_keys(ENV, add)
    print(f"\nPrzeniesione z {old_dir}: .env, strefy, historia sygnałów, logowanie TradingView.")
    if add:
        print("Dopisane nowe ustawienia: " + ", ".join(add))
    check(send=False)


def _api(token: str, method: str, params: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(params).encode() if params else None
    with urllib.request.urlopen(url, data=data, timeout=20) as r:
        return json.loads(r.read().decode())


def telegram() -> None:
    print("=== Telegram ===")
    cur = parse(read_text(ENV)) if ENV.exists() else {}
    print(f"Obecny token: {mask(cur.get('TELEGRAM_BOT_TOKEN', ''))}, chat ID: {cur.get('TELEGRAM_CHAT_ID') or '(PUSTE)'}")
    token = input("Token bota od @BotFather (Enter = zostaw obecny): ").strip() or cur.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("Bez tokena Telegram nie zadziała. Token znajdziesz u @BotFather: /mybots -> bot -> API Token.")
        return
    try:
        me = _api(token, "getMe")["result"]
        print(f"Token OK: @{me['username']}")
    except Exception as e:  # noqa: BLE001
        print(f"Telegram odrzucił token ({e}). Sprawdź, czy skopiowałeś cały token.")
        return
    chat = cur.get("TELEGRAM_CHAT_ID", "")
    ans = input(f"Chat ID [{chat or 'puste'}] (Enter = zostaw, 'szukaj' = znajdź automatycznie): ").strip()
    if ans.lower() == "szukaj" or (not ans and not chat):
        input("Napisz teraz dowolną wiadomość do bota (albo w grupie, gdzie bot jest adminem) i naciśnij Enter...")
        chats = {}
        for u in _api(token, "getUpdates").get("result", []):
            m = u.get("message") or u.get("channel_post") or u.get("my_chat_member") or {}
            c = m.get("chat")
            if c:
                chats[str(c["id"])] = c.get("title") or c.get("username") or c.get("first_name") or ""
        if not chats:
            print("Nie widzę wiadomości. Napisz do bota i uruchom ten skrypt jeszcze raz.")
            return
        for i, (cid, name) in enumerate(chats.items(), 1):
            print(f"  {i}. {cid}  {name}")
        pick = input("Który czat? [1]: ").strip() or "1"
        chat = list(chats)[int(pick) - 1]
    elif ans:
        chat = ans
    set_keys(ENV, {"TELEGRAM_ENABLED": "true", "TELEGRAM_BOT_TOKEN": token, "TELEGRAM_CHAT_ID": chat,
                   "DRY_RUN": "false"})
    print("Zapisane w .env.")
    check(send=True)


def check(send: bool = True) -> None:
    print("\n=== Sprawdzenie ustawień ===")
    env = find_env(HERE)
    if env is None:
        print(f"BRAK pliku .env w {HERE}. Uruchom 0_PRZENIES_USTAWIENIA.bat albo USTAW_TELEGRAM.bat.")
        return
    if env.name != ".env":
        shutil.copy2(env, ENV)
        print(f"Plik nazywał się {env.name} - skopiowałem go jako .env.")
    v = parse(read_text(ENV))
    on = lambda k, d="false": v.get(k, d).lower() in ("1", "true", "yes", "tak")  # noqa: E731
    print(f"Plik: {ENV}")
    print(f"DRY_RUN:          {v.get('DRY_RUN', 'true (domyślnie!)')}" + ("   <- bot NIC nie wysyła" if on("DRY_RUN", "true") else ""))
    print(f"Telegram:         {'włączony' if on('TELEGRAM_ENABLED') else 'WYŁĄCZONY'}, token {mask(v.get('TELEGRAM_BOT_TOKEN', ''))}, "
          f"chat {v.get('TELEGRAM_CHAT_ID') or '(PUSTE)'}")
    print(f"Threads / X:      {'tak' if on('THREADS_ENABLED') else 'nie'} / {'tak' if on('X_ENABLED') else 'nie'}")
    print(f"Dane:             {v.get('DATA_SOURCE', 'twelvedata')}  {v.get('SYMBOL', '')}  {v.get('TIMEFRAME', 'M30')}")
    print(f"Strategia:        {v.get('STRATEGY', 'fibzone')}, SL/TP: {v.get('RISK_MODE', 'atr')}, "
          f"formacje: {v.get('PATTERNS_ENABLED', 'true')}")
    print(f"AI (Anthropic):   klucz {mask(v.get('ANTHROPIC_API_KEY', ''))}")
    token, chat = v.get("TELEGRAM_BOT_TOKEN", ""), v.get("TELEGRAM_CHAT_ID", "")
    if send and token and chat:
        try:
            _api(token, "sendMessage", {"chat_id": chat, "text": "✅ Signal bot: ustawienia wczytane, Telegram działa."})
            print("Wiadomość testowa wysłana na Telegram ✅")
        except Exception as e:  # noqa: BLE001
            print(f"Telegram nie przyjął wiadomości: {e}  (bot musi być adminem grupy/kanału)")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    {"migrate": lambda: migrate(sys.argv[2] if len(sys.argv) > 2 else None), "telegram": telegram,
     "check": check, "status": lambda: check(send=False)}[cmd]()
