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


def test_zone_signal_wraps_forward_across_a_hundred():
    # Real signal that broke the old prefix-concat logic: "4397-02" means
    # the zone crosses upward into the 4400s (4397 -> 4402, $5 wide), not
    # 4397 -> 4302 ($95 wide) which the naive "43" + "02" concat produced.
    msg = parse("TAKE PROFIT: Kierunek: Sell Gold\nStrefa: 4397-02\nSL: 60 pips")
    assert msg.type == SignalType.ZONE
    assert msg.zone.zone_low == 4397.0
    assert msg.zone.zone_high == 4402.0


def test_zone_signal_wraps_backward_across_a_hundred():
    # Mirror case: tail is close to a's own last two digits but through the
    # hundred below (e.g. 4402-97 should mean 4397 -> 4402, not 4402 -> 4297).
    msg = parse("TAKE PROFIT: Kierunek: Sell Gold\nStrefa: 4402-97\nSL: 60 pips")
    assert msg.type == SignalType.ZONE
    assert msg.zone.zone_low == 4397.0
    assert msg.zone.zone_high == 4402.0


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


def test_add_to_position_without_direction_is_add_to_zone():
    msg = parse("TAKE PROFIT: Dołóż do pozycji\nStrefa: 4415-10\nSL: 60 pips")
    assert msg.type == SignalType.ADD_TO_ZONE
    assert msg.add_to_zone.zone_low == 4410.0
    assert msg.add_to_zone.zone_high == 4415.0
    assert msg.add_to_zone.sl_pips == 60.0
    assert msg.zone is None


def test_add_to_position_with_explicit_direction_is_still_a_normal_zone():
    # "Dołóż do pozycji" alongside its OWN "Kierunek:" line already parses
    # fine as a normal ZONE (unaffected by the add-to-zone phrase).
    msg = parse("TAKE PROFIT: Dołóż do pozycji\nKierunek: Buy Gold\nStrefa: 4425-20\nSL: 60 pips")
    assert msg.type == SignalType.ZONE
    assert msg.zone.direction == "BUY"


def test_zone_without_direction_or_add_to_position_phrase_is_not_a_signal():
    # A bare Strefa/SL with no Kierunek AND no "dołóż do pozycji" phrase
    # isn't enough context to guess a direction - stays unrecognized.
    msg = parse("Strefa: 4415-10\nSL: 60 pips")
    assert msg.type != SignalType.ZONE
    assert msg.type != SignalType.ADD_TO_ZONE
