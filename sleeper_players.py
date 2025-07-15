import requests
import json

def fetch_and_save_sleeper_players(filename="sleeper_players.json"):
    url = "https://api.sleeper.app/v1/players/nfl"
    resp = requests.get(url)
    if resp.status_code != 200:
        raise Exception(f"Failed to fetch Sleeper players: {resp.text}")
    
    all_players = resp.json()
    slim_players = {}

    for player_id, data in all_players.items():
        full_name = data.get("full_name") or f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()

        # Skip if no name
        if not full_name.strip():
            continue

        slim_players[player_id] = {
            "player_id": player_id,
            "full_name": full_name,
            "position": data.get("position", "N/A"),
            "team": data.get("team", "No Team"),
            "age": data.get("age", "N/A")
        }

    with open(filename, "w") as f:
        json.dump(slim_players, f, indent=2)

    print(f"✅ Saved {len(slim_players)} players to {filename}")

if __name__ == "__main__":
    fetch_and_save_sleeper_players()
