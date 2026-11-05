"""
NCAA Division I Softball player-game data extractor.

Preserves the original output terminology:
  processed_games.json
  player_games_season.csv

One row is written per player listed in the boxscore for each game.
Failed/unparseable games are NOT checkpointed, so they can be retried.

Usage:
  python player_data.py
  python player_data.py 2026-02-05 2026-06-05
  python player_data.py 2026-05-01
"""

import os
import re
import csv
import json
import time
from datetime import datetime, timedelta

import requests

CHECKPOINT_FILE = "processed_games.json"
OUTPUT_CSV = "player_games_season.csv"

NCAA_API_BASE = "https://ncaa-api.henrygd.me"
SCOREBOARD_URL = NCAA_API_BASE + "/scoreboard/softball/d1/{year}/{month}/{day}"
BOXSCORE_URL = NCAA_API_BASE + "/game/{game_id}/boxscore"

REQUESTS_PER_SECOND_LIMIT = 5
_MIN_INTERVAL = 1.0 / REQUESTS_PER_SECOND_LIMIT
_session = requests.Session()
_last_request_time = 0.0


def rate_limit():
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_request_time = time.monotonic()


def get_json(url, retries=3, timeout=20):
    last_error = None
    for attempt in range(retries + 1):
        try:
            rate_limit()
            response = _session.get(url, timeout=timeout)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < retries:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        delay = float(retry_after)
                    except (TypeError, ValueError):
                        delay = min(2 ** attempt, 10)
                    time.sleep(delay)
                    continue
            response.raise_for_status()
            return response.json()
        except Exception as error:
            last_error = error
            if attempt < retries:
                time.sleep(min(2 ** attempt, 10))
    raise RuntimeError(f"Request failed: {url}: {last_error}")


def load_processed_games():
    if not os.path.exists(CHECKPOINT_FILE):
        return set()
    try:
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as file:
            values = json.load(file)
        return set(str(value) for value in values)
    except (OSError, json.JSONDecodeError, TypeError):
        print("Warning: could not read processed_games.json; starting without checkpoint.")
        return set()


def save_processed_games(processed_set):
    temp_file = CHECKPOINT_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as file:
        json.dump(sorted(processed_set), file, indent=2)
    os.replace(temp_file, CHECKPOINT_FILE)


def extract_game_id(game):
    if not isinstance(game, dict):
        return ""
    for key in ("gameID", "id", "contestId", "contestID"):
        value = game.get(key)
        if value not in (None, ""):
            value = str(value).strip()
            if "/" in value:
                value = value.rstrip("/").split("/")[-1]
            return value
    url = game.get("url") or game.get("link") or ""
    match = re.search(r"/game/(\d+)", str(url))
    return match.group(1) if match else ""


def get_boxscore_root(box_data):
    if not isinstance(box_data, dict):
        return {}
    nested = box_data.get("boxscore")
    return nested if isinstance(nested, dict) else box_data


def _as_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("player", "players", "playerStats", "stats", "team", "athletes"):
            if isinstance(value.get(key), list):
                return value[key]
    return []


def _team_name(team_data):
    if not isinstance(team_data, dict):
        return "Unknown"
    team = team_data.get("team") if isinstance(team_data.get("team"), dict) else {}
    names = team_data.get("names") if isinstance(team_data.get("names"), dict) else {}
    nested_names = team.get("names") if isinstance(team.get("names"), dict) else {}
    return (
        team_data.get("name")
        or names.get("short")
        or names.get("full")
        or team.get("name")
        or nested_names.get("short")
        or nested_names.get("full")
        or team_data.get("description")
        or "Unknown"
    )


def _first_present(mapping, keys, default=None):
    if not isinstance(mapping, dict):
        return default
    for key in keys:
        if key in mapping and mapping[key] is not None and mapping[key] != "":
            return mapping[key]
    return default


def _normalize_stat_name(value):
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def _flatten_player_stats(player):
    """
    Keep the original NCAA-style abbreviations while also supporting
    stat arrays/dictionaries when the API nests individual stat values.
    """
    if not isinstance(player, dict):
        return {}

    result = dict(player)

    for container_key in ("stats", "playerStats", "hitting", "fielding", "batting"):
        nested = player.get(container_key)
        if isinstance(nested, dict):
            result.update(nested)
        elif isinstance(nested, list):
            for item in nested:
                if not isinstance(item, dict):
                    continue
                stat_name = (
                    item.get("name")
                    or item.get("stat")
                    or item.get("statName")
                    or item.get("label")
                )
                stat_value = _first_present(
                    item, ("value", "statValue", "displayValue", "total")
                )
                if stat_name is not None and stat_value is not None:
                    result[_normalize_stat_name(stat_name)] = stat_value

    return result


