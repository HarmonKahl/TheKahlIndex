import os
import csv
import json
import time
import requests
from datetime import datetime, timedelta

CHECKPOINT_FILE = "_completed_dates.txt"
OUTPUT_GAMES = "games_season.csv"
OUTPUT_TEAMS = "team_games_season.csv"

def load_completed_dates():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            return {line.strip() for line in f if line.strip()}
    return set()

def save_completed_date(date_str):
    with open(CHECKPOINT_FILE, "a", encoding="utf-8") as f:
        f.write(f"{date_str}\n")

def fetch_game_boxscore(game_id):
    url = f"https://ncaa-api.henrygd.me/game/{game_id}/boxscore"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None

def pull_season(start_date="2026-02-05", end_date="2026-06-05"):
    completed = load_completed_dates()
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    delta = timedelta(days=1)

    games_exists = os.path.exists(OUTPUT_GAMES) and os.path.getsize(OUTPUT_GAMES) > 0
    teams_exists = os.path.exists(OUTPUT_TEAMS) and os.path.getsize(OUTPUT_TEAMS) > 0

    g_file = open(OUTPUT_GAMES, "a", newline="", encoding="utf-8")
    t_file = open(OUTPUT_TEAMS, "a", newline="", encoding="utf-8")

    g_writer = csv.DictWriter(g_file, fieldnames=["date", "game_id", "away_team", "away_score", "home_team", "home_score", "status"])
    t_writer = csv.DictWriter(t_file, fieldnames=["date", "game_id", "team", "opponent", "role", "runs_for", "runs_against", "win"])

    if not games_exists: g_writer.writeheader()
    if not teams_exists: t_writer.writeheader()

    curr = start
    while curr <= end:
        date_str = curr.strftime("%Y-%m-%d")
        if date_str in completed:
            curr += delta
            continue

        sb_url = f"https://ncaa-api.henrygd.me/scoreboard/softball/d1/{curr.year}/{curr.month}/{curr.day}"
        try:
            resp = requests.get(sb_url, timeout=10)
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
                                "status": g_data.get("gameState", "final")
                            })

                            # Team A perspective
                            t_writer.writerow({
                                "date": date_str, "game_id": gid, "team": away_name, "opponent": home_name,
                                "role": "away", "runs_for": a_sc, "runs_against": h_sc, "win": int(a_sc > h_sc)
                            })
                            # Team B perspective
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
            time.sleep(0.2)
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
