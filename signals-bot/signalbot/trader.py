"""Automatyczne zagrywanie sygnałów na koncie MT5 (np. Vantage demo).

Każdy sygnał = tyle zleceń STOP, ile TP: ta sama cena wejścia i SL, każde zlecenie z innym TP
(częściowe zamknięcia). Po TP1 SL pozostałych pozycji idzie na cenę otwarcia (breakeven).
Zlecenia rozpoznajemy po numerze magic; numery zleceń zapisujemy w data/state.json.
"""
from __future__ import annotations

import logging
import math

from .config import Config
from .data import mt5_connect

log = logging.getLogger("signalbot")

DONE = 10009          # TRADE_RETCODE_DONE
DONE_PARTIAL = 10010
INVALID_FILL = 10030  # TRADE_RETCODE_INVALID_FILL


class MT5Trader:
    def __init__(self, cfg: Config, mt5=None):
        if mt5 is None:
            import MetaTrader5 as mt5  # noqa: import tylko gdy używany
        self.mt5, self.cfg = mt5, cfg
        self.symbol = cfg.trade_symbol or cfg.symbol
        self.conn = (cfg.trade_mt5_path, cfg.trade_mt5_login, cfg.trade_mt5_password, cfg.trade_mt5_server) \
            if cfg.trade_mt5_path or cfg.trade_mt5_login else \
            (cfg.mt5_path, cfg.mt5_login, cfg.mt5_password, cfg.mt5_server)
        self.connect()
        acc = mt5.account_info()
        if acc is None:
            raise RuntimeError(f"MT5: brak informacji o koncie: {mt5.last_error()}")
        demo = acc.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO
        if not demo and not cfg.trade_allow_real:
            raise RuntimeError("To NIE jest konto demo. Handel wyłączony (ustaw TRADE_ALLOW_REAL=true, "
                               "jeśli naprawdę chcesz grać na realnym).")
        log.info("Auto-trading: konto %s (%s, %s), saldo %.2f %s, symbol %s", acc.login, acc.server,
                 "DEMO" if demo else "REAL", acc.balance, acc.currency, self.symbol)

    def connect(self) -> None:
        mt5_connect(self.mt5, *self.conn)
        self.mt5.symbol_select(self.symbol, True)

    # --- pomocnicze -------------------------------------------------------------------------
    def _info(self):
        info = self.mt5.symbol_info(self.symbol)
        if info is None:
            raise RuntimeError(f"MT5: nie znam symbolu {self.symbol} (sprawdź TRADE_SYMBOL)")
        return info

    def _volumes(self, entry: float, sl: float, n: int) -> list[float]:
        info = self._info()
        step, vmin, vmax = info.volume_step, info.volume_min, info.volume_max
        if self.cfg.trade_lot > 0:
            per = self.cfg.trade_lot
        else:
            balance = self.mt5.account_info().balance
            risk_money = balance * self.cfg.trade_risk_pct / 100
            loss_per_lot = abs(entry - sl) / info.trade_tick_size * info.trade_tick_value
            per = risk_money / loss_per_lot / n if loss_per_lot > 0 else vmin
        per = math.floor(per / step + 1e-9) * step
        if per < vmin:
            log.warning("Auto-trading: wyliczony lot %.3f < minimum %.2f — używam minimum (większe ryzyko)", per, vmin)
            per = vmin
        return [round(min(per, vmax), 8)] * n

    def _send(self, req: dict):
        fills = [self.mt5.ORDER_FILLING_RETURN, self.mt5.ORDER_FILLING_IOC, self.mt5.ORDER_FILLING_FOK]
        res = None
        for f in fills:
            res = self.mt5.order_send({**req, "type_filling": f})
            if res is None or res.retcode != INVALID_FILL:
                break
        if res is None or res.retcode not in (DONE, DONE_PARTIAL):
            raise RuntimeError(f"MT5 order_send: {getattr(res, 'retcode', None)} "
                               f"{getattr(res, 'comment', self.mt5.last_error())}")
        return res

    def _positions(self, rec: dict) -> list:
        tickets = set(rec.get("mt5_orders", []))
        return [p for p in (self.mt5.positions_get(symbol=self.symbol) or [])
                if p.magic == self.cfg.trade_magic and p.identifier in tickets]

    def _pending(self, rec: dict) -> list:
        tickets = set(rec.get("mt5_orders", []))
        return [o for o in (self.mt5.orders_get(symbol=self.symbol) or []) if o.ticket in tickets]

    # --- akcje wywoływane przez fib_live ----------------------------------------------------
    def place(self, rec: dict, direction: str, entry: float, sl: float, tps: list[float]) -> None:
        self.connect()
        d = self._info().digits
        buy = direction == "BUY"
        typ = self.mt5.ORDER_TYPE_BUY_STOP if buy else self.mt5.ORDER_TYPE_SELL_STOP
        tickets = []
        for i, (tp, vol) in enumerate(zip(tps, self._volumes(entry, sl, len(tps)))):
            res = self._send({
                "action": self.mt5.TRADE_ACTION_PENDING, "symbol": self.symbol, "volume": vol, "type": typ,
                "price": round(entry, d), "sl": round(sl, d), "tp": round(tp, d),
                "magic": self.cfg.trade_magic, "comment": f"OnlyPips TP{i + 1}",
                "type_time": self.mt5.ORDER_TIME_GTC,
            })
            tickets.append(res.order)
        rec["mt5_orders"] = tickets
        log.info("Auto-trading: %s STOP %d zleceń @ %.2f SL %.2f (lot %s)", direction, len(tickets), entry, sl,
                 self._volumes(entry, sl, len(tps))[0])

    def update(self, rec: dict, entry: float, sl: float, tps: list[float]) -> None:
        self.connect()
        d = self._info().digits
        tp_by_ticket = dict(zip(rec.get("mt5_orders", []), tps))
        for o in self._pending(rec):
            self._send({"action": self.mt5.TRADE_ACTION_MODIFY, "order": o.ticket, "symbol": self.symbol,
                        "price": round(entry, d), "sl": round(sl, d), "tp": round(tp_by_ticket[o.ticket], d),
                        "type_time": self.mt5.ORDER_TIME_GTC})
        # zlecenia już wypełnione (cena dotknęła starego wejścia): stara pozycja dostaje nowy SL i TP
        for p in self._positions(rec):
            self._send({"action": self.mt5.TRADE_ACTION_SLTP, "position": p.ticket, "symbol": self.symbol,
                        "sl": round(sl, d), "tp": round(tp_by_ticket[p.identifier], d)})
        log.info("Auto-trading: zlecenia przesunięte na %.2f / SL %.2f", entry, sl)

    def cancel(self, rec: dict) -> None:
        self.connect()
        for o in self._pending(rec):
            self._send({"action": self.mt5.TRADE_ACTION_REMOVE, "order": o.ticket})
        log.info("Auto-trading: zlecenia oczekujące usunięte")

    def breakeven(self, rec: dict) -> None:
        self.connect()
        d = self._info().digits
        for p in self._positions(rec):
            if round(p.sl, d) == round(p.price_open, d):
                continue
            self._send({"action": self.mt5.TRADE_ACTION_SLTP, "position": p.ticket, "symbol": self.symbol,
                        "sl": round(p.price_open, d), "tp": p.tp})
        log.info("Auto-trading: SL na breakeven")

    def move_sl(self, rec: dict, sl: float) -> None:
        """SL wszystkich pozycji sygnału na poziom wskazany przez AI-menedżera."""
        self.connect()
        d = self._info().digits
        for p in self._positions(rec):
            self._send({"action": self.mt5.TRADE_ACTION_SLTP, "position": p.ticket, "symbol": self.symbol,
                        "sl": round(sl, d), "tp": p.tp})
        log.info("Auto-trading: SL przesunięty przez AI na %.2f", sl)

    def partial(self, rec: dict, pct: float) -> None:
        """Zamknij pct% otwartego wolumenu - najpierw pozycje z najbliższym TP."""
        self.connect()
        info = self._info()
        pos = self._positions(rec)
        if not pos:
            return
        buy = pos[0].type == self.mt5.POSITION_TYPE_BUY
        pos.sort(key=lambda p: p.tp if buy else -p.tp)
        todo = math.floor(sum(p.volume for p in pos) * pct / 100 / info.volume_step + 1e-9) * info.volume_step
        tick = self.mt5.symbol_info_tick(self.symbol)
        for p in pos:
            vol = round(min(p.volume, todo), 8)
            if vol < info.volume_min:
                break
            self._send({"action": self.mt5.TRADE_ACTION_DEAL, "position": p.ticket, "symbol": self.symbol,
                        "volume": vol, "type": self.mt5.ORDER_TYPE_SELL if buy else self.mt5.ORDER_TYPE_BUY,
                        "price": tick.bid if buy else tick.ask, "deviation": 50, "magic": self.cfg.trade_magic})
            todo = round(todo - vol, 8)
        log.info("Auto-trading: AI zamknęło %s%% pozycji", pct)

    def close_all(self, rec: dict) -> None:
        self.connect()
        self.cancel(rec)
        for p in self._positions(rec):
            buy = p.type == self.mt5.POSITION_TYPE_BUY
            tick = self.mt5.symbol_info_tick(self.symbol)
            self._send({"action": self.mt5.TRADE_ACTION_DEAL, "position": p.ticket, "symbol": self.symbol,
                        "volume": p.volume, "type": self.mt5.ORDER_TYPE_SELL if buy else self.mt5.ORDER_TYPE_BUY,
                        "price": tick.bid if buy else tick.ask, "deviation": 50, "magic": self.cfg.trade_magic})
        log.info("Auto-trading: pozycje zamknięte")


