import os
import json
import pandas as pd

def calculate_rc7(
    input_path="player_games_season.csv", 
    all_output_path="players.json", 
    qualified_output_path="qualified_players.json",
    min_ab_cutoff=10, 
    min_qualified_ab=40,
    ab_per_game_threshold=2.0
):
    if not os.path.exists(input_path) or os.stat(input_path).st_size == 0:
        print(f"Warning: {input_path} not found or empty. Writing empty arrays.")
        for path in (all_output_path, qualified_output_path):
            with open(path, "w") as f:
                json.dump([], f)
        return

    print(f"Loading player game data from {input_path}...")
    df = pd.read_csv(input_path)

    # Clean numeric columns
    numeric_cols = ["at_bats", "hits", "runs_scored", "rbi", "walks", "strikeouts"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df.get(col, 0), errors="coerce").fillna(0)

    # Create full name for grouping
    df["full_name"] = df["first_name"].fillna("").astype(str).str.strip() + " " + df["last_name"].fillna("").astype(str).str.strip()
    df["full_name"] = df["full_name"].str.strip()

    # --- 1. COMPUTE OPPONENT STRENGTH ADJUSTMENT FACTOR ---
    # Aggregate total runs scored per game/team to compute D1 average
    game_team_runs = df.groupby(["game_id", "team", "opponent"], as_index=False)["runs_scored"].sum()
    
    total_d1_runs = game_team_runs["runs_scored"].sum()
    total_d1_games = game_team_runs["game_id"].nunique()
    
    # Standard D1 average runs per 7-inning game (~4.5 baseline fallback)
    d1_avg_ra7 = (total_d1_runs / (total_d1_games * 2)) if total_d1_games > 0 else 4.5

    # Compute average runs allowed per game by opponents for each team
    team_opponents = game_team_runs.groupby("team")["runs_scored"].mean().to_dict()

    # --- 2. AGGREGATE PLAYER STATS ---
    team_game_counts = df.groupby("team")["game_id"].nunique().to_dict()

    grouped = df.groupby(["full_name", "team"], as_index=False).agg({
        "game_id": "nunique",
        "at_bats": "sum",
        "hits": "sum",
        "runs_scored": "sum",
        "rbi": "sum",
        "walks": "sum",
        "strikeouts": "sum"
    }).rename(columns={
        "game_id": "G",
        "at_bats": "AB",
        "hits": "H",
        "runs_scored": "R",
        "rbi": "RBI",
        "walks": "BB",
        "strikeouts": "SO"
    })

    # Hard Cutoff: Filter out hitters with under 10 ABs
    grouped = grouped[grouped["AB"] >= min_ab_cutoff].copy()

    all_players = []
    for _, row in grouped.iterrows():
        ab = row["AB"]
        h = row["H"]
        bb = row["BB"]
        g = row["G"]
        team = row["team"]

        # Qualification Check: >= 2.0 AB/team-game AND >= 40 total ABs
        team_total_games = team_game_counts.get(team, g)
        min_required_ab = team_total_games * ab_per_game_threshold
        is_qualified = bool(ab >= min_required_ab and ab >= min_qualified_ab)

        # Basic Runs Created (RC)
        if (ab + bb) > 0:
            a = h + bb
            b = (1.125 * h) + (0.25 * bb)  # Linear weights proxy for Total Bases
            c = ab + bb
            rc = (a * b) / c
        else:
            rc = 0.0

        # Unadjusted Runs Created per 7 (RC7)
        outs = (ab - h)
        rc7 = (rc / outs) * 21 if outs > 0 else 0.0

        # Opponent Adjustment Multiplier
        team_opp_ra7 = team_opponents.get(team, d1_avg_ra7)
        opp_multiplier = (d1_avg_ra7 / team_opp_ra7) if team_opp_ra7 > 0 else 1.0
        
        # Opponent-Adjusted RC7 (RC7/adj)
        rc7_adj = rc7 * opp_multiplier

        all_players.append({
            "name": row["full_name"],
            "team": team,
            "games_played": int(g),
            "team_games": int(team_total_games),
            "qualified": is_qualified,
            "ab": int(ab),
            "hits": int(h),
            "runs": int(row["R"]),
            "rbi": int(row["RBI"]),
            "walks": int(bb),
            "strikeouts": int(row["SO"]),
            "rc": round(rc, 2),
            "rc7": round(rc7, 2),
            "rc7_adj": round(rc7_adj, 2)
        })

    # Sort all players by Adjusted RC7 descending
    all_players.sort(key=lambda x: x["rc7_adj"], reverse=True)

    # Separate qualified subset
    qualified_players = [p for p in all_players if p["qualified"]]

    # Export players.json (>= 10 ABs)
    with open(all_output_path, "w") as f:
        json.dump(all_players, f, indent=2)

    # Export qualified_players.json (Qualified subset)
    with open(qualified_output_path, "w") as f:
        json.dump(qualified_players, f, indent=2)

    print(f"Saved {len(all_players)} total players (>= {min_ab_cutoff} ABs) to {all_output_path}.")
    print(f"Saved {len(qualified_players)} qualified players (>= {ab_per_game_threshold} AB/game AND >= {min_qualified_ab} ABs) to {qualified_output_path}.")

if __name__ == "__main__":
    calculate_rc7()
