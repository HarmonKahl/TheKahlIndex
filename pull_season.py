"""
NCAA Division I Softball season-level game data extractor.

Preserves the original output terminology:
  games_season.csv
  team_games_season.csv
  _completed_dates.txt

Usage:
  python season_data.py
  python season_data.py 2026-02-05 2026-06-05
  python season_data.py 2026-05-01

The 7.0 innings fallback is intentional, per the original per-inning
calculation approach. It is used only when innings cannot be read.
"""

import os
import re
import sys
import json
import time
import threading
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

NCAA_SCOREBOARD_BASE = "https://ncaa-api.henrygd.me"
NCAA_BOXSCORE_BASE = os.environ.get("NCAA_BOXSCORE_BASE", NCAA_SCOREBOARD_BASE)

SCOREBOARD_URL = NCAA_SCOREBOARD_BASE + "/scoreboard/softball/d1/{year}/{month}/{day}"
BOXSCORE_URL = NCAA_BOXSCORE_BASE + "/game/{game_id}/boxscore"

REQUESTS_PER_SECOND_LIMIT = 5
_MIN_INTERVAL = 1.0 / REQUESTS_PER_SECOND_LIMIT

DEFAULT_START_DATE = date(2026, 2, 5)
DEFAULT_END_DATE = date(2026, 6, 5)


class RateLimiter:
    def __init__(self, min_interval=_MIN_INTERVAL):
        self.min_interval = min_interval
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self):
        with self._lock:
            elapsed = time.monotonic() - self._last
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self._last = time.monotonic()


_limiter = RateLimiter()
_session = requests.Session()
_adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)


def _get_json(url, retries=3):
    last_error = None
    for attempt in range(retries + 1):
        try:
            _limiter.wait()
            response = _session.get(url, timeout=20)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < retries:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        delay = float(retry_after)
                    except (TypeError, ValueError):
                        delay = min(2 ** attempt, 10)
                    time.sleep(delay)
                    continue
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(min(2 ** attempt, 10))
    raise RuntimeError(f"Request failed after {retries + 1} attempts: {url}: {last_error}")


def _get_scoreboard_page(year, month, day, page):
    url = SCOREBOARD_URL.format(year=year, month=month, day=day)
    if page > 1:
        url += f"?page={page}"
    return _get_json(url)


def extract_team(side_data, fallback):
    if not isinstance(side_data, dict):
        return fallback
    names = side_data.get("names") or {}
    if isinstance(names, dict):
        return names.get("short") or names.get("full") or side_data.get("description") or fallback
    return side_data.get("description") or fallback


def extract_score(side_data):
    if not isinstance(side_data, dict):
        return None
    for key in ("score", "currentScore", "runs"):
        value = side_data.get(key)
        if value not in (None, ""):
            return value
    return None


def extract_game_id(game):
    if not isinstance(game, dict):
        return None
    for key in ("gameID", "id", "contestId", "contestID"):
        value = game.get(key)
        if value not in (None, ""):
            value = str(value).strip()
            if "/" in value:
                value = value.rstrip("/").split("/")[-1]
            return value

    url = game.get("url") or game.get("link") or ""
    match = re.search(r"/game/(\d+)", str(url))
    return match.group(1) if match else None


def unique_key(game, away_team, home_team, away_score, home_score, date_str):
    game_id = extract_game_id(game)
    if game_id:
        return f"id:{game_id}"

    url = game.get("url") or game.get("link")
    if url:
        return f"url:{url}"

    start_time = (
        game.get("startTime")
        or game.get("startTimeEpoch")
        or game.get("gameTime")
        or ""
    )
    return (
        f"fallback:{date_str}|{away_team}|{home_team}|"
        f"{away_score}|{home_score}|{start_time}"
    )


def parse_innings_pitched(ip_str):
    """Convert baseball/softball innings notation (e.g. 6.1) to decimal thirds."""
    if ip_str in (None, ""):
        return None

    value = str(ip_str).strip()
    if "." not in value:
        try:
            return float(int(value))
        except (TypeError, ValueError):
            return None

    whole_text, _, fraction_text = value.partition(".")
    try:
        whole = int(whole_text)
    except ValueError:
        return None

    thirds = {"0": 0.0, "1": 1 / 3, "2": 2 / 3}.get(fraction_text[:1])
    if thirds is None:
        return None
    return whole + thirds


