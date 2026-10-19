import json
import os
import pandas as pd


def calculate_rc7():
    csv_file = "player_boxscores_2026.csv"

    if not os.path.exists(csv_file):
        print(
            f"Warning: {csv_file} not found. Writing empty array to players.json."
        )
        with open("players.json", "w") as f:
            json.dump([], f)
        return

    df = pd.read_csv(csv_file)

    if df.empty:
        print("No boxscore rows found. Writing empty array to players.json.")
        with open("players.json", "w") as f:
            json.dump([], f)
        return

    # Clean numerical columns
    stat_cols = ["AB", "H", "BB", "2B", "3B", "HR"]
    for col in stat_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Aggregate stats by player for the season
    player_stats = (
        df.groupby(["player_name", "team"])
        .agg({
            "game_id": "nunique",
            "AB": "sum",
            "H": "sum",
            "BB": "sum",
            "2B": "sum",
            "3B": "sum",
            "HR": "sum",
        })
        .reset_index()
    )

    player_stats.rename(columns={"game_id": "games_played"}, inplace=True)

    # Calculate Total Bases, PA, and Outs
    player_stats["TB"] = (
        player_stats["H"]
        + player_stats["2B"]
        + (2 * player_stats["3B"])
        + (3 * player_stats["HR"])
    )
    player_stats["PA"] = player_stats["AB"] + player_stats["BB"]
    player_stats["Outs"] = player_stats["AB"] - player_stats["H"]

    # Classic Bill James RC & Raw RC7
    player_stats["RC"] = player_stats.apply(
        lambda r: ((r["H"] + r["BB"]) * r["TB"]) / r["PA"]
        if r["PA"] > 0
        else 0,
        axis=1,
    )
    player_stats["RC7_raw"] = player_stats.apply(
        lambda r: (r["RC"] / r["Outs"]) * 21 if r["Outs"] > 0 else 0, axis=1
    )

    # Filter qualification threshold (minimum 15 PA)
    qualified_players = player_stats[player_stats["PA"] >= 15].copy()

    # OPAF Baseline setup
    qualified_players["OPAF"] = 1.00
    qualified_players["RC7_adj"] = (
        qualified_players["RC7_raw"] * qualified_players["OPAF"]
    ).round(2)
    qualified_players["RC7_raw"] = qualified_players["RC7_raw"].round(2)

    # Sort & Output JSON
    output_df = qualified_players[[
        "player_name",
        "team",
        "games_played",
        "PA",
        "AB",
        "H",
        "HR",
        "RC7_raw",
        "OPAF",
        "RC7_adj",
    ]].sort_values(by="RC7_adj", ascending=False)

    records = output_df.to_dict(orient="records")
    with open("players.json", "w") as f:
        json.dump(records, f, indent=2)

    print(
        f"Successfully processed {len(records)} qualified players into players.json!"
    )


if __name__ == "__main__":
    calculate_rc7()
