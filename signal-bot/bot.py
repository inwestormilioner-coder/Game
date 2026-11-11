"""Bot Telegram: śledzi kanał z sygnałami i wysyła podsumowania pipsów
(dzienne, tygodniowe, miesięczne) z podziałem na strategie."""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import Update as TgUpdate
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

import reports
from signal_parser import StrategyMatcher, diff_updates, parse_signal, parse_update
from storage import Storage

load_dotenv()
logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("signal-bot")


# --- konfiguracja ---------------------------------------------------------

def _env_list(name: str) -> list[str]:
    return [x.strip() for x in os.getenv(name, "").split(",") if x.strip()]


BOT_TOKEN = os.environ["BOT_TOKEN"]
SOURCE_CHAT_ID = int(os.getenv("SOURCE_CHAT_ID", "0"))
REPORT_CHAT_IDS = [int(x) for x in _env_list("REPORT_CHAT_IDS")] or [SOURCE_CHAT_ID]
ADMIN_IDS = {int(x) for x in _env_list("ADMIN_IDS")}
TZ = ZoneInfo(os.getenv("TIMEZONE", "Europe/Warsaw"))
REPORT_TIME = time.fromisoformat(os.getenv("REPORT_TIME", "23:30")).replace(tzinfo=TZ)
WEEKLY_DAY = int(os.getenv("WEEKLY_DAY", "6"))  # 0=pon ... 6=niedziela
STRATEGIES = _env_list("STRATEGIES") or ["1", "2", "3"]
STRATEGY_NAMES = {s: os.getenv(f"STRATEGY_{s}_NAME", f"Strategia nr {s}") for s in STRATEGIES}
STRATEGY_REGEX = os.getenv("STRATEGY_REGEX") or None
INCLUDE_SL_LOSSES = os.getenv("INCLUDE_SL_LOSSES", "false").lower() in ("1", "true", "tak", "yes")
DAILY_DETAILS = os.getenv("DAILY_DETAILS", "true").lower() in ("1", "true", "tak", "yes")
FALLBACK_LAST_SIGNAL = os.getenv("FALLBACK_LAST_SIGNAL", "true").lower() in ("1", "true", "tak", "yes")
PIP_OVERRIDES = {
    k.split("=")[0].strip().upper(): float(k.split("=")[1]) for k in _env_list("PIP_SIZES") if "=" in k
}
DB_PATH = os.getenv("DB_PATH", "signals.db")

storage = Storage(DB_PATH, PIP_OVERRIDES)
strategies = StrategyMatcher(STRATEGY_REGEX)


# --- śledzenie kanału -----------------------------------------------------

async def on_post(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    chat = update.effective_chat
    if not msg or not chat:
        return
    if chat.id != SOURCE_CHAT_ID:
        if chat.type != "private":
            log.info("Wiadomość z czatu %s (%s) — nie jest ustawiony jako SOURCE_CHAT_ID", chat.id, chat.title)
        return
    text = msg.text or msg.caption or ""
    if not text.strip():
        return
    edited = bool(update.edited_message or update.edited_channel_post)

    if edited:
        existing = storage.get(chat.id, msg.message_id)
        if existing:
            # Edycja sygnału, np. dopisanie "✅" przy TP2
            u = diff_updates(parse_update(existing.raw_text), parse_update(text))
            storage.update_raw_text(existing.id, text)
            if not u.empty and storage.apply_update(existing, u):
                log.info("Edycja sygnału %s → %s", msg.message_id, storage.get(chat.id, msg.message_id))
            return

    sig = parse_signal(text, strategies)
    if sig and not msg.reply_to_message:
        storage.add_signal(chat.id, msg.message_id, msg.date, sig, text)
        log.info("Nowy sygnał #%s: %s %s strategia=%s TP=%s", msg.message_id, sig.symbol,
                 sig.direction, sig.strategy, sig.tps)
        if sig.strategy is None:
            log.warning("Nie rozpoznano strategii w sygnale #%s", msg.message_id)
        return

    u = parse_update(text)
    if u.empty:
        return
    target = None
    if msg.reply_to_message:
        target = storage.get(chat.id, msg.reply_to_message.message_id)
    if target is None and (u.symbol or FALLBACK_LAST_SIGNAL):
        target = storage.find_recent(chat.id, u.symbol)
    if target is None:
        log.info("Aktualizacja bez dopasowanego sygnału: %r", text[:80])
        return
    if storage.apply_update(target, u):
        log.info("Aktualizacja sygnału #%s → %s", target.message_id, storage.get(chat.id, target.message_id))


# --- raporty --------------------------------------------------------------

def make_report(kind: str, d: date) -> str:
    if kind == "day":
        start, end = reports.day_range(d, TZ)
        title, details = reports.daily_title(d), DAILY_DETAILS
    elif kind == "week":
        start, end = reports.week_range(d, TZ)
        title, details = reports.weekly_title(start, end), False
    else:
        start, end = reports.month_range(d, TZ)
        title, details = reports.monthly_title(d), False
    rows = storage.between(SOURCE_CHAT_ID, start, end)
    return reports.build_report(title, rows, STRATEGIES, STRATEGY_NAMES, INCLUDE_SL_LOSSES, details, TZ)


async def send_report(context: ContextTypes.DEFAULT_TYPE, kind: str, d: date) -> None:
    key = f"sent:{kind}:{d.isoformat()}"
    if storage.meta_get(key):
        return
    text = make_report(kind, d)
    for chat_id in REPORT_CHAT_IDS:
        try:
            await context.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML)
        except Exception:
            log.exception("Nie udało się wysłać raportu do %s", chat_id)
    storage.meta_set(key, datetime.now(TZ).isoformat())


