import numpy as np
import pandas as pd
import pytest

from signalbot.data import SyntheticProvider
from signalbot.patterns import (PatternParams, Zone, find_patterns, harmonic_prz, match_harmonic,
                                score_pattern, atr_array, simulate)


def path_df(points, base=1000.0, noise=0.0, seed=0):
    """Ścieżka zamknięć z odcinków liniowych [(cena, świece), ...], świece M15."""
    closes = [points[0][0]]
    for price, n in points[1:]:
        closes += list(np.linspace(closes[-1], price, n + 1)[1:])
    closes = np.array(closes, dtype=float) + base
    if noise:
        closes += np.random.default_rng(seed).normal(0, noise, len(closes))
    opens = np.r_[closes[0], closes[:-1]]
    return pd.DataFrame(dict(
        time=pd.date_range("2026-03-02", periods=len(closes), freq="15min", tz="UTC"),
        open=opens, close=closes,
        high=np.maximum(opens, closes) + 0.3, low=np.minimum(opens, closes) - 0.3,
        volume=np.full(len(closes), 100.0),
    ))


P = PatternParams(depths=(2.0,))
WARM = [(0, 0), (2, 20), (0, 20)]                # rozgrzewka ATR


def kinds(df, p=P):
    return [(x.kind, x.direction) for x in find_patterns(df, p)]


def test_double_top_sell_on_neckline_break():
    df = path_df(WARM + [(-10, 12), (20, 15), (8, 10), (20.3, 10), (-5, 18)])
    pats = [x for x in find_patterns(df, P) if x.kind == "double_top"]
    assert len(pats) == 1
    pt = pats[0]
    assert pt.direction == "SELL"
    neck = pt.details["neckline_break"]
    assert neck == pytest.approx(1007.7, abs=0.5)
    assert df["close"].iloc[pt.confirm_idx] < neck <= df["close"].iloc[pt.confirm_idx - 1]
    assert pt.sl > max(pr for _, pr, lab in pt.points if lab.startswith("Top"))
    height = min(pr for _, pr, lab in pt.points if lab.startswith("Top")) - neck
    assert pt.tps[0] == pytest.approx(neck - height)
    assert pt.tps[1] == pytest.approx(neck - 1.618 * height)


def test_triple_bottom_buy():
    df = path_df(WARM + [(10, 12), (-20, 15), (-8, 10), (-20.2, 10), (-8.5, 10), (-19.8, 10), (5, 18)])
    found = kinds(df)
    assert ("triple_bottom", "BUY") in found
    assert ("double_bottom", "BUY") not in found      # zawarty w triple - pokazujemy bogatszą formację


def test_head_and_shoulders():
    df = path_df(WARM + [(-10, 12), (14, 14), (6, 8), (24, 10), (6, 10), (14.5, 8), (-8, 16)])
    assert ("head_shoulders", "SELL") in kinds(df)


def test_no_pattern_when_tops_far_apart():
    df = path_df(WARM + [(-10, 12), (20, 15), (8, 10), (30, 10), (-5, 18)])
    assert not [k for k in kinds(df) if k[0] == "double_top"]


def test_match_gartley_ratios():
    X, A = 100.0, 200.0
    B = A - 0.618 * (A - X)       # 138.2
    C = B + 0.618 * (A - B)       # 176.4
    D = A - 0.786 * (A - X)       # 121.4
    assert "gartley" in match_harmonic(X, A, B, C, D)
    lo, hi = harmonic_prz("gartley", X, A, B, C)
    assert lo <= D <= hi
    # lustro: niedźwiedzi Gartley
    assert "gartley" in match_harmonic(-X, -A, -B, -C, -D)
    assert "bat" not in match_harmonic(X, A, B, C, D)


def test_bullish_gartley_detected_on_prz_rejection():
    # X=0, A=+30, B=+11.5 (0.618), C=+23.4 (0.636 AB), D=+6.4 (0.786 XA), potem odbicie
    df = path_df(WARM + [(0, 5), (30, 15), (11.5, 10), (23.4, 8), (6.4, 12), (20, 12)])
    pats = [x for x in find_patterns(df, P) if x.kind == "gartley"]
    assert pats and pats[0].direction == "BUY"
    pt = pats[0]
    assert pt.prz[0] <= pt.points[-1][1] <= pt.prz[1] + 0.5
    assert pt.sl < pt.points[-1][1] < pt.entry < pt.tps[0] < pt.tps[1]


def test_zone_confluence_scores():
    df = path_df(WARM + [(-10, 12), (20, 15), (8, 10), (20.3, 10), (-5, 18)])
    pt = next(x for x in find_patterns(df, P, score=False) if x.kind == "double_top")
    a = atr_array(*(df[k].to_numpy() for k in ("high", "low", "close")))
    base = score_pattern(pt, df, [], a, P).score
    z = Zone(1019.0, 1021.0, "supply", 0, None, "user", "Weekly supply")
    with_zone = score_pattern(pt, df, [z], a, P)
    assert with_zone.score == base + 1
    assert any("Weekly supply" in c for c in with_zone.confluences)


