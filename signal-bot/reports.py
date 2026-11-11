"""Okresy raportów i formatowanie podsumowań."""
from __future__ import annotations

import html
from collections import OrderedDict
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from storage import SignalRow

MONTHS = [
    "styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec",
    "lipiec", "sierpień", "wrzesień", "październik", "listopad", "grudzień",
]


def day_range(d: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(d, time.min, tz)
    return start, start + timedelta(days=1)


def week_range(d: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Tydzień poniedziałek–niedziela zawierający dzień d."""
    monday = d - timedelta(days=d.weekday())
    start = datetime.combine(monday, time.min, tz)
    return start, start + timedelta(days=7)


def month_range(d: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    first = d.replace(day=1)
    nxt = (first + timedelta(days=32)).replace(day=1)
    return datetime.combine(first, time.min, tz), datetime.combine(nxt, time.min, tz)


def is_last_day_of_month(d: date) -> bool:
    return (d + timedelta(days=1)).month != d.month


def _fmt(p: float) -> str:
    s = f"{p:+.1f}"
    return s[:-2] if s.endswith(".0") else s


def build_report(
    title: str,
    signals: list[SignalRow],
    strategies: list[str],
    strategy_names: dict[str, str],
    include_losses: bool,
    details: bool,
    tz: ZoneInfo,
) -> str:
    groups: "OrderedDict[str | None, list[SignalRow]]" = OrderedDict((s, []) for s in strategies)
    for s in signals:
        key = s.strategy if s.strategy in groups else None
        groups.setdefault(key, []).append(s)

    lines = [f"<b>{html.escape(title)}</b>", ""]
    total = 0.0
    total_signals = 0
    for key, rows in groups.items():
        if key is None and not rows:
            continue
        name = strategy_names.get(key, f"Strategia {key}") if key else "Bez strategii"
        gained = sum(r.pips for r in rows if r.max_tp > 0)
        lost = sum(r.loss_pips for r in rows if r.sl_hit)
        net = gained - lost if include_losses else gained
        n_tp = sum(1 for r in rows if r.max_tp > 0)
        n_sl = sum(1 for r in rows if r.sl_hit)
        n_open = len(rows) - n_tp - n_sl
        total += net
        total_signals += len(rows)

        lines.append(f"📈 <b>{html.escape(name)}</b>: <b>{_fmt(net)} pips</b>")
        stats = f"   Sygnały: {len(rows)} | z TP: {n_tp} | SL: {n_sl}"
        if n_open:
            stats += f" | w toku: {n_open}"
        lines.append(stats)
        if include_losses and n_sl:
            lines.append(f"   (TP: {_fmt(gained)} / SL: {_fmt(-lost)})")
        if details:
            for r in rows:
                t = r.created_at.astimezone(tz).strftime("%H:%M")
                if r.max_tp > 0:
                    res = f"TP{r.max_tp} ✅ {_fmt(r.pips)}"
                elif r.sl_hit:
                    res = f"SL ❌ {_fmt(-r.loss_pips)}" if include_losses else "SL ❌"
                else:
                    res = "⏳ w toku"
                lines.append(f"   • {t} {r.symbol} {r.direction} → {res}")
        lines.append("")

    if total_signals == 0:
        lines.append("Brak sygnałów w tym okresie.")
    else:
        lines.append(f"💰 <b>Razem: {_fmt(total)} pips</b> ({total_signals} sygnałów)")
    return "\n".join(lines)


def daily_title(d: date) -> str:
    return f"📊 Podsumowanie dnia {d:%d.%m.%Y}"


def weekly_title(start: datetime, end: datetime) -> str:
    last = (end - timedelta(days=1)).date()
    return f"📅 Podsumowanie tygodnia {start:%d.%m} – {last:%d.%m.%Y}"


def monthly_title(d: date) -> str:
    return f"🗓 Podsumowanie miesiąca: {MONTHS[d.month - 1]} {d.year}"
