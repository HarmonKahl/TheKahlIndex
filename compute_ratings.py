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


def compute_kahl_index(
    team_df, min_games=20, max_iters=100, tol=1e-6
):
    # Drop placeholder/garbage team names (e.g. "TBA")
    team_df = team_df[team_df["team"] != "TBA"].copy()

    # Step 1: Season totals -> raw runs/7, league-average-centered off/def
    season = (
        team_df.groupby("team")
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

    season["r_per_7"] = (
        season["runs_for"] / season["innings_batted"] * 7
    )
    season["ra_per_7"] = (
        season["runs_against"] / season["innings_fielded"] * 7
    )
    season["diff"] = season["r_per_7"] - season["ra_per_7"]

    # Filter out teams with too few games
    too_few = season[season["games"] < min_games]
    if len(too_few):
        print(
            f"Dropping {len(too_few)} team(s) with fewer than {min_games} games."
        )
        season = season[season["games"] >= min_games].reset_index(
            drop=True
        )

    if len(season) == 0:
        print(f"No teams left after filtering to games >= {min_games}.")
        return pd.DataFrame()

    mean_r_per_7 = season["r_per_7"].mean()
    mean_ra_per_7 = season["ra_per_7"].mean()
    season["off_adj"] = season["r_per_7"] - mean_r_per_7
    season["def_adj"] = mean_ra_per_7 - season["ra_per_7"]
    season["net_adj"] = season["off_adj"] + season["def_adj"]

    # Step 2: Each team's opponents, ONE ENTRY PER GAME PLAYED
    opponents = (
        team_df.groupby("team")["opponent"].apply(list).to_dict()
    )

    # Step 3: Iterative SOS loop, recentered every pass so league mean stays pinned at 0
    net_adj = season.set_index("team")["net_adj"].to_dict()
    rating = dict(net_adj)

    for n in range(1, max_iters + 1):
        new_rating = {}
        for team, opp_list in opponents.items():
            if team not in rating:
                continue
            opp_ratings = [
                rating[o] for o in opp_list if o in rating
            ]
            sos = np.mean(opp_ratings) if opp_ratings else 0.0
            new_rating[team] = net_adj[team] + sos

        mean_now = np.mean(list(new_rating.values()))
        new_rating = {t: r - mean_now for t, r in new_rating.items()}

        max_change = max(
            abs(new_rating[t] - rating[t]) for t in new_rating
        )
        rating = new_rating

        if max_change < tol:
            print(
                f"Converged after {n} iterations (largest change: {max_change:.6f})"
            )
            break

    # Step 4: Map back rating and compute exact SOS by definition
    season["rating"] = season["team"].map(rating)
    season["sos"] = season["rating"] - season["net_adj"]

    # Sort descending and assign ranks
    season = season.sort_values("rating", ascending=False).reset_index(
        drop=True
    )
    season["rank"] = range(1, len(season) + 1)

    # Round numerical metrics
    season["rating"] = season["rating"].round(2)
    season["r_per_7"] = season["r_per_7"].round(2)
    season["ra_per_7"] = season["ra_per_7"].round(2)
    season["sos"] = season["sos"].round(2)

    return season


def save_ratings_json(final_df, output_path="ratings.json"):
    if final_df is None or final_df.empty:
        with open(output_path, "w") as f:
            json.dump([], f)
        print(f"Wrote empty list to {output_path}")
        return

    # Structure payload matching website/app specifications
    records = []
    for _, row in final_df.iterrows():
        records.append(
            {
                "rank": int(row["rank"]),
                "team": row["team"],
                "rating": float(row["rating"]),
                "games_played": int(row["games"]),
                "wins": int(row["wins"]),
                "losses": int(row["losses"]),
                "r_per_7": float(row["r_per_7"]),
                "ra_per_7": float(row["ra_per_7"]),
                "sos": float(row["sos"]),
            }
        )

    with open(output_path, "w") as f:
        json.dump(records, f, indent=2)

    print(
        f"Successfully computed ratings for {len(records)} teams and saved to {output_path}."
    )


if __name__ == "__main__":
    df_games = load_data("team_games_season.csv")
    if df_games is not None:
        final_ratings = compute_kahl_index(df_games, min_games=20)
        save_ratings_json(final_ratings, "ratings.json")
    else:
        save_ratings_json(None, "ratings.json")
