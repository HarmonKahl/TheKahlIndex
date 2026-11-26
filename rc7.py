#!/usr/bin/env python3
"""
rc7.py -- Unified metrics generator for the Kahl Index & Hitter RC7.

Reads:
    team_games_season.csv
    player_games_season.csv

Writes:
    ratings.json
    bracketology.json
    players.json
    qualified_players.json

Usage:
    python rc7.py
    python rc7.py --audit --season 2026
"""

import argparse
import json
import os
import re
import sys

import numpy as np
import pandas as pd


# ----------------------------------------------------------------------------
# 1. Conference & School Name Alignment
# ----------------------------------------------------------------------------
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
    ("Western Athletic Conference", "Utah Valley"),
]

CONFERENCE_MAP = {school: conf for conf, school in RAW_CONFERENCES}

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
    "Miami OH": "Miami (OH)",
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


def alnum(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


# ----------------------------------------------------------------------------
# 2. Kahl Index Team Ratings & Bracketology
# ----------------------------------------------------------------------------
def compute_kahl_index(team_df, min_games=20, max_iters=100, tol=1e-6):
    team_df = team_df[(team_df["team"] != "TBA") & (team_df["opponent"] != "TBA")].copy()
    team_df["innings_batted"] = pd.to_numeric(team_df["innings_batted"], errors="coerce").fillna(7.0)
    team_df["innings_fielded"] = pd.to_numeric(team_df["innings_fielded"], errors="coerce").fillna(7.0)

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
        print("No teams remaining after filtering for Kahl Index.")
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
            print(f"Kahl Index converged after {n} iterations (change: {max_change:.6f})")
            break

    season["raa"] = season["team"].map(raa)
    season["sos"] = season["raa"] - season["net_adj"]

    season = season.sort_values("raa", ascending=False).reset_index(drop=True)
    season["rank"] = range(1, len(season) + 1)

    return season


def save_ratings_json(final_df, output_path="ratings.json"):
    if final_df is None or final_df.empty:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump([], f)
        print(f"Wrote empty list to {output_path}")
        return

    records = []
    for _, row in final_df.iterrows():
        team_name = str(row["team"])
        conference_name = CONFERENCE_MAP.get(team_name, "Independent / Other")
        records.append({
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
        })

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)
    print(f"Saved {len(records)} teams -> {output_path}")