def _player_identity(player_entry):
    if not isinstance(player_entry, dict):
        return {}

    player = player_entry.get("player")
    if not isinstance(player, dict):
        player = player_entry.get("athlete")
    if not isinstance(player, dict):
        player = player_entry

    identity = dict(player)
    # Some responses put the stats beside a nested player/athlete identity.
    for key in ("firstName", "first_name", "lastName", "last_name", "name",
                "position", "number", "jerseyNumber", "id"):
        if key not in identity and key in player_entry:
            identity[key] = player_entry[key]

    stats = _flatten_player_stats(player_entry)
    # Identity fields take precedence over similarly named stat fields.
    stats.update({key: value for key, value in identity.items() if value is not None})
    return stats


def _find_player_list(team_data):
    """
    Search known player-list locations first, then nested dictionaries.
    Only lists containing dictionaries with player-like identity fields qualify.
    """
    candidate_keys = (
        "playerStats", "players", "stats", "hittingStats",
        "playerBoxscore", "playerBoxScore", "athletes", "roster",
    )

    for key in candidate_keys:
        candidate = team_data.get(key)
        values = _as_list(candidate)
        if values and any(
            isinstance(item, dict)
            and (
                isinstance(item.get("player"), dict)
                or isinstance(item.get("athlete"), dict)
                or any(k in item for k in ("lastName", "last_name", "firstName", "name"))
            )
            for item in values
        ):
            return values

    # Check common nested containers without recursively treating every stat list as players.
    for container_key in ("teamStats", "teamBoxscore", "boxscore", "hitting", "statistics"):
        nested = team_data.get(container_key)
        if isinstance(nested, dict):
            found = _find_player_list(nested)
            if found:
                return found

    return []


def _get_teams(box_data):
    root = get_boxscore_root(box_data)
    for key in ("teamBoxscore", "teams", "teamsBoxscore", "teamStats"):
        value = root.get(key)
        teams = _as_list(value)
        if teams and all(isinstance(team, dict) for team in teams):
            # A team list should have team-level identity or player containers.
            if any(
                any(k in team for k in ("playerStats", "players", "team", "name", "teamId"))
                for team in teams
            ):
                return teams
    return []


def parse_xbh_from_notes(notes_list):
    """
    Parse NCAA text notes such as:
    '2B - SHAW, G. 1; VOGEL, K. 1. HR - LANGFORD, H. 2.'

    Returns dictionaries mapping normalized player-name keys to counts.
    """
    doubles, triples, hrs = {}, {}, {}
    if not notes_list:
        return doubles, triples, hrs

    text_parts = []
    for note in notes_list:
        if isinstance(note, dict):
            text_parts.append(str(note.get("text") or note.get("description") or ""))
        else:
            text_parts.append(str(note))
    text_block = " ".join(text_parts)

    patterns = {
        "2b": r"(?:2B|Doubles)\s*[:\-]\s*([^.]+)",
        "3b": r"(?:3B|Triples)\s*[:\-]\s*([^.]+)",
        "hr": r"(?:HR|Home Runs)\s*[:\-]\s*([^.]+)",
    }

    for stat_key, pattern in patterns.items():
        target = {"2b": doubles, "3b": triples, "hr": hrs}[stat_key]
        for match in re.finditer(pattern, text_block, flags=re.IGNORECASE):
            entries = match.group(1).split(";")
            for entry in entries:
                entry = entry.strip()
                if not entry:
                    continue
                # Typical format: LASTNAME, I. 2 or LASTNAME 1
                player_match = re.match(
                    r"(.+?)(?:,\s*[A-Z]\.)?\s+(\d+)\s*$", entry
                )
                if player_match:
                    name = _normalize_player_name(player_match.group(1))
                    count = int(player_match.group(2))
                else:
                    name = _normalize_player_name(entry)
                    count = 1
                if name:
                    target[name] = count

    return doubles, triples, hrs


