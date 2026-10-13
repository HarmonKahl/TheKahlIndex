import json
import os
import sys
import pandas as pd
import numpy as np

def load_data(team_csv_path="team_games_season.csv"):
    if not os.path.exists(team_csv_path) or os.stat(team_csv_path).st_size == 0:
        print(f"Warning: {team_csv_path} is empty or missing. Writing empty ratings.json.")
        return None

    df = pd.read_csv(team_csv_path)
    if df.empty:
        return None
    return df

def compute_kahl_index(df, min_games=20, max_iterations=50, tolerance=1e-6):
    # 1. Clean data and enforce minimum games threshold
    df = df.dropna(subset=["runs_for", "runs_against", "innings_fielded", "team", "opponent"]).copy()
    
    # Ensure no zero/invalid innings
    df["innings_fielded"] = df["innings_fielded"].apply(lambda x: x if x > 0 else 7.0)
    
    # Calculate per-game run margin per 7 innings
    df["margin_per_7"] = ((df["runs_for"] - df["runs_against"]) / df["innings_fielded"]) * 7.0

    # Filter out teams with fewer than min_games
    game_counts = df.groupby("team")["date"].count()
    valid_teams = set(game_counts[game_counts >= min_games].index)
    
    # Only keep games where BOTH teams meet the minimum games requirement
    df_filtered = df[df["team"].isin(valid_teams) & df["opponent"].isin(valid_teams)].copy()

    if df_filtered.empty:
        print("No teams met the minimum games threshold.")
        return pd.DataFrame()

    # 2. Initial raw margins per 7 innings
    team_stats = df_filtered.groupby("team")["margin_per_7"].mean().to_dict()
    ratings = team_stats.copy()

    # 3. Iterative Strength-of-Schedule Adjustment
    # Solves: Rating_team = Avg_Margin_team + Avg_Opponent_Rating
    for _ in range(max_iterations):
        new_ratings = {}
        max_diff = 0.0

        for team, group in df_filtered.groupby("team"):
            opp_ratings = group["opponent"].map(ratings)
            # Use raw unadjusted margin plus average opponent strength
            raw_margin = group["margin_per_7"].mean()
            adj_rating = raw_margin + opp_ratings.mean()
            
            diff = abs(adj_rating - ratings[team])
            if diff > max_diff:
                max_diff = diff
            new_ratings[team] = adj_rating

        ratings = new_ratings
        if max_diff < tolerance:
            break

    # Convert to DataFrame
    ratings_df = pd.DataFrame(list(ratings.items()), columns=["team", "uncentered_rating"])

    # 4. Zero-Center Baseline to Division I Mean
    # Ensures rank ~150 sits at 0.00 while preserving exact run-margin projections
    d1_mean_rating = ratings_df["uncentered_rating"].mean()
    ratings_df["rating"] = (ratings_df["uncentered_rating"] - d1_mean_rating).round(2)

    # 5. Compute Record Summaries
    team_summary = df_filtered.groupby("team").agg(
        games_played=("date", "count"),
        wins=("win", lambda x: int((x == 1).sum())),
        losses=("win", lambda x: int((x == 0).sum())),
        runs_scored=("runs_for", "sum"),
        runs_allowed=("runs_against", "sum"),
        innings_total=("innings_fielded", "sum")
    ).reset_index()

    team_summary["r_per_7"] = ((team_summary["runs_scored"] / team_summary["innings_total"]) * 7.0).round(2)
    team_summary["ra_per_7"] = ((team_summary["runs_allowed"] / team_summary["innings_total"]) * 7.0).round(2)

    # Merge ratings with summary stats
    final_df = pd.merge(ratings_df, team_summary, on="team")
    
    # Sort descending by rating
    final_df = final_df.sort_values(by="rating", ascending=False).reset_index(drop=True)
    final_df["rank"] = final_df.index + 1

    return final_df

def save_ratings_json(final_df, output_path="ratings.json"):
    if final_df is None or final_df.empty:
        with open(output_path, "w") as f:
            json.dump([], f)
        print(f"Wrote empty list to {output_path}")
        return

    records = final_df[[
        "rank", "team", "rating", "games_played", 
        "wins", "losses", "r_per_7", "ra_per_7"
    ]].to_dict("records")

    with open(output_path, "w") as f:
        json.dump(records, f, indent=2)

    print(f"Successfully computed ratings for {len(records)} teams and saved to {output_path}.")

if __name__ == "__main__":
    df_games = load_data("team_games_season.csv")
    if df_games is not None:
        final_ratings = compute_kahl_index(df_games, min_games=20)
        save_ratings_json(final_ratings, "ratings.json")
    else:
        save_ratings_json(None, "ratings.json")
