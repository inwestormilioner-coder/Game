"""Przechowywanie sygnałów w SQLite i liczenie najwyższego osiągniętego TP."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from signal_parser import Signal, Update, sl_pips, tp_pips

SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id     INTEGER NOT NULL,
    message_id  INTEGER NOT NULL,
    created_at  TEXT    NOT NULL,          -- ISO, UTC
    strategy    TEXT,
    symbol      TEXT    NOT NULL,
    direction   TEXT    NOT NULL,
    entry       REAL,
    sl          REAL,
    sl_is_pips  INTEGER NOT NULL DEFAULT 0,
    tps         TEXT    NOT NULL,          -- JSON [[wartość, czy_pipsy], ...]
    raw_text    TEXT    NOT NULL,
    max_tp      INTEGER NOT NULL DEFAULT 0, -- najwyższy osiągnięty TP (0 = brak)
    pips        REAL    NOT NULL DEFAULT 0, -- pipsy za najwyższy TP
    sl_hit      INTEGER NOT NULL DEFAULT 0,
    loss_pips   REAL    NOT NULL DEFAULT 0,
    UNIQUE (chat_id, message_id)
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


@dataclass
class SignalRow:
    id: int
    chat_id: int
    message_id: int
    created_at: datetime
    strategy: str | None
    symbol: str
    direction: str
    entry: float | None
    sl: float | None
    sl_is_pips: bool
    tps: list[tuple[float, bool]]
    raw_text: str
    max_tp: int
    pips: float
    sl_hit: bool
    loss_pips: float


def _row(r: sqlite3.Row) -> SignalRow:
    return SignalRow(
        id=r["id"],
        chat_id=r["chat_id"],
        message_id=r["message_id"],
        created_at=datetime.fromisoformat(r["created_at"]),
        strategy=r["strategy"],
        symbol=r["symbol"],
        direction=r["direction"],
        entry=r["entry"],
        sl=r["sl"],
        sl_is_pips=bool(r["sl_is_pips"]),
        tps=[tuple(x) for x in json.loads(r["tps"])],
        raw_text=r["raw_text"],
        max_tp=r["max_tp"],
        pips=r["pips"],
        sl_hit=bool(r["sl_hit"]),
        loss_pips=r["loss_pips"],
    )


class Storage:
    def __init__(self, path: str, pip_overrides: dict[str, float] | None = None):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.pip_overrides = pip_overrides or {}

    # --- sygnały ---------------------------------------------------------

    def add_signal(self, chat_id: int, message_id: int, when: datetime, sig: Signal, text: str) -> None:
        self.db.execute(
            """INSERT OR IGNORE INTO signals
               (chat_id, message_id, created_at, strategy, symbol, direction, entry, sl,
                sl_is_pips, tps, raw_text)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                chat_id,
                message_id,
                when.astimezone(timezone.utc).isoformat(),
                sig.strategy,
                sig.symbol,
                sig.direction,
                sig.entry,
                sig.sl,
                int(sig.sl_is_pips),
                json.dumps(sig.tps),
                text,
            ),
        )
        self.db.commit()

    def get(self, chat_id: int, message_id: int) -> SignalRow | None:
        r = self.db.execute(
            "SELECT * FROM signals WHERE chat_id=? AND message_id=?", (chat_id, message_id)
        ).fetchone()
        return _row(r) if r else None

    def find_recent(self, chat_id: int, symbol: str | None, days: int = 14) -> SignalRow | None:
        """Ostatni sygnał (opcjonalnie dla danego symbolu), który nie zakończył się SL."""
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        q = "SELECT * FROM signals WHERE chat_id=? AND created_at>=? AND sl_hit=0"
        args: list = [chat_id, since]
        if symbol:
            q += " AND symbol=?"
            args.append(symbol)
        r = self.db.execute(q + " ORDER BY created_at DESC LIMIT 1", args).fetchone()
        return _row(r) if r else None

    def update_raw_text(self, row_id: int, text: str) -> None:
        self.db.execute("UPDATE signals SET raw_text=? WHERE id=?", (text, row_id))
        self.db.commit()

    def apply_update(self, s: SignalRow, u: Update) -> bool:
        """Zapisuje TYLKO najwyższy osiągnięty TP. Zwraca True, jeśli coś się zmieniło."""
        new_tp = max(u.tp_hits, default=0)
        if u.all_tps:
            new_tp = max(new_tp, len(s.tps))
        new_tp = min(new_tp, len(s.tps)) if s.tps else new_tp

        max_tp, pips, sl_hit, loss = s.max_tp, s.pips, s.sl_hit, s.loss_pips
        if new_tp > max_tp:
            max_tp = new_tp
            pips = max(pips, tp_pips(s.symbol, s.entry, s.tps, max_tp, self.pip_overrides))
        if (new_tp or u.all_tps) and u.pips is not None:
            pips = max(pips, u.pips)
        if max_tp > 0:
            sl_hit, loss = False, 0.0  # po TP stop na BE / nie liczymy straty
        elif u.sl_hit:
            sl_hit = True
            loss = sl_pips(s.symbol, s.entry, s.sl, s.sl_is_pips, self.pip_overrides)

        if (max_tp, pips, sl_hit, loss) == (s.max_tp, s.pips, s.sl_hit, s.loss_pips):
            return False
        self.db.execute(
            "UPDATE signals SET max_tp=?, pips=?, sl_hit=?, loss_pips=? WHERE id=?",
            (max_tp, pips, int(sl_hit), loss, s.id),
        )
        self.db.commit()
        return True

    # --- ręczne korekty --------------------------------------------------

    def set_tp(self, chat_id: int, message_id: int, tp: int) -> SignalRow | None:
        s = self.get(chat_id, message_id)
        if not s:
            return None
        pips = tp_pips(s.symbol, s.entry, s.tps, tp, self.pip_overrides) if tp else 0.0
        self.db.execute(
            "UPDATE signals SET max_tp=?, pips=?, sl_hit=0, loss_pips=0 WHERE id=?", (tp, pips, s.id)
        )
        self.db.commit()
        return self.get(chat_id, message_id)

    def set_pips(self, chat_id: int, message_id: int, pips: float) -> SignalRow | None:
        s = self.get(chat_id, message_id)
        if not s:
            return None
        self.db.execute("UPDATE signals SET pips=? WHERE id=?", (pips, s.id))
        self.db.commit()
        return self.get(chat_id, message_id)

    def set_sl(self, chat_id: int, message_id: int) -> SignalRow | None:
        s = self.get(chat_id, message_id)
        if not s:
            return None
        loss = sl_pips(s.symbol, s.entry, s.sl, s.sl_is_pips, self.pip_overrides)
        self.db.execute(
            "UPDATE signals SET max_tp=0, pips=0, sl_hit=1, loss_pips=? WHERE id=?", (loss, s.id)
        )
        self.db.commit()
        return self.get(chat_id, message_id)

    def delete(self, chat_id: int, message_id: int) -> bool:
        cur = self.db.execute(
            "DELETE FROM signals WHERE chat_id=? AND message_id=?", (chat_id, message_id)
        )
        self.db.commit()
        return cur.rowcount > 0

    # --- raporty ---------------------------------------------------------

    def between(self, chat_id: int, start: datetime, end: datetime) -> list[SignalRow]:
        rows = self.db.execute(
            "SELECT * FROM signals WHERE chat_id=? AND created_at>=? AND created_at<? ORDER BY created_at",
            (chat_id, start.astimezone(timezone.utc).isoformat(), end.astimezone(timezone.utc).isoformat()),
        ).fetchall()
        return [_row(r) for r in rows]

    def meta_get(self, key: str) -> str | None:
        r = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r["value"] if r else None

    def meta_set(self, key: str, value: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))
        self.db.commit()
