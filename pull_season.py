import os
import sys
import requests
import pandas as pd

_session = requests.Session()

def discover_hitting_url():
    """Fetches available stat categories from NCAA API and returns the correct endpoint URL."""
    base_url = "https://ncaa-api.henrygd.me/stats/softball/d1/current/individual"
    print(f"Discovering stat categories from {base_url}...")
    
    try:
        resp = _session.get(base_url, timeout=10)
        resp.raise_for_status()
        categories = resp.json()
        
        # Look through available categories for batting/hitting metrics
        for cat in categories:
            title = str(cat.get("title") or cat.get("name") or "").lower()
            cat_id = str(cat.get("id") or cat.get("category_id") or cat.get("slug") or "")
            
            if any(term in title for term in ["batting average", "hits", "slugging"]):
                print(f"Found category: '{title}' (ID/Slug: {cat_id})")
                # Return path if provided, else construct endpoint
                if "path" in cat:
                    return f"https://ncaa-api.henrygd.me/stats/softball/d1/current/{cat['path']}"
                return f"https://ncaa-api.henrygd.me/stats/softball/d1/current/individual/{cat_id}"
                
    except Exception as e:
        print(f"Category discovery warning: {e}")

    # Common fallback slugs used by NCAA stats API for softball hitting
    print("Using standard fallback category slug: 'batting-average'")
    return "https://ncaa-api.henrygd.me/stats/softball/d1/current/individual/batting-average"

def fetch_season_player_stats(out_dir="."):
    print("\n--- Fetching NCAA Season Player Leaderboard ---")
    target_url = discover_hitting_url()
    
    all_players = []
    page = 1

    while True:
        # Check if URL already has query parameters
        sep = "&" if "?" in target_url else "?"
        page_url = f"{target_url}{sep}page={page}"
        
        try:
            resp = _session.get(page_url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"Stopped on page {page}: {e}")
            break

        stats_list = data.get("stats", []) or data.get("data", []) or data.get("rankings", [])
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

            # Safe extraction for various NCAA API player response formats
            player_name = (
                row.get("name") 
                or row.get("Player") 
                or row.get("playerName")
                or row.get("player", {}).get("name") 
                or "Unknown"
            )
            team_name = (
                row.get("team") 
                or row.get("Team") 
                or row.get("school") 
                or row.get("teamName") 
                or "Unknown"
            )

            all_players.append({
                "player_name": player_name,
                "team": team_name,
                "G": _clean(row.get("g") or row.get("G") or row.get("games")),
                "AB": _clean(row.get("ab") or row.get("AB") or row.get("atBats")),
                "H": _clean(row.get("h") or row.get("H") or row.get("hits")),
                "2B": _clean(row.get("d2") or row.get("2b") or row.get("2B") or row.get("doubles")),
                "3B": _clean(row.get("d3") or row.get("3b") or row.get("3B") or row.get("triples")),
                "HR": _clean(row.get("hr") or row.get("HR") or row.get("homeRuns")),
                "BB": _clean(row.get("bb") or row.get("BB") or row.get("walks"))
            })

        print(f"Processed page {page} ({len(stats_list)} players logged)")
        
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
