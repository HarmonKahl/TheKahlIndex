import os
import re
import csv
import json
import time
import requests
from datetime import datetime, timedelta

CHECKPOINT_FILE = "processed_games.json"
OUTPUT_CSV = "player_games_season.csv"

def load_processed_games():
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_processed_games(processed_set):
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(list(processed_set), f)

def parse_xbh_from_notes(notes_list):
    """
    Parses NCAA text notes (e.g., '2B - SHAW, G. 1; VOGEL, K. 1. HR - LANGFORD, H. 2.')
    Returns dictionaries mapping upper-case LASTNAME -> per_game_count
    """
    doubles, triples, hrs = {}, {}, {}
    if not notes_list:
        return doubles, triples, hrs

    text_block = " ".join([n.get("text", "") if isinstance(n, dict) else str(n) for n in notes_list])
    
    patterns = {
        '2b': (r'(?:2B|2b|Doubles)[:\-]\s*([^.]+)', doubles),
        '3b': (r'(?:3B|3b|Triples)[:\-]\s*([^.]+)', triples),
        'hr': (r'(?:HR|hr|Home Runs)[:\-]\s*([^.]+)', hrs),
    }
    
    for key, (pattern, target_dict) in patterns.items():
        match = re.search(pattern, text_block)
        if match:
            entries = match.group(1).split(';')
            for entry in entries:
                player_match = re.search(r'([A-Za-z\s\'\-]+)(?:\,\s*[A-Z]\.)?\s*(\d+)?', entry.strip())
                if player_match:
                    p_name = player_match.group(1).strip().upper()
                    count = int(player_match.group(2)) if player_match.group(2) else 1
                    target_dict[p_name] = count
                    
    return doubles, triples, hrs

def fetch_boxscore(game_id):
    url = f"https://ncaa-api.henrygd.me/game/{game_id}/boxscore"
    for attempt in range(2):
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                time.sleep(1.5)
        except Exception as e:
            time.sleep(0.5)
    return None

def process_game(game_id, date_str):
    box_data = fetch_boxscore(game_id)
    if not box_data:
        return []

    rows = []
    teams = box_data.get("teams", []) or box_data.get("teamBoxscore", [])
    for team_idx, team_data in enumerate(teams):
        team_name = team_data.get("name") or team_data.get("team", {}).get("name", "Unknown")
        opp_idx = 1 if team_idx == 0 else 0
        opp_name = "Unknown"
        if len(teams) > opp_idx:
            opp_name = teams[opp_idx].get("name") or teams[opp_idx].get("team", {}).get("name", "Unknown")

        notes = team_data.get("notes", []) or team_data.get("hittingNotes", [])
        d2b_map, d3b_map, hr_map = parse_xbh_from_notes(notes)

        players = team_data.get("playerStats") or team_data.get("stats") or []
        for p in players:
            last_name = p.get("lastName") or p.get("last_name") or p.get("name") or "Unknown"
            first_name = p.get("firstName") or p.get("first_name") or ""
            last_name_upper = str(last_name).strip().upper()

            rows.append({
                "date": date_str,
                "game_id": game_id,
                "team": team_name,
                "opponent": opp_name,
                "last_name": last_name,
                "first_name": first_name,
                "position": p.get("position", ""),
                "number": p.get("number", ""),
                "starter": p.get("starter", False),
                "participated": p.get("participated", True),
                "at_bats": float(p.get("ab") or p.get("atBats") or 0),
                "runs_scored": float(p.get("r") or p.get("runs") or 0),
                "hits": float(p.get("h") or p.get("hits") or 0),
                "rbi": float(p.get("rbi") or 0),
                "walks": float(p.get("bb") or p.get("walks") or 0),
                "strikeouts": float(p.get("so") or p.get("strikeouts") or 0),
                "batting_average": float(p.get("ba") or 0),
                "on_base_pct": float(p.get("obp") or 0),
                "putouts": float(p.get("po") or 0),
                "assists": float(p.get("a") or 0),
                "errors": float(p.get("e") or 0),
                "doubles": float(p.get("2b") or p.get("doubles") or d2b_map.get(last_name_upper, 0)),
                "triples": float(p.get("3b") or p.get("triples") or d3b_map.get(last_name_upper, 0)),
                "home_runs": float(p.get("hr") or p.get("homeRuns") or hr_map.get(last_name_upper, 0)),
                "doubles_hittingSeason": float(p.get("doubles_hittingSeason") or 0),
                "triples_hittingSeason": float(p.get("triples_hittingSeason") or 0),
                "home_runs_hittingSeason": float(p.get("home_runs_hittingSeason") or 0),
            })
    return rows

def extract_player_games(startDate="2026-02-05", endDate="2026-06-05"):
    processed_games = load_processed_games()
    start = datetime.strptime(startDate, "%Y-%m-%d")
    end = datetime.strptime(endDate, "%Y-%m-%d")
    delta = timedelta(days=1)

    fieldnames = [
        "date", "game_id", "team", "opponent", "last_name", "first_name", 
        "position", "number", "starter", "participated", "at_bats", "runs_scored", 
        "hits", "rbi", "walks", "strikeouts", "batting_average", "on_base_pct", 
        "putouts", "assists", "errors", "doubles", "triples", "home_runs",
        "doubles_hittingSeason", "triples_hittingSeason", "home_runs_hittingSeason"
    ]

    file_exists = os.path.exists(OUTPUT_CSV) and os.path.getsize(OUTPUT_CSV) > 0

    with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
            csvfile.flush()

        curr = start
        total_rows_added = 0

        while curr <= end:
            date_str = curr.strftime("%Y-%m-%d")
            year, month, day = curr.strftime("%Y"), curr.strftime("%m"), curr.strftime("%d")
            sb_url = f"https://ncaa-api.henrygd.me/scoreboard/softball/d1/{year}/{month}/{day}"
            
            try:
                sb_resp = requests.get(sb_url, timeout=10)
                if sb_resp.status_code == 200:
                    games = sb_resp.json().get("games", [])
                    games_written = 0

                    for entry in games:
                        game = entry.get("game", entry)
                        game_id = str(game.get("gameID", ""))
                        if not game_id or game_id in processed_games:
                            continue

                        rows = process_game(game_id, date_str)
                        if rows:
                            writer.writerows(rows)
                            csvfile.flush()
                            total_rows_added += len(rows)
                            games_written += 1

                        processed_games.add(game_id)
                        time.sleep(0.35)  # Enforce ~3 req/sec rate limit

                    save_processed_games(processed_games)
                    if games_written > 0:
                        print(f"[{date_str}] Saved {games_written} games ({total_rows_added} total rows in CSV).")
            except Exception as e:
                print(f"Error processing {date_str}: {e}")

            curr += delta

    print(f"Scraper finished. Total player rows saved: {total_rows_added}")

if __name__ == "__main__":
    extract_player_games()