def generate_bracketology(final_df, output_path="bracketology.json"):
    if final_df is None or final_df.empty:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({}, f)
        return

    df = final_df.copy()
    df["conference"] = df["team"].map(lambda t: CONFERENCE_MAP.get(t, "Independent / Other"))

    aq_df = df[df["conference"] != "Independent / Other"]
    aq_teams = aq_df.groupby("conference").first().reset_index()
    aq_team_names = set(aq_teams["team"])

    at_large_candidates = df[~df["team"].isin(aq_team_names)].sort_values("rank").reset_index(drop=True)
    at_large_teams = at_large_candidates.head(33)

    field_df = pd.concat([aq_teams, at_large_teams]).sort_values("rank").reset_index(drop=True)

    if len(field_df) < 64:
        print(f"Warning: Only {len(field_df)} teams available for Bracketology.")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({}, f)
        return

    field = field_df.head(64).to_dict("records")
    hosts = field[0:16]
    seed_2s_serpentine = list(reversed(field[16:32]))
    band_3 = field[32:48]
    band_4 = field[48:64]

    regionals = []
    for i in range(16):
        host = hosts[i]
        seed_2 = seed_2s_serpentine[i]
        pod_conferences = {host["conference"], seed_2["conference"]}

        def pick_candidate(band):
            for idx, candidate in enumerate(band):
                conf = candidate["conference"]
                if conf == "Independent / Other" or conf not in pod_conferences:
                    pod_conferences.add(conf)
                    return band.pop(idx)
            candidate = band.pop(0)
            pod_conferences.add(candidate["conference"])
            return candidate

        seed_3 = pick_candidate(band_3)
        seed_4 = pick_candidate(band_4)

        regionals.append({
            "regional_number": i + 1,
            "host_team": host["team"],
            "host_rank": host["rank"],
            "teams": [
                {"seed_in_pod": 1, "national_seed": i + 1, "team": host["team"], "conference": host["conference"], "overall_rank": host["rank"], "raa": round(float(host["raa"]), 2)},
                {"seed_in_pod": 2, "national_seed": 32 - i, "team": seed_2["team"], "conference": seed_2["conference"], "overall_rank": seed_2["rank"], "raa": round(float(seed_2["raa"]), 2)},
                {"seed_in_pod": 3, "national_seed": None, "team": seed_3["team"], "conference": seed_3["conference"], "overall_rank": seed_3["rank"], "raa": round(float(seed_3["raa"]), 2)},
                {"seed_in_pod": 4, "national_seed": None, "team": seed_4["team"], "conference": seed_4["conference"], "overall_rank": seed_4["rank"], "raa": round(float(seed_4["raa"]), 2)},
            ]
        })

    last_four_in = at_large_candidates.iloc[29:33][["team", "conference", "rank", "raa"]].to_dict("records")
    first_four_out = at_large_candidates.iloc[33:37][["team", "conference", "rank", "raa"]].to_dict("records")
    next_four_out = at_large_candidates.iloc[37:41][["team", "conference", "rank", "raa"]].to_dict("records")

    for group in (last_four_in, first_four_out, next_four_out):
        for item in group:
            item["raa"] = round(float(item["raa"]), 2)

    bracket_data = {
        "regionals": regionals,
        "last_four_in": last_four_in,
        "first_four_out": first_four_out,
        "next_four_out": next_four_out,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(bracket_data, f, indent=2)
    print(f"Generated 64-team bracketology -> {output_path}")


# ----------------------------------------------------------------------------
# 3. Player Resolution & Hitter RC7 Leaderboards
# ----------------------------------------------------------------------------
def _surname(name):
    toks = str(name).replace(",", " ").split()
    return alnum(toks[-1]) if toks else ""


def _initial(name):
    toks = str(name).split()
    return alnum(toks[0])[:1] if len(toks) > 1 else ""


def same_player(a, b):
    """'Smith' ~ 'Jane Smith' ~ 'J. Smith'; 'Jane Smith' !~ 'Kate Smith'."""
    na, nb = alnum(a), alnum(b)
    if na == nb or na.endswith(nb) or nb.endswith(na):
        return True
    ia, ib = _initial(a), _initial(b)
    return _surname(a) == _surname(b) and (not ia or not ib or ia == ib)


def resolve_players(df):
    df = df.copy()
    df["first_name"] = df["first_name"].fillna("").astype(str).str.strip()
    df["last_name"] = df["last_name"].fillna("").astype(str).str.strip()
    df["full"] = (df["first_name"] + " " + df["last_name"]).str.strip()
    df["num"] = pd.to_numeric(df["number"], errors="coerce")

    pid = pd.Series(index=df.index, dtype=object)
    display = {}
    for team, g in df.groupby("team", sort=False):
        clusters = []

        def add(c, full):
            c["names"].add(full)
            if len(full) > len(c["best"]):
                c["best"] = full

        numbered = g[g["num"].notna()]
        for num, gn in numbered.groupby("num", sort=True):
            local = []
            for idx, full in sorted(zip(gn.index, gn["full"]), key=lambda t: -len(t[1])):
                hit = next((c for c in local if any(same_player(full, n) for n in c["names"])), None)
                if hit is None:
                    hit = {"names": set(), "best": full, "id": f"{team}|#{int(num)}|{len(local)}"}
                    local.append(hit)
                add(hit, full)
                pid[idx] = hit["id"]
            clusters.extend(local)

        for idx, full in zip(g[g["num"].isna()].index, g[g["num"].isna()]["full"]):
            matches = [c for c in clusters if any(same_player(full, n) for n in c["names"])]
            if len(matches) == 1:
                c = matches[0]
            else:
                c = next((c for c in clusters if c["id"] == f"{team}|n|{alnum(full)}"), None)
                if c is None:
                    c = {"names": set(), "best": full, "id": f"{team}|n|{alnum(full)}"}
                    clusters.append(c)
            add(c, full)
            pid[idx] = c["id"]
        for c in clusters:
            display[c["id"]] = c["best"]

    df["player_id"] = pid
    df["player_name"] = df["player_id"].map(display)
    return df


def team_context(t):
    """Games played and runs-allowed-per-7 for every team, from real innings."""
    agg = t.groupby("team").agg(
        games=("game_id", "nunique"),
        runs_against=("runs_against", "sum"),
        innings_fielded=("innings_fielded", "sum"),
    )
    agg["ra7"] = agg["runs_against"] / agg["innings_fielded"] * 7
    return agg


def calculate_rc7(p, t, out_all="players.json", out_qualified="qualified_players.json",
                  min_qualified_ab=40, ab_per_team_game=2.0, quiet=False):
    p = resolve_players(p)

    num = ["at_bats", "hits", "walks", "doubles", "triples", "home_runs",
           "doubles_season_total", "triples_season_total", "home_runs_season_total"]
    for c in num:
        p[c] = pd.to_numeric(p[c], errors="coerce")

    p["pitcher_row"] = p["position"].fillna("").map(
        lambda x: "p" in [tok.strip().lower() for tok in str(x).split("/")])

    p["walks_clean"] = p["walks"].where(~p["pitcher_row"], 0).fillna(0)
    p["ab0"] = p["at_bats"].fillna(0)
    p["h0"] = p["hits"].fillna(0)

    # Opponent Pitching Adjustment Factor (weighted by plate appearances)
    ctx = team_context(t)
    d1_ra7 = (ctx["runs_against"].sum() / ctx["innings_fielded"].sum() * 7) if len(ctx) else 4.0

    p["opp_ra7"] = p["opponent"].map(ctx["ra7"]).fillna(d1_ra7)
    p["pa_game"] = p["ab0"] + p["walks_clean"]
    p["weighted_opp_ra7"] = p["opp_ra7"] * p["pa_game"]

    g = p.groupby("player_id")
    season = pd.DataFrame({
        "player_name": g["player_name"].first(),
        "team": g["team"].first(),
        "games": g.size(),
        "ab": g["ab0"].sum(),
        "hits": g["h0"].sum(),
        "walks": g["walks_clean"].sum(),
        "pitcher_rows": g["pitcher_row"].sum(),
        "d2_pg": g["doubles"].sum(min_count=1),
        "d3_pg": g["triples"].sum(min_count=1),
        "hr_pg": g["home_runs"].sum(min_count=1),
        "d2_cum": g["doubles_season_total"].max(),
        "d3_cum": g["triples_season_total"].max(),
        "hr_cum": g["home_runs_season_total"].max(),
        "weighted_opp_ra7": g["weighted_opp_ra7"].sum(),
        "total_pa": g["pa_game"].sum(),
    }).reset_index()

    for a, b in (("d2_pg", "d2_cum"), ("d3_pg", "d3_cum"), ("hr_pg", "hr_cum")):
        season[a[:-3]] = season[[a, b]].max(axis=1).fillna(0)

    out = []
    for r in season.itertuples():
        ab, h, bb = float(r.ab), float(r.hits), float(r.walks)
        if ab + bb == 0:
            continue
        d2, d3, hr = float(r.d2), float(r.d3), float(r.hr)
        xbh = d2 + d3 + hr
        if xbh > h:
            d2 = min(d2, h)
            d3 = min(d3, max(0.0, h - d2))
            hr = min(hr, max(0.0, h - d2 - d3))
            xbh = d2 + d3 + hr
        tb = (h - xbh) + 2 * d2 + 3 * d3 + 4 * hr
        rc = (h + bb) * (tb + 0.26 * bb) / (ab + bb)
        outs = ab - h
        rc7 = rc / outs * 21 if outs > 0 else 0.0

        avg_opp_ra7 = (r.weighted_opp_ra7 / r.total_pa) if r.total_pa > 0 else d1_ra7
        opaf = (d1_ra7 / avg_opp_ra7) if avg_opp_ra7 > 0 else 1.0

        team_games = int(ctx["games"].get(r.team, r.games))
        qualified = bool(ab >= team_games * ab_per_team_game and ab >= min_qualified_ab)
        out.append({
            "player_name": r.player_name, "name": r.player_name, "team": r.team,
            "PA": int(ab + bb), "HR": int(hr),
            "pitching_games": int(r.pitcher_rows),
            "RC7_raw": round(rc7, 2),
            "OPAF": round(opaf, 2),
            "RC7_adj": round(rc7 * opaf, 2),
            "ab": int(ab), "hits": int(h), "doubles": int(d2), "triples": int(d3),
            "tb": int(tb), "walks": int(bb), "qualified": qualified,
            "rc": round(rc, 2), "rc7": round(rc7, 2), "rc7_adj": round(rc7 * opaf, 2),
        })

    out.sort(key=lambda x: x["RC7_adj"], reverse=True)
    for i, row in enumerate(out, 1):
        row["rank"] = i
    qual = [dict(x) for x in out if x["qualified"]]
    for i, row in enumerate(qual, 1):
        row["rank"] = i

    with open(out_all, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    with open(out_qualified, "w", encoding="utf-8") as f:
        json.dump(qual, f, indent=2)

    if not quiet:
        print(f"{len(out)} players -> {out_all};  {len(qual)} qualified -> {out_qualified}")
    return out


# ----------------------------------------------------------------------------
# 4. NCAA Official Leaderboard Audit
# ----------------------------------------------------------------------------
def audit(players, api="https://ncaa-api.henrygd.me", season=None):
    """Compare our AB/H/BB with NCAA's official On-Base-Percentage leaderboard."""
    import requests
    season = season or pd.Timestamp.today().year
    rows, page, pages = [], 1, 1
    while page <= pages:
        r = requests.get(f"{api}/stats/softball/d1/{season}/individual/510",
                         params={"page": page} if page > 1 else None, timeout=30)
        d = r.json()
        rows += d["data"]
        pages = int(d.get("pages", 1))
        page += 1
    mine = {}
    for pl in players:
        mine.setdefault((pl["team"], alnum(pl["player_name"])), pl)
    exact = {"ab": 0, "hits": 0, "walks": 0}
    n = missing = 0
    bad = []
    for r in rows:
        team_clean = clean_school_name(r["Team"])
        key = (team_clean, alnum(r["Name"]))
        pl = mine.get(key)
        if pl is None:
            cands = [v for (tm, nm), v in mine.items() if tm == team_clean and alnum(r["Name"]).endswith(nm) and len(nm) >= 3]
            pl = cands[0] if len(cands) == 1 else None
        if pl is None:
            missing += 1
            continue
        n += 1
        diffs = {}
        for ours, theirs in (("ab", "AB"), ("hits", "H"), ("walks", "BB")):
            if pl[ours] == int(r[theirs]):
                exact[ours] += 1
            else:
                diffs[ours] = (pl[ours], int(r[theirs]))
        if diffs:
            bad.append((r["Name"], team_clean, diffs))
    print(f"\n=== PLAYER AUDIT vs official NCAA OBP leaderboard ({len(rows)} players) ===")
    print(f"matched by name: {n}   not matched: {missing}")
    for k in exact:
        print(f"  {k:5} exact for {exact[k]}/{n}")
    for b in bad[:15]:
        print("  differs:", b)
    return bad


# ----------------------------------------------------------------------------
# 5. Main Entrypoint
# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Generate Kahl Index ratings, bracketology, and hitter RC7 leaderboards.")
    ap.add_argument("--data-dir", default=".")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--season", type=int)
    a = ap.parse_args()

    out_dir = a.out_dir or a.data_dir
    os.makedirs(out_dir, exist_ok=True)

    pp = os.path.join(a.data_dir, "player_games_season.csv")
    tp = os.path.join(a.data_dir, "team_games_season.csv")

    if not os.path.exists(pp) or not os.path.exists(tp):
        sys.exit("player_games_season.csv / team_games_season.csv not found -- run ncaa_pull.py first")

    p_df = pd.read_csv(pp, dtype={"game_id": str})
    t_df = pd.read_csv(tp, dtype={"game_id": str})

    for df in (p_df, t_df):
        df["team"] = df["team"].apply(clean_school_name)
        df["opponent"] = df["opponent"].apply(clean_school_name)

    final_ratings = compute_kahl_index(t_df, min_games=20)
    save_ratings_json(final_ratings, os.path.join(out_dir, "ratings.json"))
    generate_bracketology(final_ratings, os.path.join(out_dir, "bracketology.json"))

    players = calculate_rc7(
        p_df, t_df,
        out_all=os.path.join(out_dir, "players.json"),
        out_qualified=os.path.join(out_dir, "qualified_players.json"),
    )

    if a.audit:
        audit(players, season=a.season)


if __name__ == "__main__":
    main()
