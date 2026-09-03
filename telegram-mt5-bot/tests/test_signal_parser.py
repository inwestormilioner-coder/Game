import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from signal_parser import SignalType, parse  # noqa: E402


def test_zone_signal_with_prefix_line():
    msg = parse(
        "TAKE PROFIT: Dołóż do pozycji\nKierunek: Buy Gold\nStrefa: 4425-20\nSL: 60 pips"
    )
    assert msg.type == SignalType.ZONE
    assert msg.zone.direction == "BUY"
    assert msg.zone.zone_low == 4420.0
    assert msg.zone.zone_high == 4425.0
    assert msg.zone.sl_pips == 60.0


def test_zone_signal_plain():
    msg = parse("TAKE PROFIT: Kierunek: Buy Gold\nStrefa: 4419-14\nSL: 60 pips")
    assert msg.type == SignalType.ZONE
    assert msg.zone.zone_low == 4414.0
    assert msg.zone.zone_high == 4419.0


def test_zone_signal_ascending_tail():
    msg = parse("TAKE PROFIT: Kierunek: Buy Gold\nStrefa: 4430-35\nSL: 60 pips")
    assert msg.type == SignalType.ZONE
    assert msg.zone.zone_low == 4430.0
    assert msg.zone.zone_high == 4435.0


def test_sell_direction():
    msg = parse("Kierunek: Sell Gold\nStrefa: 4430-25\nSL: 60 pips")
    assert msg.zone.direction == "SELL"


def test_breakeven_update():
    msg = parse(
        "TAKE PROFIT: +70 pips ⚖️ SL na BE już możliwy, choć rynek potrafi cofnąć. "
        "Zbieram malutką część zysków."
    )
    assert msg.type == SignalType.BREAKEVEN
    assert msg.profit_pips == 70.0


def test_breakeven_update_alt_phrasing():
    msg = parse(
        "TAKE PROFIT: +80 pips ⚖️ Można ustawić SL na BE, choć cena może jeszcze cofnąć. "
        "Biorę malutką część zysków."
    )
    assert msg.type == SignalType.BREAKEVEN
    assert msg.profit_pips == 80.0


def test_close_all_update():
    msg = parse("TAKE PROFIT: +140 pips ⚖️ Zamykam całość. Podsyłajcie swoje wyniki!")
    assert msg.type == SignalType.CLOSE_ALL
    assert msg.profit_pips == 140.0


def test_unknown_message_is_ignored():
    msg = parse("Cześć wszystkim, jak leci?")
    assert msg.type == SignalType.UNKNOWN
