#!/usr/bin/env python3
"""Pull NCAA D1 softball player-game batting/fielding rows.

Dates with games but no extractable player rows are NOT checkpointed.
This allows those dates to be retried on a future run.
"""

import argparse
import csv
import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests


# ============================================================
# CONFIGURATION
# ============================================================

SCOREBOARD_BASE = os.getenv(
    "NCAA_SCOREBOARD_BASE",
    "https://ncaa-api.henrygd.me"
).rstrip("/")

BOXSCORE_BASE = os.getenv(
    "NCAA_BOXSCORE_BASE",
    "https://ncaa-api.henrygd.me"
).rstrip("/")

CHECKPOINT_FILE = Path("_completed_dates_players.txt")
OUTPUT_CSV = Path("player_games_season.csv")

REQUEST_TIMEOUT = int(os.getenv("NCAA_REQUEST_TIMEOUT", "25"))
REQUEST_RETRIES = int(os.getenv("NCAA_REQUEST_RETRIES", "3"))
REQUEST_PAUSE = float(os.getenv("NCAA_REQUEST_PAUSE", "0.15"))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; KahlIndex/1.0)",
    "Accept": "application/json,text/plain,*/*",
}

FIELDNAMES = [
    "date",
    "game_id",
    "team",
    "opponent",
    "last_name",
    "first_name",
    "position",
    "number",
    "starter",
    "participated",
    "at_bats",
    "runs_scored",
    "hits",
    "rbi",
    "walks",
    "strikeouts",
    "batting_average",
    "on_base_pct",
    "putouts",
    "assists",
    "errors",
    "doubles",
    "triples",
    "home_runs",
    "doubles_hittingSeason",
    "triples_hittingSeason",
    "home_runs_hittingSeason",
]

PLAYER_MARKERS = {
    "lastname",
    "last_name",
    "firstname",
    "first_name",
    "athlete",
    "player",
    "playerid",
    "athleteid",
    "uniformnumber",
    "jerseynumber",
    "atbats",
    "ab",
    "hits",
    "h",
    "runs",
    "r",
    "rbi",
    "battingaverage",
    "ba",
}

STAT_ALIASES = {
    "at_bats": ["ab", "atBats", "at_bats", "at-bats"],
    "runs_scored": ["r", "runs", "runsScored", "runs_scored"],
    "hits": ["h", "hits"],
    "rbi": ["rbi", "runsBattedIn", "runs_batted_in"],
    "walks": ["bb", "walks", "baseOnBalls", "basesOnBalls"],
    "strikeouts": ["so", "k", "strikeouts"],
    "batting_average": ["ba", "avg", "battingAverage", "batting_average"],
    "on_base_pct": ["obp", "onBasePercentage", "on_base_pct"],
    "putouts": ["po", "putouts"],
    "assists": ["a", "assists"],
    "errors": ["e", "errors"],
    "doubles": ["2b", "doubles", "double"],
    "triples": ["3b", "triples", "triple"],
    "home_runs": ["hr", "homeRuns", "home_runs", "homeRunsHit"],
}


# ============================================================
# GENERAL HELPERS
# ============================================================

def norm_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def safe_float(value: Any) -> float:
    if value is None or value == "" or value == "-":
        return 0.0

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().replace("%", "")

    if text in {"", "-", "."}:
        return 0.0

    try:
        return float(text)
    except (ValueError, TypeError):
        return 0.0


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value != 0

    return str(value).strip().lower() in {
        "true", "yes", "y", "1", "starter"
    }


