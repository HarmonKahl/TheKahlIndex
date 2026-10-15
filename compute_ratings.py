import json
import os
import re
import sys
import numpy as np
import pandas as pd

# 1. Exact Conference List provided by User
RAW_CONFERENCES = [
    ("America East Conference", "Albany"),
    ("America East Conference", "Binghamton"),
    ("America East Conference", "Bryant"),
    ("America East Conference", "Maine"),
    ("America East Conference", "UMBC"),
    ("America East Conference", "UMass Lowell"),
    ("American Athletic Conference", "Charlotte"),
    ("American Athletic Conference", "East Carolina"),
    ("American Athletic Conference", "Florida Atlantic"),
    ("American Athletic Conference", "Memphis"),
    ("American Athletic Conference", "North Texas"),
    ("American Athletic Conference", "South Florida"),
    ("American Athletic Conference", "Temple"),
    ("American Athletic Conference", "Tulsa"),
    ("American Athletic Conference", "UAB"),
    ("American Athletic Conference", "UTSA"),
    ("American Athletic Conference", "Wichita State"),
    ("Atlantic 10 Conference", "Dayton"),
    ("Atlantic 10 Conference", "Fordham"),
    ("Atlantic 10 Conference", "George Mason"),
    ("Atlantic 10 Conference", "George Washington"),
    ("Atlantic 10 Conference", "La Salle"),
    ("Atlantic 10 Conference", "Rhode Island"),
    ("Atlantic 10 Conference", "Saint Joseph's"),
    ("Atlantic 10 Conference", "Saint Louis"),
    ("Atlantic 10 Conference", "St. Bonaventure"),
    ("Atlantic Coast Conference", "Boston College"),
    ("Atlantic Coast Conference", "California"),
    ("Atlantic Coast Conference", "Clemson"),
    ("Atlantic Coast Conference", "Duke"),
    ("Atlantic Coast Conference", "Florida State"),
    ("Atlantic Coast Conference", "Georgia Tech"),
    ("Atlantic Coast Conference", "Louisville"),
    ("Atlantic Coast Conference", "North Carolina"),
    ("Atlantic Coast Conference", "NC State"),
    ("Atlantic Coast Conference", "Notre Dame"),
    ("Atlantic Coast Conference", "Pittsburgh"),
    ("Atlantic Coast Conference", "SMU"),
    ("Atlantic Coast Conference", "Stanford"),
    ("Atlantic Coast Conference", "Syracuse"),
    ("Atlantic Coast Conference", "Virginia"),
    ("Atlantic Coast Conference", "Virginia Tech"),
    ("ASUN Conference", "Austin Peay"),
    ("ASUN Conference", "Bellarmine"),
    ("ASUN Conference", "Central Arkansas"),
    ("ASUN Conference", "Eastern Kentucky"),
    ("ASUN Conference", "Florida Gulf Coast"),
    ("ASUN Conference", "Jacksonville"),
    ("ASUN Conference", "Kennesaw State"),
    ("ASUN Conference", "Lipscomb"),
    ("ASUN Conference", "North Alabama"),
    ("ASUN Conference", "North Florida"),
    ("ASUN Conference", "Stetson"),
    ("ASUN Conference", "West Georgia"),
    ("Big 12 Conference", "Arizona"),
    ("Big 12 Conference", "Arizona State"),
    ("Big 12 Conference", "Baylor"),
    ("Big 12 Conference", "BYU"),
    ("Big 12 Conference", "Houston"),
    ("Big 12 Conference", "Iowa State"),
    ("Big 12 Conference", "Kansas"),
    ("Big 12 Conference", "Oklahoma State"),
    ("Big 12 Conference", "Texas Tech"),
    ("Big 12 Conference", "UCF"),
    ("Big 12 Conference", "Utah"),
    ("Big East Conference", "Butler"),
    ("Big East Conference", "Creighton"),
    ("Big East Conference", "DePaul"),
    ("Big East Conference", "Georgetown"),
    ("Big East Conference", "Providence"),
    ("Big East Conference", "Seton Hall"),
    ("Big East Conference", "St. John's"),
    ("Big East Conference", "Villanova"),
    ("Big East Conference", "UConn"),
    ("Big Sky Conference", "Idaho State"),
    ("Big Sky Conference", "Montana"),
    ("Big Sky Conference", "Northern Colorado"),
    ("Big Sky Conference", "Portland State"),
    ("Big Sky Conference", "Sacramento State"),
    ("Big Sky Conference", "Weber State"),
    ("Big South Conference", "Charleston Southern"),
    ("Big South Conference", "Gardner-Webb"),
    ("Big South Conference", "Longwood"),
    ("Big South Conference", "Presbyterian"),
    ("Big South Conference", "Radford"),
    ("Big South Conference", "USC Upstate"),
    ("Big South Conference", "Winthrop"),
    ("Big Ten Conference", "Illinois"),
    ("Big Ten Conference", "Indiana"),
    ("Big Ten Conference", "Iowa"),
    ("Big Ten Conference", "Maryland"),
    ("Big Ten Conference", "Michigan"),
    ("Big Ten Conference", "Michigan State"),
    ("Big Ten Conference", "Minnesota"),
    ("Big Ten Conference", "Nebraska"),
    ("Big Ten Conference", "Northwestern"),
    ("Big Ten Conference", "Ohio State"),
    ("Big Ten Conference", "Oregon"),
    ("Big Ten Conference", "Penn State"),
    ("Big Ten Conference", "Purdue"),
    ("Big Ten Conference", "Rutgers"),
    ("Big Ten Conference", "UCLA"),
    ("Big Ten Conference", "Washington"),
    ("Big Ten Conference", "Wisconsin"),
    ("Big West Conference", "Cal Poly"),
    ("Big West Conference", "Cal State Fullerton"),
    ("Big West Conference", "Cal State Bakersfield"),
    ("Big West Conference", "Cal State Northridge"),
    ("Big West Conference", "Hawaii"),
    ("Big West Conference", "Long Beach State"),
    ("Big West Conference", "UC Davis"),
    ("Big West Conference", "UC Riverside"),
    ("Big West Conference", "UC Santa Barbara"),
    ("Coastal Athletic Association", "Campbell"),
    ("Coastal Athletic Association", "Charleston"),
    ("Coastal Athletic Association", "Delaware"),
    ("Coastal Athletic Association", "Drexel"),
    ("Coastal Athletic Association", "Elon"),
    ("Coastal Athletic Association", "Hofstra"),
    ("Coastal Athletic Association", "Monmouth"),
    ("Coastal Athletic Association", "North Carolina A&T"),
    ("Coastal Athletic Association", "UNCW"),
    ("Coastal Athletic Association", "Stony Brook"),
    ("Coastal Athletic Association", "Towson"),
    ("Conference USA", "FIU"),
    ("Conference USA", "Jacksonville State"),
    ("Conference USA", "Liberty"),
    ("Conference USA", "Louisiana Tech"),
    ("Conference USA", "Middle Tennessee"),
    ("Conference USA", "Missouri State"),
    ("Conference USA", "New Mexico State"),
    ("Conference USA", "Sam Houston"),
    ("Conference USA", "UTEP"),
    ("Conference USA", "Western Kentucky"),
    ("Horizon League", "Green Bay"),
    ("Horizon League", "IUPUI (IU Indy)"),
    ("Horizon League", "Northern Kentucky"),
    ("Horizon League", "Oakland"),
    ("Horizon League", "Robert Morris"),
    ("Horizon League", "Youngstown State"),
    ("Ivy League", "Brown"),
    ("Ivy League", "Columbia"),
    ("Ivy League", "Cornell"),
    ("Ivy League", "Dartmouth"),
    ("Ivy League", "Harvard"),
    ("Ivy League", "Penn"),
    ("Ivy League", "Princeton"),
    ("Ivy League", "Yale"),
    ("Metro Atlantic Athletic Conference", "Canisius"),
    ("Metro Atlantic Athletic Conference", "Fairfield"),
    ("Metro Atlantic Athletic Conference", "Iona"),
    ("Metro Atlantic Athletic Conference", "Manhattan"),
    ("Metro Atlantic Athletic Conference", "Marist"),
    ("Metro Atlantic Athletic Conference", "Merrimack"),
    ("Metro Atlantic Athletic Conference", "Niagara"),
    ("Metro Atlantic Athletic Conference", "Quinnipiac"),
    ("Metro Atlantic Athletic Conference", "Rider"),
    ("Metro Atlantic Athletic Conference", "Sacred Heart"),
    ("Metro Atlantic Athletic Conference", "Saint Peter's"),
    ("Metro Atlantic Athletic Conference", "Siena"),
    ("Mid-American Conference", "Akron"),
    ("Mid-American Conference", "Ball State"),
    ("Mid-American Conference", "Bowling Green"),
    ("Mid-American Conference", "Buffalo"),
    ("Mid-American Conference", "Central Michigan"),
    ("Mid-American Conference", "Eastern Michigan"),
    ("Mid-American Conference", "Kent State"),
    ("Mid-American Conference", "Miami (OH)"),
    ("Mid-American Conference", "Northern Illinois"),
    ("Mid-American Conference", "Ohio"),
    ("Mid-American Conference", "Toledo"),
    ("Mid-American Conference", "UMass"),
    ("Mid-American Conference", "Western Michigan"),
    ("Mid-Eastern Athletic Conference", "Coppin State"),
    ("Mid-Eastern Athletic Conference", "Delaware State"),
    ("Mid-Eastern Athletic Conference", "Howard"),
    ("Mid-Eastern Athletic Conference", "Maryland Eastern Shore"),
    ("Mid-Eastern Athletic Conference", "Morgan State"),
    ("Mid-Eastern Athletic Conference", "Norfolk State"),
    ("Mid-Eastern Athletic Conference", "North Carolina Central"),
    ("Mid-Eastern Athletic Conference", "South Carolina State"),
    ("Missouri Valley Conference", "Belmont"),
    ("Missouri Valley Conference", "Bradley"),
    ("Missouri Valley Conference", "Drake"),
    ("Missouri Valley Conference", "Evansville"),
    ("Missouri Valley Conference", "Illinois State"),
    ("Missouri Valley Conference", "Indiana State"),
    ("Missouri Valley Conference", "Northern Iowa"),
    ("Missouri Valley Conference", "Southern Illinois"),
    ("Missouri Valley Conference", "UIC"),
    ("Missouri Valley Conference", "Valparaiso"),
    ("Mountain West Conference", "Boise State"),
    ("Mountain West Conference", "Colorado State"),
    ("Mountain West Conference", "Fresno State"),
    ("Mountain West Conference", "Grand Canyon"),
    ("Mountain West Conference", "Nevada"),
    ("Mountain West Conference", "New Mexico"),
    ("Mountain West Conference", "San Diego State"),
    ("Mountain West Conference", "San Jose State"),
    ("Mountain West Conference", "UNLV"),
    ("Mountain West Conference", "Utah State"),
    ("Northeast Conference", "Central Connecticut State"),
    ("Northeast Conference", "Fairleigh Dickinson"),
    ("Northeast Conference", "Le Moyne"),
    ("Northeast Conference", "LIU"),
    ("Northeast Conference", "Mercyhurst"),
    ("Northeast Conference", "New Haven"),
    ("Northeast Conference", "Saint Francis (PA)"),
    ("Northeast Conference", "Stonehill"),
    ("Northeast Conference", "Wagner"),
    ("Ohio Valley Conference", "Eastern Illinois"),
    ("Ohio Valley Conference", "Lindenwood"),
    ("Ohio Valley Conference", "Morehead State"),
    ("Ohio Valley Conference", "SE Missouri State"),
    ("Ohio Valley Conference", "SIU Edwardsville"),
    ("Ohio Valley Conference", "Southern Indiana"),
    ("Ohio Valley Conference", "Tennessee State"),
    ("Ohio Valley Conference", "Tennessee Tech"),
    ("Ohio Valley Conference", "UT Martin"),
    ("Ohio Valley Conference", "Western Illinois"),
    ("Patriot League", "Army"),
    ("Patriot League", "Boston University"),
    ("Patriot League", "Bucknell"),
    ("Patriot League", "Colgate"),
    ("Patriot League", "Holy Cross"),
    ("Patriot League", "Lafayette"),
    ("Patriot League", "Lehigh"),
    ("Southeastern Conference", "Alabama"),
    ("Southeastern Conference", "Arkansas"),
    ("Southeastern Conference", "Auburn"),
    ("Southeastern Conference", "Florida"),
    ("Southeastern Conference", "Georgia"),
    ("Southeastern Conference", "Kentucky"),
    ("Southeastern Conference", "LSU"),
    ("Southeastern Conference", "Mississippi State"),
    ("Southeastern Conference", "Missouri"),
    ("Southeastern Conference", "Oklahoma"),
    ("Southeastern Conference", "Ole Miss"),
    ("Southeastern Conference", "South Carolina"),
    ("Southeastern Conference", "Tennessee"),
    ("Southeastern Conference", "Texas"),
    ("Southeastern Conference", "Texas A&M"),
    ("Southeastern Conference", "Vanderbilt"),
    ("Southern Conference", "Chattanooga"),
    ("Southern Conference", "ETSU"),
    ("Southern Conference", "Furman"),
    ("Southern Conference", "Mercer"),
    ("Southern Conference", "Samford"),
    ("Southern Conference", "UNCG"),
    ("Southern Conference", "Western Carolina"),
    ("Southland Conference", "Houston Christian"),
    ("Southland Conference", "Incarnate Word"),
    ("Southland Conference", "Lamar"),
    ("Southland Conference", "McNeese"),
    ("Southland Conference", "Nicholls"),
    ("Southland Conference", "Northwestern State"),
    ("Southland Conference", "Southeastern Louisiana"),
    ("Southland Conference", "Stephen F. Austin"),
    ("Southland Conference", "Texas A&M-Commerce"),
    ("Southland Conference", "Texas A&M-Corpus Christi"),
    ("Southwestern Athletic Conference", "Alabama A&M"),
    ("Southwestern Athletic Conference", "Alabama State"),
    ("Southwestern Athletic Conference", "Alcorn State"),
    ("Southwestern Athletic Conference", "Arkansas-Pine Bluff"),
    ("Southwestern Athletic Conference", "Bethune-Cookman"),
    ("Southwestern Athletic Conference", "Florida A&M"),
    ("Southwestern Athletic Conference", "Grambling State"),
    ("Southwestern Athletic Conference", "Jackson State"),
    ("Southwestern Athletic Conference", "Mississippi Valley State"),
    ("Southwestern Athletic Conference", "Prairie View A&M"),
    ("Southwestern Athletic Conference", "Southern"),
    ("Southwestern Athletic Conference", "Texas Southern"),
    ("Summit League", "Kansas City"),
    ("Summit League", "North Dakota"),
    ("Summit League", "North Dakota State"),
    ("Summit League", "Omaha"),
    ("Summit League", "South Dakota"),
    ("Summit League", "South Dakota State"),
    ("Summit League", "St. Thomas"),
    ("Sun Belt Conference", "Appalachian State"),
    ("Sun Belt Conference", "Coastal Carolina"),
    ("Sun Belt Conference", "Georgia Southern"),
    ("Sun Belt Conference", "Georgia State"),
    ("Sun Belt Conference", "James Madison"),
    ("Sun Belt Conference", "Louisiana"),
    ("Sun Belt Conference", "Marshall"),
    ("Sun Belt Conference", "Old Dominion"),
    ("Sun Belt Conference", "South Alabama"),
    ("Sun Belt Conference", "Southern Miss"),
    ("Sun Belt Conference", "Texas State"),
    ("Sun Belt Conference", "Troy"),
    ("Sun Belt Conference", "ULM"),
    ("West Coast Conference", "Loyola Marymount"),
    ("West Coast Conference", "Pacific"),
    ("West Coast Conference", "Saint Mary's"),
    ("West Coast Conference", "San Diego"),
    ("West Coast Conference", "Santa Clara"),
    ("West Coast Conference", "Seattle U"),
    ("Western Athletic Conference", "Abilene Christian"),
    ("Western Athletic Conference", "California Baptist"),
    ("Western Athletic Conference", "Southern Utah"),
    ("Western Athletic Conference", "Tarleton State"),
    ("Western Athletic Conference", "UT Arlington"),
    ("Western Athletic Conference", "Utah Tech"),
    ("Western Athletic Conference", "Utah Valley")
]

