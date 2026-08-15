from __future__ import annotations

import asyncio
import re
from typing import Iterable

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from .models import PlayerRoundInfo, Snapshot


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _extract_round_number(text: str) -> int | None:
    m = re.search(r"Round\s+(\d+)", text, flags=re.IGNORECASE)
    return int(m.group(1)) if m else None


def _extract_score(text: str) -> float | None:
    m = re.search(r"\b(\d+(?:\.5)?)\b", text)
    return float(m.group(1)) if m else None


def _find_player_row(rows: Iterable[BeautifulSoup], player_name: str) -> list[str] | None:
    needle = player_name.lower()
    for row in rows:
        cols = [_clean(td.get_text(" ", strip=True)) for td in row.find_all(["td", "th"])]
        joined = " ".join(cols).lower()
        if needle in joined:
            return cols
    return None


def _round_state_from_text(page_text: str) -> str:
    low = page_text.lower()
    if "pairings done" in low:
        return "pairings_done"
    if "ranking crosstable" in low:
        return "results_published"
    if "pairings not yet generated" in low:
        return "pairings_pending"
    return "unknown"


async def fetch_snapshot(tournament_id: str, player_name: str, headless: bool = True) -> Snapshot:
    root_url = f"https://s2.chess-results.com/tnr{tournament_id}.aspx?lan=1&SNode=S0"
    crosstable_url = f"https://s2.chess-results.com/tnr{tournament_id}.aspx?lan=1&art=4&SNode=S0"
    schedule_url = f"https://s2.chess-results.com/tnr{tournament_id}.aspx?lan=1&art=14&SNode=S0"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        page = await browser.new_page()

        await page.goto(root_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(2500)
        root_html = await page.content()
        root_text = _clean(await page.inner_text("body"))

        await page.goto(crosstable_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(2500)
        crosstable_html = await page.content()
        crosstable_text = _clean(await page.inner_text("body"))

        await page.goto(schedule_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)
        schedule_text = _clean(await page.inner_text("body"))

        await browser.close()

    root_soup = BeautifulSoup(root_html, "lxml")
    cross_soup = BeautifulSoup(crosstable_html, "lxml")

    title_node = root_soup.find(string=re.compile(r"Check N Mate", flags=re.IGNORECASE))
    tournament_name = _clean(str(title_node)) if title_node else None

    latest_round = _extract_round_number(crosstable_text) or _extract_round_number(root_text)
    round_state = _round_state_from_text(crosstable_text + " " + root_text)

    next_round_time_text = None
    m = re.search(r"ROUND\s+AT\s+([0-9:. ]+[APMapm]*)", schedule_text)
    if m:
        next_round_time_text = _clean(m.group(1))

    rows = cross_soup.find_all("tr")
    row = _find_player_row(rows, player_name)
    rank = None
    points = None
    opponent = None
    color = None
    board = None
    result = None

    if row:
        if row and row[0].isdigit():
            rank = int(row[0])
        joined = " | ".join(row)
        points = _extract_score(joined)

        result_match = re.search(r"\b(1-0|0-1|½-½|0\.5-0\.5|1:0|0:1)\b", joined)
        if result_match:
            result = result_match.group(1)

        color_match = re.search(r"\b(White|Black|W|B)\b", joined, flags=re.IGNORECASE)
        if color_match:
            color = color_match.group(1)

        board_match = re.search(r"\bBoard\s*(\d+)\b", joined, flags=re.IGNORECASE)
        if board_match:
            board = board_match.group(1)

        lower_cols = [c.lower() for c in row]
        try:
            idx = next(i for i, c in enumerate(lower_cols) if player_name.lower() in c)
            if idx + 1 < len(row):
                opponent = row[idx + 1]
        except StopIteration:
            opponent = None

    return Snapshot(
        tournament_name=tournament_name,
        latest_round=latest_round,
        round_state=round_state,
        next_round_time_text=next_round_time_text,
        player_rank=rank,
        player_points=points,
        player_round=PlayerRoundInfo(
            round_no=latest_round,
            opponent=opponent,
            color=color,
            board=board,
            result=result,
        ),
    )


def fetch_snapshot_sync(tournament_id: str, player_name: str, headless: bool = True) -> Snapshot:
    return asyncio.run(fetch_snapshot(tournament_id=tournament_id, player_name=player_name, headless=headless))
