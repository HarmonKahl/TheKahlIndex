#!/usr/bin/env python3
import os
import csv
import json
import time
import requests
from datetime import datetime, timedelta

FORCE_RESET = True

CHECKPOINT_FILE = "_completed_dates.txt"
OUTPUT_GAMES = "games_season.csv"
OUTPUT_TEAMS = "team_games_season.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

GAME_COLUMNS = ["date", "game_id", "away_team", "away_score", "home_team", "home_score", "state", "status", "away_innings", "home_innings"]
TEAM_GAME_COLUMNS = ["date", "game_id", "team", "opponent", "role", "runs_for", "runs_against", "win", "innings_batted", "innings_fielded"]

def load_completed_dates():
    if not FORCE_RESET and os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            return {line.strip() for line in f if line.strip()}
    return set()

def save_completed_date(date_str):
    with open(CHECKPOINT_FILE, "a", encoding="utf-8") as f:
        f.write(f"{date_str}\n")

def fetch_game_boxscore(game_id):
    url = f"https://ncaa-api.henrygd.me/game/{game_id}/boxscore"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=4)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None

def extract_innings(box_data):
    """Extracts innings played from boxscore linescore if available."""
    if not box_data or not isinstance(box_data, dict):
        return 7.0, 7.0
    
    linescore = box_data.get("linescore") or box_data.get("boxscore", {}).get("linescore")
    if isinstance(linescore, list) and len(linescore) > 0:
        return float(len(linescore)), float(len(linescore))
    return 7.0, 7.0

def pull_season(start_date="2026-02-05", end_date="2026-06-05"):
    completed = load_completed_dates()
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    delta = timedelta(days=1)

    if FORCE_RESET:
        if os.path.exists(OUTPUT_GAMES): os.remove(OUTPUT_GAMES)
        if os.path.exists(OUTPUT_TEAMS): os.remove(OUTPUT_TEAMS)

    g_file = open(OUTPUT_GAMES, "w", newline="", encoding="utf-8")
    t_file = open(OUTPUT_TEAMS, "w", newline="", encoding="utf-8")

    g_writer = csv.DictWriter(g_file, fieldnames=GAME_COLUMNS)
    t_writer = csv.DictWriter(t_file, fieldnames=TEAM_GAME_COLUMNS)

    g_writer.writeheader()
    t_writer.writeheader()

    curr = start
    while curr <= end:
        date_str = curr.strftime("%Y-%m-%d")
        if date_str in completed:
            curr += delta
            continue

        year_str = curr.strftime("%Y")
        month_str = curr.strftime("%m")
        day_str = curr.strftime("%d")

        sb_url = f"https://ncaa-api.henrygd.me/scoreboard/softball/d1/{year_str}/{month_str}/{day_str}"
        try:
            resp = requests.get(sb_url, headers=HEADERS, timeout=8)
            if resp.status_code == 200:
                payload = resp.json()
                raw_games = payload.get("games", []) if isinstance(payload, dict) else []
                
                day_games = 0
                for item in raw_games:
                    g_data = item.get("game", item) if isinstance(item, dict) else {}
                    
                    gid = str(g_data.get("gameID") or g_data.get("id") or "").strip()
                    if "/" in gid:
                        gid = gid.rstrip("/").split("/")[-1]

                    away = g_data.get("away", {}) or {}
                    home = g_data.get("home", {}) or {}

                    away_name = away.get("names", {}).get("short") or away.get("name") or "Away"
                    home_name = home.get("names", {}).get("short") or home.get("name") or "Home"

                    away_score = away.get("score")
                    home_score = home.get("score")

                    if away_score is not None and home_score is not None:
                        try:
                            a_sc = int(away_score)
                            h_sc = int(home_score)

                            # Fetch boxscore for accurate innings
                            box = fetch_game_boxscore(gid)
                            a_inn, h_inn = extract_innings(box)

                            g_writer.writerow({
                                "date": date_str, "game_id": gid,
                                "away_team": away_name, "away_score": a_sc,
                                "home_team": home_name, "home_score": h_sc,
                                "state": g_data.get("gameState", "final"),
                                "status": g_data.get("status", ""),
                                "away_innings": a_inn, "home_innings": h_inn
                            })

                            # Away Team
                            t_writer.writerow({
                                "date": date_str, "game_id": gid, "team": away_name, "opponent": home_name,
                                "role": "away", "runs_for": a_sc, "runs_against": h_sc, "win": int(a_sc > h_sc),
                                "innings_batted": a_inn, "innings_fielded": h_inn
                            })
                            # Home Team
                            t_writer.writerow({
                                "date": date_str, "game_id": gid, "team": home_name, "opponent": away_name,
                                "role": "home", "runs_for": h_sc, "runs_against": a_sc, "win": int(h_sc > a_sc),
                                "innings_batted": h_inn, "innings_fielded": a_inn
                            })
                            day_games += 1
                            time.sleep(0.05)
                        except (ValueError, TypeError):
                            continue

                g_file.flush()
                t_file.flush()
                save_completed_date(date_str)
                print(f"[{date_str}] Processed {day_games} team games with boxscores.")
        except Exception as e:
            print(f"Error on {date_str}: {e}")

        curr += delta

    g_file.close()
    t_file.close()

if __name__ == "__main__":
    import sys
    s_date = sys.argv[1] if len(sys.argv) > 1 else "2026-02-05"
    e_date = sys.argv[2] if len(sys.argv) > 2 else "2026-06-05"
    pull_season(s_date, e_date)
