"""Wykres PNG z naniesionym setupem (strefa, BOS/CHOCH, retest, wejście, SL, TP)."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import mplfinance as mpf  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

from .strategy import Setup  # noqa: E402

RED, GREEN, GREY = "#d32f2f", "#26a69a", "#555555"
FUTURE_BARS = 28


def _label(ax, x, y, text, color, ha="left", va="center", fontsize=8):
    ax.text(x, y, text, color="white", fontsize=fontsize, ha=ha, va=va, fontweight="bold",
            bbox=dict(boxstyle="square,pad=0.25", fc=color, ec=color), zorder=6)


def render_chart(df: pd.DataFrame, s: Setup, path: Path, title: str, timeframe: str,
                 lookback: int = 60) -> Path:
    start = max(0, min(s.swing_idx - 25, s.confirm_idx - lookback))
    win = df.iloc[start : s.confirm_idx + 1].copy()
    win.index = pd.DatetimeIndex(win["time"]).tz_convert(None)
    x = lambda i: i - start  # noqa: E731  indeks świecy -> pozycja na osi

    style = mpf.make_marketcolors(up=GREEN, down=RED, edge="inherit", wick="inherit")
    fig, axes = mpf.plot(
        win[["open", "high", "low", "close"]], type="candle", returnfig=True, figsize=(12, 6.5),
        style=mpf.make_mpf_style(marketcolors=style, gridstyle=":", gridcolor="#e5e5e5",
                                 facecolor="white", y_on_right=True),
        xrotation=0, datetime_format="%d %b %H:%M", tight_layout=True,
    )
    ax = axes[0]
    last = len(win) - 1
    right = last + FUTURE_BARS
    ax.set_xlim(-1, right)

    sell = s.direction == "SELL"
    lo = min(win["low"].min(), s.tp, s.sl)
    hi = max(win["high"].max(), s.tp, s.sl)
    pad = (hi - lo) * 0.06
    ax.set_ylim(lo - pad, hi + pad)

    # strefa podaży / popytu
    zx = x(s.swing_idx)
    zone_color = RED if sell else GREEN
    ax.add_patch(Rectangle((zx, s.zone_low), right - zx, s.zone_high - s.zone_low,
                           fc=zone_color, alpha=0.10, ec=zone_color, lw=1, zorder=1))
    zone_name = "Resistance / Supply Zone" if sell else "Support / Demand Zone"
    _label(ax, right - 1, s.zone_high if sell else s.zone_low, zone_name, zone_color,
           ha="right", va="bottom" if sell else "top")

    # linie: wejście, SL, TP
    ax.hlines(s.entry, zx, right, colors=GREY, lw=1.2, zorder=3)
    ax.hlines(s.sl, x(s.retest_idx), right, colors=RED, lw=1, ls="--", zorder=3)
    ax.hlines(s.tp, x(s.extreme_idx), right, colors=GREEN, lw=1.2, zorder=3)
    _label(ax, right - 1, s.entry, f"Entry {s.entry:.2f}", GREY, ha="right")
    _label(ax, right - 1, s.sl, f"SL {s.sl:.2f}", RED, ha="right")
    _label(ax, right - 1, s.tp, f"TP {s.tp:.2f}", GREEN, ha="right")

    # BOS / CHOCH
    bx = x(s.break_idx)
    ax.hlines(s.level, zx, bx, colors=zone_color, lw=1.2, ls=":", zorder=3)
    _label(ax, (zx + bx) / 2, s.level, s.break_type, zone_color, ha="center",
           va="top" if sell else "bottom", fontsize=7)

    # retest
    rx = x(s.retest_idx)
    ry = win["high"].iloc[rx] if sell else win["low"].iloc[rx]
    ax.annotate("Retest", (rx, ry), xytext=(rx - 14, ry + (1.5 * pad if sell else -1.5 * pad)),
                fontsize=8, color=GREY, ha="center",
                arrowprops=dict(arrowstyle="->", color=GREY, lw=1))

    # Fibo impulsu: 0.5 / 0.618 / 0.786
    fx = x(s.break_idx)
    for lvl in (0.5, 0.618, 0.786):
        y = s.leg_end + (s.leg_start - s.leg_end) * lvl
        ax.hlines(y, fx, last + 3, colors="#7e57c2", lw=0.8, ls="--", alpha=0.7, zorder=2)
        ax.text(last + 3.5, y, f"{lvl:g}", color="#7e57c2", fontsize=7, ha="left", va="center")

    # FVG
    if s.fvg_low is not None:
        ax.add_patch(Rectangle((fx, s.fvg_low), right - fx, s.fvg_high - s.fvg_low,
                               fc="#7e57c2", alpha=0.15, ec="#7e57c2", lw=0.8, ls=":", zorder=1))
        ax.text(right - 1, (s.fvg_low + s.fvg_high) / 2, "FVG", color="#7e57c2", fontsize=8,
                ha="right", va="center", fontweight="bold", zorder=6)

    # płynność: zebrana (sweep) i docelowa
    if s.sweep_price is not None:
        ax.hlines(s.sweep_price, zx - 10, x(s.retest_idx), colors="#ef6c00", lw=1, zorder=3)
        ax.text(zx - 10, s.sweep_price, ("BSL" if sell else "SSL") + " sweep", color="#ef6c00",
                fontsize=7, ha="left", va="bottom" if sell else "top", fontweight="bold")
    if s.liq_target is not None and s.liq_target != s.tp:
        ax.hlines(s.liq_target, 0, right, colors="#ef6c00", lw=1, ls="-.", zorder=2)
        _label(ax, right - 1, s.liq_target, ("SSL" if sell else "BSL") + " liquidity", "#ef6c00",
               ha="right")
        ax.set_ylim(min(ax.get_ylim()[0], s.liq_target - pad), max(ax.get_ylim()[1], s.liq_target + pad))

    # strzałka do celu
    ax.annotate("", xy=(right - 8, s.tp), xytext=(last + 1, s.entry),
                arrowprops=dict(arrowstyle="-|>", color=GREEN if not sell else RED, lw=2))

    ax.set_title(f"{title}  {timeframe}  —  {s.direction} ({s.break_type})  RR 1:{s.rr:.1f}",
                 loc="left", fontsize=11, fontweight="bold")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130, facecolor="white", bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)
    return path