# Convert tuple list to dictionary
CONFERENCE_MAP = {school: conf for conf, school in RAW_CONFERENCES}

# 2. Map CSV variations/abbreviations DIRECTLY to the official school name
NAME_ALIGNMENT = {
    "North Dakota St.": "North Dakota State",
    "N. Dakota St.": "North Dakota State",
    "NDSU": "North Dakota State",
    "South Dakota St.": "South Dakota State",
    "S. Dakota St.": "South Dakota State",
    "Oklahoma St.": "Oklahoma State",
    "Iowa St.": "Iowa State",
    "Kansas St.": "Kansas State",
    "Arizona St.": "Arizona State",
    "Michigan St.": "Michigan State",
    "Ohio St.": "Ohio State",
    "Penn St.": "Penn State",
    "Mississippi St.": "Mississippi State",
    "Georgia St.": "Georgia State",
    "Appalachian St.": "Appalachian State",
    "Texas St.": "Texas State",
    "Ball St.": "Ball State",
    "Kent St.": "Kent State",
    "Fresno St.": "Fresno State",
    "Boise St.": "Boise State",
    "San Diego St.": "San Diego State",
    "San Jose St.": "San Jose State",
    "Utah St.": "Utah State",
    "Colorado St.": "Colorado State",
    "Morgan St.": "Morgan State",
    "Coppin St.": "Coppin State",
    "Norfolk St.": "Norfolk State",
    "Delaware St.": "Delaware State",
    "South Carolina St.": "South Carolina State",
    "Alabama St.": "Alabama State",
    "Jackson St.": "Jackson State",
    "Grambling St.": "Grambling State",
    "Alcorn St.": "Alcorn State",
    "Mississippi Valley St.": "Mississippi Valley State",
    "Tennessee St.": "Tennessee State",
    "Morehead St.": "Morehead State",
    "Indiana St.": "Indiana State",
    "Illinois St.": "Illinois State",
    "Missouri St.": "Missouri State",
    "Tarleton St.": "Tarleton State",
    "Kennesaw St.": "Kennesaw State",
    "Jacksonville St.": "Jacksonville State",
    "North Alabama St.": "North Alabama",
    "Mercyhurst University": "Mercyhurst",
    "Mercyhurst Univ.": "Mercyhurst",
    "UNC": "North Carolina",
    "NC State": "NC State",
    "N.C. State": "NC State",
    "Pitt": "Pittsburgh",
    "UVA": "Virginia",
    "Va. Tech": "Virginia Tech",
    "Virginia Tech": "Virginia Tech",
    "Ole Miss": "Ole Miss",
    "Mississippi": "Ole Miss",
    "USC": "South Carolina",
    "Cal": "California",
    "LSU": "LSU",
    "UCLA": "UCLA",
    "BYU": "BYU",
    "SMU": "SMU",
    "UCF": "UCF",
    "UTEP": "UTEP",
    "UTSA": "UTSA",
    "UAB": "UAB",
    "UNCW": "UNCW",
    "UNCG": "UNCG",
    "UIC": "UIC",
    "ULM": "ULM",
    "SFA": "Stephen F. Austin",
    "Stephen F. Austin St.": "Stephen F. Austin",
    "Southeastern La.": "Southeastern Louisiana",
    "St. Francis (PA)": "Saint Francis (PA)",
    "Saint Francis PA": "Saint Francis (PA)",
    "St. Bonaventure": "St. Bonaventure",
    "St. John's (NY)": "St. John's",
    "Saint Peter's": "Saint Peter's",
    "St. Peter's": "Saint Peter's",
    "St. Thomas (MN)": "St. Thomas",
    "Saint Mary's (CA)": "Saint Mary's",
    "Miami (OH)": "Miami (OH)",
    "Miami OH": "Miami (OH)"
}

