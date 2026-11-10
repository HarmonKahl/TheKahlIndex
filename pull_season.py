#!/usr/bin/env python3
"""
Pull NCAA Division I softball game and team-game data for the Kahl Index.

Workflow outputs:
    games_season.csv
    team_games_season.csv
    _completed_dates.txt

The innings columns represent innings BATTED by each team:
    games_season.csv:
        away_innings = innings the away team batted
        home_innings = innings the home team batted

    team_games_season.csv:
        innings_batted = innings that team batted
        innings_fielded = innings its opponent batted

If innings cannot be retrieved from a boxscore, the script intentionally uses
7.0 as the fallback, matching the established Kahl Index convention.

Usage:
    python pull_season.py 2026-02-05 2026-06-05
    python pull_season.py 2026-02-05 2026-06-05 --reset
    python pull_season.py 2026-02-05 2026-06-05 --no-innings

Dependencies:
    pip install pandas requests
"""

import argparse
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

NCAA_SCOREBOARD_BASE = "https://ncaa-api.henrygd.me"
NCAA_BOXSCORE_BASE = os.environ.get(
    "NCAA_BOXSCORE_BASE", "https://ncaa-api.henrygd.me"
).rstrip("/")

SCOREBOARD_URL = (
    NCAA_SCOREBOARD_BASE
    + "/scoreboard/softball/d1/{year}/{month}/{day}"
)
BOXSCORE_URL = NCAA_BOXSCORE_BASE + "/game/{game_id}/boxscore"

GAMES_FILE = "games_season.csv"
TEAM_GAMES_FILE = "team_games_season.csv"
CHECKPOINT_FILE = "_completed_dates.txt"
DEBUG_DIR = "ncaa_debug"

REQUESTS_PER_SECOND_LIMIT = 5
MIN_REQUEST_INTERVAL = 1.0 / REQUESTS_PER_SECOND_LIMIT
DEFAULT_INNINGS_FALLBACK = 7.0
DEFAULT_MAX_SCOREBOARD_PAGES = 50
DEFAULT_INNINGS_WORKERS = 5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; KahlIndex/1.0; "
        "+https://github.com/)"
    ),
    "Accept": "application/json",
}

GAME_COLUMNS = [
    "date",
    "game_id",
    "away_team",
    "away_score",
    "home_team",
    "home_score",
    "state",
    "status",
    "away_innings",
    "home_innings",
]

TEAM_GAME_COLUMNS = [
    "date",]
