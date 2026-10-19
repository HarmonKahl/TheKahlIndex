import os
import re
import sys
import time
import requests
import pandas as pd
from datetime import datetime, date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# API Endpoints
SCOREBOARD_URL = "https://ncaa-api.henrygd.me/scoreboard/softball/d1/{year}/{month:02d}/{day:02d}"
BOXSCORE_URL = "https://ncaa-api.henrygd.me/game/{game_id}/boxscore"
STATS_BASE_URL = "https://ncaa-api.henrygd.me/stats/softball/d1/current/individual/200"

_session = requests.Session()
_adapter = requests.adapters.HTTPAdapter(pool_connections=30, pool_maxsize=30)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _get_json(url):
    resp = _session.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()

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

def fetch_single_game_innings(game_id):
    if not game_id:
        return game_id, (None, None)
    try:
        data = _get_json(BOXSCORE_URL.format(game_id=game_id))
        teams_meta = data.get("teams", [])
        home_id = str(next((t["teamId"] for t in teams_meta if t.get("isHome")), ""))
        away_id = str(next((t["teamId"] for t in teams_meta if t.get("isHome") is False), ""))

        ip_by_team = {}
        box_data = data.get("teamBoxscore") or data.get("boxscore") or []
        if isinstance(box_data, dict):
            box_data = [box_data]

        for tb in box_data:
            tid = str(tb.get("teamId", ""))
            pitcher_totals = (tb.get("teamStats") or {}).get("pitcherTotals") or {}
            ip_by_team[tid] = parse_innings_pitched(pitcher_totals.get("inningsPitched"))

        return game_id, (ip_by_team.get(away_id), ip_by_team.get(home_id))
    except Exception:
        return game_id, (None, None)

def fetch_day_data(curr_date):
    date_str = curr_date.isoformat()
    url = SCOREBOARD_URL.format(year=curr_date.year, month=curr_date.month, day=curr_date.day)
    try:
        data = _get_json(url)
        raw_games = data.get("games", [])
        if not raw_games:
            return date_str, [], []

        day_games = []
        game_ids = []

        for entry in raw_games:
            game = entry.get("game", entry)
            away_data, home_data = game.get("away", {}), game.get("home", {})
            game_id = extract_game_id(game)
            if game_id:
                game_ids.append(game_id)

            day_games.append({
                "date": date_str,
                "game_id": game_id,
                "away_team": extract_team(away_data, "Away"),
                "away_score": extract_score(away_data),
                "home_team": extract_team(home_data, "Home"),
                "home_score": extract_score(home_data),
                "state": game.get("gameState", "unknown"),
                "status": game.get("status", ""),
                "away_innings": None,
                "home_innings": None
            })

        # Fetch boxscore innings concurrently for games on this date
        innings_map = {}
        if game_ids:
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(fetch_single_game_innings, gid): gid for gid in game_ids}
                for future in as_completed(futures):
                    gid, inn_tuple = future.result()
                    innings_map[gid] = inn_tuple

        team_rows = []
        for g in day_games:
            if g["game_id"] in innings_map:
                g["away_innings"], g["home_innings"] = innings_map[g["game_id"]]

            if g["away_score"] is None or g["home_score"] is None:
                continue
            try:
                a_sc, h_sc = int(g["away_score"]), int(g["home_score"])
            except (ValueError, TypeError):
                continue

            a_inn = g["away_innings"] if g["away_innings"] and g["away_innings"] > 0 else 7.0
            h_inn = g["home_innings"] if g["home_innings"] and g["home_innings"] > 0 else 7.0

            team_rows.append({"date": date_str, "game_id": g["game_id"], "team": g["away_team"], "opponent": g["home_team"], "role": "away", "runs_for": a_sc, "runs_against": h_sc, "innings_batted": a_inn, "innings_fielded": h_inn, "win": int(a_sc > h_sc)})
            team_rows.append({"date": date_str, "game_id": g["game_id"], "team": g["home_team"], "opponent": g["away_team"], "role": "home", "runs_for": h_sc, "runs_against": a_sc, "innings_batted": h_inn, "innings_fielded": a_inn, "win": int(h_sc > a_sc)})

        return date_str, day_games, team_rows

    except Exception as e:
        return date_str, [], []

