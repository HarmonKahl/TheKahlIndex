import os
import time
import requests
import pandas as pd

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://stats.ncaa.org/"
}

def fetch_cumulative_stats(output_path="cumulative_player_stats.csv"):
    print("Fetching cumulative D1 player hitting stats...")
    base_url = "https://stats.ncaa.org/rankings/national_ranking"
    
    all_players = []
    session = requests.Session()
    
    # Optional: Set current academic year dynamically or fixed
    academic_year = "2026"
    
    for page in range(1, 11):
        params = {
            "academic_year": academic_year,
            "sport_code": "WSB",
            "division": "1",
            "ranking_period": "101",
            "page": str(page)
        }
        
        try:
            print(f"Requesting page {page} of cumulative player stats...")
            response = session.get(base_url, headers=HEADERS, params=params, timeout=15)
            
            if response.status_code != 200:
                print(f"Failed page {page} with status code: {response.status_code}")
                break
                
            tables = pd.read_html(response.text)
            if not tables:
                print(f"No tables found on page {page}.")
                break
                
            df = max(tables, key=len)
            if df.empty or len(df) < 5:
                break
                
            all_players.append(df)
            time.sleep(1.5)
            
        except Exception as e:
            print(f"Error fetching page {page}: {e}")
            break

    if not all_players:
        print("Warning: Could not fetch new cumulative player stats.")
        # Ensure file exists so git add doesn't throw a fatal error
        if not os.path.exists(output_path):
            pd.DataFrame(columns=["player_name", "team", "games_played", "ab", "hits", "doubles", "triples", "hr", "walks", "strikeouts"]).to_csv(output_path, index=False)
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

    if "player_name" in combined_df.columns:
        combined_df["player_name"] = combined_df["player_name"].astype(str).str.strip()
    if "team" in combined_df.columns:
        combined_df["team"] = combined_df["team"].astype(str).str.strip()

    combined_df.drop_duplicates(subset=["player_name", "team"], inplace=True)
    combined_df.to_csv(output_path, index=False)
    print(f"Successfully saved {len(combined_df)} player cumulative stat records to {output_path}.")

if __name__ == "__main__":
    fetch_cumulative_stats()
