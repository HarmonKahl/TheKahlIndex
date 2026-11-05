import os
import re
import csv
import json
import time
import requests
from datetime import datetime, timedelta

CHECKPOINT_FILE = "_completed_dates_players.txt"
OUTPUT_CSV = "player_games_season.csv"

def load_completed_dates():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            return {line.strip() for line in f if line.strip()}
    return set()

def save_completed_date(date_str):
    with open(CHECKPOINT_FILE, "a", encoding="utf-8") as f:
        f.write(f"{date_str}\n")

def parse_xbh_from_notes(notes_list):
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
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            time.sleep(0.4)
    return None

def process_game(game_id, date_str):
    box_data = fetch_boxscore(game_id)
    if not box_data:
        return []

    if "boxscore" in box_data and isinstance(box_data["boxscore"], dict):
        box_data = box_data["boxscore"]

    teams = box_data.get("teams") or box_data.get("teamBoxscore") or []
    rows = []
    
    for team_idx, team_data in enumerate(teams):
        team_name = team_data.get("name") or team_data.get("team", {}).get("name", "Unknown")
        opp_idx = 1 if team_idx == 0 else 0
        opp_name = "Unknown"
        if len(teams) > opp_idx:
            opp_name = teams[opp_idx].get("name") or teams[opp_idx].get("team", {}).get("name", "Unknown")

        notes = team_data.get("notes") or team_data.get("hittingNotes") or []
        d2b_map, d3b_map, hr_map = parse_xbh_from_notes(notes)

        players = (
            team_data.get("playerStats") 
            or team_data.get("stats") 
            or team_data.get("players")
            or team_data.get("hittingStats")
            or []
        )

        for p in players:
            p_obj = p.get("player", p) if isinstance(p, dict) else {}
            last_name = p_obj.get("lastName") or p_obj.get("last_name") or p_obj.get("name") or "Unknown"
            first_name = p_obj.get("firstName") or p_obj.get("first_name") or ""
            last_name_upper = str(last_name).strip().upper()

            def safe_float(val):
                try:
                    return float(val) if val is not None else 0.0
                except (ValueError, TypeError):
                    return 0.0

            rows.append({
                "date": date_str,
                "game_id": game_id,
                "team": team_name,
                "opponent": opp_name,
                "last_name": last_name,
                "first_name": first_name,
                "position": p_obj.get("position", ""),
                "number": p_obj.get("number", ""),
                "starter": p_obj.get("starter", False),
                "participated": p_obj.get("participated", True),
                "at_bats": safe_float(p_obj.get("ab") or p_obj.get("atBats")),
                "runs_scored": safe_float(p_obj.get("r") or p_obj.get("runs")),
                "hits": safe_float(p_obj.get("h") or p_obj.get("hits")),
                "rbi": safe_float(p_obj.get("rbi")),
                "walks": safe_float(p_obj.get("bb") or p_obj.get("walks")),
                "strikeouts": safe_float(p_obj.get("so") or p_obj.get("strikeouts")),
                "batting_average": safe_float(p_obj.get("ba")),
                "on_base_pct": safe_float(p_obj.get("obp")),
                "putouts": safe_float(p_obj.get("po")),
                "assists": safe_float(p_obj.get("a")),
                "errors": safe_float(p_obj.get("e")),
                "doubles": safe_float(p_obj.get("2b") or p_obj.get("doubles") or d2b_map.get(last_name_upper, 0)),
                "triples": safe_float(p_obj.get("3b") or p_obj.get("triples") or d3b_map.get(last_name_upper, 0)),
                "home_runs": safe_float(p_obj.get("hr") or p_obj.get("homeRuns") or hr_map.get(last_name_upper, 0)),
                "doubles_hittingSeason": safe_float(p_obj.get("doubles_hittingSeason")),
                "triples_hittingSeason": safe_float(p_obj.get("triples_hittingSeason")),
                "home_runs_hittingSeason": safe_float(p_obj.get("home_runs_hittingSeason")),
            })
    return rows

def extract_player_games(startDate="2026-02-05", endDate="2026-06-05"):
    completed = load_completed_dates()
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
        total_rows_written = 0

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
                sb_resp = requests.get(sb_url, timeout=10)
                if sb_resp.status_code == 200:
                    payload = sb_resp.json()
                    games_list = payload.get("games", []) if isinstance(payload, dict) else []
                    
                    game_ids = []
                    for entry in games_list:
                        g_obj = entry.get("game", entry) if isinstance(entry, dict) else {}
                        gid = str(g_obj.get("gameID") or g_obj.get("id") or "").strip()
                        if "/" in gid:
                            gid = gid.rstrip("/").split("/")[-1]
                        if gid:
                            game_ids.append(gid)

                    day_rows = 0
                    for gid in game_ids:
                        rows = process_game(gid, date_str)
                        if rows:
                            writer.writerows(rows)
                            csvfile.flush()
                            day_rows += len(rows)
                        time.sleep(0.35)

                    save_completed_date(date_str)
                    total_rows_written += day_rows
                    print(f"[{date_str}] Found {len(game_ids)} games; saved {day_rows} player rows (Total: {total_rows_written}).")
                else:
                    print(f"[{date_str}] Status {sb_resp.status_code}")
            except Exception as e:
                print(f"Error on {date_str}: {e}")

            curr += delta

    print(f"Player stats extraction finished. Total rows saved: {total_rows_written}")

if __name__ == "__main__":
    extract_player_games()