def _first_present(mapping, keys):
    """Return the first nonempty value, preserving valid False and zero values."""
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        if key in mapping and mapping[key] is not None and mapping[key] != "":
            return mapping[key]
    return None


def _team_id(team):
    if not isinstance(team, dict):
        return ""
    nested = team.get("team") if isinstance(team.get("team"), dict) else {}
    value = _first_present(team, ("teamId", "id"))
    if value is None:
        value = _first_present(nested, ("teamId", "id"))
    return str(value) if value is not None else ""


def _is_home(team):
    if not isinstance(team, dict):
        return None
    for key in ("isHome", "home", "homeTeam"):
        if key in team:
            value = team[key]
            if value is True or value == 1 or str(value).lower() == "true":
                return True
            if value is False or value == 0 or str(value).lower() == "false":
                return False
    return None


def _get_team_lists(data):
    """Support the common top-level/nested NCAA boxscore team containers."""
    if not isinstance(data, dict):
        return [], []

    root = data.get("boxscore") if isinstance(data.get("boxscore"), dict) else data

    metadata = (
        root.get("teams")
        or root.get("teamsBoxscore")
        or data.get("teams")
        or data.get("teamsBoxscore")
        or []
    )
    box_teams = (
        root.get("teamBoxscore")
        or root.get("teamsBoxscore")
        or root.get("teams")
        or data.get("teamBoxscore")
        or data.get("teamsBoxscore")
        or data.get("teams")
        or []
    )

    if isinstance(metadata, dict):
        metadata = metadata.get("team") or metadata.get("teams") or []
    if isinstance(box_teams, dict):
        box_teams = box_teams.get("team") or box_teams.get("teams") or []

    return (
        metadata if isinstance(metadata, list) else [],
        box_teams if isinstance(box_teams, list) else [],
    )


def fetch_innings_for_game(game_id, debug=False, box_retries=2):
    if not game_id:
        return None, None

    data = None
    for attempt in range(box_retries + 1):
        try:
            data = _get_json(BOXSCORE_URL.format(game_id=game_id), retries=0)
            break
        except requests.exceptions.HTTPError as error:
            status = error.response.status_code if error.response is not None else None
            if status == 404:
                if debug:
                    print(f"  Boxscore 404 for game {game_id}; using 7.0 innings fallback.")
                return 7.0, 7.0
            if attempt < box_retries:
                time.sleep(1.5 * (attempt + 1))
        except Exception as error:
            if debug:
                print(f"  Innings request error for {game_id}: {error}")
            if attempt < box_retries:
                time.sleep(1.5 * (attempt + 1))

    if data is None:
        if debug:
            print(f"  No boxscore data for {game_id}; using 7.0 innings fallback.")
        return 7.0, 7.0

    root = data.get("boxscore") if isinstance(data.get("boxscore"), dict) else data
    metadata, box_teams = _get_team_lists(data)

    home_id = away_id = None
    for team in metadata:
        tid = _team_id(team)
        home_flag = _is_home(team)
        if home_flag is True:
            home_id = tid
        elif home_flag is False:
            away_id = tid

    # Preserve the original fallback ordering when home/away flags are absent.
    if (not home_id or not away_id) and len(metadata) >= 2:
        away_id = _team_id(metadata[0])
        home_id = _team_id(metadata[1])

    if not home_id or not away_id:
        if debug:
            print(f"  Could not identify home/away teams for {game_id}; using 7.0.")
        return 7.0, 7.0

    innings_by_team = {}
    for team_box in box_teams:
        tid = _team_id(team_box)
        team_stats = team_box.get("teamStats") if isinstance(team_box, dict) else {}
        if not isinstance(team_stats, dict):
            team_stats = {}

        pitcher_totals = (
            team_stats.get("pitcherTotals")
            or team_box.get("pitchingTotals")
            or team_box.get("pitching")
            or {}
        )
        if isinstance(pitcher_totals, list):
            # Some formats represent stats as a list of name/value objects.
            converted = {}
            for item in pitcher_totals:
                if isinstance(item, dict):
                    stat_name = item.get("name") or item.get("stat")
                    stat_value = item.get("value") or item.get("statValue")
                    if stat_name:
                        converted[str(stat_name)] = stat_value
            pitcher_totals = converted

        ip_raw = _first_present(
            pitcher_totals,
            ("inningsPitched", "ip", "IP", "innings pitched"),
        )
        if ip_raw is not None:
            innings_by_team[tid] = parse_innings_pitched(ip_raw)

    away_innings = innings_by_team.get(away_id)
    home_innings = innings_by_team.get(home_id)

    # Keep the user's intentional 7.0 fallback for unavailable innings.
    if away_innings is None:
        away_innings = 7.0
    if home_innings is None:
        home_innings = 7.0

    return away_innings, home_innings


