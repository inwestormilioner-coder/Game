from signalbot.ai_manager import Decision, validate


def test_sl_only_tightens_with_buffer():
    # BUY, obecny SL 4000, cena 4020, ATR 4
    assert validate(Decision("move_sl", 4010.0), "BUY", 4000, 4020, 4, 1).action == "move_sl"
    assert validate(Decision("move_sl", 3995.0), "BUY", 4000, 4020, 4, 1).action == "hold"   # oddala SL
    assert validate(Decision("move_sl", 4019.8), "BUY", 4000, 4020, 4, 1).action == "hold"   # bez bufora
    assert validate(Decision("move_sl", 4030.0), "SELL", 4040, 4020, 4, 1).action == "move_sl"
    assert validate(Decision("move_sl", 4045.0), "SELL", 4040, 4020, 4, 1).action == "hold"
    assert validate(Decision("move_sl", None), "SELL", 4040, 4020, 4, 1).action == "hold"


def test_partial_bounds():
    assert validate(Decision("partial", close_pct=50), "BUY", 0, 1, 1, 1).close_pct == 50
    assert validate(Decision("partial", close_pct=5), "BUY", 0, 1, 1, 1).action == "hold"
    assert validate(Decision("partial", close_pct=95), "BUY", 0, 1, 1, 1).action == "close"
    assert validate(Decision("partial", close_pct=50), "BUY", 0, 1, 1, 0.2).action == "close"  # resztka
