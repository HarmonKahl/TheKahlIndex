import os
import json
import pandas as pd

def calculate_rc7(
    player_games_path="player_games_season.csv",
    team_games_path="team_games_season.csv",
    all_output_path="players.json",
    qualified_output_path="qualified_players.json",
    min_ab_cutoff=10,
    min_qualified_ab=40,
    ab_per_game_threshold=2.0,
):
    if not os.path.exists(player_games_path) or os.stat(player_games_path).st_size == 0:
        print(f"{player_games_path} missing or empty.")
        return

    games_df = pd.read_csv(player_games_path)

    season = (
        games_df.groupby(["team", "last_name", "number"])
        .agg(
            games=("game_id", "count"),
            ab=("at_bats", "sum"),
            hits=("hits", "sum"),
            walks=("walks", "sum"),
            doubles=("doubles_hittingSeason", "sum"),
            triples=("triples_hittingSeason", "sum"),
            hr=("home_runs_hittingSeason", "sum"),
        )
        .reset_index()
    )
    season["name"] = season["last_name"]

    team_games_df = pd.DataFrame()
    if os.path.exists(team_games_path) and os.stat(team_games_path).st_size > 0:
        team_games_df = pd.read_csv(team_games_path)

    team_games_map, team_opp_map, d1_avg_ra7 = {}, {}, 4.0
    
    if not team_games_df.empty:
        # Normalize team names for matching
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
            print(f"Loaded opponent data for {len(team_opp_map)} teams (D1 Avg RA/7: {d1_avg_ra7:.2f})")
    else:
        print(f"Warning: {team_games_path} missing or empty. Proceeding with unadjusted RC7.")

    all_players = []
    for _, row in season.iterrows():
        team = str(row["team"]).strip()
        ab, h = float(row["ab"]), float(row["hits"])
        d2b, d3b, hr, bb = float(row["doubles"]), float(row["triples"]), float(row["hr"]), float(row["walks"])

        if ab < min_ab_cutoff:
            continue

        singles = h - (d2b + d3b + hr)
        tb = singles + (2 * d2b) + (3 * d3b) + (4 * hr)

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

    all_players.sort(key=lambda x: x["rc7_adj"], reverse=True)
    qualified_players = [p for p in all_players if p["qualified"]]

    with open(all_output_path, "w") as f:
        json.dump(all_players, f, indent=2)
    with open(qualified_output_path, "w") as f:
        json.dump(qualified_players, f, indent=2)

    print(f"Calculated RC7 for {len(all_players)} players ({len(qualified_players)} qualified).")

if __name__ == "__main__":
    calculate_rc7()
