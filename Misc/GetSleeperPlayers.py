import requests
import pandas as pd
import re

# Your normalization function
def normalize(name):
    if not isinstance(name, str):
        return ""
    name = name.lower().strip()
    name = name.replace("'", "").replace(".", "")
    name = re.sub(r"\b(jr|sr|iii|ii|iv|v)\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[^\w\s]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name

# Fetch Sleeper players
def fetch_sleeper_players():
    url = "https://api.sleeper.app/v1/players/nfl"
    resp = requests.get(url)
    data = resp.json()

    rows = []
    for player_id, info in data.items():
        full_name = info.get("full_name", "")
        position = info.get("position", "")
        if not full_name:
            continue

        rows.append({
            "player_id": player_id,
            "full_name": full_name,
            "position": position,
            "name_norm": normalize(full_name)
        })

    return pd.DataFrame(rows)

# Save to CSV for inspection
if __name__ == "__main__":
    df = fetch_sleeper_players()
    df = df.sort_values(by="name_norm")
    df.to_csv("SleeperPlayers_Normalized.csv", index=False)
    print("✅ Sleeper normalized player list written to SleeperPlayers_Normalized.csv")
