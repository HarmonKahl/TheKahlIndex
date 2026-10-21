"""
pull_player_stats.py

Pulls per-PLAYER batting and fielding stats (not just team totals) for D-I
softball games, using the same NCAA API and the same day-by-day scoreboard
discovery as pull_season.py. This is built to be dropped alongside that
file and used the same way -- same rate limiting, same resume/checkpoint
behavior, same CLI date pattern -- so it fits into the same daily-automation
plan once the 2027 season starts.

KNOWN LIMITATION (confirmed from a real box score, Nebraska vs LSU):
every player's `pitcherStats` field came back null, including actual
pitchers. Individual pitcher metrics may not be reliably available this
way -- batting and fielding per player were fully populated, though.
Team-level pitching totals (innings pitched, runs allowed, etc.) are NOT
duplicated here; use pull_season.py / team_games_season.csv for those.

IMPORTANT, UNRESOLVED QUESTION ABOUT DOUBLES/TRIPLES/HOME RUNS:
These three fields are NOT present in batterStats at all (confirmed empty
there). They only exist under a separate section called "hittingSeason".
In the one real game we've checked, hittingSeason's at-bats/hits/etc. were
IDENTICAL to that same game's batterStats -- which is consistent with
either of two very different possibilities:
  (a) hittingSeason is just a per-game duplicate (safe to sum across games)
  (b) hittingSeason is a running season-to-date cumulative total (summing
      across games would wildly overcount -- you'd want to take the LAST
      game's value for a player, not add every game's value together)
We could not tell which from a single early-season game. BEFORE building
any real metric on doubles_hittingSeason / triples_hittingSeason /
home_runs_hittingSeason, pull a few consecutive games for one player who
you know hit a double partway through the season, and check: does the
value jump by 1 in that one game and then STAY THE SAME in every later
game (per-game), or does it stay elevated/keep climbing (cumulative)?
Do not trust a season total built from these fields until you've checked.

OUTPUT: player_games_season.csv, one row per player per game.

USAGE
-----
    python pull_player_stats.py                      # yesterday only (daily job default)
    python pull_player_stats.py 2026-02-05            # one specific day
    python pull_player_stats.py 2026-02-05 2026-06-04 # a date range (backfill)
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


def extract_game_id(game):
    for key in ("gameID", "id", "contestId", "contestID"):
        val = game.get(key)
        if val:
            return str(val)
    url = game.get("url") or game.get("link") or ""
    m = re.search(r"/game/(\d+)", str(url))
    return m.group(1) if m else None


def discover_game_ids(year, month, day, max_pages=20):
    """Same scoreboard walk as pull_season.py, but we only need the game IDs here."""
    seen = set()
    for page in range(1, max_pages + 1):
        data = _get_scoreboard_page(year, month, day, page)
        raw_games = data.get("games", [])
        if not raw_games:
            break
        for entry in raw_games:
            game = entry.get("game", entry)
            gid = extract_game_id(game)
            if gid:
                seen.add(gid)
    return sorted(seen)


def _num(val):
    """Box score numeric fields come through as strings (e.g. '3', '.412'); convert safely."""
    if val in (None, ""):
        return None
    try:
        return float(val)
    except ValueError:
        return None


def extract_player_rows(boxscore_json, date_str, game_id):
    """
    Returns one dict per player per game, with their team, opponent, and
    batting/fielding line. Returns an empty list if the shape doesn't match
    what we've confirmed (so a weird game gets skipped, not crashed on).
    """
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
            # doubles/triples/home runs are NOT in batterStats -- confirmed
            # absent there. They only show up under hittingSeason. See the
            # big warning in this file's docstring about what "Season" means
            # here before summing these across games.
            hitting_season = player.get("hittingSeason") or {}
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
                # UNVERIFIED whether these three are per-game or cumulative --
                # see docstring. Do not sum across games until you've checked.
                "doubles_hittingSeason": _num(hitting_season.get("doubles")),
                "triples_hittingSeason": _num(hitting_season.get("triples")),
                "home_runs_hittingSeason": _num(hitting_season.get("homeRuns")),
            })
    return rows


def fetch_player_rows_for_game(game_id, date_str):
    try:
        data = _get_json(BOXSCORE_URL.format(game_id=game_id))
    except Exception as e:
        print(f"  boxscore fetch failed for game {game_id}: {e}")
        return []
    return extract_player_rows(data, date_str, game_id)


def fetch_player_rows_for_game(game_id, date_str, box_retries=3):
    """
    Retries a single game's box-score fetch on its own (502s and 428s from
    this API have turned out to be common and often transient -- a retry a
    couple seconds later frequently succeeds). Without this, a single flaky
    request would silently and permanently lose that one game's data, since
    this function used to swallow the error with no retry at all, and the
    day-level retry in pull_player_stats() never even sees it happen.
    """
    last_err = None
    for attempt in range(box_retries + 1):
        try:
            data = _get_json(BOXSCORE_URL.format(game_id=game_id))
            return extract_player_rows(data, date_str, game_id)
        except Exception as e:
            last_err = e
            if attempt < box_retries:
                wait = 1.5 * (2 ** attempt)  # 1.5s, 3s, 6s
                print(f"  game {game_id}: attempt {attempt + 1} failed ({e}), retrying in {wait:.1f}s")
                time.sleep(wait)
    print(f"  game {game_id}: FAILED after {box_retries + 1} attempts ({last_err}) -- no player data for this game")
    return []


def _daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def pull_player_stats(start, end, out_dir=".", max_retries=2, max_workers=5):
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

    failed_dates = []
    for i, d in enumerate(dates, 1):
        date_str = d.isoformat()
        if date_str in completed:
            continue

        day_rows, attempt = None, 0
        while attempt <= max_retries:
            try:
                game_ids = discover_game_ids(d.year, d.month, d.day)
                day_rows = fetch_player_rows_concurrent(game_ids, date_str, max_workers=max_workers)
                break
            except Exception as e:
                attempt += 1
                print(f"[{i}/{len(dates)}] {date_str}: error ({e}), retry {attempt}/{max_retries}")
                time.sleep(2 * attempt)

        if day_rows is None:
            print(f"[{i}/{len(dates)}] {date_str}: FAILED after {max_retries} retries -- "
                  f"skipped, will retry on next run")
            failed_dates.append(date_str)
            continue

        all_rows.extend(day_rows)
        completed.add(date_str)

        pd.DataFrame(all_rows).to_csv(out_path, index=False)
        with open(progress_path, "w") as f:
            f.write("\n".join(sorted(completed)))

        print(f"[{i}/{len(dates)}] {date_str}: {len(day_rows)} player-rows "
              f"(running total: {len(all_rows)})")

    if failed_dates:
        print(f"\n{len(failed_dates)} day(s) failed -- rerun to retry just those:")
        print(" ", failed_dates)
    else:
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
