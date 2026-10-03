import pandas as pd
import numpy as np

team_df = pd.read_csv("tki_2026/team_games_season.csv")

# ---- Step 1: season totals -> raw runs/7, league-average-centered off/def ----
season = (team_df.groupby("team")
            .agg(games=("opponent", "count"),
                 runs_for=("runs_for", "sum"),
                 runs_against=("runs_against", "sum"),
                 innings_batted=("innings_batted", "sum"),
                 innings_fielded=("innings_fielded", "sum"))
            .reset_index())

season["r_per_7"] = season["runs_for"] / season["innings_batted"] * 7
season["ra_per_7"] = season["runs_against"] / season["innings_fielded"] * 7
season["diff"] = season["r_per_7"] - season["ra_per_7"]

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
    print(f"WARNING: {len(unmatched)} opponent name(s) don't match any team in the ratings "
          f"table (these games are silently excluded from that opponent's SOS):")
    print(sorted(unmatched)[:20])
else:
    print("All opponent names match a team in the ratings table.")

# ---- Step 2: each team's opponents, ONE ENTRY PER GAME PLAYED ----
# (a 3-game conference series means that opponent appears 3 times — SOS
#  reflects the actual slate played, not just the unique set of teams faced)
opponents = team_df.groupby("team")["opponent"].apply(list).to_dict()

# ---- Step 3: iterative SOS loop, recentered every pass so the league mean
#      stays pinned at 0 (without this, the whole scale drifts) ----
net_adj = season.set_index("team")["net_adj"].to_dict()
rating = dict(net_adj)  # iteration 0 guess = net_adj

max_iters = 100
tol = 1e-6
history = []

for n in range(1, max_iters + 1):
    new_rating = {}
    for team, opp_list in opponents.items():
        opp_ratings = [rating[o] for o in opp_list if o in rating]
        sos = np.mean(opp_ratings) if opp_ratings else 0.0
        new_rating[team] = net_adj[team] + sos

    mean_now = np.mean(list(new_rating.values()))
    new_rating = {t: r - mean_now for t, r in new_rating.items()}  # recenter

    max_change = max(abs(new_rating[t] - rating[t]) for t in rating)
    history.append({"iteration": n, "mean_rating": np.mean(list(new_rating.values())),
                     "max_change": max_change})

    rating = new_rating
    if max_change < tol:
        print(f"Converged after {n} iterations (largest remaining change: {max_change:.6f})")
        break
else:
    print(f"Did NOT fully converge after {max_iters} iterations "
          f"(largest remaining change: {max_change:.6f}) -- consider raising max_iters")

# ---- Step 4: final SOS (opponents' CONVERGED ratings) + adj_rating ----
final_sos = {}
for team, opp_list in opponents.items():
    opp_ratings = [rating[o] for o in opp_list if o in rating]
    final_sos[team] = np.mean(opp_ratings) if opp_ratings else 0.0

season["sos"] = season["team"].map(final_sos)
season["adj_rating"] = season["team"].map(rating)

season = season.sort_values("adj_rating", ascending=False).reset_index(drop=True)
season["rank"] = range(1, len(season) + 1)

full_table = season[["rank", "team", "games", "r_per_7", "ra_per_7",
                      "off_adj", "def_adj", "net_adj", "sos", "adj_rating"]].round(2)
print(full_table.to_string(index=False))
print(f"\nFinal league mean rating: {season['adj_rating'].mean():.8f}  (should be ~0)")
