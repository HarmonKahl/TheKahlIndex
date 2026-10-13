import json
import os
import numpy as np
import pandas as pd

# Load dataset directly from root directory
csv_file = "team_games_season.csv"

if not os.path.exists(csv_file) or os.stat(csv_file).st_size == 0:
    print(f"Warning: {csv_file} is empty or missing. Writing empty ratings.json.")
    with open("ratings.json", "w") as f:
        json.dump([], f)
    exit(0)

team_df = pd.read_csv(csv_file)

if team_df.empty:
    print("No game data found in CSV. Writing empty ratings.json.")
    with open("ratings.json", "w") as f:
        json.dump([], f)
    exit(0)

# Filter out placeholder slots
team_df = team_df[team_df["team"] != "TBA"]

# Clean and fix innings: convert missing, zero, or negative innings to regulation 7.0
team_df["innings_batted"] = pd.to_numeric(
    team_df["innings_batted"], errors="coerce"
)
team_df["innings_fielded"] = pd.to_numeric(
    team_df["innings_fielded"], errors="coerce"
)

team_df["innings_batted"] = team_df["innings_batted"].apply(
    lambda x: 7.0 if pd.isna(x) or x <= 0 else x
)
team_df["innings_fielded"] = team_df["innings_fielded"].apply(
    lambda x: 7.0 if pd.isna(x) or x <= 0 else x
)

# ---- Step 1: season totals -> raw runs/7, league-average-centered off/def ----
season = (
    team_df.groupby("team")
    .agg(
        games=("opponent", "count"),
        runs_for=("runs_for", "sum"),
        runs_against=("runs_against", "sum"),
        innings_batted=("innings_batted", "sum"),
        innings_fielded=("innings_fielded", "sum"),
    )
    .reset_index()
)

# Drop teams with fewer than min_games threshold (default to 1 so early-season runs don't crash)
min_games = 1
season = season[season["games"] >= min_games].reset_index(drop=True)

if season.empty:
    print("No valid team data after filtering. Writing empty ratings.json.")
    with open("ratings.json", "w") as f:
        json.dump([], f)
    exit(0)

season["r_per_7"] = season["runs_for"] / season["innings_batted"] * 7
season["ra_per_7"] = season["runs_against"] / season["innings_fielded"] * 7
season["diff"] = season["r_per_7"] - season["ra_per_7"]

mean_r_per_7 = season["r_per_7"].mean()
mean_ra_per_7 = season["ra_per_7"].mean()
season["off_adj"] = season["r_per_7"] - mean_r_per_7
season["def_adj"] = mean_ra_per_7 - season["ra_per_7"]
season["net_adj"] = season["off_adj"] + season["def_adj"]

# ---- Step 2: each team's opponents ----
opponents = team_df.groupby("team")["opponent"].apply(list).to_dict()

# ---- Step 3: iterative SOS loop ----
net_adj = season.set_index("team")["net_adj"].to_dict()
rating = dict(net_adj)

max_iters = 100
tol = 1e-6

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
        print(f"Converged after {n} iterations.")
        break

# ---- Step 4: final SOS + adj_rating ----
season["adj_rating"] = season["team"].map(rating)
season["sos"] = season["adj_rating"] - season["net_adj"]

season = season.sort_values("adj_rating", ascending=False).reset_index(
    drop=True
)
season["rank"] = range(1, len(season) + 1)

# Format table for output
export_cols = [
    "rank",
    "team",
    "games",
    "r_per_7",
    "ra_per_7",
    "off_adj",
    "def_adj",
    "net_adj",
    "sos",
    "adj_rating",
]
full_table = season[export_cols].round(2)

# Safety check for NaNs before export
numeric_cols = [c for c in export_cols if c != "team"]
full_table = full_table.dropna(subset=numeric_cols).reset_index(drop=True)

print(full_table.head(10).to_string(index=False))

# Export as JSON for website
ratings_data = full_table.to_dict(orient="records")
with open("ratings.json", "w") as f:
    json.dump(ratings_data, f, indent=2, allow_nan=False)

print("Successfully exported ratings.json!")
