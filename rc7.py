#!/usr/bin/env python3
"""
rc7.py -- compute RC7 for every hitter from the CSVs written by ncaa_pull.py.

    python rc7.py                 # writes players.json + qualified_players.json
    python rc7.py --audit         # also compare AB/H/BB to NCAA's official player stats

Formula (unchanged from calculate_rc7.py):
    RC   = (H + BB) * (TB + 0.26*BB) / (AB + BB)
    RC7  = RC / (AB - H) * 21          (runs created per 21 outs = per 7 innings)
    RC7_adj = RC7 * OPAF               (opponent adjustment, see below)

What changed vs. the old calculate_rc7.py (details in README.md):
  * Pitcher rows are excluded from walks -- NCAA's box score puts the pitcher's
    walks-allowed in the batting-walks column, which roughly doubled every
    team's walk total.
  * A player whose name shows up as "Smith" in some games and "Jane Smith" in
    others (it varies by school) is merged into ONE player using jersey number.
  * Doubles/triples/HR use the box score's season-to-date counters.
  * "per 7" uses real innings from team_games_season.csv.
  * players.json has the keys index.html reads (player_name, PA, HR, RC7_raw,
    OPAF, RC7_adj) as well as the old ones (name, rc7, rc7_adj, rank ...).
"""

import argparse
import json
import os
import re
import sys

import pandas as pd


