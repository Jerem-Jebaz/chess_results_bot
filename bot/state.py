from __future__ import annotations

import json
from pathlib import Path

from .models import PersistedState


def load_state(path: Path) -> PersistedState:
    if not path.exists():
        return PersistedState()
    data = json.loads(path.read_text(encoding="utf-8"))
    return PersistedState.model_validate(data)


def save_state(path: Path, state: PersistedState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(state.model_dump_json(indent=2), encoding="utf-8")
