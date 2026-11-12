"""Constantes de l'intégration NBA."""
from datetime import timedelta

DOMAIN = "nba"
CONF_TEAMS = "teams"
CONF_NOTIFY_START = "notify_start"
CONF_NOTIFY_END = "notify_end"

BASE_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
STANDINGS_URL = "https://site.api.espn.com/apis/v2/sports/basketball/nba/standings"
TEAMS_URL = f"{BASE_URL}/teams"
SCOREBOARD_URL = f"{BASE_URL}/scoreboard"
TEAM_SCHEDULE_URL = f"{BASE_URL}/teams/{{team_id}}/schedule"
SUMMARY_URL = f"{BASE_URL}/summary"
# Leaders de la saison (marqueurs, passeurs, ...)
LEADERS_URL = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/statistics/byathlete"

# Catégories de leaders : clé -> (libellé, nom du tri ESPN)
LEADER_CATEGORIES = {
    "points": ("Marqueurs", "offensive.avgPoints:desc"),
    "rebounds": ("Rebondeurs", "general.avgRebounds:desc"),
    "assists": ("Passeurs", "offensive.avgAssists:desc"),
    "steals": ("Intercepteurs", "defensive.avgSteals:desc"),
    "blocks": ("Contreurs", "defensive.avgBlocks:desc"),
}
LEADERS_COUNT = 10

# Nombre de derniers matchs conservés par équipe
LAST_GAMES_COUNT = 5

SERVICE_GET_GAME_DETAILS = "get_game_details"

SCAN_INTERVAL_IDLE = timedelta(minutes=15)
SCAN_INTERVAL_LIVE = timedelta(seconds=30)

EVENT_GAME_START = "nba_game_start"
EVENT_GAME_END = "nba_game_end"
