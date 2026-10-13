import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

import pandas as pd
import requests

SCOREBOARD_URL = "https://ncaa-api.henrygd.me/scoreboard/softball/d1/{year}/{month:02d}/{day:02d}"
BOXSCORE_URL = "https://ncaa-api.henrygd.me/game/{game_id}/boxscore"

_session = requests.Session()
_adapter = requests.adapters.HTTPAdapter(
    pool_connections=20, pool_maxsize=20, max_retries=2
)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)


def _get_json(url):
    resp = _session.get(url, timeout=5)
    resp.raise_for_status()
    return resp.json()


def _get_scoreboard_page(year, month, day, page):
    url = SCOREBOARD_URL.format(year=year, month=month, day=day)
    if page > 1:
        url += f"?page={page}"
    return _get_json(url)


def extract_team(side_data, fallback):
    if not isinstance(side_data, dict):
        return fallback
    names = side_data.get("names", {})
    return (
        names.get("short")
        or names.get("full")
        or side_data.get("description")
        or fallback
    )


def extract_score(side_data):
    if not isinstance(side_data, dict):
        return None
    for key in ("score", "currentScore", "runs"):
        val = side_data.get(key)
        if val not in (None, ""):
            return val
    return None


def extract_game_id(game):
    for key in ("gameID", "id", "contestId", "contestID"):
        val = game.get(key)
        if val:
            return str(val)
    url = game.get("url") or game.get("link") or ""
    m = re.search(r"/game/(\d+)", str(url))
    return m.group(1) if m else None


def unique_key(game, away_team, home_team, away_score, home_score, date_str):
    game_id = extract_game_id(game)
    if game_id:
        return f"id:{game_id}"
    url = game.get("url") or game.get("link")
    if url:
        return f"url:{url}"
    start = (
        game.get("startTime")
        or game.get("startTimeEpoch")
        or game.get("gameTime")
        or ""
    )
    return f"fallback:{date_str}|{away_team}|{home_team}|{away_score}|{home_score}|{start}"


def parse_innings_pitched(ip_str):
    if ip_str in (None, ""):
        return None
    s = str(ip_str).strip()
    if "." not in s:
        try:
            return float(int(s))
        except ValueError:
            return None
    whole_s, _, frac_s = s.partition(".")
    try:
        whole = int(whole_s)
    except ValueError:
        return None
    thirds = {"1": 1 / 3, "2": 2 / 3}.get(frac_s[:1], 0.0)
    return whole + thirds


def estimate_innings_from_batting(hitting_stats):
    if not isinstance(hitting_stats, dict):
        return None
    try:
        ab = float(hitting_stats.get("atBats", 0) or 0)
        h = float(hitting_stats.get("hits", 0) or 0)
        sf = float(hitting_stats.get("sacrificeFlies", 0) or 0)
        sh = float(hitting_stats.get("sacrificeHits", 0) or 0)
        cs = float(hitting_stats.get("caughtStealing", 0) or 0)

        outs_made = (ab - h) + sf + sh + cs
        if outs_made > 0:
            return round(outs_made / 3.0, 4)
    except Exception:
        pass
    return None


def fetch_innings_for_game(game_id):
    if not game_id:
        return None, None
    try:
        data = _get_json(BOXSCORE_URL.format(game_id=game_id))
    except Exception:
        return None, None

    teams_meta = data.get("teams", [])
    home_id = next(
        (t["teamId"] for t in teams_meta if t.get("isHome")), None
    )
    away_id = next(
        (t["teamId"] for t in teams_meta if t.get("isHome") is False), None
    )
    if home_id is None or away_id is None:
        return None, None
    home_id, away_id = str(home_id), str(away_id)

    ip_by_team = {}
    hitting_by_team = {}

    for tb in data.get("teamBoxscore", []):
        tid = str(tb.get("teamId"))
        team_stats = tb.get("teamStats") or {}

        pitcher_totals = team_stats.get("pitcherTotals") or {}
        ip_by_team[tid] = parse_innings_pitched(
            pitcher_totals.get("inningsPitched")
        )
        hitting_by_team[tid] = team_stats.get("hittingTotals") or {}

    home_ip = ip_by_team.get(home_id)
    away_ip = ip_by_team.get(away_id)

    if home_ip is None:
        home_ip = estimate_innings_from_batting(hitting_by_team.get(away_id))
    if away_ip is None:
        away_ip = estimate_innings_from_batting(hitting_by_team.get(home_id))

    return away_ip, home_ip


def fetch_innings_concurrent(game_ids, max_workers=5):
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(fetch_innings_for_game, gid): gid for gid in game_ids
        }
        for fut in as_completed(futures):
            gid = futures[fut]
            try:
                results[gid] = fut.result()
            except Exception:
                results[gid] = (None, None)
    return results


def pull_day(year, month, day, max_pages=10, fetch_innings=True):
    date_str = f"{year}-{month:02d}-{day:02d}"
    seen, seen_order = {}, []

    for page in range(1, max_pages + 1):
        try:
            data = _get_scoreboard_page(year, month, day, page)
        except Exception:
            break

        raw_games = data.get("games", [])
        if not raw_games:
            break

        for entry in raw_games:
            game = entry.get("game", entry)
            away_data, home_data = game.get("away", {}), game.get("home", {})
            away_team = extract_team(away_data, "Away")
            home_team = extract_team(home_data, "Home")
            away_score = extract_score(away_data)
            home_score = extract_score(home_data)
            state = game.get("gameState", "unknown")
            status = game.get("status", "")
            game_id = extract_game_id(game)

            key = unique_key(
                game, away_team, home_team, away_score, home_score, date_str
            )
            if key in seen:
                continue
            seen[key] = {
                "date": date_str,
                "game_id": game_id,
                "away_team": away_team,
                "away_score": away_score,
                "home_team": home_team,
                "home_score": home_score,
                "state": state,
                "status": status,
                "away_innings": None,
                "home_innings": None,
            }
            seen_order.append(key)

    games = [seen[k] for k in seen_order]

    if fetch_innings:
        game_ids = [row["game_id"] for row in games if row["game_id"]]
        inn_map = fetch_innings_concurrent(game_ids, max_workers=5)
        for row in games:
            row["away_innings"], row["home_innings"] = inn_map.get(
                row["game_id"], (None, None)
            )

    return games


def games_to_team_rows(games):
    rows = []
    for g in games:
        if g["away_score"] is None or g["home_score"] is None:
            continue
        try:
            away_score, home_score = int(g["away_score"]), int(g["home_score"])
        except (TypeError, ValueError):
            continue

        away_inn = (
            g["away_innings"]
            if g["away_innings"] and g["away_innings"] > 0
            else 7.0
        )
        home_inn = (
            g["home_innings"]
            if g["home_innings"] and g["home_innings"] > 0
            else 7.0
        )

        pairs = [
            (
                "away",
                g["away_team"],
                g["home_team"],
                away_score,
                home_score,
                away_inn,
                home_inn,
            ),
            (
                "home",
                g["home_team"],
                g["away_team"],
                home_score,
                away_score,
                home_inn,
                away_inn,
            ),
        ]
        for (
            role,
            team,
            opponent,
            runs_for,
            runs_against,
            inn_batted,
            inn_fielded,
        ) in pairs:
            rows.append(
                {
                    "date": g["date"],
                    "game_id": g["game_id"],
                    "team": team,
                    "opponent": opponent,
                    "role": role,
                    "runs
