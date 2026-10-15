import json
import os
import re
import sys
import numpy as np
import pandas as pd


CONFERENCE_MAP = {
    "albany": "America East Conference", "binghamton": "America East Conference", "bryant": "America East Conference",
    "maine": "America East Conference", "umbc": "America East Conference", "umass lowell": "America East Conference",
    "charlotte": "American Athletic Conference", "east carolina": "American Athletic Conference", "florida atlantic": "American Athletic Conference",
    "memphis": "American Athletic Conference", "north texas": "American Athletic Conference", "south florida": "American Athletic Conference",
    "temple": "American Athletic Conference", "tulsa": "American Athletic Conference", "uab": "American Athletic Conference",
    "utsa": "American Athletic Conference", "wichita state": "American Athletic Conference", "dayton": "Atlantic 10 Conference",
    "fordham": "Atlantic 10 Conference", "george mason": "Atlantic 10 Conference", "george washington": "Atlantic 10 Conference",
    "la salle": "Atlantic 10 Conference", "rhode island": "Atlantic 10 Conference", "saint joseph's": "Atlantic 10 Conference",
    "saint louis": "Atlantic 10 Conference", "st. bonaventure": "Atlantic 10 Conference", "boston college": "Atlantic Coast Conference",
    "california": "Atlantic Coast Conference", "clemson": "Atlantic Coast Conference", "duke": "Atlantic Coast Conference",
    "florida state": "Atlantic Coast Conference", "georgia tech": "Atlantic Coast Conference", "louisville": "Atlantic Coast Conference",
    "north carolina": "Atlantic Coast Conference", "nc state": "Atlantic Coast Conference", "notre dame": "Atlantic Coast Conference",
    "pittsburgh": "Atlantic Coast Conference", "smu": "Atlantic Coast Conference", "stanford": "Atlantic Coast Conference",
    "syracuse": "Atlantic Coast Conference", "virginia": "Atlantic Coast Conference", "virginia tech": "Atlantic Coast Conference",
    "austin peay": "ASUN Conference", "bellarmine": "ASUN Conference", "central arkansas": "ASUN Conference",
    "eastern kentucky": "ASUN Conference", "florida gulf coast": "ASUN Conference", "jacksonville": "ASUN Conference",
    "kennesaw state": "ASUN Conference", "lipscomb": "ASUN Conference", "north alabama": "ASUN Conference",
    "north florida": "ASUN Conference", "stetson": "ASUN Conference", "west georgia": "ASUN Conference",
    "arizona": "Big 12 Conference", "arizona state": "Big 12 Conference", "baylor": "Big 12 Conference",
    "byu": "Big 12 Conference", "houston": "Big 12 Conference", "iowa state": "Big 12 Conference",
    "kansas": "Big 12 Conference", "oklahoma state": "Big 12 Conference", "texas tech": "Big 12 Conference",
    "ucf": "Big 12 Conference", "utah": "Big 12 Conference", "butler": "Big East Conference",
    "creighton": "Big East Conference", "depaul": "Big East Conference", "georgetown": "Big East Conference",
    "providence": "Big East Conference", "seton hall": "Big East Conference", "st. john's": "Big East Conference",
    "villanova": "Big East Conference", "uconn": "Big East Conference", "idaho state": "Big Sky Conference",
    "montana": "Big Sky Conference", "northern colorado": "Big Sky Conference", "portland state": "Big Sky Conference",
    "sacramento state": "Big Sky Conference", "weber state": "Big Sky Conference", "charleston southern": "Big South Conference",
    "gardner-webb": "Big South Conference", "longwood": "Big South Conference", "presbyterian": "Big South Conference",
    "radford": "Big South Conference", "usc upstate": "Big South Conference", "winthrop": "Big South Conference",
    "illinois": "Big Ten Conference", "indiana": "Big Ten Conference", "iowa": "Big Ten Conference",
    "maryland": "Big Ten Conference", "michigan": "Big Ten Conference", "michigan state": "Big Ten Conference",
    "minnesota": "Big Ten Conference", "nebraska": "Big Ten Conference", "northwestern": "Big Ten Conference",
    "ohio state": "Big Ten Conference", "oregon": "Big Ten Conference", "penn state": "Big Ten Conference",
    "purdue": "Big Ten Conference", "rutgers": "Big Ten Conference", "ucla": "Big Ten Conference",
    "washington": "Big Ten Conference", "wisconsin": "Big Ten Conference", "cal poly": "Big West Conference",
    "cal state fullerton": "Big West Conference", "cal state bakersfield": "Big West Conference", "cal state northridge": "Big West Conference",
    "hawaii": "Big West Conference", "long beach state": "Big West Conference", "uc davis": "Big West Conference",
    "uc riverside": "Big West Conference", "uc santa barbara": "Big West Conference", "campbell": "Coastal Athletic Association",
    "charleston": "Coastal Athletic Association", "delaware": "Coastal Athletic Association", "drexel": "Coastal Athletic Association",
    "elon": "Coastal Athletic Association", "hofstra": "Coastal Athletic Association", "monmouth": "Coastal Athletic Association",
    "north carolina a&t": "Coastal Athletic Association", "uncw": "Coastal Athletic Association", "stony brook": "Coastal Athletic Association",
    "towson": "Coastal Athletic Association", "fiu": "Conference USA", "jacksonville state": "Conference USA",
    "liberty": "Conference USA", "louisiana tech": "Conference USA", "middle tennessee": "Conference USA",
    "missouri state": "Conference USA", "new mexico state": "Conference USA", "sam houston": "Conference USA",
    "utep": "Conference USA", "western kentucky": "Conference USA", "green bay": "Horizon League",
    "iupui (iu indy)": "Horizon League", "northern kentucky": "Horizon League", "oakland": "Horizon League",
    "robert morris": "Horizon League", "youngstown state": "Horizon League", "brown": "Ivy League",
    "columbia": "Ivy League", "cornell": "Ivy League", "dartmouth": "Ivy League",
    "harvard": "Ivy League", "penn": "Ivy League", "princeton": "Ivy League",
    "yale": "Ivy League", "canisius": "Metro Atlantic Athletic Conference", "fairfield": "Metro Atlantic Athletic Conference",
    "iona": "Metro Atlantic Athletic Conference", "manhattan": "Metro Atlantic Athletic Conference", "marist": "Metro Atlantic Athletic Conference",
    "merrimack": "Metro Atlantic Athletic Conference", "niagara": "Metro Atlantic Athletic Conference", "quinnipiac": "Metro Atlantic Athletic Conference",
    "rider": "Metro Atlantic Athletic Conference", "sacred heart": "Metro Atlantic Athletic Conference", "saint peter's": "Metro Atlantic Athletic Conference",
    "siena": "Metro Atlantic Athletic Conference", "akron": "Mid-American Conference", "ball state": "Mid-American Conference",
    "bowling green": "Mid-American Conference", "buffalo": "Mid-American Conference", "central michigan": "Mid-American Conference",
    "eastern michigan": "Mid-American Conference", "kent state": "Mid-American Conference", "miami (oh)": "Mid-American Conference",
    "northern illinois": "Mid-American Conference", "ohio": "Mid-American Conference", "toledo": "Mid-American Conference",
    "umass": "Mid-American Conference", "western michigan": "Mid-American Conference", "coppin state": "Mid-Eastern Athletic Conference",
    "delaware state": "Mid-Eastern Athletic Conference", "howard": "Mid-Eastern Athletic Conference", "maryland eastern shore": "Mid-Eastern Athletic Conference",
    "morgan state": "Mid-Eastern Athletic Conference", "norfolk state": "Mid-Eastern Athletic Conference", "north carolina central": "Mid-Eastern Athletic Conference",
    "south carolina state": "Mid-Eastern Athletic Conference", "belmont": "Missouri Valley Conference", "bradley": "Missouri Valley Conference",
    "drake": "Missouri Valley Conference", "evansville": "Missouri Valley Conference", "illinois state": "Missouri Valley Conference",
    "indiana state": "Missouri Valley Conference", "northern iowa": "Missouri Valley Conference", "southern illinois": "Missouri Valley Conference",
    "uic": "Missouri Valley Conference", "valparaiso": "Missouri Valley Conference", "boise state": "Mountain West Conference",
    "colorado state": "Mountain West Conference", "fresno state": "Mountain West Conference", "grand canyon": "Mountain West Conference",
    "nevada": "Mountain West Conference", "new mexico": "Mountain West Conference", "san diego state": "Mountain West Conference",
    "san jose state": "Mountain West Conference", "unlv": "Mountain West Conference", "utah state": "Mountain West Conference",
    "central connecticut state": "Northeast Conference", "fairleigh dickinson": "Northeast Conference", "le moyne": "Northeast Conference",
    "liu": "Northeast Conference", "mercyhurst": "Northeast Conference", "new haven": "Northeast Conference",
    "saint francis (pa)": "Northeast Conference", "stonehill": "Northeast Conference", "wagner": "Northeast Conference",
    "eastern illinois": "Ohio Valley Conference", "lindenwood": "Ohio Valley Conference", "morehead state": "Ohio Valley Conference",
    "se missouri state": "Ohio Valley Conference", "siu edwardsville": "Ohio Valley Conference", "southern indiana": "Ohio Valley Conference",
    "tennessee state": "Ohio Valley Conference", "tennessee tech": "Ohio Valley Conference", "ut martin": "Ohio Valley Conference",
    "western illinois": "Ohio Valley Conference", "army": "Patriot League", "boston university": "Patriot League",
    "bucknell": "Patriot League", "colgate": "Patriot League", "holy cross": "Patriot League",
    "lafayette": "Patriot League", "lehigh": "Patriot League", "alabama": "SEC",
    "arkansas": "SEC", "auburn": "SEC", "florida": "SEC",
    "georgia": "SEC", "kentucky": "SEC", "lsu": "SEC",
    "mississippi state": "SEC", "missouri": "SEC", "oklahoma": "SEC",
    "ole miss": "SEC", "south carolina": "SEC", "tennessee": "SEC",
    "texas": "SEC", "texas a&m": "SEC", "vanderbilt": "SEC",
    "chatanooga": "Southern Conference", "etsu": "Southern Conference", "furman": "Southern Conference",
    "mercer": "Southern Conference", "samford": "Southern Conference", "uncg": "Southern Conference",
    "western carolina": "Southern Conference", "houston christian": "Southland Conference", "incarnate word": "Southland Conference",
    "lamar": "Southland Conference", "mcneese": "Southland Conference", "nicholls": "Southland Conference",
    "northwestern state": "Southland Conference", "southeastern louisiana": "Southland Conference", "stephen f. austin": "Southland Conference",
    "texas a&m-commerce": "Southland Conference", "texas a&m-corpus christi": "Southland Conference", "alabama a&m": "Southwestern Athletic Conference",
    "alabama state": "Southwestern Athletic Conference", "alcorn state": "Southwestern Athletic Conference", "arkansas-pine bluff": "Southwestern Athletic Conference",
    "bethune-cookman": "Southwestern Athletic Conference", "florida a&m": "Southwestern Athletic Conference", "grambling state": "Southwestern Athletic Conference",
    "jackson state": "Southwestern Athletic Conference", "mississippi valley state": "Southwestern Athletic Conference", "prairie view a&m": "Southwestern Athletic Conference",
    "southern": "Southwestern Athletic Conference", "texas southern": "Southwestern Athletic Conference", "kansas city": "Summit League",
    "north dakota": "Summit League", "north dakota state": "Summit League", "omaha": "Summit League",
    "south dakota": "Summit League", "south dakota state": "Summit League", "st. thomas": "Summit League",
    "appalachian state": "Sun Belt Conference", "coastal carolina": "Sun Belt Conference", "georgia southern": "Sun Belt Conference",
    "georgia state": "Sun Belt Conference", "james madison": "Sun Belt Conference", "louisiana": "Sun Belt Conference",
    "marshall": "Sun Belt Conference", "old dominion": "Sun Belt Conference", "south alabama": "Sun Belt Conference",
    "southern miss": "Sun Belt Conference", "texas state": "Sun Belt Conference", "troy": "Sun Belt Conference",
    "ulm": "Sun Belt Conference", "loyola marymount": "West Coast Conference", "pacific": "West Coast Conference",
    "saint mary's": "West Coast Conference", "san diego": "West Coast Conference", "santa clara": "West Coast Conference",
    "seattle u": "West Coast Conference", "abilene christian": "Western Athletic Conference", "california baptist": "Western Athletic Conference",
    "southern utah": "Western Athletic Conference", "tarleton state": "Western Athletic Conference", "ut arlington": "Western Athletic Conference",
    "utah tech": "Western Athletic Conference", "utah valley": "Western Athletic Conference"
}