def _normalize_player_name(name):
    value = str(name or "").strip().upper()
    value = re.sub(r",\s*[A-Z]\.?$", "", value)
    value = re.sub(r"\s+", " ", value)
    return value


def safe_float(value):
    if value is None or value == "":
        return 0.0
    if isinstance(value, str):
        value = value.replace("%", "").strip()
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def _stat(player, keys, default=0):
    return _first_present(player, keys, default)


def _get_name(player):
    full_name = _first_present(player, ("fullName", "displayName", "name"))
    first_name = _first_present(player, ("firstName", "first_name", "givenName"), "")
    last_name = _first_present(player, ("lastName", "last_name", "surname"), "")

    if full_name and (not first_name or not last_name):
        parts = str(full_name).strip().split()
        if len(parts) >= 2:
            first_name = first_name or " ".join(parts[:-1])
            last_name = last_name or parts[-1]
        elif parts:
            last_name = last_name or parts[0]

    return str(last_name or "Unknown"), str(first_name or "")


def process_game(game_id, date_str, debug=False):
    try:
        box_data = get_json(BOXSCORE_URL.format(game_id=game_id))
    except Exception as error:
        if debug:
            print(f"  {game_id}: boxscore request failed: {error}")
        return None

    root = get_boxscore_root(box_data)
    teams = _get_teams(box_data)

    if not teams:
        if debug:
            print(f"  {game_id}: no recognized team list. Top-level keys: {list(root.keys())}")
        return None

    rows = []
    teams_with_players = 0

    for team_index, team_data in enumerate(teams):
        team_name = _team_name(team_data)
        opponent_index = 1 if team_index == 0 else 0
        opponent_name = (
            _team_name(teams[opponent_index])
            if len(teams) > opponent_index else "Unknown"
        )

        notes = (
            team_data.get("notes")
            or team_data.get("hittingNotes")
            or team_data.get("teamNotes")
            or []
        )
        doubles_map, triples_map, home_runs_map = parse_xbh_from_notes(notes)

        players = _find_player_list(team_data)
        if not players:
            continue

        teams_with_players += 1

        for player_entry in players:
            player = _player_identity(player_entry)
            if not player:
                continue

            last_name, first_name = _get_name(player)
            normalized_name = _normalize_player_name(last_name)

            # Map both NCAA abbreviations and common descriptive names.
            rows.append({
                "date": date_str,
                "game_id": str(game_id),
                "team": team_name,
                "opponent": opponent_name,
                "last_name": last_name,
                "first_name": first_name,
                "position": _stat(player, ("position", "pos"), ""),
                "number": _stat(player, ("number", "jerseyNumber", "uniformNumber"), ""),
                "starter": _stat(player, ("starter", "isStarter"), False),
                "participated": _stat(player, ("participated", "didParticipate", "played"), True),
                "at_bats": safe_float(_stat(player, ("ab", "atBats", "at_bats", "atbats"))),
                "runs_scored": safe_float(_stat(player, ("r", "runs", "runsScored", "runsscored"))),
                "hits": safe_float(_stat(player, ("h", "hits"))),
                "rbi": safe_float(_stat(player, ("rbi", "runsBattedIn", "runsbattedin"))),
                "walks": safe_float(_stat(player, ("bb", "walks", "baseOnBalls", "baseonballs"))),
                "strikeouts": safe_float(_stat(player, ("so", "strikeouts", "strikeOuts"))),
                "batting_average": safe_float(_stat(player, ("ba", "battingAverage", "battingaverage"))),
                "on_base_pct": safe_float(_stat(player, ("obp", "onBasePercentage", "onbasepercentage"))),
                "putouts": safe_float(_stat(player, ("po", "putouts"))),
                "assists": safe_float(_stat(player, ("a", "assists"))),
                "errors": safe_float(_stat(player, ("e", "errors"))),
                "doubles": safe_float(_stat(
                    player, ("2b", "doubles"),
                    doubles_map.get(normalized_name, 0)
                )),
                "triples": safe_float(_stat(
                    player, ("3b", "triples"),
                    triples_map.get(normalized_name, 0)
                )),
                "home_runs": safe_float(_stat(
                    player, ("hr", "homeRuns", "homeruns"),
                    home_runs_map.get(normalized_name, 0)
                )),
                "doubles_hittingSeason": safe_float(_stat(
                    player, ("doubles_hittingSeason", "doublesHittingSeason")
                )),
                "triples_hittingSeason": safe_float(_stat(
                    player, ("triples_hittingSeason", "triplesHittingSeason")
                )),
                "home_runs_hittingSeason": safe_float(_stat(
                    player, ("home_runs_hittingSeason", "homeRunsHittingSeason")
                )),
            })

    if not rows or teams_with_players == 0:
        if debug:
            print(f"  {game_id}: boxscore downloaded, but no player rows were recognized.")
            for index, team in enumerate(teams):
                print(f"    Team {index} keys: {list(team.keys())}")
        return None

    return rows


