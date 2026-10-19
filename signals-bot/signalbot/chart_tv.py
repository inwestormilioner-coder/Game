"""TradingView-style chart for posts, drawn with TradingView Lightweight Charts™ (Apache 2.0,
bundled in assets/) and captured with a headless browser (Playwright + Chromium).

Same broker candles the bot trades on, so the picture matches MT5 / TradingView.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from .chart_fib import _trendline
from .fibzone import FibTrade
from .structure import volume_profile

ASSET = Path(__file__).parent / "assets" / "lightweight-charts.js"
W, H = 1400, 780
FUTURE = 26

HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;background:#fff;font-family:-apple-system,"Trebuchet MS",Roboto,Ubuntu,sans-serif}
#c{position:relative;width:%(w)dpx;height:%(h)dpx}
.ov{position:absolute;pointer-events:none;z-index:3}
#hdr{position:absolute;left:14px;top:10px;z-index:5;color:#131722;font-size:15px;line-height:1.45;
 background:rgba(255,255,255,.92);padding:6px 10px;border-radius:6px}
#hdr b{font-size:18px}
</style></head><body><div id="c"><div id="hdr"></div></div>
<script>%(lib)s</script><script>
const D = %(data)s;
const el = document.getElementById('c');
const chart = LightweightCharts.createChart(el, {
  width: %(w)d, height: %(h)d,
  layout: {background: {color: '#ffffff'}, textColor: '#131722', fontSize: 13},
  grid: {vertLines: {color: '#f0f3fa'}, horzLines: {color: '#f0f3fa'}},
  rightPriceScale: {borderColor: '#d1d4dc', scaleMargins: {top: 0.06, bottom: 0.12}},
  timeScale: {borderColor: '#d1d4dc', timeVisible: true, secondsVisible: false, rightOffset: 2},
  crosshair: {mode: 0},
  watermark: {visible: !!D.handle, text: D.handle, fontSize: 56, color: 'rgba(19,23,34,0.06)'},
});
const lo = D.minPrice, hi = D.maxPrice;
const candles = chart.addCandlestickSeries({
  upColor: '#089981', downColor: '#f23645', borderVisible: false,
  wickUpColor: '#089981', wickDownColor: '#f23645', priceLineVisible: false,
  autoscaleInfoProvider: () => ({priceRange: {minValue: lo, maxValue: hi}}),
});
candles.setData(D.candles.concat(D.future.map(t => ({time: t}))));
if (D.volume.length) {
  const vol = chart.addHistogramSeries({priceScaleId: 'vol', priceFormat: {type: 'volume'}, lastValueVisible: false, priceLineVisible: false});
  chart.priceScale('vol').applyOptions({scaleMargins: {top: 0.88, bottom: 0}});
  vol.setData(D.volume);
}
for (const tl of D.trendlines) {
  const s = chart.addLineSeries({color: tl.color, lineWidth: 2, lastValueVisible: false, priceLineVisible: false,
    crosshairMarkerVisible: false, autoscaleInfoProvider: () => null});
  s.setData(tl.points);
}
for (const L of D.levels) {
  candles.createPriceLine({price: L.price, color: L.color, lineWidth: L.width, lineStyle: L.style,
    axisLabelVisible: true, title: '', lineVisible: false});
}
chart.timeScale().fitContent();
document.getElementById('hdr').innerHTML = D.header;

setTimeout(() => {
  const ts = chart.timeScale(), paneW = ts.width();
  const box = (x1, x2, yTop, yBot, css) => {
    const d = document.createElement('div'); d.className = 'ov';
    d.style.cssText += `left:${x1}px;top:${Math.min(yTop, yBot)}px;width:${Math.max(1, x2 - x1)}px;height:${Math.abs(yBot - yTop)}px;${css}`;
    el.appendChild(d); return d;
  };
  // zone
  const zx = Math.max(0, ts.timeToCoordinate(D.zone.from) ?? 0);
  const z = box(zx, paneW, candles.priceToCoordinate(D.zone.top), candles.priceToCoordinate(D.zone.bot),
    `background:${D.zone.fill};border-top:1px solid ${D.zone.line};border-bottom:1px solid ${D.zone.line}`);
  z.innerHTML = `<span style="position:absolute;left:8px;top:50%%;transform:translateY(-50%%);font-weight:700;font-size:13px;color:${D.zone.line}">${D.zone.label}</span>`;
  // volume profile (left)
  if (D.vp) {
    const maxW = paneW * 0.13;
    D.vp.bins.forEach(b => box(0, b.w * maxW, candles.priceToCoordinate(b.hi) + 1, candles.priceToCoordinate(b.lo),
      `background:${b.va ? 'rgba(41,98,255,.22)' : 'rgba(120,123,134,.16)'}`));
  }
  // Fibonacci retracement (jak narzędzie Fib w TradingView)
  const F = D.fib, fx = Math.max(0, ts.timeToCoordinate(F.from) ?? 0);
  const ys = F.levels.map(L => candles.priceToCoordinate(L.price));
  for (let i = 0; i + 1 < F.levels.length; i++)
    box(fx, paneW, ys[i], ys[i + 1], `background:${F.levels[i].band}`);
  F.levels.forEach((L, i) => {
    box(fx, paneW, ys[i], ys[i] + (L.strong ? 2 : 1), `background:${L.color}`);
    const t = document.createElement('div'); t.className = 'ov';
    t.style.cssText += `right:${%(w)d - paneW + 8}px;top:${ys[i] - 17}px;font-size:12px;font-weight:${L.strong ? 700 : 500};color:${L.color};white-space:nowrap;background:rgba(255,255,255,.75);padding:0 3px`;
    t.textContent = `${L.label}${L.f} (${L.price.toFixed(2)})`; el.appendChild(t);
  });
  const x0 = ts.timeToCoordinate(F.diag.t0), x1 = ts.timeToCoordinate(F.diag.t1);
  if (x0 !== null && x1 !== null) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'ov'); svg.setAttribute('width', paneW); svg.setAttribute('height', %(h)d);
    svg.style.left = '0px'; svg.style.top = '0px';
    svg.innerHTML = `<line x1="${x1}" y1="${candles.priceToCoordinate(F.diag.p1)}" x2="${x0}" y2="${candles.priceToCoordinate(F.diag.p0)}" stroke="#787b86" stroke-width="1.5" stroke-dasharray="6 5"/>`;
    el.appendChild(svg);
  }
  window.__done = true;
}, 400);
</script></body></html>"""


