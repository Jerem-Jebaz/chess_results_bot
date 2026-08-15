from __future__ import annotations

from .models import Snapshot


def format_snapshot(snapshot: Snapshot, player_name: str) -> str:
    r = snapshot.player_round
    lines = [
        f"Tournament: {snapshot.tournament_name or 'Unknown'}",
        f"Round: {snapshot.latest_round if snapshot.latest_round is not None else 'Unknown'} ({snapshot.round_state})",
        f"Next round: {snapshot.next_round_time_text or 'Not published'}",
        f"Player: {player_name}",
        f"Rank: {snapshot.player_rank if snapshot.player_rank is not None else 'Unknown'}",
        f"Points: {snapshot.player_points if snapshot.player_points is not None else 'Unknown'}",
        f"Opponent: {r.opponent or 'Unknown'}",
        f"Color: {r.color or 'Unknown'}",
        f"Board: {r.board or 'Unknown'}",
        f"Result: {r.result or 'Pending'}",
    ]
    return "\n".join(lines)