async def scheduled(context: ContextTypes.DEFAULT_TYPE) -> None:
    today = datetime.now(TZ).date()
    await send_report(context, "day", today)
    if today.weekday() == WEEKLY_DAY:
        await send_report(context, "week", today)
    if reports.is_last_day_of_month(today):
        await send_report(context, "month", today)


# --- komendy (tylko dla adminów, w prywatnym czacie z botem) --------------

def _admin(update: TgUpdate) -> bool:
    u = update.effective_user
    return bool(u and (not ADMIN_IDS or u.id in ADMIN_IDS))


async def _reply(update: TgUpdate, text: str) -> None:
    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_start(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply(update, (
        f"Twoje ID: <code>{update.effective_user.id}</code>\n"
        f"ID tego czatu: <code>{update.effective_chat.id}</code>\n\n"
        "Komendy:\n"
        "/dzis, /wczoraj — raport dzienny\n"
        "/tydzien, /poprzedni_tydzien — raport tygodniowy\n"
        "/miesiac, /poprzedni_miesiac — raport miesięczny\n"
        "/tp &lt;id_wiadomości&gt; &lt;nr&gt; — ręcznie ustaw najwyższy TP\n"
        "/pips &lt;id_wiadomości&gt; &lt;pipsy&gt; — ręcznie ustaw pipsy\n"
        "/sl &lt;id_wiadomości&gt; — oznacz jako SL\n"
        "/usun &lt;id_wiadomości&gt; — usuń sygnał ze statystyk"
    ))


def _report_cmd(kind: str, shift: int):
    async def handler(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not _admin(update):
            return
        today = datetime.now(TZ).date()
        if kind == "day":
            d = today - timedelta(days=shift)
        elif kind == "week":
            d = today - timedelta(days=7 * shift)
        else:
            d = today.replace(day=1) - timedelta(days=1) if shift else today
        await _reply(update, make_report(kind, d))
    return handler


async def cmd_fix(update: TgUpdate, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _admin(update):
        return
    cmd = update.effective_message.text.split()[0].lstrip("/").split("@")[0]
    args = context.args
    try:
        mid = int(args[0])
        if cmd == "tp":
            row = storage.set_tp(SOURCE_CHAT_ID, mid, int(args[1]))
        elif cmd == "pips":
            row = storage.set_pips(SOURCE_CHAT_ID, mid, float(args[1].replace(",", ".")))
        elif cmd == "sl":
            row = storage.set_sl(SOURCE_CHAT_ID, mid)
        else:
            ok = storage.delete(SOURCE_CHAT_ID, mid)
            await _reply(update, "Usunięto." if ok else "Nie znaleziono sygnału.")
            return
    except (IndexError, ValueError):
        await _reply(update, "Złe argumenty. Zobacz /start")
        return
    if not row:
        await _reply(update, "Nie znaleziono sygnału o tym ID wiadomości.")
        return
    await _reply(update, f"OK: {row.symbol} {row.direction} → TP{row.max_tp}, {row.pips} pips, SL={row.sl_hit}")


def main() -> None:
    if not SOURCE_CHAT_ID:
        log.warning("SOURCE_CHAT_ID nie ustawione — bot tylko wypisze ID czatów, z których dostaje wiadomości.")
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("dzis", _report_cmd("day", 0)))
    app.add_handler(CommandHandler("wczoraj", _report_cmd("day", 1)))
    app.add_handler(CommandHandler("tydzien", _report_cmd("week", 0)))
    app.add_handler(CommandHandler("poprzedni_tydzien", _report_cmd("week", 1)))
    app.add_handler(CommandHandler("miesiac", _report_cmd("month", 0)))
    app.add_handler(CommandHandler("poprzedni_miesiac", _report_cmd("month", 1)))
    app.add_handler(CommandHandler(["tp", "pips", "sl", "usun"], cmd_fix))
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, on_post))

    app.job_queue.run_daily(scheduled, REPORT_TIME, name="reports")
    log.info("Bot działa. Raporty codziennie o %s (%s).", REPORT_TIME.strftime("%H:%M"), TZ.key)
    app.run_polling(allowed_updates=TgUpdate.ALL_TYPES)


if __name__ == "__main__":
    main()
