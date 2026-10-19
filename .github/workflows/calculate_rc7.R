library(softballR)
library(tidyverse)
library(jsonlite)

# 1. Fetch current season NCAA softball player box scores
current_year <- 2025 # Update as needed for active season
box_scores <- load_ncaa_softball_playerbox(season = current_year, category = "Hitting")

# 2. Process Player Batting Stats & Calculate Classic RC
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
    RC7_raw = ifelse(Outs > 0, (RC / Outs) * 21, 0),
    OPAF = 1.00, # Default adjustment factor
    RC7_adj = round(RC7_raw * OPAF, 2),
    RC7_raw = round(RC7_raw, 2)
  ) %>%
  filter(PA >= 30) %>% # Minimum plate appearance threshold
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

# 3. Export to players.json
write_json(player_stats, "players.json", pretty = TRUE)
cat("Successfully generated players.json\n")
