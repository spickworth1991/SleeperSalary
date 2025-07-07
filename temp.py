import requests
import pandas as pd

# Target player IDs (as strings)
target_ids = {
    "0", "10233", "11145", "11949", "12503", "13179", "2323",
    "2422", "3199", "4958", "4990", "5436", "5860", "5878",
    "5928", "7127", "7606", "7621", "7688", "8312"
}


# Fetch all players from Sleeper
url = "https://api.sleeper.app/v1/players/nfl"
sleeper_data = requests.get(url).json()

# Match by player_id
matches = []
for player in sleeper_data.values():
    if str(player.get("player_id")) in target_ids:
        matches.append({
            "player_id": player.get("player_id"),
            "full_name": player.get("full_name"),
            "position": player.get("position"),
            "team": player.get("team")
        })

# Display results
df = pd.DataFrame(matches).sort_values("player_id")
print(df)
