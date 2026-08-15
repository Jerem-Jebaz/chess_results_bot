from __future__ import annotations

import asyncio
import re
import unicodedata
from typing import Iterable, Optional

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from .models import PlayerRoundInfo, Snapshot


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _normalize_name(name: str) -> str:
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(ch for ch in s if not unicodedata.category(ch).startswith("M"))
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def _extract_round_number(text: str) -> int | None:
    # try several patterns
    m = re.search(r"Round\s+(\d+)", text, flags=re.IGNORECASE)
    if m:
        return int(m.group(1))
    m2 = re.search(r"Rd\.?\s*(\d+)", text, flags=re.IGNORECASE)
    if m2:
        return int(m2.group(1))
    return None


def _extract_score(text: str) -> float | None:
    m = re.search(r"\b(\d+(?:\.5)?)\b", text)
    return float(m.group(1)) if m else None


def _find_player_row_by_name(rows: Iterable[BeautifulSoup], player_name: str) -> Optional[list[str]]:
    needle = _normalize_name(player_name)
    for row in rows:
        cols = [_clean(td.get_text(" ", strip=True)) for td in row.find_all(["td", "th"])]
        joined = _normalize_name(" ".join(cols))
        if needle and needle in joined:
            return cols
    return None


def _extract_fide_id_from_row(cols: list[str]) -> Optional[str]:
    # Look for an integer-like FIDE id in columns
    for c in cols:
        m = re.search(r"\b(\d{5,10})\b", c)
        if m:
            return m.group(1)
    return None


def _round_state_from_text(page_text: str) -> str:
    low = page_text.lower()
    if "pairings done" in low or "pairings" in low and "done" in low:
        return "pairings_done"
    if "ranking crosstable" in low or "ranking" in low and "crosstable" in low:
        return "results_published"
    if "pairings not yet generated" in low or "pairings not yet" in low:
        return "pairings_pending"
    return "unknown"


