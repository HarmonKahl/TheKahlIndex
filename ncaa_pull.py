#!/usr/bin/env python3
"""
ncaa_pull.py -- pull every NCAA D-I softball game + box score from the live
NCAA API (https://ncaa-api.henrygd.me) and keep the CSVs up to date.

Run it any time; it figures out what is missing or unfinished and only fetches
that.  The same command works for backfilling a whole season and for the daily
update during the season.

    python ncaa_pull.py                       # daily update (this season)
    python ncaa_pull.py --season 2026         # a specific season
    python ncaa_pull.py --start 2026-02-05 --end 2026-02-20
    python ncaa_pull.py --full-refresh        # throw away saved data, redo everything
    python ncaa_pull.py --audit-only          # just compare saved data to NCAA's official totals

Files written to --out-dir (default: current folder):
    games_season.csv         one row per game (scores, innings, fetch status)
    team_games_season.csv    two rows per game (one per team)  -> rc7.py
    player_games_season.csv  one row per player per game       -> rc7.py
    _completed_dates.txt     checkpoint of completed scoreboard dates

Only third-party dependency: requests
"""

import argparse
import csv
import json
import os
import random
import re
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone

import requests

API = os.environ.get("NCAA_API_BASE", "https://ncaa-api.henrygd.me").rstrip("/")
# optional: send /game/... (box score + linescore) requests to a self-hosted ncaa-api container
GAME_API = os.environ.get("NCAA_GAME_API_BASE", API).rstrip("/")
SPORT = "softball"
DIVISION = "d1"
MAX_RPS = float(os.environ.get("NCAA_MAX_RPS", "3.0"))  # public API allows ~5/sec/IP; stay well under
MIN_RPS = 0.7
WORKERS = 4
RECHECK_DAYS = 3        # always re-pull this many most-recent days (late finals / corrections)
RETRY_RECENT_DAYS = 10  # games with no box score / linescore are retried this long
CHECKPOINT_FILE = "_completed_dates.txt"

GAME_COLS = [
    "date", "game_id", "away_team", "away_score", "home_team", "home_score",
    "state", "status", "away_innings", "home_innings",
    "innings_source", "box_status", "box_check", "duplicate_of",
]
TEAM_COLS = [
    "date", "game_id", "team", "opponent", "role", "runs_for", "runs_against",
    "win", "innings_batted", "innings_fielded",
]
PLAYER_COLS = [
    "date", "game_id", "team", "opponent", "last_name", "first_name", "position",
    "number", "starter", "participated", "pitcher_row",
    "at_bats", "runs_scored", "hits", "rbi", "walks", "strikeouts",
    "batting_average", "on_base_pct", "putouts", "assists", "errors",
    "doubles", "triples", "home_runs",
    "doubles_season_total", "triples_season_total", "home_runs_season_total",
    "season_at_bats", "season_hits", "season_walks", "xbh_ambiguous",
    "ip", "pitching_runs", "earned_runs", "hits_allowed", "walks_allowed", "strikeouts_pitched",
]


# ----------------------------------------------------------------------------
# HTTP: one shared rate limiter, retries with backoff, 404 -> None
# ----------------------------------------------------------------------------
class ApiError(Exception):
    pass


class Limiter:
    """Shared by all threads. Spaces requests out, and when the CDN pushes back
    (HTTP 428/429) it pauses everyone and slows down, then speeds up again."""

    def __init__(self, rps):
        self.max_rps = rps
        self.gap = 1.0 / rps
        self.next = 0.0
        self.ok_streak = 0
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            now = time.monotonic()
            start = max(now, self.next)
            self.next = start + self.gap
        if start > now:
            time.sleep(start - now)

    def throttled(self, pause=8.0):
        with self.lock:
            self.gap = min(self.gap * 1.5, 1.0 / MIN_RPS)
            self.next = max(self.next, time.monotonic()) + pause
            self.ok_streak = 0

    def success(self):
        with self.lock:
            self.ok_streak += 1
            if self.ok_streak >= 60 and self.gap > 1.0 / self.max_rps:
                self.gap = max(1.0 / self.max_rps, self.gap / 1.15)
                self.ok_streak = 0


