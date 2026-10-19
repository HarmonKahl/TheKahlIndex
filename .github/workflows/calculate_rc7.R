library(softballR)
library(tidyverse)
library(jsonlite)

# 1. Fetch current season NCAA softball player box scores
current_year <- 2025 # Update as needed for the active season
box_scores <- load_ncaa_softball_player_box(current_year)

# 2. Calculate Team Level Pitching RA7 (Runs Allowed per 7 Innings) for OPAF
team_pitching_ra7 <- box_scores %>%
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

# Calculate National Average Pitching RA7
nat_avg_ra7 <- mean(team_pitching_ra7$team_RA7, na.rm = TRUE)

# 3. Process Player Batting Stats & Calculate Classic RC
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

# 4. Merge Opponent Pitching Strengths & Calculate Final Adjusted Metric (RC7_adj)
# (Assuming opponent schedule weighting; default OPAF = 1 if detailed opp logs are flat)
final_players <- player_stats %>%
  left_join(team_pitching_ra7, by = "team") %>%
  mutate(
    OPAF = ifelse(team_RA7 > 0, nat_avg_ra7 / team_RA7, 1.0),
    RC7_adj = round(RC7_raw * OPAF, 2),
    RC7_raw = round(RC7_raw, 2),
    BA = round(H / AB, 3)
  ) %>%
  select(
    player_name,
    team,
    games_played,
    PA,
    AB,
    H,
    HR,
    RC7_raw,
    OPAF = round(OPAF, 2),
    RC7_adj
  ) %>%
  arrange(desc(RC7_adj))

# 5. Export to players.json
write_json(final_players, "players.json", pretty = TRUE)
cat("Successfully generated players.json\n")
