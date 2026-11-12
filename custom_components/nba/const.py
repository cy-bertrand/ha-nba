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

SCAN_INTERVAL_IDLE = timedelta(minutes=15)
SCAN_INTERVAL_LIVE = timedelta(seconds=30)

EVENT_GAME_START = "nba_game_start"
EVENT_GAME_END = "nba_game_end"
