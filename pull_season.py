import os
import sys
import requests
import pandas as pd

_session = requests.Session()

def get_hitting_category_id():
    """Queries the NCAA stats directory to automatically locate the Batting Average/Hitting category ID."""
    base_url = "https://ncaa-api.henrygd.me/stats/softball/d1/current/individual"
    try:
        resp = _session.get(base_url, timeout=10)
        resp.raise_for_status()
        categories = resp.json()
        
        # Search available categories for hitting/batting
        for cat in categories:
            cat_name = str(cat.get("title") or cat.get("name") or "").lower()
            if "batting" in cat_name or "hits" in cat_name or "average" in cat_name:
                cat_id = str(cat.get("id") or cat.get("category_id"))
                print(f"Discovered hitting category ID: {cat_id} ({cat_name})")
                return cat_id
    except Exception as e:
        print(f"Could not auto-detect category ID ({e}). Falling back to standard category 148.")
    
    return "148"

def fetch_season_player_stats(out_dir="."):
    print("\n--- Fetching NCAA Season Player Leaderboard ---")
    category_id = get_hitting_category_id()
    
    all_players = []
    page = 1

    while True:
        url = f"https://ncaa-api.henrygd.me/stats/softball/d1/current/individual/{category_id}?page={page}"
        try:
            resp = _session.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"Finished fetching player stats on page {page}: {e}")
            break

        stats_list = data.get("stats", []) or data.get("data", [])
        if not stats_list:
            print(f"No additional stats found on page {page}.")
            break

        for row in stats_list:
            def _clean(val):
                if val in (None, "", "-"):
                    return 0
                try:
                    return int(float(val))
                except (ValueError, TypeError):
                    return 0

            all_players.append({
                "player_name": row.get("name") or row.get("Player") or "Unknown",
                "team": row.get("team") or row.get("Team") or "Unknown",
                "G": _clean(row.get("g") or row.get("G")),
                "AB": _clean(row.get("ab") or row.get("AB")),
                "H": _clean(row.get("h") or row.get("H")),
                "2B": _clean(row.get("d2") or row.get("2b") or row.get("2B")),
                "3B": _clean(row.get("d3") or row.get("3b") or row.get("3B")),
                "HR": _clean(row.get("hr") or row.get("HR")),
                "BB": _clean(row.get("bb") or row.get("BB"))
            })

        print(f"Processed player stats page {page} ({len(stats_list)} players logged)")
        
        total_pages = data.get("pageCount") or data.get("totalPages")
        if total_pages and page >= int(total_pages):
            break
            
        page += 1

    if all_players:
        output_path = os.path.join(out_dir, "player_boxscores_2026.csv")
        pd.DataFrame(all_players).to_csv(output_path, index=False)
        print(f"Saved {len(all_players)} player records to {output_path} successfully!")
    else:
        print("Warning: No player stats were retrieved.")

if __name__ == "__main__":
    fetch_season_player_stats()
