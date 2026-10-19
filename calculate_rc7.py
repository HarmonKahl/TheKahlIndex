import os
import json
import pandas as pd

def calculate_rc7(
    input_path="player_games_season.csv", 
    all_output_path="players.json", 
    qualified_output_path="qualified_players.json",
    min_ab_cutoff=10, 
    ab_per_game_threshold=1.5
):
    if not os.path.exists(input_path) or os.stat(input_path).st_size == 0:
        print(f"Warning: {input_path} not found or empty. Writing empty arrays.")
        for path in (all_output_path, qualified_output_path):
            with open(path, "w") as f:
                json.dump([], f)
        return

    print(f"Loading player game data from {input_path}...")
    df = pd.read_csv(input_path)

    # Ensure required numeric columns are present and clean
    numeric_cols = ["at_bats", "hits", "runs_scored", "rbi", "walks", "strikeouts"]
    for col in numeric_cols:
        if col not in df.columns:
            df[col] = 0
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Create full name for grouping
    df["full_name"] = df["first_name"].fillna("").astype(str).str.strip() + " " + df["last_name"].fillna("").astype(str).str.strip()
    df["full_name"] = df["full_name"].str.strip()

    # 1. Calculate total team games played to evaluate qualified status
    team_game_counts = df.groupby("team")["game_id"].nunique().to_dict()

    # 2. Aggregate stats per player across all games
    grouped = df.groupby(["full_name", "team"], as_index=False).agg({
        "game_id": "nunique",      # Unique games player appeared in
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

    # --- HARD CUTOFF: Eliminate anyone with fewer than 10 ABs ---
    grouped = grouped[grouped["AB"] >= min_ab_cutoff].copy()

    all_players = []
    for _, row in grouped.iterrows():
        ab = row["AB"]
        h = row["H"]
        bb = row["BB"]
        g = row["G"]
        team = row["team"]

        # Qualification threshold: 1.5 ABs per team game
        team_total_games = team_game_counts.get(team, g)
        min_required_ab = team_total_games * ab_per_game_threshold
        is_qualified = bool(ab >= min_required_ab)

        # Basic Runs Created (RC)
        if (ab + bb) > 0:
            a = h + bb
            b = (1.125 * h) + (0.25 * bb)  # Linear weights proxy for Total Bases
            c = ab + bb
            rc = (a * b) / c
        else:
            rc = 0.0

        # Adjust per 7 innings / 21 outs (RC7)
        outs = (ab - h)
        rc7 = (rc / outs) * 21 if outs > 0 else 0.0

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
            "rc7": round(rc7, 2)
        })

    # Sort all players by RC7 descending
    all_players.sort(key=lambda x: x["rc7"], reverse=True)

    # Filter out qualified subset
    qualified_players = [p for p in all_players if p["qualified"]]

    # Save all players JSON (>= 10 ABs)
    with open(all_output_path, "w") as f:
        json.dump(all_players, f, indent=2)

    # Save qualified players JSON (>= 10 ABs AND >= 1.5 AB/team-game)
    with open(qualified_output_path, "w") as f:
        json.dump(qualified_players, f, indent=2)

    print(f"Saved {len(all_players)} total players (>= {min_ab_cutoff} ABs) to {all_output_path}.")
    print(f"Saved {len(qualified_players)} qualified players (>= {ab_per_game_threshold} AB/game) to {qualified_output_path}.")

if __name__ == "__main__":
    calculate_rc7()
