import os
import json
import pandas as pd

def calculate_rc7(input_path="player_games_season.csv", output_path="players.json", ab_per_game_threshold=1.5):
    if not os.path.exists(input_path) or os.stat(input_path).st_size == 0:
        print(f"Warning: {input_path} not found or empty. Writing empty array to {output_path}.")
        with open(output_path, "w") as f:
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

    # 1. Calculate max games played per team to determine team season game counts
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

    # Include everyone who has logged at least 1 At-Bat
    grouped = grouped[grouped["AB"] >= 1].copy()

    players_list = []
    for _, row in grouped.iterrows():
        ab = row["AB"]
        h = row["H"]
        bb = row["BB"]
        g = row["G"]
        team = row["team"]

        # Determine qualification based on 1.5 AB per team game
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

        players_list.append({
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

    # Sort players by RC7 descending
    players_list.sort(key=lambda x: x["rc7"], reverse=True)

    with open(output_path, "w") as f:
        json.dump(players_list, f, indent=2)

    total_players = len(players_list)
    qualified_players = sum(1 for p in players_list if p["qualified"])
    print(f"Saved {total_players} total hitters to {output_path} ({qualified_players} qualified @ >= {ab_per_game_threshold} AB/game).")

if __name__ == "__main__":
    calculate_rc7()