def fetch_innings_concurrent(game_ids, debug=False, max_workers=5):
    results = {}
    if not game_ids:
        return results

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(fetch_innings_for_game, game_id, debug): game_id
            for game_id in game_ids
        }
        for future in as_completed(futures):
            game_id = futures[future]
            try:
                results[game_id] = future.result()
            except Exception as error:
                if debug:
                    print(f"  Unexpected innings error for {game_id}: {error}; using 7.0.")
                results[game_id] = (7.0, 7.0)
    return results


def pull_day(year, month, day, max_pages=50, fetch_innings=True,
             debug=False, innings_workers=5):
    date_str = f"{year}-{month:02d}-{day:02d}"
    seen = {}
    seen_order = []
    page_signatures = set()
    pagination_finished = False

    for page in range(1, max_pages + 1):
        data = _get_scoreboard_page(year, month, day, page)
        raw_games = data.get("games", []) if isinstance(data, dict) else []

        if not raw_games:
            pagination_finished = True
            break

        # Stop if the endpoint ignores ?page= and repeats the same page.
        signature = tuple(
            extract_game_id(entry.get("game", entry) if isinstance(entry, dict) else {})
            or str(entry)
            for entry in raw_games
        )
        if signature in page_signatures:
            pagination_finished = True
            if debug:
                print(f"  Scoreboard repeated page {page}; stopping pagination.")
            break
        page_signatures.add(signature)

        for entry in raw_games:
            if not isinstance(entry, dict):
                continue
            game = entry.get("game", entry)
            if not isinstance(game, dict):
                continue

            away_data = game.get("away") or {}
            home_data = game.get("home") or {}
            away_team = extract_team(away_data, "Away")
            home_team = extract_team(home_data, "Home")
            away_score = extract_score(away_data)
            home_score = extract_score(home_data)
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
                "state": game.get("gameState", "unknown"),
                "status": game.get("status", ""),
                "away_innings": None,
                "home_innings": None,
            }
            seen_order.append(key)

    else:
        # Do not silently mark a date complete if the page cap was reached.
        raise RuntimeError(
            f"Reached max_pages={max_pages} for {date_str}; "
            "date was not marked complete. Increase max_pages or inspect pagination."
        )

    if not pagination_finished:
        raise RuntimeError(f"Scoreboard pagination did not finish for {date_str}.")

    games = [seen[key] for key in seen_order]

    if fetch_innings:
        game_ids = [row["game_id"] for row in games if row["game_id"]]
        innings_map = fetch_innings_concurrent(
            game_ids, debug=debug, max_workers=innings_workers
        )
        for row in games:
            row["away_innings"], row["home_innings"] = innings_map.get(
                row["game_id"], (7.0, 7.0)
            )

    return games


def games_to_team_rows(games):
    rows = []
    for game in games:
        if game["away_score"] is None or game["home_score"] is None:
            continue
        try:
            away_score = int(game["away_score"])
            home_score = int(game["home_score"])
        except (TypeError, ValueError):
            continue

        pairs = [
            (
                "away", game["away_team"], game["home_team"],
                away_score, home_score, game["away_innings"], game["home_innings"]
            ),
            (
                "home", game["home_team"], game["away_team"],
                home_score, away_score, game["home_innings"], game["away_innings"]
            ),
        ]

        for role, team, opponent, runs_for, runs_against, inn_batted, inn_fielded in pairs:
            rows.append({
                "date": game["date"],
                "game_id": game["game_id"],
                "team": team,
                "opponent": opponent,
                "role": role,
                "runs_for": runs_for,
                "runs_against": runs_against,
                "innings_batted": inn_batted,
                "innings_fielded": inn_fielded,
                "win": None if runs_for == runs_against else int(runs_for > runs_against),
            })
    return rows


