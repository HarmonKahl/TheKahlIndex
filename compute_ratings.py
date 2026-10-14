import json
import os
import sys
import numpy as np
import pandas as pd


def load_data(team_csv_path="team_games_season.csv"):
    if not os.path.exists(team_csv_path) or os.stat(team_csv_path).st_size == 0:
        print(f"Warning: {team_csv_path} is empty or missing. Writing empty ratings.json.")
        return None

    df = pd.read_csv(team_csv_path)
    if df.empty:
        return None
    return df


def compute_kahl_index(team_df, min_games=20, max_iters=100, tol=1e-6):
    # Step 0: Drop placeholder/garbage teams
    team_df = team_df[(team_df["team"] != "TBA") & (team_df["opponent"] != "TBA")].copy()

    # Determine which teams meet the minimum games threshold in the raw data
    raw_counts = team_df.groupby("team")["opponent"].count()
    valid_teams = set(raw_counts[raw_counts >= min_games].index)

    # STRICT PURGE: Keep ONLY games where BOTH the team AND opponent are valid ranked teams
    clean_df = team_df[
        team_df["team"].isin(valid_teams) & team_df["opponent"].isin(valid_teams)
    ].copy()

    # Re-verify counts after mutual purge to ensure no team dropped below min_games
    clean_counts = clean_df.groupby("team")["opponent"].count()
    final_valid_teams = set(clean_counts[clean_counts >= min_games].index)
    
    clean_df = clean_df[
        clean_df["team"].isin(final_valid_teams) & clean_df["opponent"].isin(final_valid_teams)
    ].copy()

    if clean_df.empty:
        print(f"No teams remaining after filtering games against non-ranked teams.")
        return pd.DataFrame()

    # Step 1: Season totals on PURGED data -> raw runs/7, league-centered off/def
    season = (
        clean_df.groupby("team")
        .agg(
            games=("opponent", "count"),
            runs_for=("runs_for", "sum"),
            runs_against=("runs_against", "sum"),
            innings_batted=("innings_batted", "sum"),
            innings_fielded=("innings_fielded", "sum"),
            wins=("win", lambda x: int((x == 1).sum())),
            losses=("win", lambda x: int((x == 0).sum())),
        )
        .reset_index()
    )

    season["r_per_7"] = season["runs_for"] / season["innings_batted"] * 7
    season["ra_per_7"] = season["runs_against"] / season["innings_fielded"] * 7
    season["diff"] = season["r_per_7"] - season["ra_per_7"]

    mean_r_per_7 = season["r_per_7"].mean()
    mean_ra_per_7 = season["ra_per_7"].mean()
    season["off_adj"] = season["r_per_7"] - mean_r_per_7
    season["def_adj"] = mean_ra_per_7 - season["ra_per_7"]
    season["net_adj"] = season["off_adj"] + season["def_adj"]

    # Step 2: Opponent lists from PURGED dataset (ONLY ranked opponents included)
    opponents = clean_df.groupby("team")["opponent"].apply(list).to_dict()

    # Step 3: Iterative SOS loop (centered every pass)
    net_adj = season.set_index("team")["net_adj"].to_dict()
    rating = dict(net_adj)

    for n in range(1, max_iters + 1):
        new_rating = {}
        for team, opp_list in opponents.items():
            if team not in rating:
                continue
            opp_ratings = [rating[o] for o in opp_list if o in rating]
            sos = np.mean(opp_ratings) if opp_ratings else 0.0
            new_rating[team] = net_adj[team] + sos

        mean_now = np.mean(list(new_rating.values()))
        new_rating = {t: r - mean_now for t, r in new_rating.items()}

        max_change = max(abs(new_rating[t] - rating[t]) for t in new_rating)
        rating = new_rating

        if max_change < tol:
            print(f"Converged after {n} iterations (largest change: {max_change:.6f})")
            break

    # Step 4: Map final rating & calculate exact SoS
    season["adj_rating"] = season["team"].map(rating)
    season["sos"] = season["adj_rating"] - season["net_adj"]

    season = season.sort_values("adj_rating", ascending=False).reset_index(drop=True)
    season["rank"] = range(1, len(season) + 1)

    return season


def save_ratings_json(final_df, output_path="ratings.json"):
    if final_df is None or final_df.empty:
        with open(output_path, "w") as f:
            json.dump([], f)
        print(f"Wrote empty list to {output_path}")
        return

    records = []
    for _, row in final_df.iterrows():
        records.append(
            {
                "rank": int(row["rank"]),
                "team": row["team"],
                "rating": round(float(row["adj_rating"]), 2),
                "games_played": int(row["games"]),
                "wins": int(row["wins"]),
                "losses": int(row["losses"]),
                "r_per_7": round(float(row["r_per_7"]), 2),
                "ra_per_7": round(float(row["ra_per_7"]), 2),
                "sos": round(float(row["sos"]), 2),
            }
        )

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
