"""Tracks which zone signal each MT5 order/position belongs to, so later
"Zamykam calosc" updates and the bot's own SL monitoring can find the right
tickets. The channel's own "SL na BE" messages are intentionally NOT acted
on - see main.py - the bot manages SL itself based on sl_pips/breakeven_applied
below.

Telegram signals carry no explicit ID, so campaigns are matched by
direction + symbol: the most recently opened still-active campaign for
that direction is assumed to be the one an update message refers to. If
several campaigns of the same direction are active at once, the update is
applied to all of them (documented limitation - see README).
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List

STATE_FILE = Path(__file__).parent / "state" / "campaigns.json"


@dataclass
class Campaign:
    id: str
    symbol: str
    direction: str
    magic: int
    sl_pips: float = 0.0
    tickets: List[int] = field(default_factory=list)
    opened_at: float = field(default_factory=time.time)
    active: bool = True
    breakeven_applied: bool = False


class CampaignStore:
    def __init__(self, path: Path = STATE_FILE):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._campaigns: List[Campaign] = self._load()

    def _load(self) -> List[Campaign]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text())
        return [Campaign(**c) for c in data]

    def _save(self) -> None:
        self.path.write_text(json.dumps([asdict(c) for c in self._campaigns], indent=2))

    def next_magic(self, magic_base: int) -> int:
        used = {c.magic for c in self._campaigns}
        magic = magic_base
        while magic in used:
            magic += 1
        return magic

    def add(self, campaign: Campaign) -> None:
        self._campaigns.append(campaign)
        self._save()

    def active_for(self, symbol: str, direction: str) -> List[Campaign]:
        matches = [c for c in self._campaigns if c.active and c.symbol == symbol and c.direction == direction]
        matches.sort(key=lambda c: c.opened_at, reverse=True)
        return matches

    def most_recent_active(self, symbol: str) -> List[Campaign]:
        matches = [c for c in self._campaigns if c.active and c.symbol == symbol]
        matches.sort(key=lambda c: c.opened_at, reverse=True)
        return matches

    def find_by_magic(self, magic: int) -> Campaign | None:
        for c in self._campaigns:
            if c.magic == magic:
                return c
        return None

    def deactivate(self, campaign_id: str) -> None:
        for c in self._campaigns:
            if c.id == campaign_id:
                c.active = False
        self._save()

    def mark_breakeven_applied(self, campaign_id: str) -> None:
        for c in self._campaigns:
            if c.id == campaign_id:
                c.breakeven_applied = True
        self._save()