def _daterange(start, end):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _load_existing_csv(path):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return pd.read_csv(path, dtype={"game_id": "string"}).to_dict("records")
    return []


def _deduplicate_games(rows):
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    if "game_id" in frame.columns:
        # Game ID preserves same-day doubleheaders with identical opponents/scores.
        has_id = frame["game_id"].notna() & (frame["game_id"].astype(str) != "")
        identified = frame[has_id].drop_duplicates(subset=["game_id"], keep="last")
        unidentified = frame[~has_id].drop_duplicates(
            subset=["date", "away_team", "home_team", "away_score", "home_score"],
            keep="last",
        )
        frame = pd.concat([identified, unidentified], ignore_index=True)
    else:
        frame = frame.drop_duplicates(
            subset=["date", "away_team", "home_team", "away_score", "home_score"],
            keep="last",
        )
    return frame


def _deduplicate_team_rows(rows):
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    keys = ["game_id", "team", "opponent", "role"]
    if "game_id" in frame.columns:
        has_id = frame["game_id"].notna() & (frame["game_id"].astype(str) != "")
        identified = frame[has_id].drop_duplicates(subset=keys, keep="last")
        unidentified = frame[~has_id].drop_duplicates(
            subset=["date", "team", "opponent", "role"], keep="last"
        )
        frame = pd.concat([identified, unidentified], ignore_index=True)
    else:
        frame = frame.drop_duplicates(
            subset=["date", "team", "opponent", "role"], keep="last"
        )
    return frame


def pull_season(start, end, out_dir=".", fetch_innings=True,
                debug=False, max_retries=2):
    os.makedirs(out_dir, exist_ok=True)

    games_path = os.path.join(out_dir, "games_season.csv")
    team_path = os.path.join(out_dir, "team_games_season.csv")
    progress_path = os.path.join(out_dir, "_completed_dates.txt")

    completed = set()
    if os.path.exists(progress_path):
        with open(progress_path, encoding="utf-8") as file:
            completed = {line.strip() for line in file if line.strip()}

    all_games = _load_existing_csv(games_path)
    all_team_rows = _load_existing_csv(team_path)
    dates = list(_daterange(start, end))

    for index, current_date in enumerate(dates, 1):
        date_str = current_date.isoformat()
        if date_str in completed:
            continue

        day_games = None
        for attempt in range(max_retries + 1):
            try:
                day_games = pull_day(
                    current_date.year,
                    current_date.month,
                    current_date.day,
                    fetch_innings=fetch_innings,
                    debug=debug,
                )
                break
            except Exception as error:
                if debug:
                    print(
                        f"[{index}/{len(dates)}] {date_str}: "
                        f"error ({error}), retry {attempt + 1}/{max_retries}"
                    )
                if attempt < max_retries:
                    time.sleep(2 * (attempt + 1))

        if day_games is None:
            print(f"[{date_str}] Not completed; it will be retried next run.")
            continue

        all_games.extend(day_games)
        all_team_rows.extend(games_to_team_rows(day_games))

        games_df = _deduplicate_games(all_games)
        team_df = _deduplicate_team_rows(all_team_rows)

        games_df.to_csv(games_path, index=False)
        team_df.to_csv(team_path, index=False)

        completed.add(date_str)
        with open(progress_path, "w", encoding="utf-8") as file:
            file.write("\n".join(sorted(completed)))

        print(
            f"[{index}/{len(dates)}] {date_str}: "
            f"{len(day_games)} games processed; "
            f"{len(games_df)} total unique games saved."
        )

    print(f"\nDone. {len(_deduplicate_games(all_games))} unique game records saved to {out_dir}/")
    return _deduplicate_games(all_games), _deduplicate_team_rows(all_team_rows)


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        start_date = date.fromisoformat(sys.argv[1])
        end_date = date.fromisoformat(sys.argv[2])
    elif len(sys.argv) == 2:
        start_date = end_date = date.fromisoformat(sys.argv[1])
    else:
        start_date = DEFAULT_START_DATE
        end_date = DEFAULT_END_DATE

    print(f"Pulling season from {start_date.isoformat()} to {end_date.isoformat()}...")
    pull_season(
        start_date,
        end_date,
        out_dir=".",
        fetch_innings=True,
        debug=True,
    )
