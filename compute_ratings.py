import numpy as np
import pandas as pd


def compute_kahl_index(df_team_games):
    """Computes opponent-adjusted run margins (Kahl Index) per 7 innings

    and zero-centers the baseline so 0.0 represents the true D1 average.
    """
    # 1. Calculate per-game run margin per 7 innings
    df_team_games["margin_per_7"] = (
        (df_team_games["runs_for"] - df_team_games["runs_against"])
        / df_team_games["innings_fielded"]
    ) * 7.0

    # 2. Get initial raw average per-7 margin per team
    team_stats = (
        df_team_games.groupby("team")["margin_per_7"].mean().reset_index()
    )
    team_stats.rename(columns={"margin_per_7": "raw_margin"}, inplace=True)

    # Map ratings to dictionary for iterative SoS adjustment
    ratings = dict(zip(team_stats["team"], team_stats["raw_margin"]))

    # 3. Iterative Opponent-Adjustment (Strength of Schedule)
    # 50 iterations converges the rating system across all connected games
    for _ in range(50):
        new_ratings = {}
        for team, group in df_team_games.groupby("team"):
            # Opponents' current ratings
            opp_ratings = group["opponent"].map(ratings).fillna(0.0)
            # Adjusted rating = raw performance + average opponent strength
            adj_rating = group["margin_per_7"].mean() + opp_ratings.mean()
            new_ratings[team] = adj_rating

        ratings = new_ratings

    # Convert back to DataFrame
    final_df = pd.DataFrame(
        list(ratings.items()), columns=["team", "uncentered_rating"]
    )

    # 4. CRITICAL STEP: Zero-center to Division I average
    # Subtract the overall D1 mean so rank ~150 becomes exactly 0.00
    d1_mean_baseline = final_df["uncentered_rating"].mean()
    final_df["rating"] = (
        final_df["uncentered_rating"] - d1_mean_baseline
    ).round(2)

    # Sort descending
    final_df = final_df.sort_values(by="rating", ascending=False).reset_index(
        drop=True
    )
    final_df["rank"] = final_df.index + 1

    return final_df