_limiter = Limiter(MAX_RPS)
_local = threading.local()


def _session():
    if not hasattr(_local, "s"):
        _local.s = requests.Session()
        _local.s.headers["User-Agent"] = "softball-rc7-puller/2.0"
    return _local.s


def api_get(path, params=None, tries=8):
    """GET JSON. Returns None on 404. Raises ApiError if it keeps failing."""
    url = (GAME_API if path.startswith("/game/") else API) + path
    err = None
    for attempt in range(tries):
        _limiter.wait()
        delay = min(20, 1.5 ** attempt + random.random())
        try:
            r = _session().get(url, params=params, timeout=30)
        except requests.RequestException as e:
            err = e
        else:
            if r.status_code == 200:
                _limiter.success()
                try:
                    return r.json()
                except ValueError as e:
                    err = e
            elif r.status_code == 404:
                return None
            elif r.status_code in (428, 429, 500, 502, 503, 504):
                err = ApiError(f"HTTP {r.status_code}")
                if r.status_code in (428, 429):   # CDN rate limit -> everyone backs off
                    _limiter.throttled()
                elif attempt >= 2:                # 5xx that keeps happening: give up, retried next run
                    break
                ra = r.headers.get("Retry-After")
                if ra and ra.isdigit():
                    delay = max(delay, int(ra))
            else:
                raise ApiError(f"HTTP {r.status_code} for {url}")
        if attempt < tries - 1:
            time.sleep(delay)
    raise ApiError(f"{url}: {err}")


# ----------------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------------
def today_et():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/New_York")).date()
    except Exception:
        return (datetime.now(timezone.utc) - timedelta(hours=5)).date()


def is_pitching_pos(pos):
    """True for 'p', 'p/1b', 'dp/p', '1b/p' ... (NCAA puts the pitcher's walks/runs/Ks
    allowed in the batting columns of these rows).  'dp' alone is a hitter."""
    return "p" in [t.strip().lower() for t in str(pos or "").split("/")]


def to_int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def to_num(v):
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace("%", "").strip())
    except ValueError:
        return None


def blank(v):
    return v is None or v == "" or (isinstance(v, float) and v != v)


def atomic_write_csv(path, cols, rows):
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if blank(r.get(c)) else r.get(c)) for c in cols})
    os.replace(tmp, path)


