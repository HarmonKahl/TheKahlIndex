import os
import json
import pandas as pd

def calculate_rc7(input_path="player_games_season.csv", output_path="players.json", min_ab=20):
    if not os.path.exists(input_path) or os.stat(input_path).st_size == 0:
        print(f"Warning: {input_path} not found or empty. Writing empty array to {output_path}.")
        with open(output_path, "w") as f:
            json.dump([], f)
        return

    print(f"Loading player game data from {input_path}...")
    df = pd.read_csv(input_path)

    # Ensure required numeric columns are present and clean
    numeric_cols = ["at_bats", "hits", "runs_scored", "rbi", "walks", "strikeouts"]
    for col in numeric_cols:
        if col not in df.columns:
            df[col] = 0
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Create full name for grouping
    df["full_name"] = df["first_name"].fillna("").astype(str).str.strip() + " " + df["last_name"].fillna("").astype(str).str.strip()
    df["full_name"] = df["full_name"].str.strip()

    # Aggregate stats per player across all games
    grouped = df.groupby(["full_name", "team"], as_index=False).agg({
        "game_id": "count",        # Games played
        "at_bats": "sum",
        "hits": "sum",
        "runs_scored": "sum",
        "rbi": "sum",
        "walks": "sum",
        "strikeouts": "sum"
    }).rename(columns={
        "game_id": "G",
        "at_bats": "AB",
        "hits": "H",
        "runs_scored": "R",
        "rbi": "RBI",
        "walks": "BB",
        "strikeouts": "SO"
    })

    # --- FILTER OUT PLAYERS WITH LESS THAN 20 ABs ---
    grouped = grouped[grouped["AB"] >= min_ab].copy()
    print(f"Filtered dataset to {len(grouped)} players with at least {min_ab} ABs.")

    # --- Calculate RC7 / Adjusted Runs Created ---
    players_list = []
    for _, row in grouped.iterrows():
        ab = row["AB"]
        h = row["H"]
        bb = row["BB"]
        g = row["G"]

        # Basic Runs Created (RC)
        if (ab + bb) > 0:
            a = h + bb
            b = (1.125 * h) + (0.25 * bb)  # Linear weights proxy for Total Bases
            c = ab + bb
            rc = (a * b) / c
        else:
            rc = 0.0

        # Adjust per 7 innings / 21 outs (RC7)
        outs = (ab - h)
        rc7 = (rc / outs) * 21 if outs > 0 else 0.0

        players_list.append({
            "name": row["full_name"],
            "team": row["team"],
            "games": int(g),
            "ab": int(ab),
            "hits": int(h),
            "runs": int(row["R"]),
            "rbi": int(row["RBI"]),
            "walks": int(bb),
            "strikeouts": int(row["SO"]),
            "rc": round(rc, 2),
            "rc7": round(rc7, 2)
        })

    # Sort players by RC7 descending
    players_list.sort(key=lambda x: x["rc7"], reverse=True)

    with open(output_path, "w") as f:
        json.dump(players_list, f, indent=2)

    print(f"Successfully calculated RC7 for {len(players_list)} qualified players and saved to {output_path}!")

if __name__ == "__main__":
    calculate_rc7()
