"""Wykres formacji do posta w stylu TradingView (Lightweight Charts, jak chart_tv), z zapasem na matplotlib.

Rysuje: świece do potwierdzenia, linie formacji z etykietami (Top 1 / X A B C D), neckline albo PRZ,
Wasze strefy, które dały konfluencję, proporcje Fibo harmonicznych oraz wejście, SL i cele.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pandas as pd

from .chart_tv import ASSET
from .patterns import HARMONICS, Pattern

log = logging.getLogger(__name__)
W, H = 1400, 780
FUTURE = 24

HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;background:#fff;font-family:-apple-system,"Trebuchet MS",Roboto,Ubuntu,sans-serif}
#c{position:relative;width:%(w)dpx;height:%(h)dpx}
.ov{position:absolute;pointer-events:none;z-index:3}
#hdr{position:absolute;left:14px;top:10px;z-index:5;color:#131722;font-size:15px;line-height:1.45;
 background:rgba(255,255,255,.92);padding:6px 10px;border-radius:6px;max-width:760px}
#hdr b{font-size:18px}
.lab{position:absolute;z-index:4;font-size:13px;font-weight:700;padding:1px 6px;border-radius:4px;color:#fff;
 white-space:nowrap;transform:translate(-50%%,-50%%)}
</style></head><body><div id="c"><div id="hdr"></div></div>
<script>%(lib)s</script><script>
const D = %(data)s;
const el = document.getElementById('c');
const chart = LightweightCharts.createChart(el, {
  width: %(w)d, height: %(h)d,
  layout: {background: {color: '#ffffff'}, textColor: '#131722', fontSize: 13},
  grid: {vertLines: {color: '#f0f3fa'}, horzLines: {color: '#f0f3fa'}},
  rightPriceScale: {borderColor: '#d1d4dc', scaleMargins: {top: 0.08, bottom: 0.08}},
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
for (const L of D.levels)
  candles.createPriceLine({price: L.price, color: L.color, lineWidth: L.width, lineStyle: L.style,
    axisLabelVisible: true, title: L.title, lineVisible: true});
chart.timeScale().fitContent();
document.getElementById('hdr').innerHTML = D.header;

function settled() {
  const ts = chart.timeScale();
  const x0 = ts.timeToCoordinate(D.candles[0].time), xl = ts.timeToCoordinate(D.candles[D.candles.length - 1].time);
  const w = ts.width();
  return w > 0 && x0 !== null && xl !== null && x0 < 40 && xl > w * 0.5 && xl < w;
}
let tries = 0;
function drawWhenReady() {
  if (!settled() && tries++ < 100) { chart.timeScale().fitContent(); return setTimeout(drawWhenReady, 100); }
  draw();
}
setTimeout(drawWhenReady, 100);

function draw() {
  const ts = chart.timeScale(), paneW = ts.width();
  const X = t => ts.timeToCoordinate(t), Y = p => candles.priceToCoordinate(p);
  const box = (x1, x2, p1, p2, css, label, color) => {
    const y1 = Y(p1), y2 = Y(p2), d = document.createElement('div'); d.className = 'ov';
    d.style.cssText += `left:${x1}px;top:${Math.min(y1, y2)}px;width:${Math.max(1, x2 - x1)}px;height:${Math.max(2, Math.abs(y2 - y1))}px;${css}`;
    if (label) d.innerHTML = `<span style="position:absolute;right:8px;top:2px;font-weight:700;font-size:12px;color:${color}">${label}</span>`;
    el.appendChild(d);
  };
  for (const z of D.zones) box(Math.max(0, X(z.from) ?? 0), paneW, z.top, z.bot, `background:${z.fill};border-top:1px solid ${z.line};border-bottom:1px solid ${z.line}`, z.label, z.line);
  if (D.prz) box(Math.max(0, X(D.prz.from) ?? 0), paneW, D.prz.top, D.prz.bot, `background:rgba(156,39,176,.13);border:1px dashed #9c27b0`, 'PRZ', '#9c27b0');
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', 'ov'); svg.setAttribute('width', paneW); svg.setAttribute('height', %(h)d);
  svg.style.left = '0px'; svg.style.top = '0px';
  let s = '';
  const P = D.points.map(p => [X(p.time), Y(p.price)]);
  if (D.harmonic && P.length === 5) {
    s += `<polygon points="${[P[0], P[1], P[2]].map(q => q.join(',')).join(' ')}" fill="${D.color}" fill-opacity=".10"/>`;
    s += `<polygon points="${[P[2], P[3], P[4]].map(q => q.join(',')).join(' ')}" fill="${D.color}" fill-opacity=".10"/>`;
    for (const r of D.ratioLines) {
      const a = P[r.a], b = P[r.b];
      s += `<line x1="${a[0]}" y1="${a[1]}" x2="${b[0]}" y2="${b[1]}" stroke="#787b86" stroke-width="1.2" stroke-dasharray="5 4"/>`;
      s += `<text x="${(a[0] + b[0]) / 2}" y="${(a[1] + b[1]) / 2 - 4}" font-size="12" font-weight="600" fill="#5d606b" text-anchor="middle">${r.text}</text>`;
    }
  }
  const line = D.harmonic ? P : P.concat([[X(D.confirm.time), Y(D.confirm.price)]]);
  s += `<polyline points="${line.map(q => q.join(',')).join(' ')}" fill="none" stroke="${D.color}" stroke-width="2.5"/>`;
  if (D.neck) {
    const x1 = X(D.neck[0].time), x2 = X(D.neck[1].time);
    s += `<line x1="${x1}" y1="${Y(D.neck[0].price)}" x2="${x2}" y2="${Y(D.neck[1].price)}" stroke="#ff9800" stroke-width="2" stroke-dasharray="8 5"/>`;
    s += `<text x="${x1 + 4}" y="${Y(D.neck[0].price) + 16}" font-size="12" font-weight="700" fill="#ff9800">NECKLINE</text>`;
  }
  const xc = X(D.confirm.time);
  if (xc !== null) s += `<circle cx="${xc}" cy="${Y(D.confirm.price)}" r="6" fill="none" stroke="#2962ff" stroke-width="2.5"/>`;
  svg.innerHTML = s; el.appendChild(svg);
  D.points.forEach((p, i) => {
    if (!p.label) return;
    const d = document.createElement('div'); d.className = 'lab'; d.textContent = p.label;
    d.style.background = D.color; d.style.left = P[i][0] + 'px';
    d.style.top = (P[i][1] + (p.up ? -16 : 16)) + 'px'; el.appendChild(d);
  });
  window.__done = true;
}
</script></body></html>"""