def get_conference(team_name):
    clean = str(team_name).lower().strip()
    clean_no_dot = clean.replace(".", "")
    return CONFERENCE_MAP.get(clean, CONFERENCE_MAP.get(clean_no_dot, "Independent / Other"))


def load_data(team_csv_path="team_games_season.csv"):
    if not os.path.exists(team_csv_path) or os.stat(team_csv_path).st_size == 0:
        print(f"Warning: {team_csv_path} is empty or missing. Writing empty ratings.json.")
        return None

    df = pd.read_csv(team_csv_path)
    if df.empty:
        return None
    return df


def compute_kahl_index(team_df, min_games=20, max_iters=100, tol=1e-6):
    team_df = team_df[(team_df["team"] != "TBA") & (team_df["opponent"] != "TBA")].copy()

    raw_counts = team_df.groupby("team")["opponent"].count()
    valid_teams = set(raw_counts[raw_counts >= min_games].index)

    clean_df = team_df[
        team_df["team"].isin(valid_teams) & team_df["opponent"].isin(valid_teams)
    ].copy()

    clean_counts = clean_df.groupby("team")["opponent"].count()
    final_valid_teams = set(clean_counts[clean_counts >= min_games].index)

    clean_df = clean_df[
        clean_df["team"].isin(final_valid_teams) & clean_df["opponent"].isin(final_valid_teams)
    ].copy()

    if clean_df.empty:
        print("No teams remaining after filtering games against non-ranked teams.")
        return pd.DataFrame()

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

    opponents = clean_df.groupby("team")["opponent"].apply(list).to_dict()

    net_adj = season.set_index("team")["net_adj"].to_dict()
    raa = dict(net_adj)

    for n in range(1, max_iters + 1):
        new_raa = {}
        for team, opp_list in opponents.items():
            if team not in raa:
                continue
            opp_raa = [raa[o] for o in opp_list if o in raa]
            sos = np.mean(opp_raa) if opp_raa else 0.0
            new_raa[team] = net_adj[team] + sos

        mean_now = np.mean(list(new_raa.values()))
        new_raa = {t: r - mean_now for t, r in new_raa.items()}

        max_change = max(abs(new_raa[t] - raa[t]) for t in new_raa)
        raa = new_raa

        if max_change < tol:
            print(f"Converged after {n} iterations (largest change: {max_change:.6f})")
            break

    season["raa"] = season["team"].map(raa)
    season["sos"] = season["raa"] - season["net_adj"]

    season = season.sort_values("raa", ascending=False).reset_index(drop=True)
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
        team_name = str(row["team"])
        records.append(
            {
                "rank": int(row["rank"]),
                "team": team_name,
                "conference": get_conference(team_name),
                "raa": round(float(row["raa"]), 2),
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
