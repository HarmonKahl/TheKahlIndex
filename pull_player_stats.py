#!/usr/bin/env python3
"""
Pull NCAA Division I softball player-game statistics.

Designed for the Daily Kahl Index Pipeline:
  Input:  NCAA scoreboard + game boxscores
  Output: player_games_season.csv
  State:  _player_completed_dates.txt

The script uses NCAA_BOXSCORE_BASE when provided (for example, the
henrygd/ncaa-api service in GitHub Actions). It deliberately does NOT mark a
date complete if a listed game cannot be fetched or parsed into player rows.

Usage:
  python pull_player_stats.py 2026-02-05 2026-06-05
  python pull_player_stats.py 2026-02-05 2026-06-05 --reset

Dependencies:
  pip install requests
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE = os.getenv(
    "NCAA_BOXSCORE_BASE",
    "https://ncaa-api.henrygd.me"
).rstrip("/")

OUTPUT_CSV = "player_games_season.csv"
CHECKPOINT_FILE = "_player_completed_dates.txt"
DEBUG_DIR = "ncaa_debug"

REQUEST_TIMEOUT = 25
REQUEST_DELAY_SECONDS = 0.15
MAX_SCOREBOARD_PAGES = 100

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; KahlIndex/1.0; "
        "+https://github.com/)"
    ),
    "Accept": "application/json",
}

FIELDNAMES = [
    "date", "game_id", "team", "opponent", "last_name", "first_name",
    "position", "number", "starter", "participated", "at_bats",
    "runs_scored", "hits", "rbi", "walks", "strikeouts",
    "batting_average", "on_base_pct", "putouts", "assists", "errors",
    "doubles", "triples", "home_runs",
    "doubles_hittingSeason", "triples_hittingSeason",
    "home_runs_hittingSeason",
]

# A player-stat record normally contains at least one of these fields.
STAT_KEYS = {
    "ab", "atbats", "at_bats", "r", "runs", "h", "hits", "rbi",
    "bb", "walks", "so", "strikeouts", "ba", "avg", "obp",
    "po", "putouts", "a", "assists", "e", "errors", "2b",
    "doubles", "3b", "triples", "hr", "homeruns", "home_runs",
}

PLAYER_ID_KEYS = {
    "player", "athlete", "playerid", "athleteid", "lastname",
    "last_name", "firstname", "first_name", "uniformnumber",
    "jerseynumber",
}


# ---------------------------------------------------------------------------
# HTTP and basic helpers
# ---------------------------------------------------------------------------

def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(HEADERS)
    return session


SESSION = make_session()


def request_json(url: str, params: Optional[dict] = None) -> Any:
    response = SESSION.get(url, params=params, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    try:
        return response.json()
    except ValueError as exc:
        raise ValueError(
            f"Response was not valid JSON: {response.url}"
        ) from exc


def normalized_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def first_value(obj: dict, names: Iterable[str], default=None):
    """Return the first present, non-empty value, matching keys case-insensitively."""
    if not isinstance(obj, dict):
        return default
    lookup = {normalized_key(k): v for k, v in obj.items()}
    for name in names:
        value = lookup.get(normalized_key(name))
        if value is not None and value != "":
            return value
    return default


def safe_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if text in {"-", "--", "—", "N/A", "n/a"}:
        return 0.0
    text = text.replace("%", "")
    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0


def safe_bool(value: Any, default=False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"true", "yes", "y", "1", "starter"}:
            return True
        if v in {"false", "no", "n", "0", ""}:
            return False
    return default


def save_debug_json(label: str, data: Any) -> None:
    os.makedirs(DEBUG_DIR, exist_ok=True)
    safe_label = re.sub(r"[^A-Za-z0-9_.-]", "_", label)
    path = os.path.join(DEBUG_DIR, f"{safe_label}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"  Debug response saved: {path}")
    except (OSError, TypeError) as exc:
        print(f"  Could not save debug response: {exc}")


# ---------------------------------------------------------------------------
# Checkpoint and CSV handling
# ---------------------------------------------------------------------------

def load_completed_dates(reset: bool) -> Set[str]:
    if reset or not os.path.exists(CHECKPOINT_FILE):
        return set()
    with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def save_completed_date(date_str: str) -> None:
    with open(CHECKPOINT_FILE, "a", encoding="utf-8") as f:
        f.write(date_str + "\n")


def load_existing_row_keys() -> Set[Tuple[str, str, str, str, str]]:
    """Prevent duplicate player-game rows when a partially completed date retries."""
    keys = set()
    if not os.path.exists(OUTPUT_CSV) or os.path.getsize(OUTPUT_CSV) == 0:
        return keys

    with open(OUTPUT_CSV, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            keys.add((
                str(row.get("game_id", "")).strip(),
                str(row.get("team", "")).strip().casefold(),
                str(row.get("last_name", "")).strip().casefold(),
                str(row.get("first_name", "")).strip().casefold(),
                str(row.get("number", "")).strip(),
            ))
    return keys


def initialize_csv(reset: bool) -> None:
    if reset and os.path.exists(OUTPUT_CSV):
        os.remove(OUTPUT_CSV)
    if not os.path.exists(OUTPUT_CSV) or os.path.getsize(OUTPUT_CSV) == 0:
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()


def append_rows(rows: List[dict], existing_keys: Set[tuple]) -> int:
    new_rows = []
    for row in rows:
        key = (
            str(row.get("game_id", "")).strip(),
            str(row.get("team", "")).strip().casefold(),
            str(row.get("last_name", "")).strip().casefold(),
            str(row.get("first_name", "")).strip().casefold(),
            str(row.get("number", "")).strip(),
        )
        if key not in existing_keys:
            existing_keys.add(key)
            new_rows.append(row)

    if new_rows:
        with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
            writer.writerows(new_rows)
    return len(new_rows)


# ---------------------------------------------------------------------------
# Scoreboard parsing and pagination
# ---------------------------------------------------------------------------

def unwrap_game(entry: Any) -> dict:
    if not isinstance(entry, dict):
        return {}
    game = entry.get("game")
    if isinstance(game, dict):
        return game
    contest = entry.get("contest")
    if isinstance(contest, dict):
        return contest
    return entry


def extract_game_id(entry: Any) -> Optional[str]:
    game = unwrap_game(entry)
    # Prefer fields that explicitly identify a contest/game.
    value = first_value(
        game,
        ["gameID", "gameId", "game_id", "contestId", "contestID", "contest_id"],
    )
    if value is None:
        # Generic id is accepted only on the scoreboard's game object.
        value = game.get("id")
    if value is None:
        return None

    value = str(value).strip()
    if not value:
        return None
    if "/" in value:
        value = value.rstrip("/").split("/")[-1]
    return value


def find_game_list(payload: Any) -> Optional[List[Any]]:
    """Find a scoreboard game list without assuming one exact wrapper."""
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return None

    for key in ("games", "game", "contests", "events"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            for nested_key in ("game", "games", "contest", "contests", "event"):
                nested = value.get(nested_key)
                if isinstance(nested, list):
                    return nested

    # Some wrappers put the actual response one level down.
    for value in payload.values():
        if isinstance(value, dict):
            found = find_game_list(value)
            if found is not None:
                return found
    return None


def find_total_pages(payload: Any) -> Optional[int]:
    """Read pagination metadata when the API provides it."""
    if not isinstance(payload, dict):
        return None

    candidates = [
        payload,
        payload.get("pagination"),
        payload.get("meta"),
        payload.get("metadata"),
        payload.get("pageInfo"),
        payload.get("page_info"),
    ]
    for obj in candidates:
        if not isinstance(obj, dict):
            continue
        value = first_value(
            obj,
            ["totalPages", "total_pages", "pageCount", "page_count", "pages"],
        )
        if value is not None:
            try:
                return max(1, int(value))
            except (TypeError, ValueError):
                pass
    return None


def scoreboard_url(date: datetime) -> str:
    # The henrygd API route uses numeric month/day path segments.
    return (
        f"{API_BASE}/scoreboard/softball/d1/"
        f"{date.year}/{date.month}/{date.day}"
    )


def fetch_scoreboard_games(date: datetime) -> Tuple[List[Tuple[str, Any]], bool]:
    """
    Fetch page 1 and continue through known or discoverable pages.
    Returns (unique game IDs with their source entries, scoreboard_valid).
    """
    url = scoreboard_url(date)
    all_games: Dict[str, Any] = {}
    seen_page_signatures: Set[Tuple[str, ...]] = set()
    page = 1
    total_pages = None
    valid_response = False

    while page <= MAX_SCOREBOARD_PAGES:
        params = {"page": page} if page > 1 else None
        payload = request_json(url, params=params)
        game_list = find_game_list(payload)

        if game_list is None:
            if page == 1:
                save_debug_json(f"scoreboard_{date:%Y%m%d}", payload)
                raise ValueError(
                    "Scoreboard JSON did not contain a recognizable games list."
                )
            break

        valid_response = True
        total_pages = total_pages or find_total_pages(payload)

        page_ids = []
        for entry in game_list:
            game_id = extract_game_id(entry)
            if game_id:
                page_ids.append(game_id)
                all_games.setdefault(game_id, entry)

        signature = tuple(sorted(set(page_ids)))
        if not signature:
            break
        if signature in seen_page_signatures:
            # The server may ignore ?page=; don't loop forever.
            break
        seen_page_signatures.add(signature)

        if total_pages is not None:
            if page >= total_pages:
                break
        else:
            # Probe the next page. If the API ignores the page parameter,
            # the repeated-page check above stops the loop.
            if len(game_list) == 0:
                break

        page += 1

    if page > MAX_SCOREBOARD_PAGES:
        raise RuntimeError(
            f"Scoreboard exceeded {MAX_SCOREBOARD_PAGES} pages; refusing "
            "to mark the date complete."
        )

    return list(all_games.items()), valid_response


# ---------------------------------------------------------------------------
# Boxscore parsing
# ---------------------------------------------------------------------------

def get_team_name(team_obj: Any) -> str:
    if not isinstance(team_obj, dict):
        return ""
    nested = team_obj.get("team")
    if isinstance(nested, dict):
        name = first_value(nested, ["name", "teamName", "school"])
        if name:
            return str(name).strip()
    name = first_value(team_obj, ["name", "teamName", "school", "team_name"])
    if isinstance(name, dict):
        name = first_value(name, ["name", "teamName"])
    return str(name).strip() if name else ""


def collect_team_objects(box_data: Any) -> List[dict]:
    """Locate likely team-level objects in common boxscore response layouts."""
    found = []
    seen_ids = set()

    def walk(node: Any):
        if isinstance(node, dict):
            for key in ("teams", "teamBoxscore", "team_boxscore", "teamStats"):
                value = node.get(key)
                if isinstance(value, dict):
                    value = (
                        value.get("team")
                        or value.get("teams")
                        or value.get("teamBoxscore")
                        or []
                    )
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            marker = id(item)
                            if marker not in seen_ids and get_team_name(item):
                                seen_ids.add(marker)
                                found.append(item)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(box_data)

    # If response itself is a two-team list.
    if not found and isinstance(box_data, list):
        found = [x for x in box_data if isinstance(x, dict) and get_team_name(x)]

    return found


def iter_dicts(node: Any):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from iter_dicts(value)
    elif isinstance(node, list):
        for value in node:
            yield from iter_dicts(value)


def is_player_stat_record(obj: dict) -> bool:
    keys = {normalized_key(k) for k in obj.keys()}
    has_stats = bool(keys.intersection(STAT_KEYS))
    has_player_identity = bool(keys.intersection(PLAYER_ID_KEYS))
    return has_stats and has_player_identity


def find_player_records(team_obj: dict) -> List[dict]:
    """
    Recursively locate player-stat records under one team.
    De-duplicates the same record if the response exposes multiple wrappers.
    """
    records = []
    seen = set()
    for obj in iter_dicts(team_obj):
        if is_player_stat_record(obj):
            marker = json.dumps(obj, sort_keys=True, default=str)
            if marker not in seen:
                seen.add(marker)
                records.append(obj)
    return records


def player_identity(record: dict) -> Tuple[dict, str, str]:
    person = first_value(record, ["player", "athlete"], {})
    if not isinstance(person, dict):
        person = {}

    # Some schemas put identity on the outer stat record; others nest it.
    combined = dict(person)
    for key, value in record.items():
        combined.setdefault(key, value)

    first = first_value(combined, ["firstName", "first_name", "givenName"], "")
    last = first_value(
        combined,
        ["lastName", "last_name", "surname", "familyName"],
        "",
    )
    full = first_value(combined, ["fullName", "displayName", "name"], "")

    if not first and not last and full:
        parts = str(full).strip().split()
        if len(parts) >= 2:
            first, last = " ".join(parts[:-1]), parts[-1]
        elif parts:
            last = parts[0]

    if not last:
        # Do not store a full name in last_name when a split is possible.
        last = str(full).strip() if full else "Unknown"

    return combined, str(last).strip(), str(first).strip()


def parse_xbh_from_notes(notes: Any) -> Tuple[Dict[str, int], Dict[str, int], Dict[str, int]]:
    doubles, triples, homers = {}, {}, {}
    if not notes:
        return doubles, triples, homers

    if isinstance(notes, list):
        text_block = " ".join(
            str(n.get("text", "")) if isinstance(n, dict) else str(n)
            for n in notes
        )
    else:
        text_block = str(notes)

    patterns = [
        (r"(?:2B|Doubles)\s*[:\-]\s*([^.;]+)", doubles),
        (r"(?:3B|Triples)\s*[:\-]\s*([^.;]+)", triples),
        (r"(?:HR|Home Runs)\s*[:\-]\s*([^.;]+)", homers),
    ]

    for pattern, target in patterns:
        for match in re.finditer(pattern, text_block, flags=re.IGNORECASE):
            for entry in match.group(1).split(";"):
                entry = entry.strip()
                if not entry:
                    continue
                # Accept "Last, First", "Last, F.", or "Last 2".
                count_match = re.search(r"\s+(\d+)\s*$", entry)
                count = int(count_match.group(1)) if count_match else 1
                name_part = entry[:count_match.start()].strip() if count_match else entry
                name_part = re.sub(r",\s*[A-Z]\.?$", "", name_part).strip()
                if name_part:
                    target[name_part.upper()] = count

    return doubles, triples, homers


def stat_value(record: dict, aliases: Iterable[str], fallback=0.0) -> float:
    value = first_value(record, aliases)
    return safe_float(value) if value is not None else float(fallback)


def build_player_row(
    record: dict,
    team_name: str,
    opponent: str,
    game_id: str,
    date_str: str,
    notes_maps: Tuple[dict, dict, dict],
) -> dict:
    person, last_name, first_name = player_identity(record)
    doubles_map, triples_map, homers_map = notes_maps
    last_key = last_name.upper()

    # Some fields (e.g. number, position) may be nested on player/athlete.
    def val(aliases, default=""):
        result = first_value(record, aliases)
        if result is None:
            result = first_value(person, aliases)
        return default if result is None else result

    doubles = stat_value(record, ["2b", "doubles"])
    triples = stat_value(record, ["3b", "triples"])
    homers = stat_value(record, ["hr", "homeRuns", "home_runs", "homeruns"])

    # Notes are a fallback only when the stat field is absent, not when it is 0.
    if first_value(record, ["2b", "doubles"]) is None:
        doubles = float(doubles_map.get(last_key, 0))
    if first_value(record, ["3b", "triples"]) is None:
        triples = float(triples_map.get(last_key, 0))
    if first_value(record, ["hr", "homeRuns", "home_runs", "homeruns"]) is None:
        homers = float(homers_map.get(last_key, 0))

    return {
        "date": date_str,
        "game_id": game_id,
        "team": team_name or "Unknown",
        "opponent": opponent or "Unknown",
        "last_name": last_name,
        "first_name": first_name,
        "position": val(["position", "pos"], ""),
        "number": val(["number", "jerseyNumber", "uniformNumber"], ""),
        "starter": safe_bool(val(["starter", "isStarter"], False), False),
        "participated": safe_bool(val(["participated", "played", "didPlay"], True), True),
        "at_bats": stat_value(record, ["ab", "atBats", "at_bats"]),
        "runs_scored": stat_value(record, ["r", "runs", "runsScored"]),
        "hits": stat_value(record, ["h", "hits"]),
        "rbi": stat_value(record, ["rbi", "runsBattedIn"]),
        "walks": stat_value(record, ["bb", "walks", "basesOnBalls"]),
        "strikeouts": stat_value(record, ["so", "strikeouts", "k"]),
        "batting_average": stat_value(record, ["ba", "avg", "battingAverage"]),
        "on_base_pct": stat_value(record, ["obp", "onBasePercentage"]),
        "putouts": stat_value(record, ["po", "putouts"]),
        "assists": stat_value(record, ["a", "assists"]),
        "errors": stat_value(record, ["e", "errors"]),
        "doubles": doubles,
        "triples": triples,
        "home_runs": homers,
        "doubles_hittingSeason": stat_value(record, ["doubles_hittingSeason"]),
        "triples_hittingSeason": stat_value(record, ["triples_hittingSeason"]),
        "home_runs_hittingSeason": stat_value(record, ["home_runs_hittingSeason"]),
    }


def process_game(game_id: str, date_str: str) -> List[dict]:
    url = f"{API_BASE}/game/{game_id}/boxscore"
    box_data = request_json(url)

    # Unwrap common top-level containers.
    while isinstance(box_data, dict):
        nested = None
        for key in ("boxscore", "gameBoxscore", "game_boxscore", "data"):
            candidate = box_data.get(key)
            if isinstance(candidate, (dict, list)):
                nested = candidate
                break
        if nested is None:
            break
        box_data = nested

    team_objects = collect_team_objects(box_data)
    if not team_objects:
        save_debug_json(f"boxscore_{game_id}", box_data)
        raise ValueError(
            f"Could not locate team objects in boxscore for game {game_id}."
        )

    rows = []
    for index, team_obj in enumerate(team_objects):
        team_name = get_team_name(team_obj)
        opponent = ""
        for other_index, other_team in enumerate(team_objects):
            if other_index != index:
                opponent = get_team_name(other_team)
                break

        notes = first_value(
            team_obj,
            ["notes", "hittingNotes", "hitting_notes", "teamNotes"],
            [],
        )
        note_maps = parse_xbh_from_notes(notes)
        records = find_player_records(team_obj)

        for record in records:
            row = build_player_row(
                record, team_name, opponent, game_id, date_str, note_maps
            )
            if row["last_name"] != "Unknown" or row["first_name"]:
                rows.append(row)

    if not rows:
        save_debug_json(f"boxscore_{game_id}", box_data)
        raise ValueError(
            f"Boxscore for game {game_id} was retrieved, but no player-stat "
            "records were recognized."
        )

    return rows


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def extract_player_games(start_date: str, end_date: str, reset: bool = False) -> None:
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    if end < start:
        raise ValueError("End date must be on or after start date.")

    if reset:
        # Reset both the output and its matching checkpoint.
        if os.path.exists(OUTPUT_CSV):
            os.remove(OUTPUT_CSV)
        if os.path.exists(CHECKPOINT_FILE):
            os.remove(CHECKPOINT_FILE)

    initialize_csv(reset=False)
    completed = load_completed_dates(reset=False)
    existing_keys = load_existing_row_keys()

    print(f"NCAA API base: {API_BASE}")
    print(f"Output: {OUTPUT_CSV}")
    print(f"Checkpoint: {CHECKPOINT_FILE}")
    print(f"Existing player-game rows: {len(existing_keys)}")
    print(f"Completed dates loaded: {len(completed)}")

    current = start
    total_new_rows = 0

    while current <= end:
        date_str = current.isoformat()

        if date_str in completed:
            print(f"[{date_str}] Already completed; skipping.")
            current += timedelta(days=1)
            continue

        print(f"\n[{date_str}] Fetching scoreboard...")
        try:
            games, scoreboard_valid = fetch_scoreboard_games(
                datetime(current.year, current.month, current.day)
            )
            if not scoreboard_valid:
                raise ValueError("No valid scoreboard response was received.")

            print(f"[{date_str}] Found {len(games)} unique game IDs.")

            date_rows = 0
            failed_games = []

            for game_id, _entry in games:
                try:
                    rows = process_game(game_id, date_str)
                    added = append_rows(rows, existing_keys)
                    date_rows += added
                    print(
                        f"  Game {game_id}: {len(rows)} player rows parsed; "
                        f"{added} new rows saved."
                    )
                except Exception as exc:
                    failed_games.append((game_id, str(exc)))
                    print(f"  FAILED game {game_id}: {exc}")

                time.sleep(REQUEST_DELAY_SECONDS)

            # A valid empty scoreboard is a completed no-game date.
            # A date with any listed game that failed parsing/fetching is NOT.
            if failed_games:
                print(
                    f"[{date_str}] INCOMPLETE: {len(failed_games)} of "
                    f"{len(games)} games failed. Date was NOT checkpointed."
                )
            else:
                save_completed_date(date_str)
                completed.add(date_str)
                total_new_rows += date_rows
                print(
                    f"[{date_str}] COMPLETE: {len(games)} games processed; "
                    f"{date_rows} new player rows saved."
                )

        except Exception as exc:
            print(f"[{date_str}] DATE FAILED; not checkpointed: {exc}")

        current += timedelta(days=1)

    print(f"\nFinished. New player rows written this run: {total_new_rows}")
    print(f"CSV: {OUTPUT_CSV}")
    print(f"Checkpoint: {CHECKPOINT_FILE}")


def main():
    parser = argparse.ArgumentParser(
        description="Pull NCAA Division I softball player-game statistics."
    )
    parser.add_argument("start_date", nargs="?", default="2026-02-05")
    parser.add_argument("end_date", nargs="?", default="2026-06-05")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the player CSV and player checkpoint before scraping.",
    )
    args = parser.parse_args()

    extract_player_games(args.start_date, args.end_date, reset=args.reset)


if __name__ == "__main__":
    main()
