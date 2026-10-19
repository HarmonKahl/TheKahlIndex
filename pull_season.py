import os
import requests
import pandas as pd
from datetime import datetime, timedelta

BASE_URL = "https://ncaa-api.henrygd.me"
START_DATE = datetime(2026, 2, 5)
END_DATE = datetime(2026, 6, 10)

def fetch_team_season_data(games_output="games_season.csv", team_games_output="team_games_season.csv"):
    print(f"--- Fetching NCAA Game Results ({START_DATE.strftime('%Y-%m-%d')} to {END_DATE.strftime('%Y-%m-%d')}) ---")
    
    all_games = []
    current_date = START_DATE

    while current_date <= END_DATE:
        date_str = current_date.strftime("%Y/%m/%d")
        url = f"{BASE_URL}/scoreboard/softball/d1/{date_str}"
        
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                games_list = data.get("games", []) or data.get("scoreboard", [])
                
                for g in games_list:
                    game_info = g.get("game", g) if isinstance(g, dict) else {}
                    
                    home_team = game_info.get("home", {}).get("names", {}).get("short", "")
                    away_team = game_info.get("away", {}).get("names", {}).get("short", "")
                    
                    home_score = game_info.get("home", {}).get("score", None)
                    away_score = game_info.get("away", {}).get("score", None)
                    
                    if home_score is not None and away_score is not None and home_team and away_team:
                        try:
                            hs = int(home_score)
                            aws = int(away_score)
                            
                            all_games.append({"team": home_team, "opponent": away_team, "runs_scored": hs, "runs_against": aws})
                            all_games.append({"team": away_team, "opponent": home_team, "runs_scored": aws, "runs_against": hs})
                        except ValueError:
                            continue
        except Exception:
            pass

        current_date += timedelta(days=1)

    if not all_games:
        print("Warning: No games found for the specified date range. Generating baseline files.")
        generate_fallback_files(games_output, team_games_output)
        return

    games_df = pd.DataFrame(all_games)

    team_stats = []
    for team_name, group in games_df.groupby("team"):
        gp = len(group)
        rs = group["runs_scored"].sum()
        ra = group["runs_against"].sum()
        ra7 = (ra / (gp * 7)) * 7 if gp > 0 else 0.0
        rs7 = (rs / (gp * 7)) * 7 if gp > 0 else 0.0
        
        team_stats.append({
            "team": team_name,
            "games_played": gp,
            "runs_scored": rs,
            "runs_against": ra,
            "runs_against_per_7": round(ra7, 2),
            "runs_scored_per_7": round(rs7, 2)
        })

    teams_df = pd.DataFrame(team_stats)
    team_ra_map = teams_df.set_index("team")["runs_against_per_7"].to_dict()
    
    def calc_opp_ra7(row):
        t = row["team"]
        opps = games_df[games_df["team"] == t]["opponent"]
        opp_ras = [team_ra_map[o] for o in opps if o in team_ra_map]
        return round(sum(opp_ras) / len(opp_ras), 2) if opp_ras else teams_df["runs_against_per_7"].mean()

    teams_df["opp_runs_against_per_7"] = teams_df.apply(calc_opp_ra7, axis=1)

    games_df.to_csv(games_output, index=False)
    teams_df.to_csv(team_games_output, index=False)
    print(f"Successfully saved {len(games_df)} game records and {len(teams_df)} team summaries.")

def generate_fallback_files(games_output, team_games_output):
    if not os.path.exists(games_output):
        pd.DataFrame(columns=["team", "opponent", "runs_scored", "runs_against"]).to_csv(games_output, index=False)
    if not os.path.exists(team_games_output):
        pd.DataFrame(columns=["team", "games_played", "runs_scored", "runs_against", "runs_against_per_7", "runs_scored_per_7", "opp_runs_against_per_7"]).to_csv(team_games_output, index=False)

if __name__ == "__main__":
    fetch_team_season_data()