def test_no_lookahead():
    """Formacje potwierdzone do świecy t muszą wyglądać tak samo, gdy dodamy przyszłe świece."""
    df = SyntheticProvider(seed=3).get_bars("XAU/USD", "M15", 1500)
    full = find_patterns(df)
    cut = 1100
    part = find_patterns(df.iloc[: cut + 1])
    a = {(x.kind, x.confirm_idx, round(x.entry, 4), round(x.sl, 4), x.score) for x in full if x.confirm_idx <= cut}
    b = {(x.kind, x.confirm_idx, round(x.entry, 4), round(x.sl, 4), x.score) for x in part}
    assert a == b


def test_simulate_tp_then_breakeven():
    df = path_df(WARM + [(-10, 12), (20, 15), (8, 10), (20.3, 10), (-5, 18), (10, 30)])
    pt = next(x for x in find_patterns(df, P) if x.kind == "double_top")
    simulate(df, pt)
    assert pt.outcome in ("tp1", "tp2")
    assert pt.r > 0


def test_live_posts_once_and_replies_on_tp(tmp_path, monkeypatch):
    from signalbot import pattern_live
    from signalbot.config import load_config
    from signalbot.publishers import DryRunPublisher
    from signalbot.tracker import State

    monkeypatch.setattr(pattern_live, "render_pattern_chart", lambda *a, **k: None)
    cfg = load_config(None)
    cfg.data_dir, cfg.use_ai, cfg.pattern_min_score, cfg.pattern_depths = tmp_path, False, 0, (2.0,)
    sent = []

    class Rec(DryRunPublisher):
        def publish(self, text, image=None, reply_to=None, extra_images=None):
            sent.append((text, reply_to))
            return "post-1"

    pubs = {"telegram": (Rec("telegram"), "long")}
    df = path_df(WARM + [(-10, 12), (20, 15), (8, 10), (20.3, 10), (-5, 18), (-30, 30)])
    pt = next(x for x in find_patterns(df, P) if x.kind == "double_top")
    state = State(tmp_path / "s.json")
    pattern_live.run_once_patterns(cfg, df.iloc[: pt.confirm_idx + 1], state, pubs)
    assert pt.id in state.signals and state.signals[pt.id]["status"] == "open"
    assert "Double Top" in sent[0][0] and sent[1][1] == "post-1"        # post + "Why" pod spodem
    n = len(sent)
    pattern_live.run_once_patterns(cfg, df.iloc[: pt.confirm_idx + 1], state, pubs)
    assert len(sent) == n                                                # bez duplikatu
    pattern_live.run_once_patterns(cfg, df, State(tmp_path / "s.json"), pubs)
    st = State(tmp_path / "s.json").signals[pt.id]
    assert st["status"] == "closed" and st["outcome"] == "tp2"
    assert any("TP1 hit" in t for t, _ in sent) and any("TP2 hit" in t for t, _ in sent)


WEDGE = [(14, 8), (3, 8), (17, 8), (8.5, 8), (19, 8), (-6, 12)]


@pytest.mark.parametrize("pre,sign,kind,direction,context", [
    ([(-30, 10), (0, 20)], 1, "rising_wedge", "SELL", "reversal"),        # klin po wzroście -> spadek
    ([(40, 10), (0, 20)], 1, "rising_wedge", "SELL", "continuation"),     # klin w spadku -> spadek wraca
    ([(-30, 10), (0, 20)], -1, "falling_wedge", "BUY", "reversal"),
    ([(40, 10), (0, 20)], -1, "falling_wedge", "BUY", "continuation"),
])
def test_wedges(pre, sign, kind, direction, context):
    df = path_df(WARM + [(sign * a, n) for a, n in pre + WEDGE])
    pats = [x for x in find_patterns(df, P) if "wedge" in x.kind]
    assert [(x.kind, x.direction, x.details["context"]) for x in pats] == [(kind, direction, context)]
    pt = pats[0]
    last = pt.points[-1][1]                                   # ostatni szczyt (SELL) / dołek (BUY)
    if direction == "SELL":
        assert pt.sl > last and pt.tps[0] < pt.entry < pt.details["neckline_break"]
    else:
        assert pt.sl < last and pt.tps[0] > pt.entry > pt.details["neckline_break"]
    assert pt.rr >= P.min_rr


def test_no_wedge_from_one_big_swing():
    """Jeden wielki ruch + małe odbicia to nie klin (odcinki muszą być podobne)."""
    df = path_df(WARM + [(-30, 10), (0, 20), (12, 8), (5, 8), (15, 8), (9, 8), (18, 8), (-2, 10)])
    assert not [x for x in find_patterns(df, P) if "wedge" in x.kind and x.points[0][0] < 60]
