import json
import numpy as np
import pandas as pd

# Load dataset directly from root directory
team_df = pd.read_csv("team_games_season.csv")

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

# Filter out teams with no innings to avoid division by zero
season = season[
    (season["innings_batted"] > 0) & (season["innings_fielded"] > 0)
].reset_index(drop=True)

season["r_per_7"] = season["runs_for"] / season["innings_batted"] * 7
season["ra_per_7"] = season["runs_against"] / season["innings_fielded"] * 7
season["diff"] = season["r_per_7"] - season["ra_per_7"]

mean_r_per_7 = season["r_per_7"].mean()
mean_ra_per_7 = season["ra_per_7"].mean()
season["off_adj"] = season["r_per_7"] - mean_r_per_7
season["def_adj"] = mean_ra_per_7 - season["ra_per_7"]
season["net_adj"] = season["off_adj"] + season["def_adj"]

# ---- Diagnostic: catch opponent-name mismatches ----
all_teams = set(season["team"])
all_opponents_mentioned = set(team_df["opponent"].unique())
unmatched = all_opponents_mentioned - all_teams
if unmatched:
    print(
        f"WARNING: {len(unmatched)} opponent name(s) don't match any team in the ratings table:"
    )
    print(sorted(unmatched)[:20])
else:
    print("All opponent names match a team in the ratings table.")

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
        opp_ratings = [rating[o] for o in opp_list if o in rating]
        sos = np.mean(opp_ratings) if opp_ratings else 0.0
        new_rating[team] = net_adj[team] + sos

    mean_now = np.mean(list(new_rating.values()))
    new_rating = {t: r - mean_now for t, r in new_rating.items()}

    max_change = max(abs(new_rating[t] - rating[t]) for t in rating)

    rating = new_rating
    if max_change < tol:
        print(f"Converged after {n} iterations.")
        break

# ---- Step 4: final SOS + adj_rating ----
final_sos = {}
for team, opp_list in opponents.items():
    opp_ratings = [rating[o] for o in opp_list if o in rating]
    final_sos[team] = np.mean(opp_ratings) if opp_ratings else 0.0

season["sos"] = season["team"].map(final_sos)
season["adj_rating"] = season["team"].map(rating)

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

print(full_table.head(10).to_string(index=False))

# Export as JSON for the web page
ratings_data = full_table.to_dict(orient="records")
with open("ratings.json", "w") as f:
    json.dump(ratings_data, f, indent=2)

print("Successfully exported ratings.json!")
