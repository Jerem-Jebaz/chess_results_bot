from __future__ import annotations

import hashlib
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from .config import load_config
from .formatting import format_snapshot
from .models import PersistedState
from .scraper import fetch_snapshot
from .state import load_state, save_state

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger("chess_results_bot")


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _status_text(state: PersistedState, player_name: str) -> str:
    if state.latest_snapshot is None:
        return "No snapshot yet. Wait for first poll or run /status again shortly."
    return format_snapshot(state.latest_snapshot, player_name)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Chess watcher bot online. Use /status, /round, /last, /watch on|off")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["config"]
    state = load_state(cfg.state_path)
    await update.message.reply_text(await _status_text(state, cfg.player_name))


async def cmd_round(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["config"]
    state = load_state(cfg.state_path)
    if not state.latest_snapshot:
        await update.message.reply_text("No round data yet.")
        return
    s = state.latest_snapshot
    await update.message.reply_text(
        f"Round: {s.latest_round if s.latest_round is not None else 'Unknown'} ({s.round_state})\n"
        f"Next round: {s.next_round_time_text or 'Not published'}"
    )


async def cmd_last(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["config"]
    state = load_state(cfg.state_path)
    if not state.latest_snapshot:
        await update.message.reply_text("No data yet.")
        return
    await update.message.reply_text(
        f"Last snapshot at: {state.latest_snapshot.observed_at.isoformat()}\n\n"
        f"{format_snapshot(state.latest_snapshot, cfg.player_name)}"
    )


async def cmd_watch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["config"]
    state = load_state(cfg.state_path)
    args = context.args
    if not args or args[0].lower() not in {"on", "off"}:
        await update.message.reply_text("Usage: /watch on|off")
        return
    state.watch_enabled = args[0].lower() == "on"
    save_state(cfg.state_path, state)
    await update.message.reply_text(f"Watch {'enabled' if state.watch_enabled else 'disabled'}.")


async def watcher_tick(context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["config"]
    state = load_state(cfg.state_path)
    if not state.watch_enabled:
        return

    try:
        snapshot = await fetch_snapshot(
            tournament_id=cfg.tournament_id,
            player_name=cfg.player_name,
            headless=cfg.headless,
        )
    except Exception as exc:
        logger.exception("Watcher tick failed: %s", exc)
        return

    text = format_snapshot(snapshot, cfg.player_name)
    new_hash = _hash_text(text)

    state.latest_snapshot = snapshot
    changed = new_hash != state.last_alert_hash
    if changed:
        await context.bot.send_message(chat_id=cfg.telegram_chat_id, text=f"Update detected:\n\n{text}")
        state.last_alert_hash = new_hash
    save_state(cfg.state_path, state)


def main() -> None:
    cfg = load_config()
    app = Application.builder().token(cfg.telegram_token).build()
    app.bot_data["config"] = cfg

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("round", cmd_round))
    app.add_handler(CommandHandler("last", cmd_last))
    app.add_handler(CommandHandler("watch", cmd_watch))

    app.job_queue.run_repeating(watcher_tick, interval=cfg.poll_interval_seconds, first=3)

    logger.info("Bot starting for tournament %s and player %s", cfg.tournament_id, cfg.player_name)
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