def request_json(url: str, label: str) -> Optional[Any]:
    last_error = None

    for attempt in range(1, REQUEST_RETRIES + 1):
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT
            )

            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError:
                    print(
                        f"[{label}] Response was not valid JSON: "
                        f"{response.text[:500]}"
                    )
                    return None

            last_error = (
                f"HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )

            if response.status_code < 500 and response.status_code != 429:
                break

        except requests.RequestException as exc:
            last_error = str(exc)

        if attempt < REQUEST_RETRIES:
            time.sleep(attempt * 1.0)

    print(
        f"[{label}] Request failed after "
        f"{REQUEST_RETRIES} attempt(s): {last_error}"
    )

    return None


# ============================================================
# SCOREBOARD PARSING
# ============================================================

def extract_game_id(game_entry: Any) -> Optional[str]:
    if not isinstance(game_entry, dict):
        return None

    candidates = [game_entry]

    for key in ("game", "contest", "event"):
        value = game_entry.get(key)

        if isinstance(value, dict):
            candidates.insert(0, value)

    for obj in candidates:

        for key in (
            "gameID",
            "gameId",
            "game_id",
            "id",
            "contestId",
            "contestID"
        ):
            value = obj.get(key)

            if value not in (None, ""):
                text = str(value).strip().rstrip("/")

                if "/" in text:
                    text = text.split("/")[-1]

                return text

        for key in ("url", "gameUrl", "gameURL", "href", "link"):
            value = obj.get(key)

            if isinstance(value, str):
                match = re.search(
                    r"(?:game/)?(\d{5,})(?:/|$|\?)",
                    value
                )

                if match:
                    return match.group(1)

    return None


def get_games_list(payload: Any) -> List[Any]:
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    preferred = (
        "games",
        "gameList",
        "events",
        "contests",
        "scoreboard"
    )

    for key in preferred:

        value = payload.get(key)

        if isinstance(value, list):
            return value

        if isinstance(value, dict):

            for nested_key in (
                "game",
                "games",
                "event",
                "events",
                "contest",
                "contests"
            ):
                nested = value.get(nested_key)

                if isinstance(nested, list):
                    return nested

    def walk(obj: Any) -> List[Any]:

        if isinstance(obj, dict):

            for value in obj.values():
                found = walk(value)

                if found:
                    return found

        elif isinstance(obj, list):

            if any(
                extract_game_id(item)
                for item in obj
                if isinstance(item, dict)
            ):
                return obj

            for item in obj:
                found = walk(item)

                if found:
                    return found

        return []

    return walk(payload)


def fetch_game_ids(
    date_str: str
) -> Tuple[Optional[List[str]], Optional[Any]]:

    date_obj = datetime.strptime(date_str, "%Y-%m-%d")

    url = (
        f"{SCOREBOARD_BASE}/scoreboard/softball/d1/"
        f"{date_obj:%Y/%m/%d}"
    )

    payload = request_json(
        url,
        f"SCOREBOARD {date_str}"
    )

    if payload is None:
        return None, None

    games = get_games_list(payload)

    game_ids = []

    for entry in games:

        game_id = extract_game_id(entry)

        if game_id and game_id not in game_ids:
            game_ids.append(game_id)

    if games and not game_ids:

        print(
            f"[SCOREBOARD {date_str}] Found {len(games)} "
            "entries but could not read game IDs."
        )

        print(
            f"[SCOREBOARD {date_str}] Payload preview: "
            f"{json.dumps(payload, ensure_ascii=False)[:1800]}"
        )

    return game_ids, payload


# ============================================================
# BOXSCORE FETCHING
# ============================================================

def fetch_boxscore(game_id: str) -> Optional[Any]:

    url = f"{BOXSCORE_BASE}/game/{game_id}/boxscore"

    return request_json(
        url,
        f"BOXSCORE {game_id}"
    )


# ============================================================
# NAME AND TEAM HELPERS
# ============================================================

def get_name(obj: Any) -> str:

    if not isinstance(obj, dict):
        return ""

    for key in (
        "name",
        "fullName",
        "displayName",
        "teamName",
        "schoolName"
    ):
        value = obj.get(key)

        if isinstance(value, str) and value.strip():
            return value.strip()

    for key in ("team", "player", "athlete", "person", "school"):

        value = obj.get(key)

        if isinstance(value, dict):

            found = get_name(value)

            if found:
                return found

    first = obj.get("firstName") or obj.get("first_name") or ""
    last = obj.get("lastName") or obj.get("last_name") or ""

    return f"{first} {last}".strip()


def get_player_name(
    player: Dict[str, Any]
) -> Tuple[str, str]:

    sources = [player]

    for key in ("player", "athlete", "person", "individual"):

        nested = player.get(key)

        if isinstance(nested, dict):
            sources.insert(0, nested)

    first = ""
    last = ""
    full = ""

    for source in sources:

        first = first or str(
            source.get("firstName")
            or source.get("first_name")
            or source.get("givenName")
            or ""
        ).strip()

        last = last or str(
            source.get("lastName")
            or source.get("last_name")
            or source.get("surname")
            or ""
        ).strip()

        full = full or str(
            source.get("fullName")
            or source.get("displayName")
            or source.get("name")
            or ""
        ).strip()

    if not first and not last and full:

        parts = full.split()

        if len(parts) == 1:
            last = parts[0]
        else:
            first = " ".join(parts[:-1])
            last = parts[-1]

    return first, last


def flatten_player(
    player: Dict[str, Any]
) -> Dict[str, Any]:

    merged = {}

    for key, value in player.items():

        if not isinstance(value, (dict, list)):
            merged[key] = value

    for key in (
        "player",
        "athlete",
        "person",
        "stats",
        "playerStats",
        "batting",
        "hitting",
        "fielding",
        "statistics"
    ):

        nested = player.get(key)

        if isinstance(nested, dict):

            for subkey, value in nested.items():

                if not isinstance(value, (dict, list)):

                    if (
                        subkey not in merged
                        or merged[subkey] in (None, "")
                    ):
                        merged[subkey] = value

            for subvalue in nested.values():

                if isinstance(subvalue, dict):

                    for subkey, value in subvalue.items():

                        if not isinstance(value, (dict, list)):

                            if (
                                subkey not in merged
                                or merged[subkey] in (None, "")
                            ):
                                merged[subkey] = value

    return merged


def player_like_score(obj: Any) -> int:

    if not isinstance(obj, dict):
        return 0

    keys = {norm_key(k) for k in obj.keys()}

    score = sum(
        1 for marker in PLAYER_MARKERS
        if marker in keys
    )

    if any(
        isinstance(obj.get(k), dict)
        for k in ("player", "athlete", "person")
    ):
        score += 3

    return score


def team_label(team_obj: Any) -> str:

    if not isinstance(team_obj, dict):
        return "Unknown"

    for key in (
        "name",
        "teamName",
        "schoolName",
        "displayName"
    ):

        value = team_obj.get(key)

        if isinstance(value, str) and value.strip():
            return value.strip()

    for key in ("team", "school"):

        nested = team_obj.get(key)

        if isinstance(nested, dict):

            name = get_name(nested)

            if name:
                return name

        elif isinstance(nested, str) and nested.strip():
            return nested.strip()

    return get_name(team_obj) or "Unknown"


# ============================================================
# FINDING TEAM OBJECTS
# ============================================================

def find_team_nodes(
    payload: Any
) -> List[Dict[str, Any]]:

    if not isinstance(payload, dict):
        return []

    root = (
        payload.get("boxscore")
        if isinstance(payload.get("boxscore"), dict)
        else payload
    )

    found = []

    def add_team_list(value: Any) -> bool:

        if isinstance(value, list):

            dicts = [
                item for item in value
                if isinstance(item, dict)
            ]

            if len(dicts) >= 2 and any(
                any(
                    k in item
                    for k in (
                        "teamId",
                        "teamID",
                        "team_id",
                        "teamName",
                        "teamStats",
                        "playerStats",
                        "players",
                        "hitting"
                    )
                )
                for item in dicts
            ):

                found.extend(dicts)
                return True

        if isinstance(value, dict):

            for key in (
                "team",
                "teams",
                "teamBoxscore",
                "team_boxscore"
            ):

                if key in value and add_team_list(value[key]):
                    return True

        return False

    for key in (
        "teams",
        "teamBoxscore",
        "team_boxscore",
        "teamStats",
        "team_stats"
    ):

        if key in root and add_team_list(root[key]):
            break

    if found:
        return found

    def walk(obj: Any) -> None:

        if found:
            return

        if isinstance(obj, dict):

            for value in obj.values():

                walk(value)

                if found:
                    return

        elif isinstance(obj, list):

            dicts = [
                x for x in obj
                if isinstance(x, dict)
            ]

            if len(dicts) == 2 and any(
                any(
                    k in x
                    for k in (
                        "teamId",
                        "teamID",
                        "team_id",
                        "teamStats",
                        "playerStats",
                        "players"
                    )
                )
                for x in dicts
            ):

                found.extend(dicts)
                return

            for item in obj:

                walk(item)

                if found:
                    return

    walk(root)

    return found


# ============================================================
# FINDING PLAYER RECORDS
# ============================================================

def find_player_lists(
    team_obj: Dict[str, Any]
) -> List[List[Dict[str, Any]]]:

    candidates = []
    seen_ids = set()

    def walk(obj: Any, depth: int = 0) -> None:

        if depth > 9:
            return

        if isinstance(obj, dict):

            for value in obj.values():
                walk(value, depth + 1)

        elif isinstance(obj, list):

            dicts = [
                x for x in obj
                if isinstance(x, dict)
            ]

            if dicts:

                scores = [
                    player_like_score(x)
                    for x in dicts
                ]

                strong = sum(
                    score >= 2 for score in scores
                )

                medium = sum(
                    score >= 1 for score in scores
                )

                if (
                    strong >= 1
                    or (len(dicts) >= 2 and medium >= 2)
                ):

                    list_id = id(obj)

                    if list_id not in seen_ids:

                        seen_ids.add(list_id)

                        candidates.append(
                            (strong * 10 + medium, dicts)
                        )

            for item in obj:
                walk(item, depth + 1)

    walk(team_obj)

    candidates.sort(
        key=lambda x: (x[0], len(x[1])),
        reverse=True
    )

    return [
        items for _, items in candidates
    ]


# ============================================================
# STAT EXTRACTION
# ============================================================

def get_stat(
    player: Dict[str, Any],
    aliases: Iterable[str]
) -> float:

    flat = flatten_player(player)

    normalized = {
        norm_key(k): v
        for k, v in flat.items()
    }

    for alias in aliases:

        key = norm_key(alias)

        if key in normalized:
            return safe_float(normalized[key])

    alias_keys = {
        norm_key(a) for a in aliases
    }

    for value in player.values():

        if isinstance(value, dict):

            for key, stat in value.items():

                if norm_key(key) in alias_keys:
                    return safe_float(stat)

    return 0.0


def extract_xbh_notes(
    team_obj: Dict[str, Any]
) -> Tuple[
    Dict[str, int],
    Dict[str, int],
    Dict[str, int]
]:

    maps = ({}, {}, {})

    note_values = (
        team_obj.get("notes")
        or team_obj.get("hittingNotes")
        or team_obj.get("hitting_notes")
        or []
    )

    if isinstance(note_values, dict):
        note_values = list(note_values.values())

    if not isinstance(note_values, list):
        note_values = [note_values]

    text_blob = " ".join(
        str(
            item.get("text", item.get("description", ""))
        )
        if isinstance(item, dict)
        else str(item)
        for item in note_values
    )

    patterns = [
        (
            r"(?:2B|Doubles)\s*[:\-]\s*([^.;]+)",
            maps[0]
        ),
        (
            r"(?:3B|Triples)\s*[:\-]\s*([^.;]+)",
            maps[1]
        ),
        (
            r"(?:HR|Home Runs)\s*[:\-]\s*([^.;]+)",
            maps[2]
        ),
    ]

    for pattern, target in patterns:

        match = re.search(
            pattern,
            text_blob,
            flags=re.IGNORECASE
        )

        if not match:
            continue

        for entry in match.group(1).split(";"):

            name_match = re.search(
                r"([A-Za-z][A-Za-z '\-]+?)(?:,\s*[A-Z]\.?)?(?:\s+(\d+))?$",
                entry.strip()
            )

            if name_match:

                target[
                    name_match.group(1).strip().upper()
                ] = int(name_match.group(2) or 1)

    return maps


# ============================================================
# BUILD PLAYER ROW
# ============================================================

def build_player_row(
    raw_player: Dict[str, Any],
    game_id: str,
    date_str: str,
    team_name: str,
    opponent: str,
    xbh_maps: Tuple[
        Dict[str, int],
        Dict[str, int],
        Dict[str, int]
    ],
) -> Optional[Dict[str, Any]]:

    first_name, last_name = get_player_name(raw_player)

    flat = flatten_player(raw_player)

    if not first_name and not last_name:
        return None

    if not first_name and "," in last_name:

        parts = [
            part.strip()
            for part in last_name.split(",", 1)
        ]

        if len(parts) == 2:
            last_name, first_name = parts[0], parts[1]

    last_upper = last_name.upper()

    d2b, d3b, hr_map = xbh_maps

    def value(*keys: str) -> Any:

        normalized = {
            norm_key(k): v
            for k, v in flat.items()
        }

        for key in keys:

            result = normalized.get(norm_key(key))

            if result not in (None, ""):
                return result

        return ""

    row = {
        "date": date_str,
        "game_id": str(game_id),
        "team": team_name,
        "opponent": opponent,
        "last_name": last_name,
        "first_name": first_name,
        "position": str(
            value("position", "pos") or ""
        ),
        "number": str(
            value(
                "number",
                "uniformNumber",
                "jerseyNumber",
                "jersey"
            ) or ""
        ),
        "starter": truthy(
            value("starter", "isStarter", "started")
        ),
        "participated": True,
        "at_bats": get_stat(
            raw_player,
            STAT_ALIASES["at_bats"]
        ),
        "runs_scored": get_stat(
            raw_player,
            STAT_ALIASES["runs_scored"]
        ),
        "hits": get_stat(
            raw_player,
            STAT_ALIASES["hits"]
        ),
        "rbi": get_stat(
            raw_player,
            STAT_ALIASES["rbi"]
        ),
        "walks": get_stat(
            raw_player,
            STAT_ALIASES["walks"]
        ),
        "strikeouts": get_stat(
            raw_player,
            STAT_ALIASES["strikeouts"]
        ),
        "batting_average": get_stat(
            raw_player,
            STAT_ALIASES["batting_average"]
        ),
        "on_base_pct": get_stat(
            raw_player,
            STAT_ALIASES["on_base_pct"]
        ),
        "putouts": get_stat(
            raw_player,
            STAT_ALIASES["putouts"]
        ),
        "assists": get_stat(
            raw_player,
            STAT_ALIASES["assists"]
        ),
        "errors": get_stat(
            raw_player,
            STAT_ALIASES["errors"]
        ),
        "doubles": (
            get_stat(raw_player, STAT_ALIASES["doubles"])
            or d2b.get(last_upper, 0)
        ),
        "triples": (
            get_stat(raw_player, STAT_ALIASES["triples"])
            or d3b.get(last_upper, 0)
        ),
        "home_runs": (
            get_stat(raw_player, STAT_ALIASES["home_runs"])
            or hr_map.get(last_upper, 0)
        ),
        "doubles_hittingSeason": safe_float(
            value("doubles_hittingSeason")
        ),
        "triples_hittingSeason": safe_float(
            value("triples_hittingSeason")
        ),
        "home_runs_hittingSeason": safe_float(
            value("home_runs_hittingSeason")
        ),
    }

    return row


# ============================================================
# PROCESS A GAME
# ============================================================

def process_game(
    game_id: str,
    date_str: str
) -> Tuple[List[Dict[str, Any]], str]:

    payload = fetch_boxscore(game_id)

    if payload is None:
        return [], "boxscore_request_failed"

    root = (
        payload.get("boxscore")
        if (
            isinstance(payload, dict)
            and isinstance(payload.get("boxscore"), dict)
        )
        else payload
    )

    if not isinstance(root, (dict, list)):
        return [], "unexpected_boxscore_type"

    teams = find_team_nodes(payload)

    if not teams:

        top_keys = (
            list(root.keys())
            if isinstance(root, dict)
            else [f"list[{len(root)}]"]
        )

        print(
            f"[BOX SCORE {game_id}] "
            f"Could not identify team objects. "
            f"Root keys: {top_keys}"
        )

        print(
            f"[BOX SCORE {game_id}] Response preview: "
            f"{json.dumps(payload, ensure_ascii=False)[:3500]}"
        )

        return [], "team_structure_not_found"

    rows = []
    team_summaries = []

    for index, team_obj in enumerate(teams):

        name = team_label(team_obj)

        opponent = (
            team_label(teams[1 - index])
            if len(teams) == 2
            else "Unknown"
        )

        xbh_maps = extract_xbh_notes(team_obj)

        player_lists = find_player_lists(team_obj)

        players = (
            player_lists[0]
            if player_lists
            else []
        )

        team_summaries.append(
            f"{name}: {len(players)} candidate player records"
        )

        for raw_player in players:

            row = build_player_row(
                raw_player,
                game_id,
                date_str,
                name,
                opponent,
                xbh_maps
            )

            if row is not None:
                rows.append(row)

    print(
        f"[BOX SCORE {game_id}] "
        + " | ".join(team_summaries)
        + f" | extracted {len(rows)} rows"
    )

    if not rows:

        print(
            f"[BOX SCORE {game_id}] No player rows extracted. "
            f"Response preview: "
            f"{json.dumps(payload, ensure_ascii=False)[:3500]}"
        )

        return [], "player_rows_not_found"

    return rows, "ok"


# ============================================================
# CSV AND CHECKPOINT HANDLING
# ============================================================

def load_completed_dates() -> set:

    if not CHECKPOINT_FILE.exists():
        return set()

    with CHECKPOINT_FILE.open(
        "r",
        encoding="utf-8"
    ) as file:

        return {
            line.strip()
            for line in file
            if line.strip()
        }


def save_completed_date(date_str: str) -> None:

    with CHECKPOINT_FILE.open(
        "a",
        encoding="utf-8"
    ) as file:

        file.write(date_str + "\n")


def row_key(
    row: Dict[str, Any]
) -> Tuple[str, str, str, str]:

    return (
        str(row.get("game_id", "")).strip(),
        str(row.get("team", "")).strip().casefold(),
        str(row.get("first_name", "")).strip().casefold(),
        str(row.get("last_name", "")).strip().casefold(),
    )


def load_existing_rows(
) -> Dict[Tuple[str, str, str, str], Dict[str, Any]]:

    existing = {}

    if (
        not OUTPUT_CSV.exists()
        or OUTPUT_CSV.stat().st_size == 0
    ):
        return existing

    with OUTPUT_CSV.open(
        "r",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        reader = csv.DictReader(file)

        for row in reader:

            key = row_key(row)

            existing[key] = {
                field: row.get(field, "")
                for field in FIELDNAMES
            }

    return existing


def write_rows(
    rows_by_key: Dict[
        Tuple[str, str, str, str],
        Dict[str, Any]
    ]
) -> None:

    temp_path = OUTPUT_CSV.with_suffix(".csv.tmp")

    with temp_path.open(
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=FIELDNAMES,
            extrasaction="ignore"
        )

        writer.writeheader()
        writer.writerows(rows_by_key.values())

    temp_path.replace(OUTPUT_CSV)


# ============================================================
# MAIN PLAYER EXTRACTION
# ============================================================

def extract_player_games(
    start_date: str,
    end_date: str,
    force_reset: bool = False
) -> None:

    start = datetime.strptime(
        start_date,
        "%Y-%m-%d"
    ).date()

    end = datetime.strptime(
        end_date,
        "%Y-%m-%d"
    ).date()

    if end < start:
        raise ValueError(
            "End date must be on or after start date."
        )

    if force_reset:

        if OUTPUT_CSV.exists():
            OUTPUT_CSV.unlink()

        if CHECKPOINT_FILE.exists():
            CHECKPOINT_FILE.unlink()

        print(
            "[RESET] Removed player CSV and "
            "player-date checkpoint."
        )

    completed = load_completed_dates()

    rows_by_key = load_existing_rows()

    total_new_rows = 0
    total_games = 0
    failed_games = 0

    current = start

    while current <= end:

        date_str = current.isoformat()

        if date_str in completed:

            print(
                f"[{date_str}] Already checkpointed; skipping."
            )

            current += timedelta(days=1)
            continue

        game_ids, scoreboard_payload = fetch_game_ids(
            date_str
        )

        if game_ids is None:

            print(
                f"[{date_str}] Scoreboard request failed; "
                "date NOT checkpointed."
            )

            current += timedelta(days=1)
            continue

        if not game_ids:

            print(
                f"[{date_str}] No games found; "
                "marking date complete."
            )

            save_completed_date(date_str)
            completed.add(date_str)

            current += timedelta(days=1)
            continue

        day_rows = 0
        day_failures = 0

        print(
            f"[{date_str}] Found {len(game_ids)} game(s): "
            f"{', '.join(game_ids)}"
        )

        for game_id in game_ids:

            game_rows, status = process_game(
                game_id,
                date_str
            )

            total_games += 1

            if status != "ok":

                day_failures += 1
                failed_games += 1

            for row in game_rows:

                key = row_key(row)

                if key not in rows_by_key:
                    total_new_rows += 1

                rows_by_key[key] = row
                day_rows += 1

            # Save after each successful game.
            if game_rows:
                write_rows(rows_by_key)

            time.sleep(REQUEST_PAUSE)

        print(
            f"[{date_str}] Processed {len(game_ids)} game(s); "
            f"extracted {day_rows} player rows; "
            f"{day_failures} game(s) had extraction/request problems."
        )

        # Only checkpoint dates when every game was successfully
        # processed and at least one player row was extracted.
        if day_failures == 0 and day_rows > 0:

            save_completed_date(date_str)
            completed.add(date_str)

            print(
                f"[{date_str}] Checkpoint saved."
            )

        else:

            print(
                f"[{date_str}] NOT checkpointed so it can "
                "be retried after fixing the issue."
            )

        current += timedelta(days=1)

    # Make sure the output file exists.
    if not OUTPUT_CSV.exists():
        write_rows(rows_by_key)

    print("\n========== PLAYER PULL SUMMARY ==========")

    print(f"Games attempted: {total_games}")
    print(f"New player rows added: {total_new_rows}")
    print(f"Games with request/extraction problems: {failed_games}")
    print(f"CSV: {OUTPUT_CSV.resolve()}")
    print(f"Checkpoint: {CHECKPOINT_FILE.resolve()}")

    print("=========================================\n")


# ============================================================
# COMMAND-LINE ARGUMENTS
# ============================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description="Pull NCAA D1 softball player game stats."
    )

    parser.add_argument(
        "start_date",
        nargs="?",
        default="2026-02-05",
        help="YYYY-MM-DD"
    )

    parser.add_argument(
        "end_date",
        nargs="?",
        default="2026-06-05",
        help="YYYY-MM-DD"
    )

    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete player CSV and checkpoint before rebuilding."
    )

    args = parser.parse_args()

    print(f"Scoreboard API: {SCOREBOARD_BASE}")
    print(f"Boxscore API:   {BOXSCORE_BASE}")

    extract_player_games(
        args.start_date,
        args.end_date,
        force_reset=args.reset
    )


if __name__ == "__main__":
    main()
