import json
import os
import re
import sys
import numpy as np
import pandas as pd

# 1. Base Conference List (Updated with exact custom display names)
RAW_CONFERENCES = [
    ("America East Conference", "UAlbany"),
    ("America East Conference", "Binghamton"),
    ("America East Conference", "Bryant"),
    ("America East Conference", "Maine"),
    ("America East Conference", "UMBC"),
    ("America East Conference", "UMass Lowell"),
    ("American Athletic Conference", "Charlotte"),
    ("American Athletic Conference", "East Carolina"),
    ("American Athletic Conference", "Fla. Atlantic"),
    ("American Athletic Conference", "Memphis"),
    ("American Athletic Conference", "North Texas"),
    ("American Athletic Conference", "South Fla."),
    ("American Athletic Conference", "Temple"),
    ("American Athletic Conference", "Tulsa"),
    ("American Athletic Conference", "UAB"),
    ("American Athletic Conference", "UTSA"),
    ("American Athletic Conference", "Wichita St."),
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
    ("Atlantic Coast Conference", "Florida St."),
    ("Atlantic Coast Conference", "Georgia Tech"),
    ("Atlantic Coast Conference", "Louisville"),
    ("Atlantic Coast Conference", "North Carolina"),
    ("Atlantic Coast Conference", "NC St."),
    ("Atlantic Coast Conference", "Notre Dame"),
    ("Atlantic Coast Conference", "Pittsburgh"),
    ("Atlantic Coast Conference", "SMU"),
    ("Atlantic Coast Conference", "Stanford"),
    ("Atlantic Coast Conference", "Syracuse"),
    ("Atlantic Coast Conference", "Virginia"),
    ("Atlantic Coast Conference", "Virginia Tech"),
    ("ASUN Conference", "Austin Peay"),
    ("ASUN Conference", "Bellarmine"),
    ("ASUN Conference", "Central Ark."),
    ("ASUN Conference", "Eastern Ky."),
    ("ASUN Conference", "FGCU"),
    ("ASUN Conference", "Jacksonville"),
    ("ASUN Conference", "Kennesaw St."),
    ("ASUN Conference", "Lipscomb"),
    ("ASUN Conference", "North Ala."),
    ("ASUN Conference", "North Florida"),
    ("ASUN Conference", "Queens (NC)"),
    ("ASUN Conference", "Stetson"),
    ("ASUN Conference", "West Ga."),
    ("Big 12 Conference", "Arizona"),
    ("Big 12 Conference", "Arizona St."),
    ("Big 12 Conference", "Baylor"),
    ("Big 12 Conference", "BYU"),
    ("Big 12 Conference", "Houston"),
    ("Big 12 Conference", "Iowa St."),
    ("Big 12 Conference", "Kansas"),
    ("Big 12 Conference", "Oklahoma St."),
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
    ("Big Sky Conference", "Idaho St."),
    ("Big Sky Conference", "Montana"),
    ("Big Sky Conference", "Northern Colo."),
    ("Big Sky Conference", "Portland St."),
    ("Big Sky Conference", "Sacramento St."),
    ("Big Sky Conference", "Weber St."),
    ("Big South Conference", "Charleston So."),
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
    ("Big Ten Conference", "Michigan St."),
    ("Big Ten Conference", "Minnesota"),
    ("Big Ten Conference", "Nebraska"),
    ("Big Ten Conference", "Northwestern"),
    ("Big Ten Conference", "Ohio St."),
    ("Big Ten Conference", "Oregon"),
    ("Big Ten Conference", "Penn St."),
    ("Big Ten Conference", "Purdue"),
    ("Big Ten Conference", "Rutgers"),
    ("Big Ten Conference", "UCLA"),
    ("Big Ten Conference", "Washington"),
    ("Big Ten Conference", "Wisconsin"),
    ("Big West Conference", "Cal Poly"),
    ("Big West Conference", "Cal."),
    ("Big West Conference", "CSU Bakersfield"),
    ("Big West Conference", "CSUN"),
    ("Big West Conference", "Hawaii"),
    ("Big West Conference", "Long Beach St."),
    ("Big West Conference", "UC Davis"),
    ("Big West Conference", "UC Riverside"),
    ("Big West Conference", "UC San Diego"),
    ("Big West Conference", "UC Santa Barbara"),
    ("Coastal Athletic Association", "Campbell"),
    ("Coastal Athletic Association", "Col. of Charleston"),
    ("Coastal Athletic Association", "Delaware"),
    ("Coastal Athletic Association", "Drexel"),
    ("Coastal Athletic Association", "Elon"),
    ("Coastal Athletic Association", "Hofstra"),
    ("Coastal Athletic Association", "Monmouth"),
    ("Coastal Athletic Association", "N.C. A&T"),
    ("Coastal Athletic Association", "UNCW"),
    ("Coastal Athletic Association", "Stony Brook"),
    ("Coastal Athletic Association", "Towson"),
    ("Conference USA", "FIU"),
    ("Conference USA", "Jacksonville St."),
    ("Conference USA", "Liberty"),
    ("Conference USA", "Louisiana Tech"),
    ("Conference USA", "Middle Tenn."),
    ("Conference USA", "Missouri St."),
    ("Conference USA", "New Mexico St."),
    ("Conference USA", "Sam Houston"),
    ("Conference USA", "UTEP"),
    ("Conference USA", "Western Ky."),
    ("Horizon League", "Cleveland St."),
    ("Horizon League", "Detroit Mercy"),
    ("Horizon League", "Green Bay"),
    ("Horizon League", "IU Indy"),
    ("Horizon League", "Northern Ky."),
    ("Horizon League", "Oakland"),
    ("Horizon League", "Robert Morris"),
    ("Horizon League", "Youngstown St."),
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
    ("Metro Atlantic Athletic Conference", "Mount St. Mary's"),
    ("Metro Atlantic Athletic Conference", "Niagara"),
    ("Metro Atlantic Athletic Conference", "Quinnipiac"),
    ("Metro Atlantic Athletic Conference", "Rider"),
    ("Metro Atlantic Athletic Conference", "Sacred Heart"),
    ("Metro Atlantic Athletic Conference", "Saint Peter's"),
    ("Metro Atlantic Athletic Conference", "Siena"),
    ("Mid-American Conference", "Akron"),
    ("Mid-American Conference", "Ball St."),
    ("Mid-American Conference", "Bowling Green"),
    ("Mid-American Conference", "Buffalo"),
    ("Mid-American Conference", "Central Mich."),
    ("Mid-American Conference", "Eastern Michigan"),
    ("Mid-American Conference", "Kent St."),
    ("Mid-American Conference", "Miami (OH)"),
    ("Mid-American Conference", "NIU"),
    ("Mid-American Conference", "Ohio"),
    ("Mid-American Conference", "Toledo"),
    ("Mid-American Conference", "Massachusetts"),
    ("Mid-American Conference", "Western Mich."),
    ("Mid-Eastern Athletic Conference", "Coppin St."),
    ("Mid-Eastern Athletic Conference", "Delaware St."),
    ("Mid-Eastern Athletic Conference", "Hampton"),
    ("Mid-Eastern Athletic Conference", "Howard"),
    ("Mid-Eastern Athletic Conference", "UMES"),
    ("Mid-Eastern Athletic Conference", "Morgan St."),
    ("Mid-Eastern Athletic Conference", "Norfolk St."),
    ("Mid-Eastern Athletic Conference", "N.C. Central"),
    ("Mid-Eastern Athletic Conference", "South Carolina St."),
    ("Missouri Valley Conference", "Belmont"),
    ("Missouri Valley Conference", "Bradley"),
    ("Missouri Valley Conference", "Drake"),
    ("Missouri Valley Conference", "Evansville"),
    ("Missouri Valley Conference", "Illinois St."),
    ("Missouri Valley Conference", "Indiana St."),
    ("Missouri Valley Conference", "Loyola Chicago"),
    ("Missouri Valley Conference", "Northern Iowa"),
    ("Missouri Valley Conference", "Southern Ill."),
    ("Missouri Valley Conference", "UIC"),
    ("Missouri Valley Conference", "UNI"),
    ("Missouri Valley Conference", "Valparaiso"),
    ("Mountain West Conference", "Boise St."),
    ("Mountain West Conference", "Colorado St."),
    ("Mountain West Conference", "Fresno St."),
    ("Mountain West Conference", "Grand Canyon"),
    ("Mountain West Conference", "Nevada"),
    ("Mountain West Conference", "New Mexico"),
    ("Mountain West Conference", "San Diego St."),
    ("Mountain West Conference", "San Jose St."),
    ("Mountain West Conference", "UNLV"),
    ("Mountain West Conference", "Utah St."),
    ("Northeast Conference", "Central Conn. St."),
    ("Northeast Conference", "FDU"),
    ("Northeast Conference", "Le Moyne"),
    ("Northeast Conference", "LIU"),
    ("Northeast Conference", "Mercyhurst"),
    ("Northeast Conference", "New Haven"),
    ("Northeast Conference", "Saint Francis"),
    ("Northeast Conference", "Stonehill"),
    ("Northeast Conference", "Wagner"),
    ("Ohio Valley Conference", "Eastern Ill."),
    ("Ohio Valley Conference", "Lindenwood"),
    ("Ohio Valley Conference", "Morehead St."),
    ("Ohio Valley Conference", "Murray St."),
    ("Ohio Valley Conference", "Southeast Mo. St."),
    ("Ohio Valley Conference", "SIUE"),
    ("Ohio Valley Conference", "Southern Ind."),
    ("Ohio Valley Conference", "Tennessee St."),
    ("Ohio Valley Conference", "Tennessee Tech"),
    ("Ohio Valley Conference", "UT Martin"),
    ("Ohio Valley Conference", "Western Ill."),
    ("Patriot League", "Army West Point"),
    ("Patriot League", "Boston U."),
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
    ("Southeastern Conference", "Mississippi St."),
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
    ("Southern Conference", "UNC Greensboro"),
    ("Southern Conference", "Western Caro."),
    ("Southern Conference", "Wofford"),
    ("Southland Conference", "Houston Christian"),
    ("Southland Conference", "UIW"),
    ("Southland Conference", "Lamar University"),
    ("Southland Conference", "McNeese"),
    ("Southland Conference", "Nicholls"),
    ("Southland Conference", "Northwestern St."),
    ("Southland Conference", "Southeastern Louisiana"),
    ("Southland Conference", "Stephen F. Austin"),
    ("Southland Conference", "East Texas A&M"),
    ("Southland Conference", "A&M-Corpus Christi"),
    ("Southwestern Athletic Conference", "Alabama A&M"),
    ("Southwestern Athletic Conference", "Alabama St."),
    ("Southwestern Athletic Conference", "Alcorn"),
    ("Southwestern Athletic Conference", "Ark.-Pine Bluff"),
    ("Southwestern Athletic Conference", "Bethune-Cookman"),
    ("Southwestern Athletic Conference", "Florida A&M"),
    ("Southwestern Athletic Conference", "Grambling"),
    ("Southwestern Athletic Conference", "Jackson St."),
    ("Southwestern Athletic Conference", "Mississippi Val."),
    ("Southwestern Athletic Conference", "Prairie View"),
    ("Southwestern Athletic Conference", "Southern U."),
    ("Southwestern Athletic Conference", "Texas Southern"),
    ("Summit League", "Kansas City"),
    ("Summit League", "North Dakota"),
    ("Summit League", "North Dakota St."),
    ("Summit League", "Omaha"),
    ("Summit League", "South Dakota"),
    ("Summit League", "South Dakota St."),
    ("Summit League", "St. Thomas"),
    ("Sun Belt Conference", "App State"),
    ("Sun Belt Conference", "Coastal Carolina"),
    ("Sun Belt Conference", "Ga. Southern"),
    ("Sun Belt Conference", "Georgia St."),
    ("Sun Belt Conference", "James Madison"),
    ("Sun Belt Conference", "Louisiana"),
    ("Sun Belt Conference", "Marshall"),
    ("Sun Belt Conference", "Old Dominion"),
    ("Sun Belt Conference", "South Alabama"),
    ("Sun Belt Conference", "Southern Miss."),
    ("Sun Belt Conference", "Texas St."),
    ("Sun Belt Conference", "Troy"),
    ("Sun Belt Conference", "ULM"),
    ("West Coast Conference", "LMU (CA)"),
    ("West Coast Conference", "Oregon St."),
    ("West Coast Conference", "Pacific"),
    ("West Coast Conference", "Saint Mary's"),
    ("West Coast Conference", "San Diego"),
    ("West Coast Conference", "Santa Clara"),
    ("West Coast Conference", "Seattle U"),
    ("Western Athletic Conference", "Abilene Christian"),
    ("Western Athletic Conference", "California Baptist"),
    ("Western Athletic Conference", "Southern Utah"),
    ("Western Athletic Conference", "Tarleton St."),
    ("Western Athletic Conference", "UT Arlington"),
    ("Western Athletic Conference", "Utah Tech"),
    ("Western Athletic Conference", "Utah Valley")
]

