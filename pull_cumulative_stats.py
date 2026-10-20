import os
import re
import time
import requests
import pandas as pd
from datetime import datetime, timedelta

BASE_URL = "https://ncaa-api.henrygd.me"
START_DATE = datetime(2026, 2, 5)
END_DATE = datetime(2026, 6, 10)

def parse_extra_bases_from_notes(notes_list):
    """
    Parses box score notes/text arrays for 2B, 3B, HR text lines:
    e.g. ['2B: Smith (2), Johnson (1)', 'HR: Davis (1)']
    """
    extra_bases = {}
    if not notes_list:
        return extra_bases

    full_text = " ; ".join([str(n) for n in notes_list])
    patterns = {
        "2b": r"2B:\s*([^;<]+)",
        "3b": r"3B:\s*([^;<]+)",
        "hr": r"HR:\s*([^;<]+)"
    }
    
    for cat, pattern in patterns.items():
        matches = re.findall(pattern, full_text, re.IGNORECASE)
        for match in matches:
            entries = match.split(",")
            for entry in entries:
                entry = entry.strip()
                if not entry:
                    continue
                m = re.match(r"([A-Za-z\s\.'-]+?)\s*\(?(\d+)?\)?$", entry)
                if m:
                    pname = m.group(1).strip()
                    count = int(m.group(2)) if m.group(2) else 1
                    if pname not in extra_bases:
                        extra_bases[pname] = {"2b": 0, "3b": 0, "hr": 0}
                    extra_bases[pname][cat] += count

    return extra_bases

def fetch_cumulative_stats(output_path="cumulative_player_stats.csv"):
    print(f"Fetching game boxscores ({START_DATE.strftime('%Y-%m-%d')} to {END_DATE.strftime('%Y-%m-%d')})...")
    
    # 1. Collect game IDs from schedule
    game_ids = []
    current_date = START_DATE
    
    while current_date <= END_DATE:
        date_str = current_date.strftime("%Y/%m/%d")
        url = f"{BASE_URL}/scoreboard/softball/d1/{date_str}"
        try:
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                data = res.json()
                games = data.get("games", []) or data.get("scoreboard", [])
                for g in games:
                    game_info = g.get("game", g) if isinstance(g, dict) else {}
                    gid = game_info.get("url", "") or game_info.get("id", "") or game_info.get("gameId", "")
                    if "/" in str(gid):
                        gid = str(gid).strip("/").split("/")[-1]
                    if gid and gid not in game_ids:
                        game_ids.append(gid)
        except Exception:
            pass
        current_date += timedelta(days=1)

    print(f"Found {len(game_ids)} game box scores across the date range. Aggregating stats...")
    
    player_totals = {}

    # 2. Parse box scores
    for gid in game_ids:
        box_url = f"{BASE_URL}/game/{gid}/boxscore"
        try:
            time.sleep(0.05)
            box_res = requests.get(box_url, timeout=10)
            if box_res.status_code != 200:
                continue
                
            box_data = box_res.json()
            
            # Extract notes / footnotes for 2B, 3B, HR text
            notes = box_data.get("notes", []) or box_data.get("text", []) or []
            extra_bases_map = parse_extra_bases_from_notes(notes)
            
            # Extract hitting tables
            tables = box_data.get("tables", []) or box_data.get("teams", [])
            for tbl in tables:
                team_name = tbl.get("header", "") or tbl.get("name", "") or "D1_Team"
                
                # Player rows are inside 'data' or 'players'
                rows = tbl.get("data", []) or tbl.get("players", []) or tbl.get("stats", [])
                
                for r in rows:
                    if isinstance(r, dict):
                        pname = r.get("Player") or r.get("name") or r.get("player") or ""
                        
                        # Skip total rows
                        if not pname or str(pname).lower() in ["totals", "total", "team"]:
                            continue
                            
                        pname = str(pname).strip()
                        
                        # Extract numeric stats cleanly
                        ab = int(pd.to_numeric(r.get("AB", r.get("ab", 0)), errors="coerce") or 0)
                        h = int(pd.to_numeric(r.get("H", r.get("h", 0)), errors="coerce") or 0)
                        bb = int(pd.to_numeric(r.get("BB", r.get("bb", 0)), errors="coerce") or 0)
                        so = int(pd.to_numeric(r.get("SO", r.get("k", r.get("so", 0))), errors="coerce") or 0)
                        
                        # Check direct columns first, then fallback to text notes
                        d2b = int(pd.to_numeric(r.get("2B", r.get("d2b", 0)), errors="coerce") or 0)
                        d3b = int(pd.to_numeric(r.get("3B", r.get("d3b", 0)), errors="coerce") or 0)
                        hr = int(pd.to_numeric(r.get("HR", r.get("hr", 0)), errors="coerce") or 0)
                        
                        if d2b == 0 and d3b == 0 and hr == 0 and pname in extra_bases_map:
                            d2b = extra_bases_map[pname]["2b"]
                            d3b = extra_bases_map[pname]["3b"]
                            hr = extra_bases_map[pname]["hr"]

                        key = (pname, team_name)
                        if key not in player_totals:
                            player_totals[key] = {
                                "games_played": 0, "ab": 0, "hits": 0,
                                "doubles": 0, "triples": 0, "hr": 0,
                                "walks": 0, "strikeouts": 0
                            }
                            
                        player_totals[key]["games_played"] += 1
                        player_totals[key]["ab"] += ab
                        player_totals[key]["hits"] += h
                        player_totals[key]["doubles"] += d2b
                        player_totals[key]["triples"] += d3b
                        player_totals[key]["hr"] += hr
                        player_totals[key]["walks"] += bb
                        player_totals[key]["strikeouts"] += so

        except Exception:
            continue

    rows = []
    for (pname, team), s in player_totals.items():
        rows.append({
            "player_name": pname,
            "team": team,
            "games_played": s["games_played"],
            "ab": s["ab"],
            "hits": s["hits"],
            "doubles": s["doubles"],
            "triples": s["triples"],
            "hr": s["hr"],
            "walks": s["walks"],
            "strikeouts": s["strikeouts"]
        })

    df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=[
        "player_name", "team", "games_played", "ab", "hits", 
        "doubles", "triples", "hr", "walks", "strikeouts"
    ])

    df.to_csv(output_path, index=False)
    print(f"Successfully generated cumulative player stats for {len(df)} players.")

if __name__ == "__main__":
    fetch_cumulative_stats()
