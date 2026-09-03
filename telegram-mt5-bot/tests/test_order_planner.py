import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from order_planner import generate_price_levels, plan_orders  # noqa: E402
from signal_parser import ZoneSignal  # noqa: E402


def test_generate_price_levels_covers_whole_zone_every_half_dollar():
    levels = generate_price_levels(4420.0, 4425.0, 0.5)
    assert levels == [4420.0, 4420.5, 4421.0, 4421.5, 4422.0, 4422.5, 4423.0, 4423.5, 4424.0, 4424.5, 4425.0]


def test_generate_price_levels_handles_reversed_bounds():
    assert generate_price_levels(4425.0, 4420.0, 0.5) == generate_price_levels(4420.0, 4425.0, 0.5)


def test_plan_orders_buy_zone_tp_ladder_from_lowest_entry():
    zone = ZoneSignal(direction="BUY", zone_low=4420.0, zone_high=4425.0, sl_pips=60)
    plans = plan_orders(zone, lot=0.01, step=0.5, pip_size=0.1, start_tp_pips=60, tp_increment_pips=10)

    assert len(plans) == 11
    assert all(p.lot == 0.01 for p in plans)

    # lowest entry gets the tightest TP (60 pips), each order above it +10
    assert plans[0].entry_price == 4420.0
    assert plans[0].tp_pips == 60
    assert plans[5].tp_pips == 110
    assert plans[-1].entry_price == 4425.0
    assert plans[-1].tp_pips == 160

    # SL is ONE shared price for the whole grid: 60 pips ($6) below the
    # lowest entry (4420.0) - not measured from each order's own entry
    assert all(p.sl_price == 4414.0 for p in plans)
    for p in plans:
        assert round(p.tp_price - p.entry_price, 2) == round(p.tp_pips * 0.1, 2)


def test_plan_orders_sell_zone_mirrors_direction():
    zone = ZoneSignal(direction="SELL", zone_low=4425.0, zone_high=4430.0, sl_pips=60)
    plans = plan_orders(zone, lot=0.01, step=0.5, pip_size=0.1, start_tp_pips=60, tp_increment_pips=10)

    # SL is ONE shared price: 60 pips above the highest entry (4430.0)
    assert all(p.sl_price == 4436.0 for p in plans)
    for p in plans:
        assert p.sl_price > p.entry_price
        assert p.tp_price < p.entry_price
