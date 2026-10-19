import os
import requests
import pandas as pd

API_BASE = "https://ncaa-api.henrygd.me/stats/softball/d1/current/individual"

def fetch_cumulative_stats(output_path="cumulative_player_stats.csv"):
    print("Fetching cumulative player stats from henrygd.me API...")
    
    # Category path for Batting / Hits / Total Bases
    # Defaulting to national individual hitting stats
    url = f"{API_BASE}/batting"
    
    all_players = []
    
    # Paginate through player leaderboard pages
    for page in range(1, 15):
        try:
            response = requests.get(url, params={"page": page}, timeout=15)
            if response.status_code != 200:
                # Fall back to root hitting endpoint if category slug varies
                if page == 1:
                    response = requests.get(API_BASE, timeout=15)
                else:
                    break
            
            data = response.json()
            players = data.get("stats", []) or data.get("data", [])
            
            if not players:
                break
                
            for p in players:
                # Parse fields safely from API response
                all_players.append({
                    "player_name": p.get("player") or p.get("name") or p.get("playerName", ""),
                    "team": p.get("team") or p.get("school", ""),
                    "games_played": int(p.get("g") or p.get("gp") or 0),
                    "ab": int(p.get("ab") or 0),
                    "hits": int(p.get("h") or 0),
                    "doubles": int(p.get("d2b") or p.get("2b") or 0),
                    "triples": int(p.get("d3b") or p.get("3b") or 0),
                    "hr": int(p.get("hr") or 0),
                    "walks": int(p.get("bb") or 0),
                    "strikeouts": int(p.get("so") or p.get("k") or 0)
                })
                
        except Exception as e:
            print(f"Error fetching page {page}: {e}")
            break

    if not all_players:
        print("Warning: No player data returned from API.")
        return

    df = pd.DataFrame(all_players)
    df.drop_duplicates(subset=["player_name", "team"], inplace=True)
    df.to_csv(output_path, index=False)
    print(f"Successfully saved {len(df)} cumulative player records to {output_path}.")

if __name__ == "__main__":
    fetch_cumulative_stats()