def _ts(t) -> int:
    return int(pd.Timestamp(t).timestamp())


def render_fib_tv(df: pd.DataFrame, tr: FibTrade, path: Path, title: str, timeframe: str,
                  lookback: int = 90, tl_short: int = 30, tl_long: int = 100, handle: str = "",
                  source: str = "") -> Path:
    from playwright.sync_api import sync_playwright

    end = tr.entry_idx
    start = max(0, end - lookback)
    win = df.iloc[start : end + 1]
    step = int((df["time"].iloc[end] - df["time"].iloc[end - 1]).total_seconds())
    t_end = _ts(win["time"].iloc[-1])
    future = [t_end + step * (i + 1) for i in range(FUTURE)]
    buy = tr.direction == "BUY"
    rng = tr.fib1 - tr.fib0
    lv = lambda f: tr.fib0 + f * rng  # noqa: E731
    entry = lv(0.1272)

    candles = [dict(time=_ts(r.time), open=r.open, high=r.high, low=r.low, close=r.close)
               for r in win.itertuples(index=False)]
    volume = []
    if "volume" in win.columns:
        volume = [dict(time=_ts(r.time), value=float(r.volume),
                       color="rgba(8,153,129,.35)" if r.close >= r.open else "rgba(242,54,69,.35)")
                  for r in win.itertuples(index=False)]

    levels = [dict(price=entry, color="#2962ff", width=2, style=0, title="ENTRY"),
              dict(price=tr.sl, color="#f23645", width=2, style=0, title="SL"),
              dict(price=tr.fib0, color="#787b86", width=1, style=1, title="0")]
    for i, f in enumerate(tr.tp_fibs):
        levels.append(dict(price=lv(f), color="#089981", width=1, style=2, title=f"TP{i + 1} ({f:g})"))

    trendlines = []
    if end - tl_long >= 0:
        for vals, lowest, col in ((df["low"].to_numpy(), True, "rgba(8,153,129,.55)"),
                                  (df["high"].to_numpy(), False, "rgba(242,54,69,.55)")):
            x1, y1, x2, y2 = _trendline(vals, end, tl_short, tl_long, lowest)
            k = (y2 - y1) / (x2 - x1)
            a = max(x1, start)
            trendlines.append(dict(color=col, points=[
                dict(time=_ts(df["time"].iloc[a]), value=float(y1 + k * (a - x1))),
                dict(time=future[-1], value=float(y1 + k * (end + FUTURE - x1)))]))

    # Fibo: wszystkie poziomy jak w narzędziu TradingView
    palette = {-0.1272: "#f23645", 0.0: "#787b86", 0.1272: "#2962ff", 0.236: "#f7525f", 0.382: "#ff9800",
               0.5: "#4caf50", 0.618: "#089981", 0.705: "#00bcd4", 0.786: "#2196f3", 1.0: "#787b86",
               1.272: "#9c27b0", 1.618: "#673ab7"}
    fib_levels = []
    for f, c in sorted(palette.items(), key=lambda kv: lv(kv[0])):
        tag = "SL · " if f == -0.1272 else "ENTRY · " if f == 0.1272 else ""
        if f in tr.tp_fibs:
            tag = f"TP{list(tr.tp_fibs).index(f) + 1} · "
        fib_levels.append(dict(f=f"{f:g}", price=float(lv(f)), color=c, label=tag, strong=bool(tag),
                               band=c + "14"))
    seg = df.iloc[tr.fib1_idx : end + 1]
    i0 = tr.fib1_idx + int(np.argmin(seg["low"].to_numpy()) if buy else np.argmax(seg["high"].to_numpy()))
    fib = dict(from_=None, levels=fib_levels,
               diag=dict(t1=_ts(df["time"].iloc[max(start, tr.fib1_idx)]), p1=float(tr.fib1),
                         t0=_ts(df["time"].iloc[i0]), p0=float(tr.fib0)))
    prices = [win["low"].min(), win["high"].max(), lv(-0.1272), lv(1.618)]
    pad = (max(prices) - min(prices)) * 0.03
    vp = None
    prof = volume_profile(df, end, 200, bins=48)
    if prof is not None:
        mx = prof.volume.max()
        vp = dict(bins=[dict(lo=float(prof.edges[i]), hi=float(prof.edges[i + 1]), w=float(prof.volume[i] / mx),
                             va=bool(prof.val <= (prof.edges[i] + prof.edges[i + 1]) / 2 <= prof.vah))
                        for i in range(len(prof.volume))
                        if prof.edges[i] >= min(prices) - pad and prof.edges[i + 1] <= max(prices) + pad])

    col = "#089981" if buy else "#f23645"
    header = (f"<b>{title} · {timeframe}</b>{(' · ' + source) if source else ''}<br>"
              f"<span style='color:{col};font-weight:700'>{tr.direction}</span> {entry:.2f} &nbsp;"
              f"SL {tr.sl:.2f}")
    data = dict(
        candles=candles, future=future, volume=volume, levels=levels, trendlines=trendlines, vp=vp,
        minPrice=float(min(prices) - pad), maxPrice=float(max(prices) + pad), handle=handle, header=header,
        zone=dict(from_=None, top=float(tr.zone_top), bot=float(tr.zone_bot),
                  label="BUY ZONE" if buy else "SELL ZONE",
                  fill="rgba(8,153,129,.12)" if buy else "rgba(242,54,69,.10)", line=col),
    )
    zone_from = _ts(df["time"].iloc[max(start, tr.fib1_idx)])
    fib["from"] = zone_from
    fib.pop("from_")
    data["fib"] = fib
    data["zone"]["from"] = zone_from
    data["zone"].pop("from_")

    html = HTML % dict(w=W, h=H, lib=ASSET.read_text(encoding="utf-8"), data=json.dumps(data, default=float))
    path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        exe = os.environ.get("CHROMIUM_PATH")  # opcjonalnie: własna przeglądarka
        browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=2)
        page.set_content(html)
        page.wait_for_function("window.__done === true", timeout=15000)
        page.locator("#c").screenshot(path=str(path))
        browser.close()
    return path


def render_post_chart(df: pd.DataFrame, tr: FibTrade, path: Path, title: str, timeframe: str,
                      handle: str = "", source: str = "") -> Path:
    """TradingView-style chart; falls back to matplotlib if the browser is not available."""
    try:
        return render_fib_tv(df, tr, path, title, timeframe, handle=handle, source=source)
    except Exception as e:  # noqa: BLE001 - any browser problem -> simple chart
        import logging

        logging.getLogger(__name__).warning("TradingView-style chart failed (%s), using matplotlib", e)
        from .chart_fib import render_fib

        return render_fib(df, tr, path, title, timeframe, handle=handle)
