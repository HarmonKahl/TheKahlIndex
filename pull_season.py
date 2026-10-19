import os
import time
import cloudscraper
import pandas as pd
from bs4 import BeautifulSoup

YEAR = "2026"

def fetch_team_season_data(
    games_output="games_season.csv", 
    team_games_output="team_games_season.csv"
):
    print(f"--- Fetching NCAA Team Game Results and Metrics for {YEAR} ---")
    
    index_url = "https://stats.ncaa.org/team/inst_team_list"
    params = {
        "academic_year": YEAR,
        "conf_id": "-1",
        "division": "1",
        "sport_code": "WSB"
    }
    
    # Initialize cloudscraper session to bypass 403 blocks
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'darwin',
            'desktop': True
        }
    )
    
    try:
        response = scraper.get(index_url, params=params, timeout=20)
        if response.status_code != 200:
            print(f"Failed to load team list page. Status: {response.status_code}")
            generate_fallback_files(games_output, team_games_output)
            return

        soup = BeautifulSoup(response.text, "html.parser")
        team_links = []
        
        for a in soup.find_all("a", href=True):
            if "/team/" in a["href"] and "stats" not in a["href"]:
                team_name = a.text.strip()
                team_url = "https://stats.ncaa.org" + a["href"]
                if team_name and team_url not in [t[1] for t in team_links]:
                    team_links.append((team_name, team_url))
                    
        print(f"Found {len(team_links)} Division-I teams.")

    except Exception as e:
        print(f"Error fetching team directory: {e}")
        generate_fallback_files(games_output, team_games_output)
        return

    all_games = []
    team_summaries = []

    for team_name, url in team_links:
        try:
            time.sleep(1.0)
            res = scraper.get(url, timeout=15)
            if res.status_code != 200:
                continue

            tables = pd.read_html(res.text)
            if not tables:
                continue

            schedule_df = max(tables, key=len)
            schedule_df.columns = [str(c).strip().lower() for c in schedule_df.columns]

            opponent_col = next((c for c in schedule_df.columns if "opponent" in c), None)
            result_col = next((c for c in schedule_df.columns if "result" in c or "score" in c), None)

            if not opponent_col or not result_col:
                continue

            games_played = 0
            total_runs_scored = 0
            total_runs_against = 0

            for _, row in schedule_df.iterrows():
                opp = str(row[opponent_col]).strip()
                res_str = str(row[result_col]).strip()

                if not res_str or "cancel" in res_str.lower() or "ppd" in res_str.lower():
                    continue

                parts = res_str.replace("W", "").replace("L", "").strip().split("-")
                if len(parts) >= 2:
                    try:
                        runs_scored = int(parts[0].strip().split()[0])
                        runs_against = int(parts[1].strip().split()[0])

                        games_played += 1
                        total_runs_scored += runs_scored
                        total_runs_against += runs_against

                        all_games.append({
                            "team": team_name,
                            "opponent": opp,
                            "runs_scored": runs_scored,
                            "runs_against": runs_against
                        })
                    except ValueError:
                        continue

            if games_played > 0:
                ra7 = (total_runs_against / (games_played * 7)) * 7
                rs7 = (total_runs_scored / (games_played * 7)) * 7

                team_summaries.append({
                    "team": team_name,
                    "games_played": games_played,
                    "runs_scored": total_runs_scored,
                    "runs_against": total_runs_against,
                    "runs_against_per_7": round(ra7, 2),
                    "runs_scored_per_7": round(rs7, 2)
                })

        except Exception as e:
            print(f"Error parsing team {team_name}: {e}")
            continue

    if not team_summaries:
        print("Warning: Could not extract team schedule data. Generating fallback files.")
        generate_fallback_files(games_output, team_games_output)
        return

    games_df = pd.DataFrame(all_games)
    teams_df = pd.DataFrame(team_summaries)

    team_ra_map = teams_df.set_index("team")["runs_against_per_7"].to_dict()
    
    def calc_opp_ra7(row):
        team = row["team"]
        opps = games_df[games_df["team"] == team]["opponent"]
        opp_ras = [team_ra_map[o] for o in opps if o in team_ra_map]
        return round(sum(opp_ras) / len(opp_ras), 2) if opp_ras else teams_df["runs_against_per_7"].mean()

    teams_df["opp_runs_against_per_7"] = teams_df.apply(calc_opp_ra7, axis=1)

    games_df.to_csv(games_output, index=False)
    teams_df.to_csv(team_games_output, index=False)
    print(f"Successfully saved {len(games_df)} games and {len(teams_df)} team summaries.")

def generate_fallback_files(games_output, team_games_output):
    if not os.path.exists(games_output):
        pd.DataFrame(columns=["team", "opponent", "runs_scored", "runs_against"]).to_csv(games_output, index=False)
    if not os.path.exists(team_games_output):
        pd.DataFrame(columns=["team", "games_played", "runs_scored", "runs_against", "runs_against_per_7", "runs_scored_per_7", "opp_runs_against_per_7"]).to_csv(team_games_output, index=False)

if __name__ == "__main__":
    fetch_team_season_data()