def _ts(t) -> int:
    return int(pd.Timestamp(t).timestamp())


def chart_data(df: pd.DataFrame, pt: Pattern, title: str, timeframe: str, handle: str = "",
               source: str = "", lookback: int = 40) -> dict:
    end = pt.confirm_idx
    start = max(0, pt.points[0][0] - lookback)
    win = df.iloc[start : end + 1]
    step = int((df["time"].iloc[end] - df["time"].iloc[end - 1]).total_seconds())
    t_end = _ts(win["time"].iloc[-1])
    future = [t_end + step * (i + 1) for i in range(FUTURE)]
    tm = lambda i: _ts(df["time"].iloc[max(start, i)])  # noqa: E731
    sell = pt.direction == "SELL"
    col = "#f23645" if sell else "#089981"
    candles = [dict(time=_ts(r.time), open=r.open, high=r.high, low=r.low, close=r.close)
               for r in win.itertuples(index=False)]
    levels = [dict(price=pt.entry, color="#2962ff", width=2, style=0, title="ENTRY"),
              dict(price=pt.sl, color="#f23645", width=2, style=0, title="SL")]
    levels += [dict(price=x, color="#089981", width=1, style=2, title=f"TP{i + 1}") for i, x in enumerate(pt.tps)]
    harmonic = pt.family == "harmonic"
    # etykieta nad szczytem, pod dołkiem
    pts = []
    for k, (i, pr, lab) in enumerate(pt.points):
        nxt = pt.points[k + 1][1] if k + 1 < len(pt.points) else None
        prv = pt.points[k - 1][1] if k else None
        up = (pr >= (nxt if nxt is not None else prv)) if (nxt is not None or prv is not None) else True
        pts.append(dict(time=tm(i), price=float(pr), label=lab, up=bool(up)))
    ratio_lines = []
    if harmonic:
        r = pt.ratios
        g = HARMONICS[pt.kind]
        ratio_lines = [dict(a=0, b=2, text=f"{r.get('b', 0):.3f}"), dict(a=1, b=3, text=f"{r.get('c', 0):.3f}"),
                       dict(a=2, b=4, text=f"{r.get('cd', 0):.3f}")]
        if g["d_of"] == "XA":
            ratio_lines.append(dict(a=0, b=4, text=f"{r.get('d_xa', 0):.3f} XA"))
        else:
            ratio_lines.append(dict(a=3, b=4, text=f"{r.get('d_xc', 0):.3f} XC"))
    zones = []
    for key, label in (("zone_M", "ZONE"), ("zone_H1", "H1 ZONE"), ("zone_user", "KEY ZONE")):
        z = pt.details.get(key)
        if z:
            zones.append(dict(**{"from": tm(pt.points[0][0] - 10)}, bot=float(z[0]), top=float(z[1]), label=label,
                              fill="rgba(242,54,69,.10)" if sell else "rgba(8,153,129,.12)", line=col))
    prices = [win["low"].min(), win["high"].max(), pt.sl, *pt.tps]
    if pt.prz:
        prices += list(pt.prz)
    pad = (max(prices) - min(prices)) * 0.04
    neck = None
    if pt.neckline:
        (i1, p1), (i2, p2) = pt.neckline
        neck = [dict(time=tm(i1), price=float(p1)), dict(time=tm(i2), price=float(p2))]
    conf = " · ".join(pt.confluences) if pt.confluences else "no extra confluence"
    header = (f"<b>{title} · {timeframe}</b>{(' · ' + source) if source else ''}<br>"
              f"<span style='color:{col};font-weight:700'>{pt.name} · {pt.direction}</span>"
              f" &nbsp;Entry {pt.entry:.2f} &nbsp;SL {pt.sl:.2f}<br>"
              f"<span style='font-size:13px;color:#5d606b'>Confluence {pt.score}: {conf}</span>")
    return dict(candles=candles, future=future, levels=levels, points=pts, harmonic=harmonic,
                ratioLines=ratio_lines, zones=zones, neck=neck, color=col, handle=handle, header=header,
                prz=dict(**{"from": tm(pt.points[3][0])}, bot=float(pt.prz[0]), top=float(pt.prz[1])) if pt.prz else None,
                confirm=dict(time=_ts(df["time"].iloc[end]), price=float(pt.entry)),
                minPrice=float(min(prices) - pad), maxPrice=float(max(prices) + pad))


