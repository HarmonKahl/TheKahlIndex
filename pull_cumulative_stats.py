import os
import requests
import pandas as pd

# Community Mirror API for NCAA Stats
BASE_URL = "https://ncaa-api.henrygd.me/stats/softball/d1/current/individual"

def fetch_cumulative_stats(output_path="cumulative_player_stats.csv"):
    """
    Fetches cumulative Division-I hitting stats via the henrygd.me NCAA API proxy,
    normalizes key columns, and saves/overwrites cumulative_player_stats.csv.
    """
    print("Fetching cumulative player stats from henrygd.me API...")
    
    # Primary hitting category endpoints to query
    endpoints = [
        f"{BASE_URL}/batting-average",
        f"{BASE_URL}/home-runs",
        BASE_URL  # Fallback to root individual stats endpoint
    ]
    
    all_players = []
    
    for url in endpoints:
        print(f"Trying API endpoint: {url}")
        success = False
        
        # Paginate through player leaderboard pages
        for page in range(1, 15):
            try:
                response = requests.get(url, params={"page": page}, timeout=15)
                
                if response.status_code != 200:
                    break
                
                data = response.json()
                # Parse list of player objects from API schema variations
                players = data.get("stats", []) or data.get("data", []) or data.get("rankings", [])
                
                if not players:
                    break
                    
                success = True
                for p in players:
                    # Clean/extract fields from API JSON response
                    player_name = p.get("player") or p.get("name") or p.get("playerName") or ""
                    team = p.get("team") or p.get("school") or p.get("teamName") or ""
                    
                    if not player_name:
                        continue

                    all_players.append({
                        "player_name": str(player_name).strip(),
                        "team": str(team).strip(),
                        "games_played": int(p.get("g") or p.get("gp") or p.get("games") or 0),
                        "ab": int(p.get("ab") or p.get("atBats") or 0),
                        "hits": int(p.get("h") or p.get("hits") or 0),
                        "doubles": int(p.get("d2b") or p.get("2b") or p.get("doubles") or 0),
                        "triples": int(p.get("d3b") or p.get("3b") or p.get("triples") or 0),
                        "hr": int(p.get("hr") or p.get("homeRuns") or 0),
                        "walks": int(p.get("bb") or p.get("walks") or 0),
                        "strikeouts": int(p.get("so") or p.get("k") or p.get("strikeouts") or 0)
                    })
                    
            except Exception as e:
                print(f"Error requesting page {page} from {url}: {e}")
                break
                
        if success and len(all_players) > 0:
            print(f"Successfully retrieved stats from endpoint: {url}")
            break

    if not all_players:
        print("Warning: No player cumulative stats fetched from API.")
        # Ensure dummy file structure exists so downstream steps do not crash git
        if not os.path.exists(output_path):
            pd.DataFrame(columns=[
                "player_name", "team", "games_played", "ab", "hits", 
                "doubles", "triples", "hr", "walks", "strikeouts"
            ]).to_csv(output_path, index=False)
        return

    # Convert to DataFrame
    df = pd.DataFrame(all_players)

    # Ensure numeric types
    numeric_cols = ["games_played", "ab", "hits", "doubles", "triples", "hr", "walks", "strikeouts"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    # Deduplicate in case of overlapping API pages
    df.drop_duplicates(subset=["player_name", "team"], inplace=True)

    # Save fresh snapshot to CSV
    df.to_csv(output_path, index=False)
    print(f"Successfully saved {len(df)} player cumulative stat records to {output_path}.")

if __name__ == "__main__":
    fetch_cumulative_stats()
