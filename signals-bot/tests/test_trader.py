from types import SimpleNamespace as NS

from signalbot import data
from signalbot.config import Config
from signalbot.trader import MT5Trader


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO, ORDER_FILLING_RETURN, ORDER_FILLING_IOC, ORDER_FILLING_FOK = 0, 2, 1, 0
    ORDER_TYPE_BUY_STOP, ORDER_TYPE_SELL_STOP, ORDER_TYPE_BUY, ORDER_TYPE_SELL = 4, 5, 0, 1
    TRADE_ACTION_PENDING, TRADE_ACTION_MODIFY, TRADE_ACTION_REMOVE, TRADE_ACTION_SLTP, TRADE_ACTION_DEAL = 5, 7, 8, 6, 1
    ORDER_TIME_GTC, POSITION_TYPE_BUY = 0, 0

    def __init__(self, mode=0):
        self.mode, self.sent, self.orders, self.positions, self.n = mode, [], [], [], 100

    def initialize(self, *a, **k): return True
    def terminal_info(self): return NS()
    def shutdown(self): pass
    def last_error(self): return (0, "")
    def symbol_select(self, *a): return True
    def account_info(self): return NS(trade_mode=self.mode, login=1, server="Vantage-Demo", balance=10000.0, currency="USD")
    def symbol_info(self, s): return NS(volume_step=0.01, volume_min=0.01, volume_max=100, digits=2,
                                        trade_tick_size=0.01, trade_tick_value=1.0)
    def symbol_info_tick(self, s): return NS(bid=4000.0, ask=4000.3)
    def orders_get(self, symbol=None): return self.orders
    def positions_get(self, symbol=None): return self.positions

    def order_send(self, req):
        self.sent.append(req)
        if req["action"] == self.TRADE_ACTION_PENDING and req["type_filling"] == self.ORDER_FILLING_RETURN:
            return NS(retcode=10030, comment="invalid fill")  # broker chce IOC
        self.n += 1
        if req["action"] == self.TRADE_ACTION_PENDING:
            self.orders.append(NS(ticket=self.n))
        return NS(retcode=10009, order=self.n, comment="done")


def test_trader_flow():
    data._MT5_CURRENT = None
    mt5 = FakeMT5()
    t = MT5Trader(Config(trade_enabled=True, symbol="XAUUSD"), mt5)
    rec = {}
    t.place(rec, "BUY", 4010.0, 4005.0, [4012.0, 4014.0, 4016.0, 4018.0, 4020.0])
    pend = [r for r in mt5.sent if r["action"] == mt5.TRADE_ACTION_PENDING and r["type_filling"] == mt5.ORDER_FILLING_IOC]
    assert len(rec["mt5_orders"]) == 5 and len(pend) == 5
    # 1% z 10000 = 100$, SL 5$ -> 0.20 lota łącznie -> 0.04 na zlecenie
    assert all(r["volume"] == 0.04 and r["price"] == 4010.0 and r["sl"] == 4005.0 for r in pend)
    assert [r["tp"] for r in pend] == [4012.0, 4014.0, 4016.0, 4018.0, 4020.0]

    t.update(rec, 4011.0, 4006.0, [4013.0, 4015.0, 4017.0, 4019.0, 4021.0])
    mods = [r for r in mt5.sent if r["action"] == mt5.TRADE_ACTION_MODIFY]
    assert len(mods) == 5 and mods[0]["price"] == 4011.0 and mods[-1]["tp"] == 4021.0

    # część już wypełniona przed aktualizacją: stara pozycja dostaje nowy SL i swój TP
    mt5.positions = [NS(ticket=800, identifier=rec["mt5_orders"][0], magic=770077)]
    t.update(rec, 4011.5, 4006.5, [4013.5, 4015.5, 4017.5, 4019.5, 4021.5])
    moved = [r for r in mt5.sent if r["action"] == mt5.TRADE_ACTION_SLTP]
    assert moved == [{"action": mt5.TRADE_ACTION_SLTP, "position": 800, "symbol": "XAUUSD", "sl": 4006.5,
                      "tp": 4013.5, "type_filling": mt5.ORDER_FILLING_RETURN}]
    mt5.sent.clear()

    # wypełnione: pozycje z identifier = numer zlecenia; TP1 zamknął pierwszą
    mt5.orders = []
    mt5.positions = [NS(ticket=900 + i, identifier=o, magic=770077, sl=4006.0, price_open=4011.2, tp=0.0,
                        type=0, volume=0.04) for i, o in enumerate(rec["mt5_orders"][1:])]
    mt5.positions.append(NS(ticket=999, identifier=1, magic=770077, sl=1, price_open=1, tp=1, type=0, volume=1))
    t.breakeven(rec)
    be = [r for r in mt5.sent if r["action"] == mt5.TRADE_ACTION_SLTP]
    assert len(be) == 4 and all(r["sl"] == 4011.2 for r in be)   # obca pozycja nietknięta

    t.close_all(rec)
    assert len([r for r in mt5.sent if r["action"] == mt5.TRADE_ACTION_DEAL]) == 4


def test_real_account_blocked():
    data._MT5_CURRENT = None
    try:
        MT5Trader(Config(trade_enabled=True), FakeMT5(mode=2))
    except RuntimeError as e:
        assert "demo" in str(e)
    else:
        raise AssertionError("real account must be blocked")
