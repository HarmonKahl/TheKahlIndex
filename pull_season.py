import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

import pandas as pd
import requests

SCOREBOARD_URL = "https://ncaa-api.henrygd.me/scoreboard/softball/d1/{year}/{month:02d}/{day:02d}"
BOXSCORE_URL = "https://ncaa-api.henrygd.me/game/{game_id}/boxscore"

REQUESTS_PER_SECOND_LIMIT = 5
_MIN_INTERVAL = 1.0 / REQUESTS_PER_SECOND_LIMIT


class RateLimiter:
    def __init__(self, min_interval=_MIN_INTERVAL):
        self.min_interval = min_interval
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self):
        with self._lock:
            elapsed = time.time() - self._last
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self._last = time.time()


_limiter = RateLimiter()
_session = requests.Session()
_adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)


def _get_json(url):
    _limiter.wait()
    resp = _session.get(url, timeout=15)
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


def unique_key(game, away_team, home_team, away_score, home_score, date_str, idx=0):
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
    return f"fallback:{date_str}|{away_team}|{home_team}|{away_score}|{home_score}|{start}|idx:{idx}"


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
    thirds = {"0": 0.0, "1": 1 / 3, "2": 2 / 3}.get(frac_s[:1], 0.0)
    return whole + thirds


def fetch_boxscore_data(game_id, debug=False):
    """Fetches innings pitched AND individual player hitting box scores."""
    if not game_id:
        return (None, None), []
    try:
        data = _get_json(BOXSCORE_URL.format(game_id=game_id))
    except Exception as e:
        if debug:
            print(f"  boxscore fetch failed for game {game_id}: {e}")
        return (None, None), []

    teams_meta = data.get("teams", [])
    home_id = next((t["teamId"] for t in teams_meta if t.get("isHome")), None)
    away_id = next((t["teamId"] for t in teams_meta if t.get("isHome") is False), None)
    
    team_names = {
        str(t.get("teamId")): t.get("shortName", t.get("name", "Unknown"))
        for t in teams_meta
    }

    home_id = str(home_id) if home_id is not None else None
    away_id = str(away_id) if away_id is not None else None

    ip_by_team = {}
    player_rows = []

    for tb in data.get("teamBoxscore", []):
        tid = str(tb.get("teamId"))
        team_name = team_names.get(tid, "Unknown")
        
        # 1. Innings Pitched
        pitcher_totals = (tb.get("teamStats") or {}).get("pitcherTotals") or {}
        ip_by_team[tid] = parse_innings_pitched(
            pitcher_totals.get("inningsPitched")
        )

        # 2. Extract Individual Player Hitting Stats
        for player in tb.get("playerStats", []):
            stats = player.get("stats", {})
            # Ensure player had at least 1 AB or BB (i.e. made a plate appearance)
            try:
                ab = int(stats.get("ab", 0) or 0)
                bb = int(stats.get("bb", 0) or 0)
                if ab == 0 and bb == 0:
                    continue
                
                player_rows.append({
                    "game_id": game_id,
                    "player_name": player.get("name", "Unknown"),
                    "team": team_name,
                    "AB": ab,
                    "H": int(stats.get("hits", stats.get("h", 0)) or 0),
                    "BB": bb,
                    "2B": int(stats.get("d", stats.get("2b", 0)) or 0),
                    "3B": int(stats.get("t", stats.get("3b", 0)) or 0),
                    "HR": int(stats.get("hr", 0) or 0)
                })
            except (ValueError, TypeError):
                continue

    away_ip = ip_by_team.get(away_id) if away_id else None
    home_ip = ip_by_team.get(home_id) if home_id else None

    return (away_ip, home_ip), player_rows


def fetch_boxscores_concurrent(game_ids, debug=False, max_workers=5):
    results_inn = {}
    all_player_rows = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(fetch_boxscore_data, gid, debug): gid
            for gid in game_ids
        }
        for fut in as_completed(futures):
            gid = futures[fut]
            try:
                inn, players = fut.result()
                results_inn[gid] = inn
                all_player_rows.extend(players)
            except Exception as e:
                if debug:
                    print(f"  concurrent fetch failed for game {gid}: {e}")
                results_inn[gid] = (None, None)
    return results_inn, all_player_rows


def pull_day(
    year,
    month,
    day,
    max_pages=20,
    fetch_innings=True,
    debug=False,
    innings_workers=5,
):
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

        for idx, entry in enumerate(raw_games):
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
                game,
                away_team,
                home_team,
                away_score,
                home_score,
                date_str,
                idx=idx,
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
    day_player_rows = []

    if fetch_innings:
        game_ids = [row["game_id"] for row in games if row["game_id"]]
        inn_map, day_player_rows = fetch_boxscores_concurrent(
            game_ids, debug=debug, max_workers=innings_workers
        )
        for row in games:
            row["away_innings"], row["home_innings"] = inn_map.get(
                row["game_id"], (None, None)
            )

    return games, day_player_rows


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
                    "runs_for": runs_for,
                    "runs_against": runs_against,
                    "innings_batted": inn_batted,
                    "innings_fielded": inn_fielded,
                    "win": (
                        None
                        if runs_for == runs_against
                        else int(runs_for > runs_against)
                    ),
                }
            )
    return rows


def _daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def pull_season(
    start,
    end,
    out_dir=".",
    fetch_innings=True,
    debug=False,
    max_retries=2,
):
    os.makedirs(out_dir, exist_ok=True)
    games_path = os.path.join(out_dir, "games_season.csv")
    team_path = os.path.join(out_dir, "team_games_season.csv")
    player_path = os.path.join(out_dir, "player_boxscores_2026.csv")
    progress_path = os.path.join(out_dir, "_completed_dates.txt")

    completed = set()
    if os.path.exists(progress_path):
        with open(progress_path) as f:
            completed = set(line.strip() for line in f if line.strip())

    if not os.
