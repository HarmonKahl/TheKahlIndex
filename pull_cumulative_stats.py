import os
import time
import pandas as pd
from curl_cffi import requests

def fetch_cumulative_stats(output_path="cumulative_player_stats.csv"):
    print("Fetching cumulative player stats via curl_cffi Chrome impersonation...")
    
    url = "https://stats.ncaa.org/rankings/national_ranking"
    session = requests.Session(impersonate="chrome120")
    
    all_players = []
    
    for page in range(1, 15):
        params = {
            "academic_year": "2026",
            "sport_code": "WSB",
            "division": "1",
            "ranking_period": "101",
            "page": str(page)
        }
        
        try:
            response = session.get(url, params=params, timeout=20)
            if response.status_code != 200:
                print(f"Page {page} returned status code: {response.status_code}")
                break
                
            tables = pd.read_html(response.text)
            if not tables:
                break
                
            df = max(tables, key=len)
            if df.empty or len(df) < 5:
                break
                
            all_players.append(df)
            time.sleep(1.0)
            
        except Exception as e:
            print(f"Error fetching page {page}: {e}")
            break

    if not all_players:
        print("Warning: Could not pull cumulative stats. Creating baseline file.")
        if not os.path.exists(output_path):
            pd.DataFrame(columns=[
                "player_name", "team", "games_played", "ab", "hits", 
                "doubles", "triples", "hr", "walks", "strikeouts"
            ]).to_csv(output_path, index=False)
        return

    combined_df = pd.concat(all_players, ignore_index=True)
    combined_df.columns = [str(col).strip().lower() for col in combined_df.columns]
    
    column_mapping = {
        "player": "player_name",
        "name": "player_name",
        "team": "team",
        "g": "games_played",
        "gp": "games_played",
        "ab": "ab",
        "h": "hits",
        "2b": "doubles",
        "3b": "triples",
        "hr": "hr",
        "bb": "walks",
        "so": "strikeouts",
        "k": "strikeouts"
    }
    
    combined_df.rename(columns=column_mapping, inplace=True)
    
    target_cols = ["games_played", "ab", "hits", "doubles", "triples", "hr", "walks", "strikeouts"]
    for col in target_cols:
        if col not in combined_df.columns:
            combined_df[col] = 0
        else:
            combined_df[col] = pd.to_numeric(combined_df[col], errors="coerce").fillna(0)

    combined_df.drop_duplicates(subset=["player_name", "team"], inplace=True)
    combined_df.to_csv(output_path, index=False)
    print(f"Successfully saved {len(combined_df)} player records to {output_path}.")

if __name__ == "__main__":
    fetch_cumulative_stats()
