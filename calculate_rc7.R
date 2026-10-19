library(softballR)
library(tidyverse)
library(jsonlite)

# 1. Get current season year
current_year <- as.numeric(format(Sys.Date(), "%Y"))
cat(paste0("Fetching player box scores for season: ", current_year, "\n"))

# 2. Fetch NCAA softball player hitting box scores
box_scores <- tryCatch({
  load_ncaa_softball_playerbox(season = current_year, category = "Hitting")
}, error = function(e) {
  message(paste("Error loading box scores:", e$message))
  return(NULL)
})

# Default empty structure if fetch fails or yields zero rows
if (is.null(box_scores) || nrow(box_scores) == 0) {
  message("No box score data available. Writing empty array to players.json.")
  write_json(list(), "players.json", pretty = TRUE)
  quit(save = "no", status = 0)
}

# Ensure core counting stats are numeric
box_scores <- box_scores %>%
  mutate(across(c(AB, H, BB, X2B, X3B, HR), ~ as.numeric(as.character(.))))

# 3. Calculate Team Level Pitching RA7 for OPAF
team_pitching_ra7 <- tryCatch({
  pitching_box <- load_ncaa_softball_playerbox(season = current_year, category = "Pitching")
  if (!is.null(pitching_box) && nrow(pitching_box) > 0) {
    pitching_box %>%
      mutate(
        IP = as.numeric(as.character(IP)),
        R = as.numeric(as.character(R))
      ) %>%
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
  } else { NULL }
}, error = function(e) {
  message("Pitching logs unavailable, falling back to neutral OPAF baseline.")
  return(NULL)
})

nat_avg_ra7 <- if (!is.null(team_pitching_ra7) && nrow(team_pitching_ra7) > 0) {
  mean(team_pitching_ra7$team_RA7, na.rm = TRUE)
} else {
  4.00
}

# 4. Calculate Classic RC & Scale to RC7
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
    RC = ifelse(PA > 0, ((H + BB) * TB) / PA, 0),
    RC7_raw = ifelse(Outs > 0, (RC / Outs) * 21, 0)
  ) %>%
  filter(PA >= 30)

# 5. Apply Pitching Adjustments (OPAF)
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

# 6. Select, Sort, and Output to JSON
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

write_json(final_output, "players.json", pretty = TRUE)
cat("Successfully generated players.json for season ", current_year, "\n")
