# Context

## Project
- Name: chess_results_bot
- Goal: Monitor tournament/player updates from Chess-Results and send Telegram alerts/commands.
- Tracked player: Joel Chelsan Jebaz

## Constraints
- Use Python virtual environment (`.venv`) for Python work.
- Keep state and context locally in repo files.
- Do not push without explicit user approval.

## Data source notes
- Tournament links are round-dependent for pairings (`art=2&rd=X`), so logic anchors on tournament id and stable root endpoints.
- This implementation uses Playwright browser rendering because stripped static responses may omit table data.

## Current implementation
- Python Telegram bot created in `bot/`.
- Commands: `/start`, `/status`, `/round`, `/last`, `/watch on|off`.
- Watcher job polls and compares snapshot hash; sends alerts only on changes.
- State persisted to `state/state.json` (configurable).

## Next operational step
- Configure `.env` secrets and run bot on always-on host.
