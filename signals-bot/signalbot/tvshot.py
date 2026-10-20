"""Zrzut ekranu Twojego wykresu z TradingView (Twój layout: TPZ, wskaźniki, rysunki).

Jednorazowe logowanie (otworzy się okno przeglądarki - zaloguj się do TradingView i zamknij okno):
    python -m signalbot.tvshot login
Test zrzutu:
    python -m signalbot.tvshot test

Sesja jest zapisana w folderze TV_PROFILE_DIR (domyślnie tv_profile/) - to jak zalogowana przeglądarka,
nie udostępniaj tego folderu nikomu.
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

log = logging.getLogger(__name__)

TF_TO_TV = {"M1": "1", "M5": "5", "M15": "15", "M30": "30", "H1": "60", "H4": "240", "D1": "D"}
W, H = 1600, 900


def chart_url(base: str, tv_symbol: str, timeframe: str) -> str:
    u = urlparse(base or "https://www.tradingview.com/chart/")
    q = dict(parse_qsl(u.query))
    if tv_symbol:
        q["symbol"] = tv_symbol
    q["interval"] = TF_TO_TV.get(timeframe, timeframe)
    return urlunparse(u._replace(query=urlencode(q)))


def login(profile_dir: str) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(profile_dir, headless=False, viewport={"width": W, "height": H})
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.tradingview.com/accounts/signin/")
        print("Zaloguj się do TradingView w otwartym oknie, potem ZAMKNIJ okno przeglądarki.")
        try:
            page.wait_for_event("close", timeout=0)
        except Exception:  # noqa: BLE001
            pass
        ctx.close()
    print(f"Sesja zapisana w {profile_dir}")


def capture(url: str, path: Path, profile_dir: str, wait_s: float = 8.0, headless: bool = True) -> Path:
    """Otwiera wykres i zapisuje zrzut obszaru wykresu (bez bocznych pasków narzędzi)."""
    from playwright.sync_api import sync_playwright

    path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(profile_dir, headless=headless,
                                                   viewport={"width": W, "height": H}, device_scale_factor=2)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector("canvas", timeout=60000)
            time.sleep(wait_s)                      # wskaźniki (TPZ itd.) potrzebują chwili na przeliczenie
            page.keyboard.press("Escape")           # zamyka ewentualne okienka
            target = None
            for sel in (".layout__area--center", ".chart-container", ".chart-markup-table"):
                loc = page.locator(sel).first
                if loc.count():
                    target = loc
                    break
            (target or page).screenshot(path=str(path))
        finally:
            ctx.close()
    return path


def capture_for(cfg, path: Path) -> Path | None:
    """Zrzut wg ustawień z .env; None, jeśli się nie udało (bot użyje własnego wykresu)."""
    try:
        url = chart_url(cfg.tv_chart_url, cfg.tv_symbol, cfg.timeframe)
        return capture(url, path, cfg.tv_profile_dir)
    except Exception as e:  # noqa: BLE001
        log.warning("Zrzut z TradingView nie wyszedł (%s) - używam własnego wykresu", e)
        return None


def main() -> None:
    from .config import load_config

    logging.basicConfig(level=logging.INFO)
    cfg = load_config()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "test"
    if cmd == "login":
        login(cfg.tv_profile_dir)
    else:
        out = capture(chart_url(cfg.tv_chart_url, cfg.tv_symbol, cfg.timeframe),
                      cfg.data_dir / "tv_test.png", cfg.tv_profile_dir, headless=False)
        print(f"Zrzut zapisany: {out}")


if __name__ == "__main__":
    main()
