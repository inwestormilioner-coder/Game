"""Wykres setupu "odbicie od strefy + Fibo" do posta."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import mplfinance as mpf  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

from .fibzone import FIB_TPS, FibTrade  # noqa: E402

RED, GREEN, BLUE, GREY = "#d32f2f", "#26a69a", "#2962ff", "#555555"


def _trendline(vals: np.ndarray, end: int, short: int, long: int, lowest: bool):
    """Linia jak w TrendLineSample: ekstremum w [short+1, long] -> ekstremum w [1, short] świec wstecz."""
    pick = np.argmin if lowest else np.argmax
    x2 = end - short + int(pick(vals[end - short : end]))
    x1 = end - long + int(pick(vals[end - long : end - short]))
    return x1, vals[x1], x2, vals[x2]


def render_fib(df: pd.DataFrame, tr: FibTrade, path: Path, title: str, timeframe: str,
               lookback: int = 110, tl_short: int = 30, tl_long: int = 100, handle: str = "") -> Path:
    end = tr.entry_idx
    start = max(0, end - lookback)
    win = df.iloc[start : end + 1].copy()
    win.index = pd.DatetimeIndex(win["time"]).tz_convert(None)
    x = lambda i: i - start  # noqa: E731
    style = mpf.make_marketcolors(up=GREEN, down=RED, edge="inherit", wick="inherit")
    fig, axes = mpf.plot(win[["open", "high", "low", "close"]], type="candle", returnfig=True, figsize=(12, 6.8),
                         style=mpf.make_mpf_style(marketcolors=style, gridstyle=":", gridcolor="#e5e5e5",
                                                  facecolor="white", y_on_right=True),
                         datetime_format="%d %b %H:%M", xrotation=0, tight_layout=True)
    ax = axes[0]
    last, right = len(win) - 1, len(win) - 1 + 34
    ax.set_xlim(-1, right)
    buy = tr.direction == "BUY"
    rng = tr.fib1 - tr.fib0
    lvl = lambda f: tr.fib0 + f * rng  # noqa: E731

    ys = [lvl(-0.1272), lvl(1.618), win["low"].min(), win["high"].max()]
    pad = (max(ys) - min(ys)) * 0.04
    ax.set_ylim(min(ys) - pad, max(ys) + pad)

    # strefa
    zc = GREEN if buy else RED
    ax.add_patch(Rectangle((-1, tr.zone_bot), right + 1, tr.zone_top - tr.zone_bot, fc=zc, alpha=0.13, ec=zc, lw=0.8))
    ax.text(1, (tr.zone_bot + tr.zone_top) / 2, ("BUY ZONE" if buy else "SELL ZONE"), color=zc, fontsize=8,
            fontweight="bold", va="center")

    # linie trendu (z danych do świecy wejścia)
    for vals, lowest, col in ((df["low"].to_numpy(), True, GREEN), (df["high"].to_numpy(), False, RED)):
        if end - tl_long >= 0:
            x1, y1, x2, y2 = _trendline(vals, end, tl_short, tl_long, lowest)
            slope = (y2 - y1) / (x2 - x1)
            xa, xb = max(x1, start), end + 34
            ax.plot([x(xa), x(xb)], [y1 + slope * (xa - x1), y1 + slope * (xb - x1)], color=col, lw=1.6, alpha=0.8)

    # Fibo
    fx = x(max(tr.fib1_idx, start))
    for f in (-0.1272, 0.0, 0.1272, *FIB_TPS):
        y = lvl(f)
        if f == 0.1272:
            col, lw, tag = BLUE, 1.8, f"ENTRY {'BUY' if buy else 'SELL'} STOP"
        elif f == -0.1272:
            col, lw, tag = RED, 1.8, "SL"
        elif f in FIB_TPS:
            col, lw, tag = GREEN, 0.9, f"TP{FIB_TPS.index(f) + 1}"
        else:
            col, lw, tag = GREY, 0.9, ""
        ax.hlines(y, fx, right, colors=col, lw=lw, ls="-" if tag in ("SL",) or tag.startswith("ENTRY") else "--",
                  alpha=0.85, zorder=3)
        ax.text(right - 0.5, y, f"{tag}  {f:g} ({y:.2f})".strip(), color="white", fontsize=7, ha="right", va="center",
                fontweight="bold", bbox=dict(boxstyle="square,pad=0.2", fc=col, ec=col), zorder=6)

    ax.annotate("", xy=(right - 10, lvl(1.0)), xytext=(last + 1, tr.entry),
                arrowprops=dict(arrowstyle="-|>", color=GREEN if buy else RED, lw=2))
    ax.set_title(f"{title} {timeframe} — {tr.direction} STOP z odbicia od strefy (Fibo)", loc="left",
                 fontsize=11, fontweight="bold")
    if handle:
        ax.text(0.5, 0.5, handle, transform=ax.transAxes, fontsize=34, color="#000000", alpha=0.06,
                ha="center", va="center", fontweight="bold")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130, facecolor="white", bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)
    return path
