import os
import json
import pandas as pd

def resolve_team_player_names(df, name_col="last_name"):
    """
    Two-pass resolver to merge standalone last names ('Manos') 
    with full/initialed names ('B. Manos' / 'Bailey Manos') on the same team.
    """
    def format_name(raw):
        if not isinstance(raw, str) or not raw.strip():
            return "Unknown"
        s = raw.strip()
        if "," in s:
            parts = s.split(",", 1)
            last, first = parts[0].strip().title(), parts[1].strip().title()
            return f"{first[0]}. {last}" if first else last
        parts = s.split()
        if len(parts) == 1:
            return parts[0].capitalize()
        first, last = parts[0], " ".join(parts[1:])
        return f"{first[0].upper()}. {last.title()}"

    df["formatted_name"] = df[name_col].astype(str).apply(format_name)

    # Pass 1: Build a lookup map for each team (last_name -> full_formatted_name)
    team_name_maps = {}
    for team, group in df.groupby("team"):
        last_to_full = {}
        unique_names = group["formatted_name"].unique()
        for n in unique_names:
            parts = str(n).split()
            if len(parts) > 1:
                last_name = parts[-1].lower()
                last_to_full[last_name] = str(n)
        team_name_maps[team] = last_to_full

    # Pass 2: Safely map row values ensuring scalar string returns
    def final_resolve(row):
        team = row["team"]
        fname = str(row["formatted_name"])
        parts = fname.split()
        if len(parts) == 1:
            last_name = parts[0].lower()
            resolved = team_name_maps.get(team, {}).get(last_name, fname)
            if isinstance(resolved, (list, tuple, pd.Series)):
                return str(resolved[0])
            return str(resolved)
        return fname

    df["clean_name"] = df.apply(final_resolve, axis=1).astype(str)
    return df


