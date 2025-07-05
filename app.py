import json
import re
from google.oauth2 import service_account
from googleapiclient.discovery import build
import pandas as pd
import requests
from flask import Flask, request, render_template, redirect, url_for, flash, session



app = Flask(__name__)
app.secret_key = "supersecret"  # Needed for flashing messages

CONFIG_FILE = "config/leagues.json"
ADMIN_PASSWORD = "sleeperpass123"

SERVICE_ACCOUNT_FILE = "config/nfl-stats-ff-00a13e9db7db.json"  # update path if needed
SPREADSHEET_ID = "1fm6o9HFT48F1AG0A5f4te3BDK8PHVnxksUVjWTDSCiI"
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

def get_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('sheets', 'v4', credentials=creds)


def load_flattened_salary_data():
    df = pd.read_csv("SalaryDB.csv", dtype={"player_id": str})
    df["player_id"] = df["player_id"].astype(str).str.strip()
    return df


def load_all_leagues():
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        leagues = load_all_leagues()
        name = request.form.get("league_name", "").strip()
        pw = request.form.get("league_password", "")
        admin_pw = request.form.get("admin_password", "")

        league = leagues.get(name)
        if not league or pw != league.get("password"):
            flash("Invalid league name or password.", "error")
            return redirect(url_for("login"))

        session["league_name"] = name
        session["is_admin"] = (admin_pw == league.get("admin_password"))

        if session["is_admin"]:
            return redirect(url_for("admin_page", league_name=name))
        else:
            return redirect(url_for("league_summary", league_name=name))

    return render_template("login.html")




def get_league_rosters(league_id):
    url = f"https://api.sleeper.app/v1/league/{league_id}/rosters"
    resp = requests.get(url)
    if resp.status_code != 200:
        raise Exception(f"Failed to fetch rosters: {resp.text}")
    return resp.json()



@app.route("/league/<league_name>")
def league_summary(league_name):
    leagues = load_all_leagues()
    config = leagues.get(league_name)
    if not config:
        return "❌ League not found."

    league_id = config.get("league_id")
    if not league_id:
        return "❌ League ID not set. Admin must configure it."

    try:
        df = load_flattened_salary_data()
        rosters = get_league_rosters(league_id)

        # Make sure all player_ids in df are strings
        df["player_id"] = df["player_id"].astype(str).str.strip()

        team_data = []
        for roster in rosters:
            user_id = roster.get("owner_id")
            starters = roster.get("starters", [])
            players = roster.get("players", [])

            all_ids = list(set(map(str, (starters or []) + (players or []))))

            # Track unmatched player IDs for debugging
            unmatched_ids = [pid for pid in all_ids if pid not in df["player_id"].values]

            team_df = df[df["player_id"].isin(all_ids)].copy()

            total_cap = 0
            if "Cap Hit" in team_df.columns:
                team_df["Cap Hit Num"] = pd.to_numeric(
                    team_df["Cap Hit"]
                        .replace({r'[\$,]': '', '-': '0', '': '0'}, regex=True),
                    errors="coerce"
                ).fillna(0.0)

                total_cap = team_df["Cap Hit Num"].sum()

            team_data.append({
                "user_id": user_id,
                "player_count": len(all_ids),
                "matched_count": len(team_df),
                "total_cap": f"${total_cap:,.0f}",
                "players": team_df.to_dict(orient="records"),
                "unmatched_ids": unmatched_ids  # optional: remove in production
            })

        return render_template("league.html", league_name=league_name, teams=team_data)

    except Exception as e:
        return f"❌ Error: {str(e)}"



@app.route("/admin/<league_name>", methods=["GET", "POST"])
def admin_page(league_name):
    leagues = load_all_leagues()
    if not session.get("is_admin") or session.get("league_name") != league_name:
        return "🔒 Access denied."

    if request.method == "POST":
        league_id = request.form.get("league_id", "").strip()
        leagues[league_name]["league_id"] = league_id
        with open(CONFIG_FILE, "w") as f:
            json.dump(leagues, f, indent=2)
        flash("✅ League ID updated.", "success")
        return redirect(url_for("admin_page", league_name=league_name))

    config = leagues[league_name]

    # Load unmatched player IDs across the whole league
    unmatched_ids = []
    try:
        df = load_flattened_salary_data()
        df["player_id"] = df["player_id"].astype(str).str.strip()

        league_id = config.get("league_id")
        rosters = get_league_rosters(league_id)

        for roster in rosters:
            starters = roster.get("starters", [])
            players = roster.get("players", [])
            all_ids = list(set(map(str, (starters or []) + (players or []))))
            ids_not_matched = [pid for pid in all_ids if pid not in df["player_id"].values]
            unmatched_ids.extend(ids_not_matched)

        unmatched_ids = sorted(set(unmatched_ids))  # Remove duplicates + sort
    except Exception as e:
        unmatched_ids = [f"(Error fetching unmatched IDs: {str(e)})"]

    return render_template(
        "admin_settings.html",
        config=config,
        league_name=league_name,
        unmatched_ids=unmatched_ids
    )



@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)