async def fetch_snapshot(tournament_id: str, player_name: str, headless: bool = True) -> Snapshot:
    root_url = f"https://s2.chess-results.com/tnr{tournament_id}.aspx?lan=1&SNode=S0"
    crosstable_url = f"https://s2.chess-results.com/tnr{tournament_id}.aspx?lan=1&art=4&SNode=S0"
    schedule_url = f"https://s2.chess-results.com/tnr{tournament_id}.aspx?lan=1&art=14&SNode=S0"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        page = await browser.new_page()

        # Fetch root
        await page.goto(root_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        root_html = await page.content()
        root_text = _clean(await page.inner_text("body"))

        # Fetch crosstable
        await page.goto(crosstable_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)
        crosstable_html = await page.content()
        crosstable_text = _clean(await page.inner_text("body"))

        # Fetch schedule/notice
        await page.goto(schedule_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(1000)
        schedule_text = _clean(await page.inner_text("body"))

        # try to find latest round link from root page (art=2&rd=X)
        root_soup = BeautifulSoup(root_html, "lxml")
        latest_round: Optional[int] = None
        for a in root_soup.find_all("a", href=True):
            href = a["href"]
            m = re.search(r"art=2&rd=(\d+)", href)
            if m:
                try:
                    r = int(m.group(1))
                    if latest_round is None or r > latest_round:
                        latest_round = r
                except Exception:
                    pass

        # fallback: extract from crosstable text
        extracted_round = _extract_round_number(crosstable_text) or _extract_round_number(root_text)
        latest_round = latest_round or extracted_round

        # If we found a latest round, fetch pairings page for that round
        pairings_html = None
        pairings_text = ""
        if latest_round:
            pairings_url = f"https://s2.chess-results.com/tnr{tournament_id}.aspx?lan=1&art=2&rd={latest_round}&SNode=S0"
            await page.goto(pairings_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(1500)
            pairings_html = await page.content()
            pairings_text = _clean(await page.inner_text("body"))

        await browser.close()

    # parse soups
    root_soup = BeautifulSoup(root_html, "lxml")
    cross_soup = BeautifulSoup(crosstable_html, "lxml")
    pair_soup = BeautifulSoup(pairings_html, "lxml") if pairings_html else None

    title_node = root_soup.find(string=re.compile(r"Check N Mate", flags=re.IGNORECASE))
    tournament_name = _clean(str(title_node)) if title_node else None

    latest_round_final = latest_round or extracted_round
    round_state = _round_state_from_text(crosstable_text + " " + root_text + " " + pairings_text)

    next_round_time_text = None
    m = re.search(r"ROUND\s+AT\s+([0-9:. ]+[APMapm]*)", schedule_text)
    if m:
        next_round_time_text = _clean(m.group(1))

    # Try to find player in pairings first (more detailed)
    rank = None
    points = None
    opponent = None
    color = None
    board = None
    result = None

    def _parse_row_cells(cols: list[str]):
        nonlocal rank, points, opponent, color, board, result
        joined = " | ".join(cols)
        # rank often first
        if cols and cols[0].isdigit():
            try:
                rank = int(cols[0])
            except Exception:
                rank = None
        points = _extract_score(joined)
        # find result patterns
        rm = re.search(r"\b(1-0|0-1|1\/2-1\/2|½-½|0\.5-0\.5|1:0|0:1)\b", joined)
        if rm:
            result = rm.group(1)
        # color detection
        cm = re.search(r"\b(White|Black|W|B)\b", joined, flags=re.IGNORECASE)
        if cm:
            color = cm.group(1)[0].upper()
        bm = re.search(r"\bBoard\s*(\d+)\b", joined, flags=re.IGNORECASE)
        if bm:
            board = bm.group(1)

    found = False
    if pair_soup:
        rows = pair_soup.find_all("tr")
        prow = _find_player_row_by_name(rows, player_name)
        if prow:
            _parse_row_cells(prow)
            # attempt opponent extraction: look for adjacent cell containing opponent name
            try:
                idx = next(i for i, c in enumerate([_normalize_name(x) for x in prow]) if _normalize_name(player_name) in c)
                if idx + 1 < len(prow):
                    opponent = _clean(prow[idx + 1])
            except StopIteration:
                opponent = None
            found = True

    # fallback: cross table search
    if not found:
        rows = cross_soup.find_all("tr")
        crow = _find_player_row_by_name(rows, player_name)
        if crow:
            _parse_row_cells(crow)
            # opponent heuristics: many crosstables include 1.Rd 2.Rd columns; find column with pattern like '123b1' and map
            joined = " | ".join(crow)
            # simple heuristic: opponent name often immediately after Rank and Name columns
            try:
                name_idx = next(i for i, c in enumerate([_normalize_name(x) for x in crow]) if _normalize_name(player_name) in c)
                # opponent might be in next cell
                if name_idx + 1 < len(crow):
                    opponent = _clean(crow[name_idx + 1])
            except StopIteration:
                opponent = None

    # as final fallback, include some root notice if opponent still missing
    if not opponent:
        # try to find player line by simple text search in root_text and extract nearby words
        low = _normalize_name(root_text)
        needle = _normalize_name(player_name)
        if needle in low:
            # take a window around occurrence
            i = low.find(needle)
            snippet = root_text[max(0, i - 200) : i + 200]
            opponent = _clean(snippet)

    return Snapshot(
        tournament_name=tournament_name,
        latest_round=latest_round_final,
        round_state=round_state,
        next_round_time_text=next_round_time_text,
        player_rank=rank,
        player_points=points,
        player_round=PlayerRoundInfo(
            round_no=latest_round_final,
            opponent=opponent,
            color=color,
            board=board,
            result=result,
        ),
    )


def fetch_snapshot_sync(tournament_id: str, player_name: str, headless: bool = True) -> Snapshot:
    return asyncio.run(fetch_snapshot(tournament_id=tournament_id, player_name=player_name, headless=headless))
