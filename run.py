import requests
import csv

def fetch_json(url):
    response = requests.get(url)
    response.raise_for_status()
    return response.json()

def build_league_data(league_id):
    # Get league name
    league_info = fetch_json(f"https://api.sleeper.app/v1/league/{league_id}")
    league_name = league_info.get("name", f"League {league_id}")

    # Get users (user_id → display_name)
    users = fetch_json(f"https://api.sleeper.app/v1/league/{league_id}/users")
    user_map = {user["user_id"]: user.get("display_name", "Unknown") for user in users}

    # Get rosters (includes total points)
    rosters = fetch_json(f"https://api.sleeper.app/v1/league/{league_id}/rosters")

    league_rows = []
    for roster in rosters:
        user_id = roster.get("owner_id")
        points = roster.get("settings", {}).get("fpts", 0)
        if user_id:
            display_name = user_map.get(user_id, "Unknown")
            league_rows.append({
                "league_id": league_id,
                "league_name": league_name,
                "display_name": display_name,
                "total_points": round(points, 2)
            })

    return league_rows

def build_tournament_summary(league_ids):
    all_rows = []

    for league_id in league_ids:
        league_data = build_league_data(league_id)
        all_rows.extend(league_data)

    # Write League Totals
    with open("league_totals.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["league_id", "league_name", "display_name", "total_points"])
        writer.writeheader()
        for row in sorted(all_rows, key=lambda x: (x["league_name"], -x["total_points"])):
            writer.writerow(row)

    # Write Overall Totals (per league + display_name combo)
    with open("overall_totals.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["league_name", "display_name", "total_points"])
        writer.writeheader()
        for row in sorted(all_rows, key=lambda x: -x["total_points"]):
            writer.writerow({
                "league_name": row["league_name"],
                "display_name": row["display_name"],
                "total_points": row["total_points"]
            })

# === Example usage ===
league_ids = [
    "999392600970825728",  # Example IDs
    "1117649535347683328",
    "1104461823471992832"
]
build_tournament_summary(league_ids)