def clean_school_name(raw_name):
    """Normalize raw team string to exact canonical name from user's list."""
    if not isinstance(raw_name, str):
        return "Unknown"
    
    cleaned = raw_name.strip()
    
    # 1. Exact direct match
    if cleaned in CONFERENCE_MAP:
        return cleaned
        
    # 2. Direct lookup in alignment dictionary
    if cleaned in NAME_ALIGNMENT:
        return NAME_ALIGNMENT[cleaned]
        
    # 3. Swap trailing ' St.' for ' State'
    if cleaned.endswith(" St."):
        swapped = cleaned[:-4] + " State"
        if swapped in CONFERENCE_MAP:
            return swapped

    if cleaned.endswith(" St"):
        swapped = cleaned[:-3] + " State"
        if swapped in CONFERENCE_MAP:
            return swapped

    return cleaned

def load_data(team_csv_path="team_games_season.csv"):
    if not os.path.exists(team_csv_path) or os.stat(team_csv_path).st_size == 0:
        print(f"Warning: {team_csv_path} is empty or missing.")
        return None

    df = pd.read_csv(team_csv_path)
    if df.empty:
        return None
        
    # ALIGN NAMES IMMEDIATELY AT SOURCE
    df["team"] = df["team"].apply(clean_school_name)
    df["opponent"] = df["opponent"].apply(clean_school_name)
    
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
        print("No teams remaining after filtering.")
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
            print(f"Converged after {n} iterations (change: {max_change:.6f})")
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
        conference_name = CONFERENCE_MAP.get(team_name, "Independent / Other")

        records.append(
            {
                "rank": int(row["rank"]),
                "team": team_name,
                "conference": conference_name,
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

    print(f"Saved {len(records)} teams to {output_path}.")

if __name__ == "__main__":
    df_games = load_data("team_games_season.csv")
    if df_games is not None:
        final_ratings = compute_kahl_index(df_games, min_games=20)
        save_ratings_json(final_ratings, "ratings.json")
    else:
        save_ratings_json(None, "ratings.json")
