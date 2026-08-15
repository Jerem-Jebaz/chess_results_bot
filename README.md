# Chess Results Bot

Telegram watcher bot for Chess-Results tournament tracking focused on **Joel Chelsan Jebaz**.

## Features
- Watches tournament state and round status.
- Tracks Joel's latest info (rank, points, opponent/result when detectable).
- Sends alerts only when snapshot changes.
- Supports `/status`, `/round`, `/last`, `/watch on|off` commands.

## Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env
```

Fill `.env` with Telegram values.

## Run
```bash
source .venv/bin/activate
python -m bot.main
```

## Notes
- Parsing depends on browser-rendered page content and may require parser adjustments if Chess-Results page structure changes.
- Keep this running on an always-on host for continuous alerts.
- No push is performed unless explicitly approved.
