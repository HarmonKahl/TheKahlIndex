import os
import time
import requests
import pandas as pd

BASE_URL = "https://ncaa-api.henrygd.me"

def fetch_cumulative_stats(output_path="cumulative_player_stats.csv"):
    print("Fetching game boxscores from henrygd.me API to aggregate cumulative stats...")
    
    # 1. Fetch recent game IDs from scoreboard
    scoreboard_url = f"{BASE_URL}/scoreboard/softball/d1"
    game_ids = []
    
    try:
        res = requests.get(scoreboard_url, timeout=15)
        if res.status_code == 200:
            data = res.json()
            games = data.get("games", []) or data.get("scoreboard", [])
            for g in games:
                gid = g.get("game", {}).get("url", "") or g.get("id", "") or g.get("gameId", "")
                # Format game ID from URL path if needed
                if "/" in str(gid):
                    gid = str(gid).strip("/").split("/")[-1]
                if gid:
                    game_ids.append(gid)
    except Exception as e:
        print(f"Error fetching game IDs from scoreboard: {e}")

    print(f"Found {len(game_ids)} game box scores to parse.")
    
    player_totals = {}

    # 2. Iterate through box scores and extract hitting stats
    for gid in game_ids[:100]:  # Limit for fast execution
        box_url = f"{BASE_URL}/game/{gid}/boxscore"
        try:
            time.sleep(0.2)
            box_res = requests.get(box_url, timeout=10)
            if box_res.status_code != 200:
                continue
                
            box_data = box_res.json()
            teams_data = box_data.get("teams", []) or [box_data.get("home", {}), box_data.get("away", {})]
            
            for tdata in teams_data:
                team_name = tdata.get("name", "") or tdata.get("team", "") or "D1_Team"
                players = tdata.get("players", []) or tdata.get("batting", [])
                
                for p in players:
                    pname = p.get("name") or p.get("player") or p.get("playerName") or ""
                    if not pname or str(pname).lower() in ["totals", "team"]:
                        continue
                        
                    pname = str(pname).strip()
                    stats = p.get("stats", p)
                    
                    ab = int(stats.get("ab", 0) or 0)
                    h = int(stats.get("h", 0) or 0)
                    d2b = int(stats.get("d2b", stats.get("2b", 0)) or 0)
                    d3b = int(stats.get("d3b", stats.get("3b", 0)) or 0)
                    hr = int(stats.get("hr", 0) or 0)
                    bb = int(stats.get("bb", 0) or 0)
                    so = int(stats.get("so", stats.get("k", 0)) or 0)
                    
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

        except Exception:
            continue

    # Build output CSV
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