# Convert tuple list to dictionary
CONFERENCE_MAP = {school: conf for conf, school in RAW_CONFERENCES}

# 2. Comprehensive Alignment Dictionary for Scraped Names -> Custom Display Names
NAME_ALIGNMENT = {
    "Florida Atlantic": "Fla. Atlantic",
    "Cal State Fullerton": "Cal.",
    "Cal St. Fullerton": "Cal.",
    "South Florida": "South Fla.",
    "Boston University": "Boston U.",
    "Western Kentucky": "Western Ky.",
    "Appalachian State": "App State",
    "Appalachian St.": "App State",
    "Central Arkansas": "Central Ark.",
    "LMU": "LMU (CA)",
    "Loyola Marymount": "LMU (CA)",
    "Southern Illinois": "Southern Ill.",
    "North Alabama": "North Ala.",
    "Incarnate Word": "UIW",
    "UNC Greensboro": "UNC Greensboro",
    "UNCG": "UNC Greensboro",
    "Southern Mississippi": "Southern Miss.",
    "Southern Miss": "Southern Miss.",
    "Northern Iowa": "UNI",
    "Georgia Southern": "Ga. Southern",
    "Lamar": "Lamar University",
    "Oregon State": "Oregon St.",
    "Wofford": "Wofford",
    "Western Carolina": "Western Caro.",
    "Murray State": "Murray St.",
    "Central Michigan": "Central Mich.",
    "Northern Illinois": "NIU",
    "Florida Gulf Coast": "FGCU",
    "Army": "Army West Point",
    "Western Michigan": "Western Mich.",
    "MTSU": "Middle Tenn.",
    "Middle Tennessee": "Middle Tenn.",
    "UCSD": "UC San Diego",
    "UC San Diego": "UC San Diego",
    "Eastern Illinois": "Eastern Ill.",
    "Eastern Kentucky": "Eastern Ky.",
    "Northern Colorado": "Northern Colo.",
    "Prairie View A&M": "Prairie View",
    "Loyola Chicago": "Loyola Chicago",
    "SEMO": "Southeast Mo. St.",
    "SE Missouri St.": "Southeast Mo. St.",
    "Southeast Missouri State": "Southeast Mo. St.",
    "Charleston": "Col. of Charleston",
    "College of Charleston": "Col. of Charleston",
    "UMass": "Massachusetts",
    "CSUN": "CSUN",
    "Cal State Northridge": "CSUN",
    "Queens": "Queens (NC)",
    "Queens University": "Queens (NC)",
    "Albany": "UAlbany",
    "SIUE": "SIUE",
    "SIU Edwardsville": "SIUE",
    "West Georgia": "West Ga.",
    "Southern": "Southern U.",
    "Texas A&M-Corpus Christi": "A&M-Corpus Christi",
    "Texas A&M Corpus Christi": "A&M-Corpus Christi",
    "NKU": "Northern Ky.",
    "Northern Kentucky": "Northern Ky.",
    "Southern Indiana": "Southern Ind.",
    "Detroit Mercy": "Detroit Mercy",
    "Central Conn. St.": "Central Conn. St.",
    "Central Connecticut State": "Central Conn. St.",
    "Bakersfield": "CSU Bakersfield",
    "Cal State Bakersfield": "CSU Bakersfield",
    "North Carolina A&T": "N.C. A&T",
    "NC A&T": "N.C. A&T",
    "Charleston Southern": "Charleston So.",
    "Mount St. Mary's": "Mount St. Mary's",
    "IU Indy": "IU Indy",
    "IUPUI": "IU Indy",
    "IUPUI (IU Indy)": "IU Indy",
    "Western Illinois": "Western Ill.",
    "Western Ill.": "Western Ill.",
    "East Texas A&M": "East Texas A&M",
    "Texas A&M-Commerce": "East Texas A&M",
    "Arkansas Pine Bluff": "Ark.-Pine Bluff",
    "Arkansas-Pine Bluff": "Ark.-Pine Bluff",
    "Fairleigh Dickinson": "FDU",
    "Hampton": "Hampton",
    "Grambling State": "Grambling",
    "Grambling St.": "Grambling",
    "Alcorn State": "Alcorn",
    "Alcorn St.": "Alcorn",
    "N.C. Central": "N.C. Central",
    "North Carolina Central": "N.C. Central",
    "SFU": "Saint Francis",
    "Saint Francis (PA)": "Saint Francis",
    "St. Francis (PA)": "Saint Francis",
    "UMES": "UMES",
    "Maryland Eastern Shore": "UMES",
    "Mississippi Valley State": "Mississippi Val.",
    "Mississippi Valley St.": "Mississippi Val.",
    "North Dakota State": "North Dakota St.",
    "N. Dakota St.": "North Dakota St.",
    "South Dakota State": "South Dakota St.",
    "S. Dakota St.": "South Dakota St.",
    "Oklahoma State": "Oklahoma St.",
    "Iowa State": "Iowa St.",
    "Kansas State": "Kansas St.",
    "Arizona State": "Arizona St.",
    "Michigan State": "Michigan St.",
    "Ohio State": "Ohio St.",
    "Penn State": "Penn St.",
    "Mississippi State": "Mississippi St.",
    "Georgia State": "Georgia St.",
    "Texas State": "Texas St.",
    "Ball State": "Ball St.",
    "Kent State": "Kent St.",
    "Fresno State": "Fresno St.",
    "Boise State": "Boise St.",
    "San Diego State": "San Diego St.",
    "San Jose State": "San Jose St.",
    "Utah State": "Utah St.",
    "Colorado State": "Colorado St.",
    "Morgan State": "Morgan St.",
    "Coppin State": "Coppin St.",
    "Norfolk State": "Norfolk St.",
    "Delaware State": "Delaware St.",
    "South Carolina State": "South Carolina St.",
    "Alabama State": "Alabama St.",
    "Jackson State": "Jackson St.",
    "Tennessee State": "Tennessee St.",
    "Morehead State": "Morehead St.",
    "Indiana State": "Indiana St.",
    "Illinois State": "Illinois St.",
    "Missouri State": "Missouri St.",
    "Tarleton State": "Tarleton St.",
    "Kennesaw State": "Kennesaw St.",
    "Jacksonville State": "Jacksonville St.",
    "North Alabama State": "North Ala.",
    "Mercyhurst University": "Mercyhurst",
    "Mercyhurst Univ.": "Mercyhurst",
    "UNC": "North Carolina",
    "NC State": "NC St.",
    "N.C. State": "NC St.",
    "Pitt": "Pittsburgh",
    "UVA": "Virginia",
    "Va. Tech": "Virginia Tech",
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
    "UIC": "UIC",
    "ULM": "ULM",
    "SFA": "Stephen F. Austin",
    "Stephen F. Austin State": "Stephen F. Austin",
    "Southeastern La.": "Southeastern Louisiana",
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
    if not isinstance(raw_name, str):
        return "Unknown"
    cleaned = raw_name.strip()
    if cleaned in NAME_ALIGNMENT:
        return NAME_ALIGNMENT[cleaned]
    if cleaned in CONFERENCE_MAP:
        return cleaned
    if " State" in cleaned:
        swapped = cleaned.replace(" State", " St.")
        if swapped in CONFERENCE_MAP:
            return swapped
        if swapped in NAME_ALIGNMENT:
            return NAME_ALIGNMENT[swapped]
    return cleaned

def load_data(team_csv_path="team_games_season.csv"):
    if not os.path.exists(team_csv_path) or os.stat(team_csv_path).st_size == 0:
        print(f"Warning: {team_csv_path} is empty or missing.")
        return None
    df = pd.read_csv(team_csv_path)
    if df.empty:
        return None
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

def generate_bracketology(final_df, output_path="bracketology.json"):
    if final_df is None or final_df.empty:
        with open(output_path, "w") as f:
            json.dump({}, f)
        return

    df = final_df.copy()

    # Tag conferences
    df["conference"] = df["team"].map(lambda t: CONFERENCE_MAP.get(t, "Independent / Other"))

    # Step 1: Identify 31 Automatic Qualifiers (AQ) - Top team per conference
    aq_df = df[df["conference"] != "Independent / Other"]
    aq_teams = aq_df.groupby("conference").first().reset_index()
    aq_team_names = set(aq_teams["team"])

    # Step 2: At-Large Pool (Best teams regardless of conference not already an AQ)
    at_large_candidates = df[~df["team"].isin(aq_team_names)].sort_values("rank").reset_index(drop=True)
    
    # Take top 33 At-Large bids
    at_large_teams = at_large_candidates.head(33)

    # Combine AQ and At-Large teams into 64-team field
    field_df = pd.concat([aq_teams, at_large_teams]).sort_values("rank").reset_index(drop=True)

    if len(field_df) < 64:
        print(f"Warning: Only {len(field_df)} teams available for Bracketology.")
        return

    field = field_df.head(64).to_dict("records")

    # Step 3: Seed Bands (16 teams per band)
    hosts = field[0:16]        # Seed 1s (Regional Hosts)
    band_2 = field[16:32]      # Seed 2s
    band_3 = field[32:48]      # Seed 3s
    band_4 = field[48:64]      # Seed 4s

    regionals = []

    # Step 4: Fill Regional Pods with Conference Conflict Protection
    for i in range(16):
        host = hosts[i]
        pod = [host]
        pod_conferences = {host["conference"]}

        def pick_candidate(band):
            for idx, candidate in enumerate(band):
                conf = candidate["conference"]
                if conf == "Independent / Other" or conf not in pod_conferences:
                    pod_conferences.add(conf)
                    return band.pop(idx)
            candidate = band.pop(0)
            pod_conferences.add(candidate["conference"])
            return candidate

        seed_2 = pick_candidate(band_2)
        seed_3 = pick_candidate(band_3)
        seed_4 = pick_candidate(band_4)

        pod.extend([seed_2, seed_3, seed_4])

        regionals.append({
            "regional_number": i + 1,
            "host_team": host["team"],
            "host_rank": host["rank"],
            "teams": [
                {"seed_in_pod": 1, "team": pod[0]["team"], "conference": pod[0]["conference"], "overall_rank": pod[0]["rank"], "raa": round(float(pod[0]["raa"]), 2)},
                {"seed_in_pod": 2, "team": pod[1]["team"], "conference": pod[1]["conference"], "overall_rank": pod[1]["rank"], "raa": round(float(pod[1]["raa"]), 2)},
                {"seed_in_pod": 3, "team": pod[2]["team"], "conference": pod[2]["conference"], "overall_rank": pod[2]["rank"], "raa": round(float(pod[2]["raa"]), 2)},
                {"seed_in_pod": 4, "team": pod[3]["team"], "conference": pod[3]["conference"], "overall_rank": pod[3]["rank"], "raa": round(float(pod[3]["raa"]), 2)},
            ]
        })

    # Step 5: Bubble Watch Breakdown
    # At-Large ranks 30-33 = Last 4 In
    last_four_in = at_large_candidates.iloc[29:33][["team", "conference", "rank", "raa"]].to_dict("records")
    # At-Large ranks 34-37 = First 4 Out
    first_four_out = at_large_candidates.iloc[33:37][["team", "conference", "rank", "raa"]].to_dict("records")
    # At-Large ranks 38-41 = Next 4 Out
    next_four_out = at_large_candidates.iloc[37:41][["team", "conference", "rank", "raa"]].to_dict("records")

    bracket_data = {
        "regionals": regionals,
        "last_four_in": last_four_in,
        "first_four_out": first_four_out,
        "next_four_out": next_four_out
    }

    with open(output_path, "w") as f:
        json.dump(bracket_data, f, indent=2)

    print(f"Successfully generated bracketology and bubble watch to {output_path}.")

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
        generate_bracketology(final_ratings, "bracketology.json")
    else:
        save_ratings_json(None, "ratings.json")
        generate_bracketology(None, "bracketology.json")
