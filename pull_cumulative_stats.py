import os
import time
import io
import pandas as pd
from curl_cffi import requests

def fetch_cumulative_stats(output_path="cumulative_player_stats.csv"):
    print("Fetching cumulative player stats via curl_cffi...")
    
    # Official NCAA ranking list endpoint with explicit category parameters
    url = "https://stats.ncaa.org/rankings/change_sport_year_div"
    session = requests.Session(impersonate="chrome120")
    
    all_players = []
    
    # Category 20 corresponds to national individual batting stats
    for page in range(1, 15):
        params = {
            "academic_year": "2026",
            "sport_code": "WSB",
            "division": "1",
            "rate": "1",
            "stat_seq": "20",
            "page": str(page)
        }
        
        try:
            response = session.get(url, params=params, timeout=20)
            if response.status_code != 200:
                print(f"Page {page} status: {response.status_code}")
                break
                
            tables = pd.read_html(io.StringIO(response.text))
            
            # Filter for the main player stats table
            player_table = None
            for tbl in tables:
                col_str = "".join([str(c).lower() for c in tbl.columns])
                if "player" in col_str or "name" in col_str:
                    player_table = tbl
                    break
                    
            if player_table is None or player_table.empty:
                print(f"No player data table found on page {page}.")
                break
                
            all_players.append(player_table)
            time.sleep(1.0)
            
        except Exception as e:
            print(f"Error on page {page}: {e}")
            break

    if not all_players:
        print("Warning: Could not pull cumulative stats table. Generating empty structure.")
        if not os.path.exists(output_path):
            pd.DataFrame(columns=["player_name", "team", "games_played", "ab", "hits", "doubles", "triples", "hr", "walks", "strikeouts"]).to_csv(output_path, index=False)
        return

    combined_df = pd.concat(all_players, ignore_index=True)
    combined_df.columns = [str(col).strip().lower() for col in combined_df.columns]
    
    column_mapping = {
        "player": "player_name", "name": "player_name",
        "team": "team", "cl": "year",
        "g": "games_played", "gp": "games_played",
        "ab": "ab", "h": "hits", "2b": "doubles", 
        "3b": "triples", "hr": "hr", "bb": "walks", "so": "strikeouts"
    }
    
    combined_df.rename(columns=column_mapping, inplace=True)
    
    target_cols = ["games_played", "ab", "hits", "doubles", "triples", "hr", "walks", "strikeouts"]
    for col in target_cols:
        if col in combined_df.columns:
            combined_df[col] = pd.to_numeric(combined_df[col], errors="coerce").fillna(0).astype(int)
        else:
            combined_df[col] = 0

    combined_df.drop_duplicates(subset=["player_name", "team"], inplace=True)
    combined_df.to_csv(output_path, index=False)
    print(f"Successfully saved {len(combined_df)} player cumulative records to {output_path}.")

if __name__ == "__main__":
    fetch_cumulative_stats()
