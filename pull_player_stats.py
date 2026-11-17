"""
pull_player_stats.py

Pulls per-PLAYER batting/fielding lines for D-I softball games, one row per
player per game, into player_games_season.csv.

WHERE DOUBLES / TRIPLES / HOME RUNS COME FROM
The box score's per-player batterStats has NO extra-base-hit fields. They live
in the section below the box score, teamBoxscore[].teamStats.battingStats:
    "doubles": [{"lastName": "Frahm", "total": "1", "seasonTotal": "1"}, ...]
`total` is that GAME's count (safe to sum across games); `seasonTotal` is the
running season-to-date count. We store both, so the sum of a player's per-game
`doubles` should equal his last `doubles_season_total` -- a built-in check.

Each player's XBH columns are one of:
  a number          the section exists and we matched the player (0 = none hit)
  blank (unknown)   the team's box score had no battingStats section at all,
                    OR two players on the team share the exact same last name
                    and that name appears in the XBH lists (can't tell them apart)
Unknown is NEVER silently treated as zero downstream (see calculate_rc7.py).

USAGE
    python pull_player_stats.py                       # yesterday (daily job)
    python pull_player_stats.py 2026-02-05             # one day
    python pull_player_stats.py 2026-02-05 2026-06-10  # backfill
"""

import os
import re
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

import pandas as pd
import requests

# Scoreboard stays on the public demo (never blocked). Box scores can be routed
# to a self-hosted container via NCAA_BOXSCORE_BASE (set in the workflow).
NCAA_SCOREBOARD_BASE = "https://ncaa-api.henrygd.me"
NCAA_BOXSCORE_BASE = os.environ.get("NCAA_BOXSCORE_BASE", "https://ncaa-api.henrygd.me")
SCOREBOARD_URL = NCAA_SCOREBOARD_BASE + "/scoreboard/softball/d1/{year}/{month:02d}/{day:02d}"
BOXSCORE_URL = NCAA_BOXSCORE_BASE + "/game/{game_id}/boxscore"

REQUESTS_PER_SECOND_LIMIT = 5
_MIN_INTERVAL = 1.0 / REQUESTS_PER_SECOND_LIMIT

COLUMNS = [
    "date", "game_id", "team", "opponent", "last_name", "first_name", "position",
    "number", "starter", "participated", "at_bats", "runs_scored", "hits", "rbi",
    "walks", "strikeouts", "batting_average", "on_base_pct", "putouts", "assists",
    "errors", "doubles", "triples", "home_runs", "doubles_season_total",
    "triples_season_total", "home_runs_season_total", "xbh_ambiguous",
]

# Run-wide diagnostics so you can SEE how complete the XBH data is.
XBH_STATS = Counter()
_stats_lock = threading.Lock()


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
    seen = set()
    for page in range(1, max_pages + 1):
        data = _get_scoreboard_page(year, month, day, page)
        raw_games = data.get("games", [])
        if not raw_games:
            break
        before = len(seen)
        for entry in raw_games:
            gid = extract_game_id(entry.get("game", entry))
            if gid:
                seen.add(gid)
        if len(seen) == before:  # page added nothing new -> stop paging
            break
    return sorted(seen)


def _num(val):
    if val in (None, ""):
        return None
    try:
        return float(val)
    except ValueError:
        return None


def _xbh_section(team_stats, key):
    """Returns (section_present, {lastName: (game_total, season_total)})."""
    batting = (team_stats or {}).get("battingStats")
    if not isinstance(batting, dict) or key not in batting:
        return False, {}
    out = {}
    for entry in batting.get(key) or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("lastName", "")).strip()
        if not name:
            continue
        game_total = _num(entry.get("total"))
        season_total = _num(entry.get("seasonTotal"))
        prev_game, prev_season = out.get(name, (0.0, None))
        out[name] = (
            prev_game + (game_total if game_total is not None else 1.0),
            season_total if season_total is not None else prev_season,
        )
    return True, out


