from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import List

from telegram import Bot

from .config import load_config
from .formatting import format_snapshot
from .scraper import fetch_snapshot
from .state import load_state, save_state

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger("chess_results_bot.one_shot")


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _describe_changes(prev, curr) -> List[str]:
    changes: List[str] = []
    if prev is None:
        changes.append("Initial snapshot")
        return changes

    if prev.latest_round != curr.latest_round:
        changes.append(f"Round changed: {prev.latest_round} -> {curr.latest_round}")

    if prev.round_state != curr.round_state:
        changes.append(f"Round state: {prev.round_state} -> {curr.round_state}")

    # player-specific
    pprev = prev.player_round
    pcurr = curr.player_round
    if pprev.opponent != pcurr.opponent:
        changes.append(f"Opponent: {pprev.opponent or 'Unknown'} -> {pcurr.opponent or 'Unknown'}")
    if pprev.result != pcurr.result:
        changes.append(f"Result: {pprev.result or 'Pending'} -> {pcurr.result or 'Pending'}")
    if pprev.color != pcurr.color:
        changes.append(f"Color: {pprev.color or 'Unknown'} -> {pcurr.color or 'Unknown'}")

    if prev.player_points != curr.player_points:
        changes.append(f"Points: {prev.player_points or 'Unknown'} -> {curr.player_points or 'Unknown'}")
    if prev.player_rank != curr.player_rank:
        changes.append(f"Rank: {prev.player_rank or 'Unknown'} -> {curr.player_rank or 'Unknown'}")

    return changes


async def run_once() -> int:
    cfg = load_config()
    state = load_state(cfg.state_path)

    try:
        snapshot = await fetch_snapshot(cfg.tournament_id, cfg.player_name, headless=cfg.headless)
    except Exception as exc:
        logger.exception("Failed to fetch snapshot: %s", exc)
        return 2

    # compare with previous snapshot
    prev = state.latest_snapshot
    changes = _describe_changes(prev, snapshot)

    text = format_snapshot(snapshot, cfg.player_name)
    new_hash = _hash_text(text)

    send_message = False
    message_body = None

    # If no previous snapshot, or meaningful changes detected, prepare message
    if not prev:
        send_message = True
        message_body = f"Initial snapshot:\n\n{text}"
    elif changes:
        send_message = True
        # detect round finished (results published)
        round_finished = (
            (prev.round_state != "results_published" and snapshot.round_state == "results_published")
            or (prev.latest_round != snapshot.latest_round and snapshot.round_state == "results_published")
        )
        header = "Update detected"
        if round_finished:
            header = "Round finished"
        message_body = header + ":\n\n" + "\n".join(changes) + "\n\n" + text

    # Telegram has a max message size (4096). Chunk or truncate to avoid BadRequest: Message is too long
    def _chunk_text(text: str, max_len: int = 4000):
        # naive chunker that prefers splitting on blank lines or newlines
        if len(text) <= max_len:
            yield text
            return
        parts = text.split("\n\n")
        cur = ""
        for p in parts:
            candidate = (cur + "\n\n" + p) if cur else p
            if len(candidate) <= max_len:
                cur = candidate
            else:
                if cur:
                    yield cur
                # if single part too large, further split by lines
                if len(p) > max_len:
                    lines = p.split("\n")
                    cur2 = ""
                    for l in lines:
                        cand2 = (cur2 + "\n" + l) if cur2 else l
                        if len(cand2) <= max_len:
                            cur2 = cand2
                        else:
                            if cur2:
                                yield cur2
                            # last resort: hard split
                            for i in range(0, len(l), max_len):
                                yield l[i : i + max_len]
                            cur2 = ""
                    if cur2:
                        yield cur2
                    cur = ""
                else:
                    cur = p
        if cur:
            yield cur

    async def _safe_send(bot: Bot, chat_id: str, text: str) -> bool:
        from telegram.error import BadRequest

        send = getattr(bot, "send_message", None)
        if send is None:
            logger.error("Telegram Bot has no send_message method")
            return False

        # attempt to send in chunks
        try:
            for chunk in _chunk_text(text, max_len=4000):
                if asyncio.iscoroutinefunction(send):
                    await send(chat_id=chat_id, text=chunk)
                else:
                    send(chat_id=chat_id, text=chunk)
            return True
        except BadRequest as bre:
            msg = str(bre)
            if "Message is too long" in msg or len(text) > 4096:
                # try truncating and sending a short summary instead
                truncated = text[:3900] + "\n\n...(truncated)"
                try:
                    if asyncio.iscoroutinefunction(send):
                        await send(chat_id=chat_id, text=truncated)
                    else:
                        send(chat_id=chat_id, text=truncated)
                    return True
                except Exception:
                    logger.exception("Failed to send truncated telegram message")
                    return False
            else:
                logger.exception("Telegram BadRequest while sending message: %s", bre)
                return False
        except Exception:
            logger.exception("Unexpected error sending telegram message")
            return False

    if send_message and cfg.telegram_token and cfg.telegram_chat_id:
        bot = Bot(token=cfg.telegram_token)
        ok = await _safe_send(bot, cfg.telegram_chat_id, message_body or "")
        if ok:
            logger.info("Alert sent to chat %s", cfg.telegram_chat_id)
            state.last_alert_hash = new_hash
        else:
            logger.error("Failed to deliver alert to chat %s", cfg.telegram_chat_id)
    elif send_message:
        logger.info("Changes detected but Telegram not configured.\n%s", message_body)

    # always persist latest snapshot
    state.latest_snapshot = snapshot
    save_state(cfg.state_path, state)
    return 0


def main() -> None:
    exit_code = asyncio.run(run_once())
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