def alnum(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


# ----------------------------------------------------------------------------
# one player = one id, even if the name is written differently game to game
# ----------------------------------------------------------------------------
def _surname(name):
    toks = str(name).replace(",", " ").split()
    return alnum(toks[-1]) if toks else ""


def _initial(name):
    toks = str(name).split()
    return alnum(toks[0])[:1] if len(toks) > 1 else ""


def same_player(a, b):
    """'Smith' ~ 'Jane Smith' ~ 'J. Smith'; 'Jane Smith' !~ 'Kate Smith'."""
    na, nb = alnum(a), alnum(b)
    if na == nb or na.endswith(nb) or nb.endswith(na):
        return True
    ia, ib = _initial(a), _initial(b)
    return _surname(a) == _surname(b) and (not ia or not ib or ia == ib)


def resolve_players(df):
    """Adds player_id and player_name. Identity = (team, jersey number); names
    split two different players who share a number and attach rows that have
    no number. Same player written 'Smith' / 'J. Smith' / 'Jane Smith' -> one."""
    df = df.copy()
    df["first_name"] = df["first_name"].fillna("").astype(str).str.strip()
    df["last_name"] = df["last_name"].fillna("").astype(str).str.strip()
    df["full"] = (df["first_name"] + " " + df["last_name"]).str.strip()
    df["num"] = pd.to_numeric(df["number"], errors="coerce")

    pid = pd.Series(index=df.index, dtype=object)
    display = {}
    for team, g in df.groupby("team", sort=False):
        clusters = []  # {"names": set, "best": str, "id": str}

        def add(c, full):
            c["names"].add(full)
            if len(full) > len(c["best"]):
                c["best"] = full

        # pass 1: rows with a jersey number, one number at a time
        numbered = g[g["num"].notna()]
        for num, gn in numbered.groupby("num", sort=True):
            local = []
            for idx, full in sorted(zip(gn.index, gn["full"]), key=lambda t: -len(t[1])):
                hit = next((c for c in local if any(same_player(full, n) for n in c["names"])), None)
                if hit is None:
                    hit = {"names": set(), "best": full, "id": f"{team}|#{int(num)}|{len(local)}"}
                    local.append(hit)
                add(hit, full)
                pid[idx] = hit["id"]
            clusters.extend(local)
        # pass 2: rows with no number -> join the one matching player, else make one
        for idx, full in zip(g[g["num"].isna()].index, g[g["num"].isna()]["full"]):
            matches = [c for c in clusters if any(same_player(full, n) for n in c["names"])]
            if len(matches) == 1:
                c = matches[0]
            else:
                c = next((c for c in clusters if c["id"] == f"{team}|n|{alnum(full)}"), None)
                if c is None:
                    c = {"names": set(), "best": full, "id": f"{team}|n|{alnum(full)}"}
                    clusters.append(c)
            add(c, full)
            pid[idx] = c["id"]
        for c in clusters:
            display[c["id"]] = c["best"]

    df["player_id"] = pid
    df["player_name"] = df["player_id"].map(display)
    return df


# ----------------------------------------------------------------------------
def load(player_path, team_path):
    p = pd.read_csv(player_path, dtype={"game_id": str})
    t = pd.read_csv(team_path, dtype={"game_id": str})
    return p, t


def team_context(t):
    """Games played and runs-allowed-per-7 for every team, from real innings."""
    t = t.copy()
    t["team"] = t["team"].astype(str).str.strip()
    agg = t.groupby("team").agg(
        games=("game_id", "nunique"),
        runs_against=("runs_against", "sum"),
        innings_fielded=("innings_fielded", "sum"),
    )
    agg["ra7"] = agg["runs_against"] / agg["innings_fielded"] * 7
    return agg


def calculate(player_path="player_games_season.csv", team_path="team_games_season.csv",
              out_all="players.json", out_qualified="qualified_players.json",
              min_qualified_ab=40, ab_per_team_game=2.0, quiet=False):
    p, t = load(player_path, team_path)
    p = resolve_players(p)

    num = ["at_bats", "hits", "walks", "doubles", "triples", "home_runs",
           "doubles_season_total", "triples_season_total", "home_runs_season_total"]
    for c in num:
        p[c] = pd.to_numeric(p[c], errors="coerce")
    # pitching rows ('p', 'p/1b', 'dp/p', '1b/p' ...): NCAA puts the pitcher's walks
    # allowed in the batting-walks column, so those walks can't be trusted.
    p["pitcher_row"] = p["position"].fillna("").map(
        lambda x: "p" in [t.strip().lower() for t in str(x).split("/")])

    # NCAA puts a pitcher's walks-ALLOWED in the batting walks column.
    p["walks_clean"] = p["walks"].where(~p["pitcher_row"], 0).fillna(0)
    p["ab0"] = p["at_bats"].fillna(0)
    p["h0"] = p["hits"].fillna(0)

    g = p.groupby("player_id")
    season = pd.DataFrame({
        "player_name": g["player_name"].first(),
        "team": g["team"].first(),
        "games": g.size(),
        "ab": g["ab0"].sum(),
        "hits": g["h0"].sum(),
        "walks": g["walks_clean"].sum(),
        "pitcher_rows": g["pitcher_row"].sum(),
        "d2_pg": g["doubles"].sum(min_count=1),
        "d3_pg": g["triples"].sum(min_count=1),
        "hr_pg": g["home_runs"].sum(min_count=1),
        "d2_cum": g["doubles_season_total"].max(),
        "d3_cum": g["triples_season_total"].max(),
        "hr_cum": g["home_runs_season_total"].max(),
    }).reset_index()
    for a, b in (("d2_pg", "d2_cum"), ("d3_pg", "d3_cum"), ("hr_pg", "hr_cum")):
        season[a[:-3]] = season[[a, b]].max(axis=1).fillna(0)

    ctx = team_context(t)
    d1_ra7 = (ctx["runs_against"].sum() / ctx["innings_fielded"].sum() * 7) if len(ctx) else 4.0

    out = []
    for r in season.itertuples():
        ab, h, bb = float(r.ab), float(r.hits), float(r.walks)
        if ab + bb == 0:
            continue
        d2, d3, hr = float(r.d2), float(r.d3), float(r.hr)
        xbh = d2 + d3 + hr
        if xbh > h:  # extra-base hits can't exceed hits
            d2 = min(d2, h)
            d3 = min(d3, max(0.0, h - d2))
            hr = min(hr, max(0.0, h - d2 - d3))
            xbh = d2 + d3 + hr
        tb = (h - xbh) + 2 * d2 + 3 * d3 + 4 * hr
        rc = (h + bb) * (tb + 0.26 * bb) / (ab + bb)
        outs = ab - h
        rc7 = rc / outs * 21 if outs > 0 else 0.0

        ra7 = ctx["ra7"].get(r.team) if r.team in ctx.index else None
        opaf = (d1_ra7 / ra7) if ra7 and ra7 > 0 else 1.0
        team_games = int(ctx["games"].get(r.team, r.games))
        qualified = bool(ab >= team_games * ab_per_team_game and ab >= min_qualified_ab)
        out.append({
            "player_name": r.player_name, "name": r.player_name, "team": r.team,
            "PA": int(ab + bb), "HR": int(hr),
            "pitching_games": int(r.pitcher_rows), "RC7_raw": round(rc7, 2), "OPAF": round(opaf, 2), "RC7_adj": round(rc7 * opaf, 2),
            "ab": int(ab), "hits": int(h), "doubles": int(d2), "triples": int(d3),
            "tb": int(tb), "walks": int(bb), "qualified": qualified,
            "rc": round(rc, 2), "rc7": round(rc7, 2), "rc7_adj": round(rc7 * opaf, 2),
        })

    out.sort(key=lambda x: x["RC7_adj"], reverse=True)
    for i, row in enumerate(out, 1):
        row["rank"] = i
    qual = [dict(x) for x in out if x["qualified"]]
    for i, row in enumerate(qual, 1):
        row["rank"] = i
    with open(out_all, "w") as f:
        json.dump(out, f, indent=2)
    with open(out_qualified, "w") as f:
        json.dump(qual, f, indent=2)
    if not quiet:
        print(f"{len(out)} players -> {out_all};  {len(qual)} qualified -> {out_qualified}")
    return out, p


# ----------------------------------------------------------------------------
def audit(players, api="https://ncaa-api.henrygd.me", season=None):
    """Compare our AB/H/BB with NCAA's official On-Base-Percentage leaderboard."""
    import requests
    season = season or pd.Timestamp.today().year
    rows, page, pages = [], 1, 1
    while page <= pages:
        r = requests.get(f"{api}/stats/softball/d1/{season}/individual/510",
                         params={"page": page} if page > 1 else None, timeout=30)
        d = r.json()
        rows += d["data"]
        pages = int(d.get("pages", 1))
        page += 1
    mine = {}
    for pl in players:
        mine.setdefault((pl["team"], alnum(pl["player_name"])), pl)
    by_sur = {}
    for (team, nm), pl in mine.items():
        by_sur.setdefault((team, nm), pl)
    exact = {"ab": 0, "hits": 0, "walks": 0}
    n = missing = 0
    bad = []
    for r in rows:
        key = (r["Team"], alnum(r["Name"]))
        pl = mine.get(key)
        if pl is None:  # our name may be surname-only
            cands = [v for (tm, nm), v in mine.items() if tm == r["Team"] and alnum(r["Name"]).endswith(nm) and len(nm) >= 3]
            pl = cands[0] if len(cands) == 1 else None
        if pl is None:
            missing += 1
            continue
        n += 1
        diffs = {}
        for ours, theirs in (("ab", "AB"), ("hits", "H"), ("walks", "BB")):
            if pl[ours] == int(r[theirs]):
                exact[ours] += 1
            else:
                diffs[ours] = (pl[ours], int(r[theirs]))
        if diffs:
            bad.append((r["Name"], r["Team"], diffs))
    print(f"\n=== PLAYER AUDIT vs official NCAA OBP leaderboard ({len(rows)} players) ===")
    print(f"matched by name: {n}   not matched: {missing}")
    for k in exact:
        print(f"  {k:5} exact for {exact[k]}/{n}")
    for b in bad[:15]:
        print("  differs:", b)
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=".")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--season", type=int)
    a = ap.parse_args()
    out_dir = a.out_dir or a.data_dir
    pp = os.path.join(a.data_dir, "player_games_season.csv")
    tp = os.path.join(a.data_dir, "team_games_season.csv")
    if not os.path.exists(pp) or not os.path.exists(tp):
        sys.exit("player_games_season.csv / team_games_season.csv not found -- run ncaa_pull.py first")
    players, _ = calculate(pp, tp, os.path.join(out_dir, "players.json"),
                           os.path.join(out_dir, "qualified_players.json"))
    if a.audit:
        audit(players, season=a.season)


if __name__ == "__main__":
    main()