def make_trader(cfg: Config):
    if not cfg.trade_enabled:
        return None
    if cfg.dry_run:
        log.info("Auto-trading pominięty: DRY_RUN=true")
        return None
    try:
        return MT5Trader(cfg)
    except Exception as e:  # sygnały mają iść dalej, nawet gdy konto handlowe nie działa
        log.error("Auto-trading WYŁĄCZONY: %s", e)
        return None


def trade_check(cfg: Config) -> None:
    """Test połączenia: pokazuje konto i lot, stawia zlecenie BUY STOP daleko od ceny i od razu je usuwa."""
    t = MT5Trader(cfg)
    info, tick = t._info(), t.mt5.symbol_info_tick(t.symbol)
    entry = tick.ask + 20
    sl, tp = entry - 5, entry + 5
    print(f"Symbol {t.symbol}: bid {tick.bid} ask {tick.ask}, lot min {info.volume_min} krok {info.volume_step}")
    vols = t._volumes(entry, sl, len(cfg.tp_levels))
    print(f"Przy SL 5$ i ryzyku {cfg.trade_risk_pct}%: {len(vols)} zleceń po {vols[0]} lota")
    rec: dict = {}
    t.place(rec, "BUY", entry, sl, [tp])
    print(f"Testowe zlecenie BUY STOP @ {entry:.2f} postawione (ticket {rec['mt5_orders'][0]})")
    t.cancel(rec)
    print("…i usunięte. Auto-trading działa.")
