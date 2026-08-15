from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


RoundState = Literal["pairings_pending", "pairings_done", "results_published", "unknown"]


class PlayerRoundInfo(BaseModel):
    round_no: int | None = None
    opponent: str | None = None
    color: str | None = None
    board: str | None = None
    result: str | None = None


class Snapshot(BaseModel):
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tournament_name: str | None = None
    latest_round: int | None = None
    round_state: RoundState = "unknown"
    next_round_time_text: str | None = None
    player_rank: int | None = None
    player_points: float | None = None
    player_round: PlayerRoundInfo = Field(default_factory=PlayerRoundInfo)


class PersistedState(BaseModel):
    watch_enabled: bool = True
    latest_snapshot: Snapshot | None = None
    last_alert_hash: str | None = None
