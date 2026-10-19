import os
import time
import requests
import pandas as pd

# Standard headers to mimic a browser request to NCAA endpoints
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def fetch_cumulative_stats(output_path="cumulative_player_stats.csv"):
    """
    Fetches Division-I cumulative player hitting statistics from official 
    NCAA endpoints, extracts extra-base hits (2B, 3B, HR), normalizes columns, 
    and saves/overwrites cumulative_player_stats.csv.
    """
    print("Fetching cumulative D1 player hitting stats...")
    
    # Base URL for NCAA Division I Softball Individual Batting Stats
    # Note: NCAA statistical category 101 corresponds to Batting Leaderboards
    base_url = "https://stats.ncaa.org/rankings/national_ranking"
    
    all_players = []
    
    # Iterate through leaderboard pages (typically 1 to 15 pages cover qualified D1 hitters)
    # You can expand the range if you want deep bench listings
    max_pages = 10 
    
    for page in range(1, max_pages + 1):
        params = {
            "academic_year": "2026",  # Update to target season year
            "sport_code": "WSB",       # Women's Softball
            "division": "1",
            "ranking_period": "101",
            "page": str(page)
        }
        
        try:
            print(f"Requesting page {page} of cumulative player stats...")
            response = requests.get(base_url, headers=HEADERS, params=params, timeout=15)
            
            if response.status_code != 200:
                print(f"Failed page {page} with status code: {response.status_code}")
                break
                
            # Parse HTML tables on the page
            tables = pd.read_html(response.text)
            if not tables:
                print(f"No tables found on page {page}.")
                break
                
            # The primary leaderboard is usually the largest table on the page
            df = max(tables, key=len)
            
            if df.empty or len(df) < 5:
                print(f"Reached end of data at page {page}.")
                break
                
            all_players.append(df)
            
            # Politeness delay to prevent rate limits
            time.sleep(1.0)
            
        except Exception as e:
            print(f"Error fetching page {page}: {e}")
            break

    if not all_players:
        print("Error: No cumulative player stats fetched. Exiting without overwriting file.")
        return

    # Combine all scraped pages into a single DataFrame
    combined_df = pd.concat(all_players, ignore_index=True)
    
    # Clean column names (strip whitespace and lower case)
    combined_df.columns = [str(col).strip().lower() for col in combined_df.columns]
    
    # Standardize varying NCAA column headers into expected pipeline keys
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
    
    # Ensure mandatory numerical columns exist and convert to numeric
    target_cols = ["games_played", "ab", "hits", "doubles", "triples", "hr", "walks", "strikeouts"]
    for col in target_cols:
        if col not in combined_df.columns:
            combined_df[col] = 0
        else:
            combined_df[col] = pd.to_numeric(combined_df[col], errors="coerce").fillna(0)

    # Clean text columns
    if "player_name" in combined_df.columns:
        combined_df["player_name"] = combined_df["player_name"].astype(str).str.strip()
    if "team" in combined_df.columns:
        combined_df["team"] = combined_df["team"].astype(str).str.strip()

    # Deduplicate in case overlapping pages were scraped
    combined_df.drop_duplicates(subset=["player_name", "team"], inplace=True)

    # Overwrite cumulative_player_stats.csv with the fresh snapshot
    combined_df.to_csv(output_path, index=False)
    print(f"Successfully saved {len(combined_df)} player cumulative stat records to {output_path}.")

if __name__ == "__main__":
    fetch_cumulative_stats()
