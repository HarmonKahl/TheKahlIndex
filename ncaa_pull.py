#!/usr/bin/env python3
"""
pull_pitchers.py -- companion to ncaa_pull.py. Pulls PITCHING data for every
final game listed in games_season.csv.  Needs ncaa_pull.py in the same folder
(it reuses its rate limiter / retries), and changes nothing in ncaa_pull.py.

    python pull_pitchers.py                # pull whatever is missing (backfill + daily)
    python pull_pitchers.py --limit 25     # quick test on 25 games
    python pull_pitchers.py --refresh      # throw away saved pitching data, redo everything

Writes (to --out-dir, default current folder):
    team_pitching_games_season.csv   2 rows per game: each team's pitching totals
    pitcher_games_season.csv         1 row per pitcher per game (see "source" below)
    _pitching_done_games.txt         checkpoint
    _pitching_schema_samples.json    raw examples of any per-pitcher stat blocks the API
                                     actually populated (so field names can be checked)

WHAT THE API DOES AND DOES NOT GIVE US (read this before trusting a number)
  * team totals   teamStats.pitcherTotals: IP, H, R, ER, BB, K, BF per team per game.
                  Not all of these are reliable.  In the one Nebraska/LSU box score we
                  inspected, hitsAllowed equalled each team's OWN hit total, not the
                  opponent's.  So every team row carries *_ok columns that compare each
                  total to the opponent's batting line (1 = agrees, 0 = differs).
  * per pitcher   source = "pitcherStats"   the API's own per-pitcher block (null in every
                                            box score inspected so far, used if it appears)
                  source = "pitchers_list"  teamStats.pitchingStats.pitchers (empty so far)
                  source = "batting_columns" fallback: NCAA appears to put a pitcher's
                                            runs / walks / strikeouts in the BATTING columns
                                            of his row.  Stored as bc_runs / bc_walks /
                                            bc_strikeouts, NOT as pitching stats, because
                                            that is unproven.  There is no per-pitcher IP,
                                            hits or ER in this fallback.
                  A pitcher who also hit (AB/H/RBI > 0) has a mixed line (mixed_line = 1):
                  the same columns hold both jobs, so don't use them.
  * The team rows' rows_* columns test the fallback: do the pitchers' bc_ columns add up to
    the opponent's runs / strikeouts / walks (pitching reading) or to the team's OWN strikeouts /
    walks (batting reading)?  The summary at the end of every run prints the agreement rates.
    Trust per-pitcher numbers only if those rates are high.
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

import ncaa_pull as nc
from ncaa_pull import (ApiError, api_get, atomic_write_csv, blank, is_final,
                       is_pitching_pos, parse_ip, read_csv, to_int, to_num, today_et)

WORKERS = 4
RECHECK_DAYS = 3     # box scores of the most recent days are always re-pulled (stat corrections)
SAVE_EVERY = 250

TEAM_COLS = [
    "date", "game_id", "team", "opponent", "role",
    "ip", "hits_allowed", "runs_allowed", "earned_runs", "walks_allowed",
    "strikeouts", "batters_faced", "pitches", "win", "loss", "save",
    "hits_ok", "runs_ok", "walks_ok", "strikeouts_ok",
    "n_pitcher_rows", "n_mixed_rows", "rows_runs_sum", "rows_walks_sum", "rows_strikeouts_sum",
    "rows_runs_vs_opp_runs", "rows_k_vs_opp_k", "rows_k_vs_own_k",
    "rows_bb_vs_opp_bb", "rows_bb_vs_own_bb",
]
PITCHER_COLS = [
    "date", "game_id", "team", "opponent", "last_name", "first_name", "position",
    "number", "starter", "source",
    "ip", "hits_allowed", "runs_allowed", "earned_runs", "walks", "strikeouts",
    "batters_faced", "pitches", "decision",
    "bc_at_bats", "bc_hits", "bc_runs", "bc_rbi", "bc_walks", "bc_strikeouts", "mixed_line",
]


# ----------------------------------------------------------------------------
# parsing
# ----------------------------------------------------------------------------
def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def pick(d, *names):
    """First non-empty value among several possible key names (case/punctuation-insensitive)."""
    if not isinstance(d, dict):
        return None
    norm = {_norm(k): v for k, v in d.items()}
    for n in names:
        v = norm.get(_norm(n))
        if v not in (None, ""):
            return v
    return None


def _decision(d):
    for key, label in (("win", "W"), ("loss", "L"), ("save", "S")):
        v = pick(d, key)
        if v is True or str(v).strip().lower() in {"true", "1", "yes", "y"}:
            return label
    return ""


def pitch_fields(d):
    return {
        "ip": parse_ip(pick(d, "inningsPitched", "ip", "innings")),
        "hits_allowed": to_num(pick(d, "hitsAllowed", "hits", "h")),
        "runs_allowed": to_num(pick(d, "runsAllowed", "runs", "r")),
        "earned_runs": to_num(pick(d, "earnedRunsAllowed", "earnedRuns", "er")),
        "walks": to_num(pick(d, "walksAllowed", "walks", "bb")),
        "strikeouts": to_num(pick(d, "strikeouts", "so", "k")),
        "batters_faced": to_num(pick(d, "battersFaced", "bf")),
        "pitches": to_num(pick(d, "numberOfPitches", "pitches", "pitchCount")),
        "decision": _decision(d),
    }


def eq(a, b):
    """1 if equal, 0 if different, blank if either side is unknown."""
    if a is None or b is None:
        return ""
    return int(float(a) == float(b))


def _label(v):
    if v in (None, "", False):
        return ""
    if isinstance(v, dict):
        return str(pick(v, "lastName", "name", "fullName") or "")
    return str(v)


def extract_pitching(box, game):
    """Returns (team_rows, pitcher_rows, samples). Raises ValueError if the box score is unusable."""
    teams = {str(t.get("teamId")): t for t in box.get("teams") or []}
    tbs = box.get("teamBoxscore") or []
    if len(teams) != 2 or len(tbs) != 2:
        raise ValueError("box score does not have two teams")
    sides = {}
    for tb in tbs:
        meta = teams.get(str(tb.get("teamId")))
        if meta is None:
            raise ValueError("team id mismatch in box score")
        sides["home" if meta.get("isHome") else "away"] = tb
    if set(sides) != {"home", "away"}:
        raise ValueError("could not tell home from away")

    names = {"home": game["home_team"], "away": game["away_team"]}
    scores = {"home": to_int(game.get("home_score")), "away": to_int(game.get("away_score"))}
    bat = {s: ((sides[s].get("teamStats") or {}).get("batterTotals") or {}) for s in sides}
    team_rows, pitcher_rows, samples = [], [], []

    for side, tb in sides.items():
        other = "away" if side == "home" else "home"
        team, opp = names[side], names[other]
        stats = tb.get("teamStats") or {}
        pt = stats.get("pitcherTotals") if isinstance(stats.get("pitcherTotals"), dict) else {}
        pst = stats.get("pitchingStats") if isinstance(stats.get("pitchingStats"), dict) else {}
        players = tb.get("playerStats") or []
        rows = []

        # 1) per-player pitcherStats block, or 2) fallback: rows whose position includes 'p'
        for p in players:
            ps = p.get("pitcherStats")
            pos = str(p.get("position") or "").strip()
            has_ps = isinstance(ps, dict) and bool(ps)
            if not has_ps and not is_pitching_pos(pos):
                continue
            b = p.get("batterStats") or {}
            row = {
                "date": game["date"], "game_id": game["game_id"], "team": team, "opponent": opp,
                "last_name": str(p.get("lastName") or "").strip(),
                "first_name": str(p.get("firstName") or "").strip(),
                "position": pos, "number": p.get("number"), "starter": p.get("starter"),
                "source": "pitcherStats" if has_ps else "batting_columns",
                "ip": None, "hits_allowed": None, "runs_allowed": None, "earned_runs": None,
                "walks": None, "strikeouts": None, "batters_faced": None, "pitches": None,
                "decision": "",
                "bc_at_bats": to_num(b.get("atBats")), "bc_hits": to_num(b.get("hits")),
                "bc_runs": to_num(b.get("runsScored")), "bc_rbi": to_num(b.get("runsBattedIn")),
                "bc_walks": to_num(b.get("walks")), "bc_strikeouts": to_num(b.get("strikeouts")),
            }
            row["mixed_line"] = int(any((row[k] or 0) > 0 for k in ("bc_at_bats", "bc_hits", "bc_rbi")))
            if has_ps:
                row.update(pitch_fields(ps))
                samples.append({"source": "pitcherStats", "game_id": game["game_id"], "data": ps})
            rows.append(row)

        # 3) teamStats.pitchingStats.pitchers, if the API ever fills it in
        plist = pst.get("pitchers")
        if isinstance(plist, list):
            for e in plist:
                if not isinstance(e, dict) or not e:
                    continue
                last = str(pick(e, "lastName", "last_name") or "").strip()
                first = str(pick(e, "firstName", "first_name") or "").strip()
                full = str(pick(e, "name", "fullName", "playerName") or "").strip()
                if not last and full:
                    parts = full.split()
                    last, first = parts[-1], " ".join(parts[:-1])
                fields = pitch_fields(e)
                same = [r for r in rows if last and r["last_name"].lower() == last.lower()]
                if same:     # already have this pitcher: just fill gaps
                    for k, v in fields.items():
                        if same[0].get(k) in (None, "") and v not in (None, ""):
                            same[0][k] = v
                    continue
                roster = [p for p in players if last and str(p.get("lastName") or "").strip().lower() == last.lower()]
                r0 = roster[0] if len(roster) == 1 else {}
                b = r0.get("batterStats") or {}
                row = {
                    "date": game["date"], "game_id": game["game_id"], "team": team, "opponent": opp,
                    "last_name": last, "first_name": first,
                    "position": str(r0.get("position") or "").strip(), "number": r0.get("number"),
                    "starter": r0.get("starter"), "source": "pitchers_list",
                    "bc_at_bats": to_num(b.get("atBats")), "bc_hits": to_num(b.get("hits")),
                    "bc_runs": to_num(b.get("runsScored")), "bc_rbi": to_num(b.get("runsBattedIn")),
                    "bc_walks": to_num(b.get("walks")), "bc_strikeouts": to_num(b.get("strikeouts")),
                }
                row["mixed_line"] = int(any((row[k] or 0) > 0 for k in ("bc_at_bats", "bc_hits", "bc_rbi")))
                row.update(fields)
                samples.append({"source": "pitchers_list", "game_id": game["game_id"], "data": e})
                rows.append(row)

        # ---- team row, with self-audit columns ----
        bc = [r for r in rows if r["source"] == "batting_columns"]
        bc_mixed = sum(r["mixed_line"] for r in bc)
        have = bool(bc) and bc_mixed == 0
        s_runs = sum((r["bc_runs"] or 0) for r in bc)
        s_bb = sum((r["bc_walks"] or 0) for r in bc)
        s_k = sum((r["bc_strikeouts"] or 0) for r in bc)
        opp_b, own_b = bat[other], bat[side]
        h_a, r_a = to_num(pt.get("hitsAllowed")), to_num(pt.get("runsAllowed"))
        bb_a, k_a = to_num(pt.get("walksAllowed")), to_num(pt.get("strikeouts"))
        team_rows.append({
            "date": game["date"], "game_id": game["game_id"], "team": team, "opponent": opp, "role": side,
            "ip": parse_ip(pt.get("inningsPitched")), "hits_allowed": h_a, "runs_allowed": r_a,
            "earned_runs": to_num(pt.get("earnedRunsAllowed")), "walks_allowed": bb_a,
            "strikeouts": k_a, "batters_faced": to_num(pt.get("battersFaced")),
            "pitches": to_num(pst.get("numberOfPitches")),
            "win": _label(pst.get("win")), "loss": _label(pst.get("loss")), "save": _label(pst.get("save")),
            "hits_ok": eq(h_a, to_num(opp_b.get("hits"))),
            "runs_ok": eq(r_a, to_num(opp_b.get("runsScored"))),
            "walks_ok": eq(bb_a, to_num(opp_b.get("walks"))),
            "strikeouts_ok": eq(k_a, to_num(opp_b.get("strikeouts"))),
            "n_pitcher_rows": len(rows), "n_mixed_rows": sum(r["mixed_line"] for r in rows),
            "rows_runs_sum": s_runs if have else None, "rows_walks_sum": s_bb if have else None,
            "rows_strikeouts_sum": s_k if have else None,
            "rows_runs_vs_opp_runs": eq(s_runs, scores[other]) if have else "",
            "rows_k_vs_opp_k": eq(s_k, to_num(opp_b.get("strikeouts"))) if have else "",
            "rows_k_vs_own_k": eq(s_k, to_num(own_b.get("strikeouts"))) if have else "",
            "rows_bb_vs_opp_bb": eq(s_bb, to_num(opp_b.get("walks"))) if have else "",
            "rows_bb_vs_own_bb": eq(s_bb, to_num(own_b.get("walks"))) if have else "",
        })
        pitcher_rows.extend(rows)
    return team_rows, pitcher_rows, samples


def fetch_one(game):
    """Never raises. status: ok | none (no box score) | unusable (odd structure) | error (retry next run)."""
    gid = game["game_id"]
    try:
        box = api_get(f"/game/{gid}/boxscore")
    except ApiError as e:
        return {"game_id": gid, "status": "error", "error": re.sub(r"/game/\d+", "/game/N", str(e))[:110]}
    if not box or not box.get("teamBoxscore"):
        return {"game_id": gid, "status": "none"}
    try:
        t, p, s = extract_pitching(box, game)
    except ValueError as e:
        return {"game_id": gid, "status": "unusable", "error": str(e)}
    return {"game_id": gid, "status": "ok", "team_rows": t, "pitcher_rows": p, "samples": s}


# ----------------------------------------------------------------------------
# reporting
# ----------------------------------------------------------------------------
def _rate(rows, col):
    vals = [str(r.get(col, "")) for r in rows]
    ones = sum(1 for v in vals if v in ("1", "1.0"))
    zeros = sum(1 for v in vals if v in ("0", "0.0"))
    n = ones + zeros
    return f"{ones}/{n} ({100 * ones / n:.0f}%)" if n else "no data"


def report(team_by_game, pit_by_game):
    trows = [r for v in team_by_game.values() for r in v]
    prows = [r for v in pit_by_game.values() for r in v]
    print("\n=== PITCHING DATA AUDIT ===")
    print(f"team-games with pitching totals: {len(trows)}   pitcher rows: {len(prows)}")
    print(f"pitcher row sources: {dict(Counter(r.get('source') for r in prows))}")
    mixed = sum(1 for r in prows if str(r.get("mixed_line")) in ("1", "1.0"))
    print(f"pitcher rows that also batted (mixed_line=1, unusable): {mixed}")
    print("Team totals vs the opponent's batting line (should be ~100% if the API is right):")
    for col, label in (("hits_ok", "hits allowed"), ("runs_ok", "runs allowed"),
                       ("walks_ok", "walks allowed"), ("strikeouts_ok", "strikeouts")):
        print(f"   {label:14s} {_rate(trows, col)}")
    print("Pitchers' batting-column fallback (only team-games with no mixed rows):")
    for col, label in (("rows_runs_vs_opp_runs", "runs  = opponent's runs (pitching reading)"),
                       ("rows_k_vs_opp_k", "K     = opponent batters' K (pitching reading)"),
                       ("rows_k_vs_own_k", "K     = own team's batting K (batting reading)"),
                       ("rows_bb_vs_opp_bb", "BB    = opponent batters' BB (pitching reading)"),
                       ("rows_bb_vs_own_bb", "BB    = own team's batting BB (batting reading)")):
        print(f"   {label:50s} {_rate(trows, col)}")
    print("Use per-pitcher bc_ columns only if the pitching-reading rates are high and the batting-reading rates are low.")


# ----------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--refresh", action="store_true", help="ignore saved pitching data and redo everything")
    ap.add_argument("--limit", type=int, help="only process this many games (quick test)")
    args = ap.parse_args(argv)

    gpath = os.path.join(args.out_dir, "games_season.csv")
    tpath = os.path.join(args.out_dir, "team_pitching_games_season.csv")
    ppath = os.path.join(args.out_dir, "pitcher_games_season.csv")
    dpath = os.path.join(args.out_dir, "_pitching_done_games.txt")
    spath = os.path.join(args.out_dir, "_pitching_schema_samples.json")

    games = [g for g in read_csv(gpath)[0] if is_final(g) and not g.get("duplicate_of")]
    if not games:
        print(f"No final games found in {gpath}; run ncaa_pull.py first.")
        return 0

    team_by_game, pit_by_game, done = {}, {}, set()
    if not args.refresh:
        for r in read_csv(tpath)[0]:
            team_by_game.setdefault(r["game_id"], []).append(r)
        for r in read_csv(ppath)[0]:
            pit_by_game.setdefault(r["game_id"], []).append(r)
        done = nc.load_completed_dates(dpath)

    cutoff = today_et() - timedelta(days=RECHECK_DAYS)
    todo = [g for g in games if g["game_id"] not in done or date.fromisoformat(g["date"]) >= cutoff]
    todo.sort(key=lambda g: (g["date"], g["game_id"]))
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(games)} final games on file, {len(done)} already have pitching data, {len(todo)} to fetch.")

    samples, counts, err_msgs = [], Counter(), Counter()

    def save():
        order = sorted(games, key=lambda g: (g["date"], g["game_id"]))
        atomic_write_csv(tpath, TEAM_COLS, [r for g in order for r in team_by_game.get(g["game_id"], [])])
        atomic_write_csv(ppath, PITCHER_COLS, [r for g in order for r in pit_by_game.get(g["game_id"], [])])
        nc.save_completed_dates(dpath, done)
        if samples:
            with open(spath, "w", encoding="utf-8") as f:
                json.dump(samples, f, indent=1, default=str)

    try:
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futs = {ex.submit(fetch_one, g): g for g in todo}
            for i, fut in enumerate(as_completed(futs), 1):
                res = fut.result()
                gid, st = res["game_id"], res["status"]
                counts[st] += 1
                if st == "ok":
                    team_by_game[gid], pit_by_game[gid] = res["team_rows"], res["pitcher_rows"]
                    done.add(gid)
                    for s in res["samples"]:
                        if len(samples) < 8:
                            samples.append(s)
                elif st in ("none", "unusable"):
                    team_by_game.pop(gid, None)
                    pit_by_game.pop(gid, None)
                    done.add(gid)
                else:
                    err_msgs[res.get("error", "")] += 1
                if i % SAVE_EVERY == 0:
                    save()
                    print(f"  {i}/{len(todo)} games done")
    except KeyboardInterrupt:
        print("\nInterrupted -- saving what we have. Re-run to continue.")
        save()
        return 130

    save()
    print(f"\nfetched: {dict(counts)}")
    for m, n in err_msgs.most_common(3):
        print(f"   {n}x {m}")
    report(team_by_game, pit_by_game)
    if samples:
        print(f"\nThe API DID fill in per-pitcher stat blocks for some games -- raw examples saved to {spath}")
    if len(todo) >= 4 and counts["error"] == len(todo):
        print("RESULT: every fetch failed -- check the log above.")
        return 1
    if counts["error"]:
        print(f"RESULT: completed; {counts['error']} game(s) failed and will be retried next run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
