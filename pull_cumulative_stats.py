import os
import re
import time
import io
import pandas as pd
from bs4 import BeautifulSoup
from curl_cffi import requests

YEAR = "2026"

def parse_extra_bases_from_footnote(soup):
    """
    Parses box score footnotes for extra-base hit listings like:
    2B: Smith (2), Johnson (1); HR: Davis (1)
    Returns dict mapping player name -> {'2b': int, '3b': int, 'hr': int}
    """
    extra_bases = {}
    patterns = {
        "2b": r"2B:\s*([^;<]+)",
        "3b": r"3B:\s*([^;<]+)",
        "hr": r"HR:\s*([^;<]+)"
    }
    
    text_content = soup.get_text()
    
    for cat, pattern in patterns.items():
        matches = re.findall(pattern, text_content, re.IGNORECASE)
        for match in matches:
            # Entries are comma-separated player lists
            entries = match.split(",")
            for entry in entries:
                entry = entry.strip()
                if not entry:
                    continue
                # Extract player name and optional count (e.g. "Smith 2" or "Smith (2)")
                m = re.match(r"([A-Za-z\s\.'-]+?)\s*\(?(\d+)?\)?$", entry)
                if m:
                    pname = m.group(1).strip()
                    count = int(m.group(2)) if m.group(2) else 1
                    
                    if pname not in extra_bases:
                        extra_bases[pname] = {"2b": 0, "3b": 0, "hr": 0}
                    extra_bases[pname][cat] += count

    return extra_bases

def fetch_cumulative_stats(games_csv="games_season.csv", output_path="cumulative_player_stats.csv"):
    print("Fetching player cumulative stats by aggregating box-score tables & footnotes...")
    
    session = requests.Session(impersonate="chrome120")
    
    # 1. Fetch D1 institutional team links directly from selection outline
    index_url = f"https://stats.ncaa.org/selection_outline?sport_code=WSB&academic_year={YEAR}&division=1"
    
    player_totals = {}  # (player_name, team) -> dict of stat accumulators
    
    try:
        res = session.get(index_url, timeout=20)
        soup = BeautifulSoup(res.text, "html.parser")
        
        boxscore_urls = set()
        
        # Gather individual contest/boxscore links from team schedule pages
        team_links = [a["href"] for a in soup.find_all("a", href=True) if "/teams/" in a["href"] or "/team/" in a["href"]]
        print(f"Discovered {len(team_links)} team portals. Crawling game boxscores...")
        
        # Target game contest pages (limit team crawl to top 100 for fast CI execution)
        for tlink in team_links[:100]:
            t_url = "https://stats.ncaa.org" + tlink if tlink.startswith("/") else tlink
            try:
                tres = session.get(t_url, timeout=15)
                tsoup = BeautifulSoup(tres.text, "html.parser")
                
                for ga in tsoup.find_all("a", href=True):
                    if "/contests/" in ga["href"] or "box_score" in ga["href"]:
                        g_url = "https://stats.ncaa.org" + ga["href"] if ga["href"].startswith("/") else ga["href"]
                        boxscore_urls.add(g_url)
            except Exception:
                continue
                
        print(f"Found {len(boxscore_urls)} unique boxscore links. Parsing stats...")
        
        # 2. Parse boxscore tables and footnote extra-base hits
        for g_url in list(boxscore_urls)[:150]:  # Process available game boxscores
            time.sleep(0.3)
            try:
                box_res = session.get(g_url, timeout=15)
                if box_res.status_code != 200:
                    continue
                    
                bsoup = BeautifulSoup(box_res.text, "html.parser")
                
                # Parse footnote extra-base hits
                footnotes = parse_extra_bases_from_footnote(bsoup)
                
                # Parse hitting data tables
                tables = pd.read_html(io.StringIO(box_res.text))
                for tbl in tables:
                    tbl.columns = [str(c).strip().lower() for c in tbl.columns]
                    
                    if "player" in tbl.columns and "ab" in tbl.columns:
                        for _, row in tbl.iterrows():
                            pname = str(row.get("player", "")).strip()
                            if not pname or pname.lower() in ["totals", "total", "team"]:
                                continue
                                
                            # Extract numeric hitting columns safely
                            ab = int(pd.to_numeric(row.get("ab", 0), errors="coerce") or 0)
                            h = int(pd.to_numeric(row.get("h", 0), errors="coerce") or 0)
                            bb = int(pd.to_numeric(row.get("bb", 0), errors="coerce") or 0)
                            so = int(pd.to_numeric(row.get("so", row.get("k", 0)), errors="coerce") or 0)
                            
                            # Footnote match for extra bases
                            eb_data = footnotes.get(pname, {"2b": 0, "3b": 0, "hr": 0})
                            
                            key = (pname, "D1_Team")
                            if key not in player_totals:
                                player_totals[key] = {
                                    "games_played": 0, "ab": 0, "hits": 0, 
                                    "doubles": 0, "triples": 0, "hr": 0, 
                                    "walks": 0, "strikeouts": 0
                                }
                                
                            player_totals[key]["games_played"] += 1
                            player_totals[key]["ab"] += ab
                            player_totals[key]["hits"] += h
                            player_totals[key]["doubles"] += eb_data["2b"]
                            player_totals[key]["triples"] += eb_data["3b"]
                            player_totals[key]["hr"] += eb_data["hr"]
                            player_totals[key]["walks"] += bb
                            player_totals[key]["strikeouts"] += so

            except Exception as e:
                continue

    except Exception as e:
        print(f"Error crawling box scores: {e}")

    # Build final DataFrame output
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
    print(f"Successfully generated cumulative stats for {len(df)} players.")

if __name__ == "__main__":
    fetch_cumulative_stats()
