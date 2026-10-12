import json

import numpy as np
import pandas as pd

team_df = pd.read_csv("team_games_season.csv")

# Drop placeholder/garbage team names (e.g. "TBA" scheduling slots with 0
# recorded innings) before anything else runs, so a divide-by-zero can't
# poison the whole system.
team_df = team_df[team_df["team"] != "TBA"]

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

season["r_per_7"] = season["runs_for"] / season["innings_batted"] * 7
season["ra_per_7"] = season["runs_against"] / season["innings_fielded"] * 7
season["diff"] = season["r_per_7"] - season["ra_per_7"]

# Drop teams with too small a sample to trust. NOTE: this is tuned for a
# full-season dataset. Early in a real season (few games played league-wide),
# this threshold may need to be lowered or temporarily skipped, since most
# teams won't have 20 games yet -- revisit this once daily updates are live.
min_games = 20
too_few = season[season["games"] < min_games]
if len(too_few):
    print(f"Dropping {len(too_few)} team(s) with fewer than {min_games} games:")
    print(too_few[["team", "games"]].to_string(index=False))
    season = season[season["games"] >= min_games].reset_index(drop=True)

if len(season) == 0:
    raise ValueError(
        f"No teams left after filtering to games >= {min_games} -- "
        f"check that min_games isn't set higher than your data allows "
        f"(e.g. early in a season, or a partial pull)."
    )

mean_r_per_7 = season["r_per_7"].mean()
mean_ra_per_7 = season["ra_per_7"].mean()
season["off_adj"] = season["r_per_7"] - mean_r_per_7
season["def_adj"] = mean_ra_per_7 - season["ra_per_7"]
season["net_adj"] = season["off_adj"] + season["def_adj"]

# ---- Diagnostic: catch opponent-name mismatches before they silently bias SOS ----
all_teams = set(season["team"])
all_opponents_mentioned = set(team_df["opponent"].unique())
unmatched = all_opponents_mentioned - all_teams
if unmatched:
    print(
        f"WARNING: {len(unmatched)} opponent name(s) don't match any team in the "
        f"ratings table (these games are silently excluded from that opponent's SOS):"
    )
    print(sorted(unmatched)[:20])
else:
    print("All opponent names match a team in the ratings table.")

# ---- Step 2: each team's opponents, ONE ENTRY PER GAME PLAYED ----
opponents = team_df.groupby("team")["opponent"].apply(list).to_dict()

# ---- Step 3: iterative SOS loop, recentered every pass so the league mean
#      stays pinned at 0 ----
net_adj = season.set_index("team")["net_adj"].to_dict()
rating = dict(net_adj)

max_iters = 100
tol = 1e-6

for n in range(1, max_iters + 1):
    new_rating = {}
    for team, opp_list in opponents.items():
        if team not in rating:
            continue  # this team itself was dropped (too few games / TBA)
        opp_ratings = [rating[o] for o in opp_list if o in rating]
        sos = np.mean(opp_ratings) if opp_ratings else 0.0
        new_rating[team] = net_adj[team] + sos

    mean_now = np.mean(list(new_rating.values()))
    new_rating = {t: r - mean_now for t, r in new_rating.items()}

    max_change = max(abs(new_rating[t] - rating[t]) for t in new_rating)
    rating = new_rating
    if max_change < tol:
        print(f"Converged after {n} iterations (largest remaining change: {max_change:.6f})")
        break
else:
    print(
        f"Did NOT fully converge after {max_iters} iterations "
        f"(largest remaining change: {max_change:.6f}) -- consider raising max_iters"
    )

# ---- Step 4: adj_rating + sos ----
# sos is defined as exactly "how much did schedule move your rating" --
# adj_rating minus net_adj -- rather than a separately-recomputed average of
# opponents' final ratings. The two are mathematically close but not
# identical on an uneven schedule graph (the loop's internal recentering
# constant isn't guaranteed to be zero), so defining sos this way guarantees
# net_adj + sos == adj_rating exactly, always, by construction.
season["adj_rating"] = season["team"].map(rating)
season["sos"] = season["adj_rating"] - season["net_adj"]

season = season.sort_values("adj_rating", ascending=False).reset_index(drop=True)
season["rank"] = range(1, len(season) + 1)

export_cols = [
    "rank", "team", "games", "r_per_7", "ra_per_7",
    "off_adj", "def_adj", "net_adj", "sos", "adj_rating",
]
full_table = season[export_cols].round(2)

# Safety net: a NaN in any numeric column would get written as a literal
# `NaN` token by json.dump, which is NOT valid JSON -- browsers' fetch().json()
# throws a SyntaxError on it, silently breaking the website with no visible
# error. Drop any such rows (there shouldn't be any after the filters above)
# and fail loudly (allow_nan=False) if one somehow still slips through,
# rather than silently shipping broken JSON to the site.
numeric_cols = [c for c in export_cols if c not in ("team",)]
bad_rows = full_table[full_table[numeric_cols].isna().any(axis=1)]
if len(bad_rows):
    print(f"WARNING: dropping {len(bad_rows)} row(s) with NaN values before export:")
    print(bad_rows.to_string(index=False))
    full_table = full_table.dropna(subset=numeric_cols).reset_index(drop=True)

print(full_table.head(10).to_string(index=False))
print(f"\nFinal league mean rating: {season['adj_rating'].mean():.8f}  (should be ~0)")
print(f"Teams in final ratings: {len(full_table)}")

ratings_data = full_table.to_dict(orient="records")
with open("ratings.json", "w") as f:
    json.dump(ratings_data, f, indent=2, allow_nan=False)

print("Successfully exported ratings.json!")
