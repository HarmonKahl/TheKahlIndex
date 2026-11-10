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
TEAM_GAME_COLUMNS = ["date", "game_id", "team", "opponent", "role", "runs_for", "runs_against", "win"]

def load_completed_dates():
    if not FORCE_RESET and os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            return {line.strip() for line in f if line.strip()}
    return set()

def save_completed_date(date_str):
    with open(CHECKPOINT_FILE, "a", encoding="utf-8") as f:
        f.write(f"{date_str}\n")

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

                            g_writer.writerow({
                                "date": date_str, "game_id": gid,
                                "away_team": away_name, "away_score": a_sc,
                                "home_team": home_name, "home_score": h_sc,
                                "state": g_data.get("gameState", "final"),
                                "status": g_data.get("status", ""),
                                "away_innings": 7.0, "home_innings": 7.0
                            })

                            t_writer.writerow({
                                "date": date_str, "game_id": gid, "team": away_name, "opponent": home_name,
                                "role": "away", "runs_for": a_sc, "runs_against": h_sc, "win": int(a_sc > h_sc)
                            })
                            t_writer.writerow({
                                "date": date_str, "game_id": gid, "team": home_name, "opponent": away_name,
                                "role": "home", "runs_for": h_sc, "runs_against": a_sc, "win": int(h_sc > a_sc)
                            })
                            day_games += 1
                        except (ValueError, TypeError):
                            continue

                g_file.flush()
                t_file.flush()
                save_completed_date(date_str)
                print(f"[{date_str}] Processed {day_games} team games.")
            time.sleep(0.15)
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