# ---------------------------------------------------------------------------
# PART 1: GAME SCORES & INNING COUNTS
# ---------------------------------------------------------------------------

def pull_game_scores(start, end, out_dir="."):
    print(f"\n--- Scraping Game Scores & Innings ({start} to {end}) ---")
    games_path = os.path.join(out_dir, "games_season.csv")
    team_path = os.path.join(out_dir, "team_games_season.csv")
    progress_path = os.path.join(out_dir, "_completed_dates.txt")

    completed = set()
    if os.path.exists(progress_path):
        with open(progress_path) as f:
            completed = set(line.strip() for line in f if line.strip())

    all_games = pd.read_csv(games_path).to_dict("records") if os.path.exists(games_path) and os.stat(games_path).st_size > 0 else []
    all_team_rows = pd.read_csv(team_path).to_dict("records") if os.path.exists(team_path) and os.stat(team_path).st_size > 0 else []

    dates_to_pull = []
    curr = start
    while curr <= end:
        if curr.isoformat() not in completed:
            dates_to_pull.append(curr)
        curr += timedelta(days=1)

    print(f"Total dates to process: {len(dates_to_pull)}")

    # Process days concurrently (5 dates at a time)
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fetch_day_data, d): d for d in dates_to_pull}
        for future in as_completed(futures):
            date_str, day_games, team_rows = future.result()
            all_games.extend(day_games)
            all_team_rows.extend(team_rows)
            completed.add(date_str)
            print(f"Completed {date_str}: {len(day_games)} games logged.")

    pd.DataFrame(all_games).to_csv(games_path, index=False)
    pd.DataFrame(all_team_rows).to_csv(team_path, index=False)
    with open(progress_path, "w") as f:
        f.write("\n".join(sorted(completed)))

# ---------------------------------------------------------------------------
# PART 2: PLAYER HITTING LEADERBOARD
# ---------------------------------------------------------------------------

def fetch_season_player_stats(out_dir="."):
    print("\n--- Fetching NCAA Season Player Leaderboard ---")
    all_players = []
    page = 1

    while True:
        url = f"{STATS_BASE_URL}?page={page}"
        try:
            resp = _session.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"Finished at page {page}: {e}")
            break

        stats_list = data.get("stats", []) or data.get("data", [])
        if not stats_list:
            break

        for row in stats_list:
            def _clean(val):
                if val in (None, "", "-"):
                    return 0
                try:
                    return int(float(val))
                except (ValueError, TypeError):
                    return 0

            all_players.append({
                "player_name": row.get("name") or row.get("Player") or "Unknown",
                "team": row.get("team") or row.get("Team") or "Unknown",
                "G": _clean(row.get("g") or row.get("G")),
                "AB": _clean(row.get("ab") or row.get("AB")),
                "H": _clean(row.get("h") or row.get("H")),
                "2B": _clean(row.get("d2") or row.get("2b") or row.get("2B")),
                "3B": _clean(row.get("d3") or row.get("3b") or row.get("3B")),
                "HR": _clean(row.get("hr") or row.get("HR")),
                "BB": _clean(row.get("bb") or row.get("BB"))
            })

        print(f"Processed player stats page {page} ({len(stats_list)} players)")
        total_pages = data.get("pageCount") or data.get("totalPages")
        if total_pages and page >= int(total_pages):
            break
        page += 1

    if all_players:
        output_path = os.path.join(out_dir, "player_boxscores_2026.csv")
        pd.DataFrame(all_players).to_csv(output_path, index=False)
        print(f"Saved {len(all_players)} player records to {output_path} successfully!")

# ---------------------------------------------------------------------------
# MAIN EXECUTION
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) >= 3:
        start_date = datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
        end_date = datetime.strptime(sys.argv[2], "%Y-%m-%d").date()
    elif len(sys.argv) == 2:
        start_date = datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
        end_date = start_date
    else:
        today = date.today()
        start_date = today - timedelta(days=1)
        end_date = today

    pull_game_scores(start_date, end_date)
    fetch_season_player_stats()