def read_csv(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return [], []
    with open(path, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        return list(rd), rd.fieldnames or []


def load_completed_dates(path):
    if not os.path.exists(path):
        return set()
    with open(path, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def save_completed_dates(path, dates_set):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for d_str in sorted(dates_set):
            f.write(d_str + "\n")
    os.replace(tmp, path)


# ----------------------------------------------------------------------------
# scoreboard: which games exist on which day
# ----------------------------------------------------------------------------
def season_dates(season):
    """Dates NCAA lists games for (includes cancelled games, which is fine)."""
    try:
        data = api_get(f"/schedule-alt/{SPORT}/{DIVISION}/{season}")
        games = data["data"]["schedules"]["games"]
        out = set()
        for g in games:
            if g.get("count", 0) > 0:
                m, d, y = g["contestDate"].split("/")
                out.add(date(int(y), int(m), int(d)))
        if out:
            return out
    except Exception as e:
        print(f"  (schedule lookup failed: {e}; falling back to every day Jan 15 - Jun 30)")
    d, end, out = date(season, 1, 15), date(season, 6, 30), set()
    while d <= end:
        out.add(d)
        d += timedelta(days=1)
    return out


def fetch_scoreboard(d):
    data = api_get(f"/scoreboard/{SPORT}/{DIVISION}/{d.year}/{d.month:02d}/{d.day:02d}")
    if data is None:
        return []
    rows = {}
    for entry in data.get("games", []):
        g = entry.get("game", entry)
        gid = str(g.get("gameID") or "").strip()
        if not gid:
            continue
        away, home = g.get("away") or {}, g.get("home") or {}
        rows[gid] = {
            "date": d.isoformat(), "game_id": gid,
            "away_team": (away.get("names") or {}).get("short") or "",
            "away_score": to_int(away.get("score")),
            "home_team": (home.get("names") or {}).get("short") or "",
            "home_score": to_int(home.get("score")),
            "state": g.get("gameState") or "",
            "status": g.get("currentPeriod") or "",
        }
    return list(rows.values())


def is_final(g):
    return (g.get("state") == "final"
            and to_int(g.get("away_score")) is not None
            and to_int(g.get("home_score")) is not None)


# ----------------------------------------------------------------------------
# per-game detail: linescore (innings) + box score (players)
# ----------------------------------------------------------------------------
def parse_ip(v):
    if blank(v):
        return None
    w, _, f = str(v).strip().partition(".")
    try:
        return int(w) + {"": 0, "0": 0, "1": 1 / 3, "2": 2 / 3}.get(f[:1], 0)
    except ValueError:
        return None


def fetch_linescore(game_id):
    """Innings each team batted, from the inning-by-inning line score."""
    data = api_get(f"/game/{game_id}")
    if not data:
        return None
    contests = data.get("contests") or []
    if not contests:
        return None
    periods = [p for p in (contests[0].get("linescores") or [])
               if str(p.get("period")).isdigit()]

    def batted(v):
        return v not in (None, "", "X", "x", "-")

    away = sum(1 for p in periods if batted(p.get("visit")))
    home = sum(1 for p in periods if batted(p.get("home")))
    away_runs = sum(to_int(p.get("visit")) or 0 for p in periods)
    home_runs = sum(to_int(p.get("home")) or 0 for p in periods)
    if away == 0 or home == 0:
        return None
    return {"away_innings": float(away), "home_innings": float(home),
            "away_runs": away_runs, "home_runs": home_runs}


def _xbh_lists(team_stats):
    bs = (team_stats or {}).get("battingStats")
    out = {}
    for key in ("doubles", "triples", "homeRuns"):
        if isinstance(bs, dict) and key in bs:
            out[key] = [e for e in (bs.get(key) or []) if isinstance(e, dict)]
        else:
            out[key] = None  # section missing -> unknown, not zero
    return out


def parse_boxscore(box, game):
    """Returns (player_rows, ip_by_side, check). Raises ValueError if unusable."""
    teams = {str(t.get("teamId")): t for t in box.get("teams") or []}
    tbs = box.get("teamBoxscore") or []
    if len(teams) != 2 or len(tbs) != 2:
        raise ValueError("box score does not have two teams")
    rows, ip, check_ok = [], {}, True

    for tb in tbs:
        meta = teams.get(str(tb.get("teamId")))
        if meta is None:
            raise ValueError("team id mismatch in box score")
        side = "home" if meta.get("isHome") else "away"
        team = game["home_team"] if side == "home" else game["away_team"]
        opp = game["away_team"] if side == "home" else game["home_team"]
        stats = tb.get("teamStats") or {}
        players = tb.get("playerStats") or []
        ip[side] = parse_ip((stats.get("pitcherTotals") or {}).get("inningsPitched"))

        built = []
        for p in players:
            b = p.get("batterStats") or {}
            f = p.get("fieldStats") or {}
            hs = p.get("hittingSeason") or {}
            ps = p.get("pitcherStats") or {}
            pos = str(p.get("position") or "").strip()
            built.append({
                "date": game["date"], "game_id": game["game_id"],
                "team": team, "opponent": opp,
                "last_name": str(p.get("lastName") or "").strip(),
                "first_name": str(p.get("firstName") or "").strip(),
                "position": pos, "number": p.get("number"),
                "starter": p.get("starter"), "participated": p.get("participated"),
                "pitcher_row": is_pitching_pos(pos),
                "at_bats": to_num(b.get("atBats")), "runs_scored": to_num(b.get("runsScored")),
                "hits": to_num(b.get("hits")), "rbi": to_num(b.get("runsBattedIn")),
                "walks": to_num(b.get("walks")), "strikeouts": to_num(b.get("strikeouts")),
                "batting_average": to_num(b.get("battingAverage")),
                "on_base_pct": to_num(b.get("onBasePercentage")),
                "putouts": to_num(f.get("putouts")), "assists": to_num(f.get("assists")),
                "errors": to_num(f.get("errors")),
                "doubles": None, "triples": None, "home_runs": None,
                "doubles_season_total": to_num(hs.get("doubles")),
                "triples_season_total": to_num(hs.get("triples")),
                "home_runs_season_total": to_num(hs.get("homeRuns")),
                "season_at_bats": to_num(hs.get("atBats")),
                "season_hits": to_num(hs.get("hits")),
                "season_walks": to_num(hs.get("walks")),
                "xbh_ambiguous": False,
                "ip": parse_ip(ps.get("inningsPitched")),
                "pitching_runs": to_num(ps.get("runsAllowed")),
                "earned_runs": to_num(ps.get("earnedRuns")),
                "hits_allowed": to_num(ps.get("hitsAllowed")),
                "walks_allowed": to_num(ps.get("walks")),
                "strikeouts_pitched": to_num(ps.get("strikeouts")),
            })

        def full(r):
            return f"{r['first_name']} {r['last_name']}".strip().lower()

        lists = _xbh_lists(stats)
        for key, col in (("doubles", "doubles"), ("triples", "triples"), ("homeRuns", "home_runs")):
            entries = lists[key]
            if entries is None:
                continue
            for r in built:
                r[col] = 0.0
            for e in entries:
                nm = str(e.get("lastName") or "").strip().lower()
                if not nm:
                    continue
                n = to_num(e.get("total"))
                n = 1.0 if n is None else n
                hit = [r for r in built if full(r) == nm] or \
                      [r for r in built if r["last_name"].lower() == nm] or \
                      [r for r in built if full(r).split(" ")[-1:] == nm.split(" ")[-1:]]
                if len(hit) == 1:
                    hit[0][col] += n
                else:
                    for r in hit:
                        r[col], r["xbh_ambiguous"] = None, True
        rows.extend(built)

        bt = stats.get("batterTotals") or {}
        for k, col in (("atBats", "at_bats"), ("hits", "hits")):
            tot = to_num(bt.get(k))
            if tot is not None and sum(r[col] or 0 for r in built) != tot:
                check_ok = False
    return rows, ip, ("ok" if check_ok else "mismatch")


def fetch_game_detail(game, want_box=True):
    """All network work for one game. Returns dict of results (never raises)."""
    gid = game["game_id"]
    res = {"game_id": gid}
    try:
        res["linescore"] = fetch_linescore(gid)
        res["linescore_error"] = None
    except ApiError as e:
        res["linescore"], res["linescore_error"] = None, str(e)
    if not want_box:
        return res
    try:
        box = api_get(f"/game/{gid}/boxscore")
        if box is None or not (box.get("teamBoxscore")):
            res["box_status"] = "none"
        else:
            rows, ip, check = parse_boxscore(box, game)
            if not rows:
                res["box_status"] = "none"
            else:
                res.update(box_status="ok", rows=rows, ip=ip, box_check=check)
    except (ApiError, ValueError) as e:
        res["box_status"], res["box_error"] = "error", str(e)
    return res


# ----------------------------------------------------------------------------
# build team_games_season.csv from the games table
# ----------------------------------------------------------------------------
def build_team_rows(games):
    out = []
    for g in games:
        if not is_final(g):
            continue
        a, h = to_int(g["away_score"]), to_int(g["home_score"])
        ai, hi = to_num(g.get("away_innings")), to_num(g.get("home_innings"))
        for role, team, opp, rf, ra, ib, ifd in (
            ("away", g["away_team"], g["home_team"], a, h, ai, hi),
            ("home", g["home_team"], g["away_team"], h, a, hi, ai),
        ):
            out.append({
                "date": g["date"], "game_id": g["game_id"], "team": team, "opponent": opp,
                "role": role, "runs_for": rf, "runs_against": ra,
                "win": None if rf == ra else int(rf > ra),
                "innings_batted": ib, "innings_fielded": ifd,
            })
    return out


# ----------------------------------------------------------------------------
# duplicate tournament game filter
# ----------------------------------------------------------------------------
def mark_duplicates(games):
    for g in games.values():
        g["duplicate_of"] = ""
    groups = {}
    for g in games.values():
        if is_final(g):
            key = (g["date"], frozenset({(g["away_team"], g["away_score"]), (g["home_team"], g["home_score"])}))
            groups.setdefault(key, []).append(g)
    n = 0
    for members in groups.values():
        members.sort(key=lambda g: int(g["game_id"]))
        kept = [members[0]]
        for g in members[1:]:
            if min(abs(int(g["game_id"]) - int(k["game_id"])) for k in kept) > 50:
                g["duplicate_of"] = members[0]["game_id"]
                n += 1
            else:
                kept.append(g)
    return n


# ----------------------------------------------------------------------------
# audit against NCAA's official team totals
# ----------------------------------------------------------------------------
def fetch_official_team_scoring(season):
    rows, page, pages, updated = [], 1, 1, ""
    while page <= pages:
        d = api_get(f"/stats/{SPORT}/{DIVISION}/{season}/team/284", params={"page": page} if page > 1 else None)
        if not d:
            break
        rows += d.get("data", [])
        pages = int(d.get("pages", 1))
        updated = d.get("updated", updated)
        page += 1
    return rows, updated


def audit(games, season):
    print("\n=== AUDIT vs official NCAA team totals ===")
    try:
        off, updated = fetch_official_team_scoring(season)
    except ApiError as e:
        print(f"could not fetch official totals: {e}")
        return
    if not off:
        print("official totals not available yet")
        return
    print(f"official source says: {updated}")
    scored, runs, noscore = Counter(), Counter(), Counter()
    for g in games:
        if g.get("duplicate_of") or g["state"] != "final":
            continue
        for team, rs in ((g["away_team"], g["away_score"]), (g["home_team"], g["home_score"])):
            if is_final(g):
                scored[team] += 1
                runs[team] += to_int(rs)
            else:
                noscore[team] += 1
    exact = with_ns = 0
    short, over = [], []
    for r in off:
        t, G, R = r["Team"], to_int(r["G"]), to_int(r["R"])
        if scored[t] == G and runs[t] == R:
            exact += 1
        elif scored[t] + noscore[t] == G:
            with_ns += 1
        elif scored[t] + noscore[t] < G:
            short.append((t, G - scored[t] - noscore[t], noscore[t], G, scored[t]))
        else:
            over.append((t, scored[t] + noscore[t] - G, G, scored[t]))
    n = len(off)
    print(f"{n} D-I teams in NCAA's official totals:")
    print(f"  {exact:3} match official games AND runs exactly")
    print(f"  {with_ns:3} match once you count games NCAA lists as FINAL but never published a score for")
    print(f"  {len(short):3} are missing 1+ games that are not in NCAA's game feed at all")
    print(f"  {len(over):3} have more games than the official count")
    print(f"NCAA lists {sum(1 for g in games if g['state'] == 'final' and not is_final(g) and not g.get('duplicate_of'))} "
          f"games as FINAL with no score/box score (mostly conference-tournament games); "
          f"no data exists for them in this API.")
    for label, rows_, fmt in (
        ("most-short teams (team, games missing, of which listed-without-score, official G, our scored G):",
         sorted(short, key=lambda x: -x[1])[:10], None),
        ("teams with extra games (team, extra, official G, our G):", over[:10], None),
    ):
        if rows_:
            print(label)
            for x in rows_:
                print("  ", x)
    print("(NCAA's stats page can lag the scoreboard, so small differences right after games finish are normal)")


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--season", type=int, help="season year (default: current calendar year)")
    ap.add_argument("--start", help="first date YYYY-MM-DD (limits the pull)")
    ap.add_argument("--end", help="last date YYYY-MM-DD")
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--full-refresh", action="store_true", help="ignore saved files and redo everything")
    ap.add_argument("--no-boxscores", action="store_true", help="games + innings only")
    ap.add_argument("--audit-only", action="store_true")
    ap.add_argument("--no-audit", action="store_true")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    gpath = os.path.join(args.out_dir, "games_season.csv")
    tpath = os.path.join(args.out_dir, "team_games_season.csv")
    ppath = os.path.join(args.out_dir, "player_games_season.csv")
    cpath = os.path.join(args.out_dir, CHECKPOINT_FILE)

    today = today_et()
    season = args.season or today.year

    # ---- load saved state -------------------------------------------------
    games, players = {}, {}
    completed_dates = set()
    if not args.full_refresh:
        completed_dates = load_completed_dates(cpath)
        for r in read_csv(gpath)[0]:
            for k in ("away_score", "home_score"):
                r[k] = to_int(r.get(k))
            games[r["game_id"]] = r
        prow, pcols = read_csv(ppath)
        if prow and ("pitcher_row" not in pcols or "ip" not in pcols):
            print("Existing player_games_season.csv lacks pitching columns -- it will be rebuilt from scratch.")
            for g in games.values():
                g["box_status"] = g["box_check"] = ""
        else:
            for r in prow:
                players.setdefault(r["game_id"], []).append(r)
    print(f"Loaded {len(games)} saved games, {len(players)} saved box scores, {len(completed_dates)} completed dates. Season {season}, today {today}.")

    if args.audit_only:
        audit(list(games.values()), season)
        return 0

    # ---- decide which dates to (re)pull ----------------------------------
    start = date.fromisoformat(args.start) if args.start else date(season, 1, 1)
    end = date.fromisoformat(args.end) if args.end else min(today, date(season, 12, 31))
    cand = {d for d in season_dates(season) if start <= d <= end}
    d = max(start, end - timedelta(days=RECHECK_DAYS - 1))
    while d <= end:                      # always include the recent window
        cand.add(d)
        d += timedelta(days=1)
    have_dates = {g["date"] for g in games.values()} | completed_dates
    todo = set()
    for d in cand:
        if d.isoformat() not in have_dates or d >= end - timedelta(days=RECHECK_DAYS - 1):
            todo.add(d)
    for g in games.values():             # unfinished / scoreless games -> repull their day
        gd = date.fromisoformat(g["date"])
        if start <= gd <= end and not is_final(g):
            todo.add(gd)
    todo = sorted(todo)
    print(f"Scoreboard: {len(todo)} day(s) to pull.")

    failed_days = []
    for i, d in enumerate(todo, 1):
        try:
            fresh = fetch_scoreboard(d)
        except ApiError as e:
            print(f"  [{i}/{len(todo)}] {d}: FAILED ({e}) -- will retry next run")
            failed_days.append(d.isoformat())
            continue
        fresh_ids = set()
        for new in fresh:
            fresh_ids.add(new["game_id"])
            old = games.get(new["game_id"])
            keep = ("away_innings", "home_innings", "innings_source", "box_status", "box_check")
            if old and is_final(old) and is_final(new) and \
                    old["away_score"] == new["away_score"] and old["home_score"] == new["home_score"]:
                for k in keep:
                    new[k] = old.get(k)
            games[new["game_id"]] = new
        for gid in [k for k, g in games.items() if g["date"] == d.isoformat() and k not in fresh_ids]:
            if is_final(games[gid]) and games[gid].get("box_status") == "ok":
                print(f"  note: final game {gid} ({games[gid]['away_team']} @ {games[gid]['home_team']}) "
                      f"vanished from the {d} scoreboard; keeping it")
            else:
                del games[gid]           # was cancelled / moved
                players.pop(gid, None)
        completed_dates.add(d.isoformat())
        if i % 20 == 0 or i == len(todo):
            print(f"  [{i}/{len(todo)}] scoreboard through {d}  ({len(games)} games total)")

    dup_n = mark_duplicates(games)
    for gid, g in games.items():
        if g.get("duplicate_of"):
            players.pop(gid, None)
    if dup_n:
        print(f"{dup_n} tournament game(s) are listed twice by NCAA; the extra copy is ignored (duplicate_of column).")

    # ---- which games need linescore / box score --------------------------
    def needs_detail(g):
        if not is_final(g) or g.get("duplicate_of"):
            return False
        recent = date.fromisoformat(g["date"]) >= today - timedelta(days=RETRY_RECENT_DAYS)
        src, box = g.get("innings_source") or "", g.get("box_status") or ""
        if src == "" or box == "" or box == "error":
            return True
        return recent and (box == "none" or src != "linescore")

    work = [g for g in games.values() if needs_detail(g)]
    work.sort(key=lambda g: g["date"])
    print(f"Detail fetch (linescore + box score) needed for {len(work)} game(s).")

    def save():
        glist = sorted(games.values(), key=lambda g: (g["date"], g["game_id"]))
        atomic_write_csv(gpath, GAME_COLS, glist)
        atomic_write_csv(tpath, TEAM_COLS, build_team_rows([g for g in glist if not g.get("duplicate_of")]))
        plist = [r for g in glist if not g.get("duplicate_of") for r in players.get(g["game_id"], [])]
        for r in plist:   # always recompute from the position text
            r["pitcher_row"] = is_pitching_pos(r.get("position"))
        atomic_write_csv(ppath, PLAYER_COLS, plist)
        save_completed_dates(cpath, completed_dates)

    errors, err_msgs = Counter(), Counter()
    done = 0
    t0 = time.time()
    try:
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = {ex.submit(fetch_game_detail, g, not args.no_boxscores): g for g in work}
            for fut in as_completed(futs):
                g = futs[fut]
                res = fut.result()
                ls = res.get("linescore")
                if ls:
                    g["away_innings"], g["home_innings"] = ls["away_innings"], ls["home_innings"]
                    g["innings_source"] = "linescore"
                elif res.get("linescore_error"):
                    errors["linescore"] += 1
                    err_msgs[re.sub(r"/game/\d+", "/game/N", res["linescore_error"])[:110]] += 1
                    if not g.get("innings_source"):
                        g["innings_source"] = ""   # retry next run
                if not args.no_boxscores:
                    st = res.get("box_status", "error")
                    g["box_status"] = st
                    if st == "ok":
                        players[g["game_id"]] = res["rows"]
                        g["box_check"] = res["box_check"]
                        if not ls:   # fall back to box-score innings pitched
                            ai, hi = res["ip"].get("home"), res["ip"].get("away")
                            if ai and hi:
                                g["away_innings"], g["home_innings"] = ai, hi
                                g["innings_source"] = "boxscore"
                    else:
                        players.pop(g["game_id"], None)
                        if st == "error":
                            errors["boxscore"] += 1
                            err_msgs[re.sub(r"/game/\d+", "/game/N", res.get("box_error", ""))[:110]] += 1
                if not g.get("innings_source") and not res.get("linescore_error"):
                    g["innings_source"] = "missing"   # NCAA has no linescore for it
                done += 1
                if done % 250 == 0:
                    save()
                    rate = done / (time.time() - t0)
                    print(f"  {done}/{len(work)} games done (~{(len(work) - done) / rate / 60:.0f} min left)")
    except KeyboardInterrupt:
        print("\nInterrupted -- saving what we have. Re-run to continue where it left off.")
        save()
        return 130

    save()

    # ---- summary ----------------------------------------------------------
    gl = list(games.values())
    final = [g for g in gl if is_final(g) and not g.get("duplicate_of")]
    c_box = Counter(g.get("box_status") or "?" for g in final)
    c_inn = Counter(g.get("innings_source") or "?" for g in final)
    mism = sum(1 for g in final if g.get("box_check") == "mismatch")
    print("\n=== SUMMARY ===")
    print(f"games on file:      {len(gl)}  (final: {len(final)}, not final: {len(gl) - len(final)})")
    print(f"box scores:         {dict(c_box)}")
    print(f"innings source:     {dict(c_inn)}")
    if mism:
        print(f"box-score AB/H totals disagreed with player rows in {mism} game(s) (see box_check column)")
    print(f"player rows:        {sum(len(v) for v in players.values())}")
    if failed_days:
        print(f"scoreboard days that FAILED (rerun to retry): {failed_days}")
    if errors:
        print(f"fetch errors this run: {dict(errors)}  (those games are retried automatically next run)")
        for m, n in err_msgs.most_common(5):
            print(f"   {n}x {m}")
    if not args.no_audit and not args.start and not args.end:
        audit(gl, season)
    n_failed = sum(errors.values())
    too_many = bool(work) and n_failed > 0.03 * len(work) * (1 if args.no_boxscores else 2)
    if failed_days or too_many:
        print("RESULT: incomplete -- too many fetch failures; re-run to fill the gaps.")
        return 0
    if n_failed:
        print(f"RESULT: completed with {n_failed} minor fetch error(s) (will retry automatically next run).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
