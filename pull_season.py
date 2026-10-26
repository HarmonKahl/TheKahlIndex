import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

import pandas as pd
import requests

NCAA_SCOREBOARD_BASE = "https://ncaa-api.henrygd.me"
NCAA_BOXSCORE_BASE = os.environ.get("NCAA_BOXSCORE_BASE", "https://ncaa-api.henrygd.me")
SCOREBOARD_URL = NCAA_SCOREBOARD_BASE + "/scoreboard/softball/d1/{year}/{month:02d}/{day:02d}"
BOXSCORE_URL = NCAA_BOXSCORE_BASE + "/game/{game_id}/boxscore"

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
    resp = _session.get(url, timeout=10)
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
    return names.get("short") or names.get("full") or side_data.get("description") or fallback


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
    start = game.get("startTime") or game.get("startTimeEpoch") or game.get("gameTime") or ""
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
    thirds = {"0": 0.0, "1": 1 / 3, "2": 2 / 3}.get(frac_s[:1], 0.0)
    return whole + thirds


def fetch_innings_for_game(game_id, debug=False, box_retries=1):
    if not game_id:
        return None, None

    data = None
    for attempt in range(box_retries + 1):
        try:
            data = _get_json(BOXSCORE_URL.format(game_id=game_id))
            break
        except requests.exceptions.HTTPError as err:
            if err.response is not None and err.response.status_code == 404:
                # Game boxscore doesn't exist yet; fail fast
                return 7.0, 7.0
            if attempt < box_retries:
                time.sleep(1.0)
        except Exception:
            if attempt < box_retries:
                time.sleep(1.0)

    if data is None:
        return 7.0, 7.0

    teams_meta = data.get("teams") or data.get("teamsBoxscore") or []
    home_id, away_id = None, None
    for t in teams_meta:
        tid = str(t.get("teamId") or t.get("id") or t.get("team", {}).get("id", ""))
        is_home = t.get("isHome") or t.get("home") or t.get("homeTeam")
        if is_home in (True, "true", "True", 1):
            home_id = tid
        elif is_home in (False, "false", "False", 0):
            away_id = tid

    if (not home_id or not away_id) and len(teams_meta) >= 2:
        away_id = str(teams_meta[0].get("teamId") or teams_meta[0].get("id", ""))
        home_id = str(teams_meta[1].get("teamId") or teams_meta[1].get("id", ""))

    if not home_id or not away_id:
        return 7.0, 7.0

    ip_by_team = {}
    box_teams = data.get("teamBoxscore") or data.get("teamsBoxscore") or data.get("teams") or []
    
    for tb in box_teams:
        tid = str(tb.get("teamId") or tb.get("id") or tb.get("team", {}).get("id", ""))
        pitcher_totals = (
            (tb.get("teamStats") or {}).get("pitcherTotals") or 
            tb.get("pitchingTotals") or 
            tb.get("pitching") or {}
        )
        ip_raw = pitcher_totals.get("inningsPitched") or pitcher_totals.get("ip") or pitcher_totals.get("IP")
        if ip_raw is not None:
            ip_by_team[tid] = parse_innings_pitched(ip_raw)

    home_ip = ip_by_team.get(home_id)
    away_ip = ip_by_team.get(away_id)

    if home_ip is None and away_ip is None:
        return 7.0, 7.0

    return away_ip, home_ip


def fetch_innings_concurrent(game_ids, debug=False, max_workers=5):
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(fetch_innings_for_game, gid, debug): gid for gid in game_ids}
        for fut in as_completed(futures):
            gid = futures[fut]
            try:
                results[gid] = fut.result()
            except Exception:
                results[gid] = (7.0, 7.0)
    return results


