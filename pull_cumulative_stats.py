import os
import time
import json
import requests
import pandas as pd
from datetime import datetime, timedelta

BASE_URL = "https://ncaa-api.henrygd.me"
START_DATE = datetime(2026, 2, 5)
END_DATE = datetime(2026, 6, 10)
CACHE_FILE = "boxscore_cache.json"

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(cache):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f)
    except Exception as e:
        print(f"Error saving cache: {e}")

def fetch_cumulative_stats(output_path="cumulative_player_stats.csv"):
    print(f"Fetching game boxscores ({START_DATE.strftime('%Y-%m-%d')} to {END_DATE.strftime('%Y-%m-%d')})...")
    
    # 1. Gather Game IDs
    game_ids = []
    current_date = START_DATE
    
    while current_date <= END_DATE:
        date_str = current_date.strftime("%Y/%m/%d")
        url = f"{BASE_URL}/scoreboard/softball/d1/{date_str}"
        try:
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                data = res.json()
                games = data.get("games", []) or data.get("scoreboard", [])
                for g in games:
                    game_info = g.get("game", g) if isinstance(g, dict) else {}
                    gid = game_info.get("url", "") or game_info.get("id", "") or game_info.get("gameId", "")
                    if "/" in str(gid):
                        gid = str(gid).strip("/").split("/")[-1]
                    if gid and str(gid) not in game_ids:
                        game_ids.append(str(gid))
        except Exception:
            pass

        current_date += timedelta(days=1)

    print(f"Found {len(game_ids)} game box scores across the date range.")
    
    cache = load_cache()
    player_totals = {}

    # 2. Process Games
    fetched_count = 0
    for gid in game_ids:
        if gid in cache:
            box_data = cache[gid]
        else:
            box_url = f"{BASE_URL}/game/{gid}/boxscore"
            try:
                time.sleep(0.05)
                box_res = requests.get(box_url, timeout=10)
                if box_res.status_code != 200:
                    continue
                box_data = box_res.json()
                cache[gid] = box_data
                fetched_count += 1
                if fetched_count % 100 == 0:
                    save_cache(cache)
            except Exception:
                continue

        if not box_data:
            continue

        # Flexible schema mapping for henrygd.me
        teams = (
            box_data.get("teamsBoxscore") or 
            box_data.get("teams") or 
            box_data.get("boxscore", {}).get("teams") or 
            []
        )
        
        for tdata in teams:
            team_name = (
                tdata.get("name") or 
                tdata.get("teamName") or 
                tdata.get("team", {}).get("name") or 
                "D1_Team"
            )
            
            # Locate hitting entries
            player_entries = []
            if "players" in tdata:
                player_entries = tdata["players"]
            elif "playerStats" in tdata:
                player_entries = tdata["playerStats"]
            elif "tables" in tdata:
                for tbl in tdata["tables"]:
                    if "hit" in str(tbl.get("title", "")).lower() or "bat" in str(tbl.get("title", "")).lower():
                        player_entries.extend(tbl.get("data", []))
            
            for p in player_entries:
                pname = p.get("name") or p.get("player") or p.get("playerName") or p.get("firstName", "") + " " + p.get("lastName", "")
                pname = str(pname).strip()
                
                if not pname or pname.lower() in ["totals", "team", "total"]:
                    continue
                    
                stats = p.get("stats", p)
                if isinstance(stats, list):
                    continue
                    
                ab = int(pd.to_numeric(stats.get("ab", stats.get("AB", 0)), errors="coerce") or 0)
                h = int(pd.to_numeric(stats.get("h", stats.get("H", 0)), errors="coerce") or 0)
                d2b = int(pd.to_numeric(stats.get("d2b", stats.get("2b", stats.get("2B", 0))), errors="coerce") or 0)
                d3b = int(pd.to_numeric(stats.get("d3b", stats.get("3b", stats.get("3B", 0))), errors="coerce") or 0)
                hr = int(pd.to_numeric(stats.get("hr", stats.get("HR", 0)), errors="coerce") or 0)
                bb = int(pd.to_numeric(stats.get("bb", stats.get("BB", 0)), errors="coerce") or 0)
                so = int(pd.to_numeric(stats.get("so", stats.get("k", stats.get("SO", 0))), errors="coerce") or 0)
                
                key = (pname, team_name)
                if key not in player_totals:
                    player_totals[key] = {
                        "games_played": 0, "ab": 0, "hits": 0,
                        "doubles": 0, "triples": 0, "hr": 0,
                        "walks": 0, "strikeouts": 0
                    }
                    
                player_totals[key]["games_played"] += 1
                player_totals[key]["ab"] += ab
                player_totals[key]["hits"] += h
                player_totals[key]["doubles"] += d2b
                player_totals[key]["triples"] += d3b
                player_totals[key]["hr"] += hr
                player_totals[key]["walks"] += bb
                player_totals[key]["strikeouts"] += so

    save_cache(cache)

    rows = []
    for (pname, team), s in player_totals.items():
        rows.append({
            "player_name": pname,
            "team": team,
            "games_played": s["games_played"],
            "ab": s["ab"],
            "hits": s["hits"],
            "doubles": s["doubles"],
            "triples": s["triples"],
            "hr": s["hr"],
            "walks": s["walks"],
            "strikeouts": s["strikeouts"]
        })

    df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=[
        "player_name", "team", "games_played", "ab", "hits", 
        "doubles", "triples", "hr", "walks", "strikeouts"
    ])

    df.to_csv(output_path, index=False)
    print(f"Successfully generated cumulative player stats for {len(df)} players.")

if __name__ == "__main__":
    fetch_cumulative_stats()
