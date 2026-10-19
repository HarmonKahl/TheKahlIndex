library(softballR)
library(tidyverse)
library(jsonlite)

# 1. Dynamically get current season year (2026)
current_year <- as.numeric(format(Sys.Date(), "%Y"))

cat(paste0("Fetching player box scores for season: ", current_year, "\n"))

# 2. Fetch NCAA softball player hitting box scores via softballR
box_scores <- load_ncaa_softball_playerbox(season = current_year, category = "Hitting")

# 3. Calculate Team Level Pitching RA7 (Runs Allowed per 7 Innings) for OPAF
# Extract pitching data if available, otherwise default OPAF baseline
team_pitching_ra7 <- tryCatch({
  pitching_box <- load_ncaa_softball_playerbox(season = current_year, category = "Pitching")
  pitching_box %>%
    filter(!is.na(IP) & IP > 0) %>%
    group_by(team) %>%
    summarise(
      total_IP = sum(IP, na.rm = TRUE),
      total_R_allowed = sum(R, na.rm = TRUE),
      .groups = "drop"
    ) %>%
    mutate(
      team_RA7 = ifelse(total_IP > 0, (total_R_allowed / total_IP) * 7, 0)
    )
}, error = function(e) {
  message("Pitching logs unavailable, falling back to neutral OPAF.")
  return(NULL)
})

# Calculate National Average Pitching RA7
nat_avg_ra7 <- if (!is.null(team_pitching_ra7) && nrow(team_pitching_ra7) > 0) {
  mean(team_pitching_ra7$team_RA7, na.rm = TRUE)
} else {
  4.00 # Standard Division I baseline fallback
}

# 4. Process Player Batting Stats & Calculate Classic RC
player_stats <- box_scores %>%
  filter(!is.na(AB) & AB > 0) %>%
  group_by(player_id, player_name, team) %>%
  summarise(
    games_played = n_distinct(game_id),
    AB = sum(AB, na.rm = TRUE),
    H = sum(H, na.rm = TRUE),
    BB = sum(BB, na.rm = TRUE),
    X2B = sum(X2B, na.rm = TRUE),
    X3B = sum(X3B, na.rm = TRUE),
    HR = sum(HR, na.rm = TRUE),
    .groups = "drop"
  ) %>%
  mutate(
    TB = H + X2B + (2 * X3B) + (3 * HR),
    PA = AB + BB,
    Outs = AB - H,
    
    # Bill James Classic RC: ((H + BB) * TB) / (AB + BB)
    RC = ifelse(PA > 0, ((H + BB) * TB) / PA, 0),
    
    # Raw RC per 21 outs (7 innings)
    RC7_raw = ifelse(Outs > 0, (RC / Outs) * 21, 0)
  ) %>%
  filter(PA >= 30) # Minimum plate appearance threshold

# 5. Merge Pitching Strength Adjustments (OPAF)
if (!is.null(team_pitching_ra7) && nrow(team_pitching_ra7) > 0) {
  final_players <- player_stats %>%
    left_join(team_pitching_ra7, by = "team") %>%
    mutate(
      OPAF = ifelse(!is.na(team_RA7) & team_RA7 > 0, nat_avg_ra7 / team_RA7, 1.00),
      RC7_adj = round(RC7_raw * OPAF, 2),
      RC7_raw = round(RC7_raw, 2),
      OPAF = round(OPAF, 2)
    )
} else {
  final_players <- player_stats %>%
    mutate(
      OPAF = 1.00,
      RC7_adj = round(RC7_raw, 2),
      RC7_raw = round(RC7_raw, 2)
    )
}

# 6. Format and Sort Final Columns
final_output <- final_players %>%
  select(
    player_name,
    team,
    games_played,
    PA,
    AB,
    H,
    HR,
    RC7_raw,
    OPAF,
    RC7_adj
  ) %>%
  arrange(desc(RC7_adj))

# 7. Write directly to JSON file
write_json(final_output, "players.json", pretty = TRUE)
cat("Successfully generated players.json for season ", current_year, "\n")
