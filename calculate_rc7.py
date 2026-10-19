import os
import json
import pandas as pd

def calculate_rc7(
    stats_path="cumulative_player_stats.csv",
    team_games_path="team_games_season.csv",
    all_output_path="players.json",
    qualified_output_path="qualified_players.json",
    min_ab_cutoff=10,
    min_qualified_ab=40,
    ab_per_game_threshold=2.0
):
    if not os.path.exists(stats_path) or os.stat(stats_path).st_size == 0:
        print("Cumulative stats file missing or empty.")
        return

    players_df = pd.read_csv(stats_path)
    
    if not os.path.exists(team_games_path):
        print(f"Warning: {team_games_path} missing. Proceeding with unadjusted RC7.")
        team_games_df = pd.DataFrame()
    else:
        team_games_df = pd.read_csv(team_games_path)

    # Robust column detection for team games played
    if not team_games_df.empty:
        games_col = "games_played" if "games_played" in team_games_df.columns else "games"
        team_games_map = team_games_df.set_index("team")[games_col].to_dict()
        
        # Calculate League D1 Average RA7
        ra_col = "runs_against_per_7" if "runs_against_per_7" in team_games_df.columns else "ra7"
        if ra_col in team_games_df.columns:
            d1_avg_ra7 = team_games_df[ra_col].mean()
            team_opp_map = team_games_df.set_index("team")["opp_runs_against_per_7"].to_dict() if "opp_runs_against_per_7" in team_games_df.columns else {}
        else:
            d1_avg_ra7 = 4.0
            team_opp_map = {}
    else:
        team_games_map = {}
        d1_avg_ra7 = 4.0
        team_opp_map = {}

    all_players = []
    for _, row in players_df.iterrows():
        team = str(row.get("team", "")).strip()
        ab = float(row.get("ab", 0))
        h = float(row.get("hits", 0))
        d2b = float(row.get("doubles", 0))
        d3b = float(row.get("triples", 0))
        hr = float(row.get("hr", 0))
        bb = float(row.get("walks", 0))

        if ab < min_ab_cutoff:
            continue

        # Exact Total Bases Equation
        singles = h - (d2b + d3b + hr)
        tb = singles + (2 * d2b) + (3 * d3b) + (4 * hr)

        # Bill James Runs Created
        a = h + bb
        b = tb + (0.26 * bb)
        c = ab + bb
        rc = (a * b) / c if c > 0 else 0.0

        # Unadjusted RC7
        outs = ab - h
        rc7 = (rc / outs) * 21 if outs > 0 else 0.0

        # Opponent Adjustment Factor
        opp_ra7 = team_opp_map.get(team, d1_avg_ra7)
        m_opp = (d1_avg_ra7 / opp_ra7) if (opp_ra7 and opp_ra7 > 0) else 1.0
        rc7_adj = rc7 * m_opp

        # Dynamic Qualification Status
        team_games = team_games_map.get(team, row.get("games_played", 1))
        is_qualified = bool(ab >= (team_games * ab_per_game_threshold) and ab >= min_qualified_ab)

        all_players.append({
            "name": str(row.get("player_name", "")).strip(),
            "team": team,
            "ab": int(ab),
            "hits": int(h),
            "tb": int(tb),
            "walks": int(bb),
            "qualified": is_qualified,
            "rc": round(rc, 2),
            "rc7": round(rc7, 2),
            "rc7_adj": round(rc7_adj, 2)
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