def calculate_rc7(
    player_games_path="player_games_season.csv",
    team_games_path="team_games_season.csv",
    all_output_path="players.json",
    qualified_output_path="qualified_players.json",
    min_qualified_ab=40,
    ab_per_game_threshold=2.0,
):
    if not os.path.exists(player_games_path) or os.stat(player_games_path).st_size == 0:
        print(f"{player_games_path} missing or empty.")
        return

    games_df = pd.read_csv(player_games_path)

    # 1. Deduplicate & Resolve Names
    name_col = "last_name" if "last_name" in games_df.columns else "name"
    games_df = resolve_team_player_names(games_df, name_col=name_col)

    # 2. Ensure numeric types for core stats
    cols = ["at_bats", "hits", "walks", "doubles", "triples", "home_runs",
            "doubles_hittingSeason", "triples_hittingSeason", "home_runs_hittingSeason"]
    for col in cols:
        if col in games_df.columns:
            games_df[col] = pd.to_numeric(games_df[col], errors="coerce").fillna(0)
        else:
            games_df[col] = 0

    # 3. Aggregate Player Stats safely
    def compute_player_totals(group):
        ab = group["at_bats"].sum()
        hits = group["hits"].sum()
        walks = group["walks"].sum()
        
        # Direct per-game sums
        d2b_pg = group["doubles"].sum()
        d3b_pg = group["triples"].sum()
        hr_pg = group["home_runs"].sum()

        # Cumulative max values
        d2b_cum = group["doubles_hittingSeason"].max()
        d3b_cum = group["triples_hittingSeason"].max()
        hr_cum = group["home_runs_hittingSeason"].max()

        # Pick whichever metric captures her actual extra-base hits without undercounting
        d2b = max(d2b_pg, d2b_cum)
        d3b = max(d3b_pg, d3b_cum)
        hr = max(hr_pg, hr_cum)

        return pd.Series({
            "games": len(group),
            "ab": ab,
            "hits": hits,
            "walks": walks,
            "doubles": d2b,
            "triples": d3b,
            "hr": hr,
        })

    season = (
        games_df.groupby(["team", "clean_name"])
        .apply(compute_player_totals, include_groups=False)
        .reset_index()
    )
    season["name"] = season["clean_name"]

    # 4. Opponent Strength Mapping
    team_games_df = pd.DataFrame()
    if os.path.exists(team_games_path) and os.stat(team_games_path).st_size > 0:
        team_games_df = pd.read_csv(team_games_path)

    team_games_map, team_opp_map, d1_avg_ra7 = {}, {}, 4.0
    
    if not team_games_df.empty:
        team_games_df["team"] = team_games_df["team"].astype(str).str.strip()

        if "runs_against_per_7" in team_games_df.columns:
            team_games_map = team_games_df.set_index("team")["games_played"].to_dict()
            team_opp_map = team_games_df.set_index("team")["runs_against_per_7"].to_dict()
            d1_avg_ra7 = team_games_df["runs_against_per_7"].mean()
        elif "runs_against" in team_games_df.columns:
            team_totals = (
                team_games_df.groupby("team")
                .agg(
                    games=("runs_against", "count"),
                    runs_against=("runs_against", "sum")
                )
                .reset_index()
            )
            team_totals["ra_per_7"] = team_totals["runs_against"] / team_totals["games"].replace(0, 1)
            
            team_games_map = team_totals.set_index("team")["games"].to_dict()
            team_opp_map = team_totals.set_index("team")["ra_per_7"].to_dict()
            d1_avg_ra7 = team_totals["ra_per_7"].mean()

    all_players = []
    for _, row in season.iterrows():
        team = str(row["team"]).strip()
        ab, h = float(row["ab"]), float(row["hits"])
        d2b, d3b, hr, bb = float(row["doubles"]), float(row["triples"]), float(row["hr"]), float(row["walks"])

        if (ab + bb) == 0:
            continue

        # Sanity cap: Extra-base hits cannot exceed total hits
        xbh = d2b + d3b + hr
        if xbh > h and h > 0:
            d2b = min(d2b, h)
            d3b = min(d3b, max(0.0, h - d2b))
            hr = min(hr, max(0.0, h - d2b - d3b))
            xbh = d2b + d3b + hr

        singles = max(0.0, h - xbh)
        tb = singles + (2 * d2b) + (3 * d3b) + (4 * hr)

        # Tech Version RC Formula
        a = h + bb
        b = tb + (0.26 * bb)
        c = ab + bb
        rc = (a * b) / c if c > 0 else 0.0

        outs = ab - h
        rc7 = (rc / outs) * 21 if outs > 0 else 0.0

        opp_ra7 = team_opp_map.get(team, d1_avg_ra7)
        m_opp = (d1_avg_ra7 / opp_ra7) if (opp_ra7 and opp_ra7 > 0) else 1.0
        rc7_adj = rc7 * m_opp

        team_games = team_games_map.get(team, row["games"])
        is_qualified = bool(ab >= (team_games * ab_per_game_threshold) and ab >= min_qualified_ab)

        all_players.append({
            "name": row["name"],
            "team": team,
            "ab": int(ab),
            "hits": int(h),
            "tb": int(tb),
            "walks": int(bb),
            "qualified": is_qualified,
            "rc": round(rc, 2),
            "rc7": round(rc7, 2),
            "rc7_adj": round(rc7_adj, 2),
        })

    # Sort & Rank All Players
    all_players.sort(key=lambda x: x["rc7_adj"], reverse=True)
    for rank, player in enumerate(all_players, start=1):
        player["rank"] = rank

    # Sort & Rank Qualified Players
    qualified_players = [dict(p) for p in all_players if p["qualified"]]
    for rank, player in enumerate(qualified_players, start=1):
        player["rank"] = rank

    with open(all_output_path, "w") as f:
        json.dump(all_players, f, indent=2)

    with open(qualified_output_path, "w") as f:
        json.dump(qualified_players, f, indent=2)

    print(f"Exported {len(all_players)} total players to {all_output_path}")
    print(f"Exported {len(qualified_players)} qualified players to {qualified_output_path}")

if __name__ == "__main__":
    calculate_rc7()