def extract_player_rows(boxscore_json, date_str, game_id):
    teams_meta = boxscore_json.get("teams", [])
    team_by_id = {str(t.get("teamId")): t for t in teams_meta}
    if len(team_by_id) != 2:
        return []

    rows = []
    for tb in boxscore_json.get("teamBoxscore", []):
        tid = str(tb.get("teamId"))
        team_meta = team_by_id.get(tid, {})
        team_name = team_meta.get("nameShort") or team_meta.get("nameFull") or tid
        opp_meta = next((t for oid, t in team_by_id.items() if oid != tid), {})
        opp_name = opp_meta.get("nameShort") or opp_meta.get("nameFull") or ""

        players = tb.get("playerStats") or []
        team_stats = tb.get("teamStats") or {}
        dbl_ok, dbl = _xbh_section(team_stats, "doubles")
        trp_ok, trp = _xbh_section(team_stats, "triples")
        hr_ok, hrs = _xbh_section(team_stats, "homeRuns")
        has_section = dbl_ok and trp_ok and hr_ok

        roster_names = [str(p.get("lastName", "")).strip() for p in players]
        name_counts = Counter(roster_names)
        listed_names = set(dbl) | set(trp) | set(hrs)

        with _stats_lock:
            XBH_STATS["team_games"] += 1
            if not has_section:
                XBH_STATS["team_games_without_xbh_section"] += 1
            for nm in listed_names:
                XBH_STATS["xbh_names_listed"] += 1
                if nm not in name_counts:
                    XBH_STATS["xbh_names_unmatched"] += 1

        for player, name in zip(players, roster_names):
            batter = player.get("batterStats") or {}
            field = player.get("fieldStats") or {}

            ambiguous = has_section and name_counts[name] > 1 and name in listed_names
            if not has_section or ambiguous:
                d2 = d3 = hr = s2 = s3 = shr = None
                if ambiguous:
                    with _stats_lock:
                        XBH_STATS["xbh_ambiguous_players"] += 1
            else:
                d2, s2 = dbl.get(name, (0.0, None))
                d3, s3 = trp.get(name, (0.0, None))
                hr, shr = hrs.get(name, (0.0, None))

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
                "on_base_pct": _num(str(batter.get("onBasePercentage", "")).replace("%", "")),
                "putouts": _num(field.get("putouts")),
                "assists": _num(field.get("assists")),
                "errors": _num(field.get("errors")),
                "doubles": d2,
                "triples": d3,
                "home_runs": hr,
                "doubles_season_total": s2,
                "triples_season_total": s3,
                "home_runs_season_total": shr,
                "xbh_ambiguous": bool(ambiguous),
            })
    return rows


def fetch_player_rows_for_game(game_id, date_str, box_retries=3):
    """
    Returns (rows, failed). A 404 means no box score exists (canceled game):
    that is NOT a failure. Anything else that keeps failing IS a failure, so
    the day is not marked complete and gets retried instead of silently
    losing that game.
    """
    last_err = None
    for attempt in range(box_retries + 1):
        try:
            data = _get_json(BOXSCORE_URL.format(game_id=game_id))
            return extract_player_rows(data, date_str, game_id), False
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return [], False
            last_err = e
        except Exception as e:
            last_err = e
        if attempt < box_retries:
            time.sleep(1.5 * (2 ** attempt))
    print(f"  game {game_id}: FAILED after {box_retries + 1} attempts ({last_err})")
    return [], True


def fetch_player_rows_concurrent(game_ids, date_str, max_workers=5):
    all_rows, failed_ids = [], []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(fetch_player_rows_for_game, g, date_str): g for g in game_ids}
        for fut in as_completed(futures):
            gid = futures[fut]
            try:
                rows, failed = fut.result()
            except Exception:
                rows, failed = [], True
            all_rows.extend(rows)
            if failed:
                failed_ids.append(gid)
    return all_rows, failed_ids


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

    all_rows = []
    if os.path.exists(out_path) and os.stat(out_path).st_size > 0:
        existing = pd.read_csv(out_path, dtype={"game_id": str})
        if "xbh_ambiguous" in existing.columns:
            all_rows = existing.to_dict("records")
        else:
            print("Existing player_games_season.csv uses an older column layout -- starting fresh.")
            completed = set()

    dates = list(_daterange(start, end))
    print(f"{len(dates)} day(s) requested, {len(completed)} already done\n")

    failed_dates = []
    for i, d in enumerate(dates, 1):
        date_str = d.isoformat()
        if date_str in completed:
            continue

        day_rows = None
        for attempt in range(max_retries + 1):
            try:
                game_ids = discover_game_ids(d.year, d.month, d.day)
                rows, failed_ids = fetch_player_rows_concurrent(game_ids, date_str, max_workers)
                if failed_ids:
                    raise RuntimeError(f"{len(failed_ids)} box score(s) failed, e.g. {failed_ids[:3]}")
                day_rows = rows
                break
            except Exception as e:
                print(f"[{i}/{len(dates)}] {date_str}: {e} (attempt {attempt + 1}/{max_retries + 1})")
                time.sleep(2 * (attempt + 1))

        if day_rows is None:
            print(f"[{i}/{len(dates)}] {date_str}: NOT marked complete -- will retry on next run")
            failed_dates.append(date_str)
            continue

        all_rows.extend(day_rows)
        completed.add(date_str)
        pd.DataFrame(all_rows, columns=COLUMNS).to_csv(out_path, index=False)
        with open(progress_path, "w") as f:
            f.write("\n".join(sorted(completed)))
        print(f"[{i}/{len(dates)}] {date_str}: {len(day_rows)} player-rows (total {len(all_rows)})")

    print("\n--- XBH data coverage this run ---")
    for k in ("team_games", "team_games_without_xbh_section", "xbh_names_listed",
              "xbh_names_unmatched", "xbh_ambiguous_players"):
        print(f"  {k}: {XBH_STATS[k]}")
    if failed_dates:
        print(f"\n{len(failed_dates)} day(s) incomplete -- rerun to retry: {failed_dates}")
    return pd.DataFrame(all_rows, columns=COLUMNS)


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
    print(f"Done: {len(df)} player-rows total")