def render_pattern_tv(df: pd.DataFrame, pt: Pattern, path: Path, title: str, timeframe: str,
                      handle: str = "", source: str = "") -> Path:
    from playwright.sync_api import sync_playwright

    data = chart_data(df, pt, title, timeframe, handle, source)
    html = HTML % dict(w=W, h=H, lib=ASSET.read_text(encoding="utf-8"), data=json.dumps(data, default=float))
    path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        exe = os.environ.get("CHROMIUM_PATH")
        browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=2)
        page.set_content(html)
        page.wait_for_function("window.__done === true", timeout=30000)
        page.locator("#c").screenshot(path=str(path))
        browser.close()
    return path


def render_pattern_mpl(df: pd.DataFrame, pt: Pattern, path: Path, title: str, timeframe: str,
                       handle: str = "") -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    end = pt.confirm_idx
    start = max(0, pt.points[0][0] - 40)
    w = df.iloc[start : end + 1].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(14, 7.8), dpi=110)
    for i, r in enumerate(w.itertuples(index=False)):
        c = "#089981" if r.close >= r.open else "#f23645"
        ax.plot([i, i], [r.low, r.high], color=c, lw=0.8)
        ax.add_patch(plt.Rectangle((i - 0.35, min(r.open, r.close)), 0.7, abs(r.close - r.open) or 0.01, color=c))
    col = "#f23645" if pt.direction == "SELL" else "#089981"
    xs = [i - start for i, _, _ in pt.points]
    ax.plot(xs, [p for _, p, _ in pt.points], color=col, lw=2.2)
    for x, (_, p, lab) in zip(xs, pt.points):
        if lab:
            ax.annotate(lab, (x, p), ha="center", fontsize=10, fontweight="bold", color="white",
                        bbox=dict(boxstyle="round", fc=col, ec="none"))
    if pt.neckline:
        (i1, p1), (i2, p2) = pt.neckline
        ax.plot([i1 - start, i2 - start + 6], [p1, p2 + (p2 - p1) / max(1, i2 - i1) * 6], "--", color="#ff9800", lw=1.8)
    if pt.prz:
        ax.axhspan(pt.prz[0], pt.prz[1], xmin=0.6, color="#9c27b0", alpha=0.12)
    n = len(w) + 15
    for y, c, lab in [(pt.entry, "#2962ff", "ENTRY"), (pt.sl, "#f23645", "SL"),
                      *[(x, "#089981", f"TP{i + 1}") for i, x in enumerate(pt.tps)]]:
        ax.hlines(y, len(w) - 1, n, colors=c, lw=1.4)
        ax.text(n, y, f" {lab} {y:.2f}", color=c, va="center", fontsize=9)
    ax.set_xlim(-1, n + 8)
    ax.set_title(f"{title} · {timeframe} · {pt.name} {pt.direction}", loc="left", fontsize=13)
    if handle:
        ax.text(0.5, 0.5, handle, transform=ax.transAxes, fontsize=48, color="#131722", alpha=0.06,
                ha="center", va="center")
    ax.grid(alpha=0.2)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path


def render_pattern_chart(df: pd.DataFrame, pt: Pattern, path: Path, title: str, timeframe: str,
                         handle: str = "", source: str = "") -> Path:
    try:
        return render_pattern_tv(df, pt, path, title, timeframe, handle, source)
    except Exception as e:  # noqa: BLE001
        log.warning("Wykres TradingView formacji nie wyszedł (%s), matplotlib", e)
        return render_pattern_mpl(df, pt, path, title, timeframe, handle)
