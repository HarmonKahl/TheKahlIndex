"""
pull_player_stats.py

Pulls per-PLAYER batting and fielding stats for D-I softball games using the NCAA API.
Only queries games marked as FINAL on the scoreboard to prevent fetching nonexistent box scores.
"""

import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

import pandas as pd
import requests

SCOREBOARD_URL = "https://ncaa-api.henrygd.me/scoreboard/softball/d1/{year}/{month:02d}/{day:02d}"
BOXSCORE_URL = "https://ncaa-api.henrygd.me/game/{game_id}/boxscore"

REQUESTS_PER_SECOND_LIMIT = 2.0
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
_adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=10)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)


def _get_json_with_retry(url, max_retries=3):
    """Fetches JSON, skipping non-existent box scores immediately on 404/400."""
    RETRYABLE_CODES = {428, 500, 502, 503, 504}

    for attempt in range(max_retries):
        _limiter.wait()
        try:
            resp = _session.get(url, timeout=10)

            # If the box score doesn't exist (canceled/unplayed game), don't waste retries
            if resp.status_code in (400, 404):
                return None

            if resp.status_code in RETRYABLE_CODES:
                time.sleep(1.5 * (attempt + 1))
                continue

            resp.raise_for_status()
            return resp.json()

        except requests.exceptions.HTTPError as e:
            if resp.status_code in RETRYABLE_CODES and attempt < max_retries - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise e
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            time.sleep(1.0 * (attempt + 1))

    return None


def _get_scoreboard_page(year, month, day, page):
    url = SCOREBOARD_URL.format(year=year, month=month, day=day)
    if page > 1:
        url += f"?page={page}"
    return _get_json_with_retry(url)


def extract_game_id(game):
    for key in ("gameID", "id", "contestId", "contestID"):
        val = game.get(key)
        if val:
            return str(val)
    url = game.get("url") or game.get("link") or ""
    m = re.search(r"/game/(\d+)", str(url))
    return m.group(1) if m else None


def discover_game_ids(year, month, day, max_pages=20):
    """Only fetches game IDs for games that were actually completed (FINAL)."""
    seen = set()
    for page in range(1, max_pages + 1):
        data = _get_scoreboard_page(year, month, day, page)
        if not data:
            break

        raw_games = data.get("games", [])
        if not raw_games:
            break

        for entry in raw_games:
            game = entry.get("game", entry)
            
            # Check game status -- skip canceled, postponed, or unplayed games
            state = str(game.get("gameState") or game.get("status") or "").lower()
            if "final" not in state and "completed" not in state and state != "f":
                continue

            gid = extract_game_id(game)
            if gid:
                seen.add(gid)

    return sorted(seen)


def _num(val):
    if val in (None, ""):
        return None
    try:
        return float(val)
    except ValueError:
        return None


def extract_player_rows(boxscore_json, date_str, game_id):
    if not boxscore_json or not isinstance(boxscore_json, dict):
        return []

    teams_meta = boxscore_json.get("teams", [])
    team_by_id = {str(t.get("teamId")): t for t in teams_meta}
    if len(team_by_id) != 2:
        return []

    team_boxscores = boxscore_json.get("teamBoxscore", [])
    rows = []
    for tb in team_boxscores:
        tid = str(tb.get("teamId"))
        team_meta = team_by_id.get(tid, {})
        team_name = team_meta.get("nameShort") or team_meta.get("nameFull") or tid
        opp_meta = next((t for oid, t in team_by_id.items() if oid != tid), {})
        opp_name = opp_meta.get("nameShort") or opp_meta.get("nameFull") or ""

        for player in tb.get("playerStats", []):
            batter = player.get("batterStats") or {}
            field = player.get("fieldStats") or {}
            rows.append({
                "date": date_str,
                "game_id": game_id,
                "team": team_name,
                "opponent": opp_name,
                "last_name": player.get("lastName", ""),
                "first_name": player.get("firstName", ""),
                "position": player.get("position", ""),
                "number": player.get("number"),
                "starter": player.get("starter"),
                "participated": player.get("participated"),
                "at_bats": _num(batter.get("atBats")),
                "runs_scored": _num(batter.get("runsScored")),
                "hits": _num(batter.get("hits")),
                "rbi": _num(batter.get("runsBattedIn")),
                "walks": _num(batter.get("walks")),
                "strikeouts": _num(batter.get("strikeouts")),
                "batting_average": _num(batter.get("battingAverage")),
                "on_base_pct": _num(
                    str(batter.get("onBasePercentage", "")).replace("%", "")
                ),
                "putouts": _num(field.get("putouts")),
                "assists": _num(field.get("assists")),
                "errors": _num(field.get("errors")),
            })
    return rows


def fetch_player_rows_for_game(game_id, date_str):
    try:
        data = _get_json_with_retry(BOXSCORE_URL.format(game_id=game_id))
        if not data:
            return []
    except Exception:
        return []
    return extract_player_rows(data, date_str, game_id)


def fetch_player_rows_concurrent(game_ids, date_str, max_workers=2):
    all_rows = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(fetch_player_rows_for_game, gid, date_str): gid for gid in game_ids}
        for fut in as_completed(futures):
            try:
                all_rows.extend(fut.result())
            except Exception:
                pass
    return all_rows


def _daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def pull_player_stats(start, end, out_dir=".", max_retries=2, max_workers=2):
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "player_games_season.csv")
    progress_path = os.path.join(out_dir, "_player_completed_dates.txt")

    completed = set()
    if os.path.exists(progress_path):
        with open(progress_path) as f:
            completed = set(line.strip() for line in f if line.strip())

    all_rows = pd.read_csv(out_path).to_dict("records") if os.path.exists(out_path) else []

    dates = list(_daterange(start, end))
    print(f"{len(dates)} day(s) requested, {len(completed)} already done\n")

    for i, d in enumerate(dates, 1):
        date_str = d.isoformat()
        if date_str in completed:
            continue

        try:
            game_ids = discover_game_ids(d.year, d.month, d.day)
            day_rows = fetch_player_rows_concurrent(game_ids, date_str, max_workers=max_workers)
        except Exception as e:
            print(f"[{i}/{len(dates)}] {date_str}: error ({e})")
            continue

        all_rows.extend(day_rows)
        completed.add(date_str)

        pd.DataFrame(all_rows).to_csv(out_path, index=False)
        with open(progress_path, "w") as f:
            f.write("\n".join(sorted(completed)))

        print(f"[{i}/{len(dates)}] {date_str}: {len(day_rows)} player-rows "
              f"(running total: {len(all_rows)})")

    print(f"\nDone. {len(all_rows)} player-rows written to {out_path}")
    return pd.DataFrame(all_rows)


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        start_date = date.fromisoformat(sys.argv[1])
        end_date = date.fromisoformat(sys.argv[2])
    elif len(sys.argv) == 2:
        start_date = end_date = date.fromisoformat(sys.argv[1])
    else:
        start_date = end_date = date.today() - timedelta(days=1)

    print(f"Pulling player stats from {start_date.isoformat()} to {end_date.isoformat()}...")
    df = pull_player_stats(start_date, end_date, out_dir=".")
    print(f"Pulled {len(df)} player-rows total")
