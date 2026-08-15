from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError


class BotConfig(BaseModel):
    telegram_token: str = Field(min_length=10)
    telegram_chat_id: str = Field(min_length=1)
    tournament_id: str = Field(default="1413687", min_length=1)
    player_name: str = Field(default="Joel Chelsan Jebaz", min_length=1)
    poll_interval_seconds: int = Field(default=90, ge=30, le=600)
    state_path: Path = Field(default=Path("state/state.json"))
    headless: bool = True


def load_config() -> BotConfig:
    load_dotenv()
    raw = {
        "telegram_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
        "tournament_id": os.getenv("TOURNAMENT_ID", "1413687"),
        "player_name": os.getenv("PLAYER_NAME", "Joel Chelsan Jebaz"),
        "poll_interval_seconds": int(os.getenv("POLL_INTERVAL_SECONDS", "90")),
        "state_path": Path(os.getenv("STATE_PATH", "state/state.json")),
        "headless": os.getenv("BROWSER_HEADLESS", "true").lower() != "false",
    }
    try:
        return BotConfig.model_validate(raw)
    except ValidationError as exc:
        raise SystemExit(f"Invalid configuration: {exc}") from exc
