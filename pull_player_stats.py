import os
import re
import csv
import json
import time
import requests
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

CHECKPOINT_FILE = "processed_games.json"
OUTPUT_CSV = "player_games_season.csv"
MAX_WORKERS = 3  # Matches NCAA API safe rate limit

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
    try:
        # Strict 3-second timeout to prevent hanging connections
        resp = requests.get(url, timeout=3)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None

def process_single_game(game_id, date_str):
    box_data = fetch_boxscore(game_id)
    if not box_data:
        return game_id, []

    rows = []
    teams = box_data.get("teams", []) or box_data.get("teamBoxscore", [])
    for team_idx, team_data in enumerate(teams):
        team_name = team_data.get("name") or team_data.get("team", {}).get("name", "Unknown")
        opp_idx = 1 if team_idx == 0 else 0
        opp_name = "Unknown"
        if len(teams) > opp_idx:
            opp_name = teams[opp_idx].get("name") or teams