def _scoreboard_games_for_date(current_date, max_pages=50):
    year, month, day = current_date.year, current_date.month, current_date.day
    games_by_id = {}
    page_signatures = set()
    pagination_finished = False

    for page in range(1, max_pages + 1):
        url = SCOREBOARD_URL.format(year=year, month=month, day=day)
        if page > 1:
            url += f"?page={page}"

        data = get_json(url)
        raw_games = data.get("games", []) if isinstance(data, dict) else []

        if not raw_games:
            pagination_finished = True
            break

        signature = tuple(
            extract_game_id(entry.get("game", entry) if isinstance(entry, dict) else {})
            or str(entry)
            for entry in raw_games
        )
        if signature in page_signatures:
            pagination_finished = True
            break
        page_signatures.add(signature)

        for entry in raw_games:
            if not isinstance(entry, dict):
                continue
            game = entry.get("game", entry)
            game_id = extract_game_id(game)
            if game_id:
                games_by_id[game_id] = game

    else:
        raise RuntimeError(
            f"Reached max_pages={max_pages} for {current_date}; "
            "increase max_pages or inspect scoreboard pagination."
        )

    if not pagination_finished:
        raise RuntimeError(f"Scoreboard pagination did not finish for {current_date}.")

    return list(games_by_id.keys())


def extract_player_games(startDate="2026-02-05", endDate="2026-06-05", debug=True):
    processed_games = load_processed_games()
    start = datetime.strptime(startDate, "%Y-%m-%d")
    end = datetime.strptime(endDate, "%Y-%m-%d")

    fieldnames = [
        "date", "game_id", "team", "opponent", "last_name", "first_name",
        "position", "number", "starter", "participated", "at_bats", "runs_scored",
        "hits", "rbi", "walks", "strikeouts", "batting_average", "on_base_pct",
        "putouts", "assists", "errors", "doubles", "triples", "home_runs",
        "doubles_hittingSeason", "triples_hittingSeason", "home_runs_hittingSeason"
    ]

    file_exists = os.path.exists(OUTPUT_CSV) and os.path.getsize(OUTPUT_CSV) > 0
    total_rows = 0

    with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
            csvfile.flush()

        current_date = start
        while current_date <= end:
            date_str = current_date.strftime("%Y-%m-%d")

            try:
                game_ids = _scoreboard_games_for_date(current_date)
            except Exception as error:
                print(f"[{date_str}] Scoreboard failed: {error}. Date will be retried.")
                current_date += timedelta(days=1)
                continue

            games_processed_today = 0
            games_failed_today = 0

            for game_id in game_ids:
                if game_id in processed_games:
                    continue

                rows = process_game(game_id, date_str, debug=debug)

                # None means request/structure/player extraction failed. Do not checkpoint.
                if rows is None:
                    games_failed_today += 1
                    continue

                # A valid empty list is not expected for a completed team boxscore.
                if rows:
                    writer.writerows(rows)
                    csvfile.flush()
                    total_rows += len(rows)

                # Checkpoint only after successful boxscore parsing.
                processed_games.add(game_id)
                save_processed_games(processed_games)
                games_processed_today += 1
                time.sleep(0.15)

            print(
                f"[{date_str}] Found {len(game_ids)} games; "
                f"processed {games_processed_today}; "
                f"failed/unrecognized {games_failed_today}; "
                f"{total_rows} new player rows saved."
            )

            current_date += timedelta(days=1)

    print(f"Finished. Saved {total_rows} new player rows to {OUTPUT_CSV}.")


if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 3:
        start_date = sys.argv[1]
        end_date = sys.argv[2]
    elif len(sys.argv) == 2:
        start_date = end_date = sys.argv[1]
    else:
        start_date = "2026-02-05"
        end_date = "2026-06-05"

    extract_player_games(start_date, end_date, debug=True)