def pull_day(year, month, day, max_pages=20, fetch_innings=True, debug=False, innings_workers=5):
    date_str = f"{year}-{month:02d}-{day:02d}"
    seen, seen_order = {}, []

    for page in range(1, max_pages + 1):
        data = _get_scoreboard_page(year, month, day, page)
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

            key = unique_key(game, away_team, home_team, away_score, home_score, date_str)
            if key in seen:
                continue
            seen[key] = {
                "date": date_str, "game_id": game_id,
                "away_team": away_team, "away_score": away_score,
                "home_team": home_team, "home_score": home_score,
                "state": state, "status": status,
                "away_innings": None, "home_innings": None,
            }
            seen_order.append(key)

    games = [seen[k] for k in seen_order]

    if fetch_innings:
        game_ids = [row["game_id"] for row in games if row["game_id"]]
        inn_map = fetch_innings_concurrent(game_ids, debug=debug, max_workers=innings_workers)
        for row in games:
            row["away_innings"], row["home_innings"] = inn_map.get(row["game_id"], (7.0, 7.0))

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

        pairs = [
            ("away", g["away_team"], g["home_team"], away_score, home_score, g["away_innings"], g["home_innings"]),
            ("home", g["home_team"], g["away_team"], home_score, away_score, g["home_innings"], g["away_innings"]),
        ]
        for role, team, opponent, runs_for, runs_against, inn_batted, inn_fielded in pairs:
            rows.append({
                "date": g["date"], "game_id": g["game_id"],
                "team": team, "opponent": opponent, "role": role,
                "runs_for": runs_for, "runs_against": runs_against,
                "innings_batted": inn_batted, "innings_fielded": inn_fielded,
                "win": None if runs_for == runs_against else int(runs_for > runs_against),
            })
    return rows


def _daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def pull_season(start, end, out_dir=".", fetch_innings=True, debug=False, max_retries=2):
    os.makedirs(out_dir, exist_ok=True)
    games_path = os.path.join(out_dir, "games_season.csv")
    team_path = os.path.join(out_dir, "team_games_season.csv")
    progress_path = os.path.join(out_dir, "_completed_dates.txt")

    completed = set()
    if os.path.exists(progress_path):
        with open(progress_path) as f:
            completed = set(line.strip() for line in f if line.strip())

    all_games = pd.read_csv(games_path).to_dict("records") if os.path.exists(games_path) else []
    all_team_rows = pd.read_csv(team_path).to_dict("records") if os.path.exists(team_path) else []

    dates = list(_daterange(start, end))

    for i, d in enumerate(dates, 1):
        date_str = d.isoformat()
        if date_str in completed:
            continue

        day_games, attempt = None, 0
        while attempt <= max_retries:
            try:
                day_games = pull_day(d.year, d.month, d.day, fetch_innings=fetch_innings, debug=debug)
                break
            except Exception as e:
                attempt += 1
                if debug:
                    print(f"[{i}/{len(dates)}] {date_str}: error ({e}), retry {attempt}/{max_retries}")
                time.sleep(2 * attempt)

        if day_games is None:
            continue

        all_games.extend(day_games)
        all_team_rows.extend(games_to_team_rows(day_games))
        completed.add(date_str)

        # Robust multi-column deduplication
        games_df = pd.DataFrame(all_games).drop_duplicates(
            subset=["date", "away_team", "home_team", "away_score", "home_score"]
        ) if all_games else pd.DataFrame()
        
        team_df = pd.DataFrame(all_team_rows).drop_duplicates(
            subset=["date", "team", "opponent", "role"]
        ) if all_team_rows else pd.DataFrame()

        games_df.to_csv(games_path, index=False)
        team_df.to_csv(team_path, index=False)

        with open(progress_path, "w") as f:
            f.write("\n".join(sorted(completed)))

        print(f"[{i}/{len(dates)}] {date_str}: {len(day_games)} games processed.")

    print(f"\nDone. {len(all_games)} raw records saved to {out_dir}/")
    return pd.DataFrame(all_games), pd.DataFrame(all_team_rows)


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        start_date = date.fromisoformat(sys.argv[1])
        end_date = date.fromisoformat(sys.argv[2])
    elif len(sys.argv) == 2:
        start_date = end_date = date.fromisoformat(sys.argv[1])
    else:
        # Full 2026 NCAA D-I Softball Season
        start_date = date(2026, 2, 5)
        end_date = date(2026, 6, 5)

    print(f"Pulling season from {start_date.isoformat()} to {end_date.isoformat()}...")
    pull_season(start_date, end_date, out_dir=".", fetch_innings=True, debug=True)
