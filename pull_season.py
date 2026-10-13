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


def fetch_innings_for_game(game_id, debug=False):
    if not game_id:
        return None, None
    try:
        data = _get_json(BOXSCORE_URL.format(game_id=game_id))
    except Exception as e:
        if debug:
            print(f"  boxscore fetch failed for game {game_id}: {e}")
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
    for tb in data.get("teamBoxscore", []):
        tid = str(tb.get("teamId"))
        pitcher_totals = (tb.get("teamStats") or {}).get("pitcherTotals") or {}
        ip_by_team[tid] = parse_innings_pitched(
            pitcher_totals.get("inningsPitched")
        )

    home_ip = ip_by_team.get(home_id)
    away_ip = ip_by_team.get(away_id)
    if home_ip is None or away_ip is None:
        return None, None
    return away_ip, home_ip


def fetch_innings_concurrent(game_ids, debug=False, max_workers=5):
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(fetch_innings_for_game, gid, debug): gid
            for gid in game_ids
        }
        for fut in as_completed(futures):
            gid = futures[fut]
            try:
                results[gid] = fut.result()
            except Exception as e:
                if debug:
                    print(f"  concurrent fetch failed for game {gid}: {e}")
                results[gid] = (None, None)
    return results


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

        if debug:
            print(f"    page {page}: {len(raw_games)} game(s)")

    games = [seen[k] for k in seen_order]

    if fetch_innings:
        game_ids = [row["game_id"] for row in games if row["game_id"]]
        inn_map = fetch_innings_concurrent(
            game_ids, debug=debug, max_workers=innings_workers
        )
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


def filter_min_games(team_df, min_games=20):
    """Filters out any team that has played fewer than min_games."""
    if team_df.empty or "team" not in team_df.columns:
        return team_df
    
    counts = team_df.groupby("team")["date"].count()
    valid_teams = counts[counts >= min_games].index
    
    filtered_df = team_df[team_df["team"].isin(valid_teams)].copy()
    print(f"Filtered out {len(counts) - len(valid_teams)} teams with fewer than {min_games} games.")
    return filtered_df


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
    min_games=20,
):
    os.makedirs(out_dir, exist_ok=True)
    games_path = os.path.join(out_dir, "games_season.csv")
    team_path = os.path.join(out_dir, "team_games_season.csv")
    progress_path = os.path.join(out_dir, "_completed_dates.txt")

    completed = set()
    if os.path.exists(progress_path):
        with open(progress_path) as f:
            completed = set(line.strip() for line in f if line.strip())

    if not os.path.exists(team_path) or os.stat(team_path).st_size == 0:
        completed = set()

    all_games = (
        pd.read_csv(games_path).to_dict("records")
        if os.path.exists(games_path) and os.stat(games_path).st_size > 0
        else []
    )
    all_team_rows = (
        pd.read_csv(team_path).to_dict("records")
        if os.path.exists(team_path) and os.stat(team_path).st_size > 0
        else []
    )

    dates = list(_daterange(start, end))

    failed_dates = []
    for i, d in enumerate(dates, 1):
        date_str = d.isoformat()
        if date_str in completed:
            continue

        day_games, attempt = None, 0
        while attempt <= max_retries:
            try:
                day_games = pull_day(
                    d.year,
                    d.month,
                    d.day,
                    fetch_innings=fetch_innings,
                    debug=debug,
                )
                break
            except Exception as e:
                attempt += 1
                time.sleep(2 * attempt)

        if day_games is None:
            failed_dates.append(date_str)
            continue

        all_games.extend(day_games)
        all_team_rows.extend(games_to_team_rows(day_games))
        completed.add(date_str)

        # Convert to DataFrame to apply min_games threshold filter
        team_df = pd.DataFrame(all_team_rows)
        team_df = filter_min_games(team_df, min_games=min_games)

        pd.DataFrame(all_games).to_csv(games_path, index=False)
        team_df.to_csv(team_path, index=False)
        with open(progress_path, "w") as f:
            f.write("\n".join(sorted(completed)))

        print(
            f"[{i}/{len(dates)}] {date_str}: {len(day_games)} games "
            f"(running total: {len(all_games)} games, {len(team_df)} team-rows)"
        )

    final_team_df = filter_min_games(pd.DataFrame(all_team_rows), min_games=min_games)
    return pd.DataFrame(all_games), final_team_df


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        start_date = datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
        end_date = datetime.strptime(sys.argv[2], "%Y-%m-%d").date()
    else:
        today = date.today()
        current_year = today.year
        start_date = date(current_year, 2, 1)
        end_date = min(today, date(current_year, 6, 30))

    pull_season(start=start_date, end=end_date, out_dir=".", min_games=20)
