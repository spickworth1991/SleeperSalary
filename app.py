# ======================== Imports ========================
import json
import os
from datetime import datetime
import pandas as pd
import requests
from flask import Flask, render_template, request, redirect, url_for, session, flash
from google.oauth2 import service_account
from googleapiclient.discovery import build
from difflib import get_close_matches


# ======================== Flask App Setup ========================
app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = "supersecret"  # Needed for flashing messages

if os.environ.get("RENDER") == "true":
    SERVICE_ACCOUNT_FILE = "nfl-stats-ff-00a13e9db7db.json"
else:
    SERVICE_ACCOUNT_FILE = "config/leagues.json"

SPREADSHEET_ID = "1fm6o9HFT48F1AG0A5f4te3BDK8PHVnxksUVjWTDSCiI"
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']


# ======================== Utility Functions ========================
def get_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('sheets', 'v4', credentials=creds)


def load_flattened_salary_data():
    global SALARY_DB_CACHE
    if SALARY_DB_CACHE is not None:
        return SALARY_DB_CACHE
    if os.environ.get("RENDER") == "true":
        df = pd.read_csv("SalaryDB.csv", dtype={"player_id": str})
        df["player_id"] = df["player_id"].astype(str).str.strip()
        SALARY_DB_CACHE = df
        return df
    else:
        df = pd.read_csv("SalaryDB.csv", dtype={"player_id": str})
        df["player_id"] = df["player_id"].astype(str).str.strip()
        SALARY_DB_CACHE = df
        return df


def get_league_rosters(league_id):
    url = f"https://api.sleeper.app/v1/league/{league_id}/rosters"
    resp = requests.get(url)
    if resp.status_code != 200:
        raise Exception(f"Failed to fetch rosters: {resp.text}")
    return resp.json()


def get_league_users(league_id):
    url = f"https://api.sleeper.app/v1/league/{league_id}/users"
    resp = requests.get(url)
    if resp.status_code != 200:
        raise Exception(f"Failed to fetch users: {resp.text}")
    return resp.json()


def load_all_leagues():
    service = get_service()
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID,
                                range="config!A2:F").execute()
    values = result.get('values', [])
    leagues = {}
    for row in values:
        if len(row) < 5:
            continue
        league_name = row[0]
        leagues[league_name] = {
            "password": row[1],
            "admin_password": row[2],
            "league_id": row[3],
            "league_name": league_name,
        }
        if len(row) >= 5 and row[4]:
            try:
                leagues[league_name]["themes"] = json.loads(row[4])
            except:
                leagues[league_name]["themes"] = {}
        if len(row) >= 6:
            leagues[league_name]["draft_room_public"] = row[5].strip().lower() == "true"
        else:
            leagues[league_name]["draft_room_public"] = False

    return leagues


def save_new_league_to_google_sheet(league_name, password, admin_password,
                                    league_id):
    service = get_service()
    sheet = service.spreadsheets()
    values = [[
        league_name.strip(),
        password.strip(),
        admin_password.strip(),
        league_id.strip(),
        json.dumps({})
    ]]
    body = {"values": values}
    sheet.values().append(spreadsheetId=SPREADSHEET_ID,
                          range="config!A2",
                          valueInputOption="RAW",
                          insertDataOption="INSERT_ROWS",
                          body=body).execute()


def update_league_config(league_name, field, value):
    service = get_service()
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID,
                                range="config!A2:A").execute()
    league_names = [row[0] for row in result.get("values", [])]
    if league_name not in league_names:
        return False
    row_index = league_names.index(league_name) + 2
    col_map = {
        "password": "B",
        "admin_password": "C",
        "league_id": "D",
        "themes": "E",
        "draft_room_public": "F"
    }
    if field == "themes":
        value = json.dumps(value)
    range_ = f"config!{col_map[field]}{row_index}"
    sheet.values().update(spreadsheetId=SPREADSHEET_ID,
                          range=range_,
                          valueInputOption="RAW",
                          body={
                              "values": [[value]]
                          }).execute()
    return True


def save_league_session_to_sheet(league_id, users, rosters):
    service = get_service()
    sheets_api = service.spreadsheets()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Step 1: Get list of sheet tabs
    metadata = sheets_api.get(spreadsheetId=SPREADSHEET_ID).execute()
    sheet_titles = [s["properties"]["title"] for s in metadata["sheets"]]

    # Step 2: Create the sheet if missing
    if str(league_id) not in sheet_titles:
        sheets_api.batchUpdate(spreadsheetId=SPREADSHEET_ID,
                               body={
                                   "requests": [{
                                       "addSheet": {
                                           "properties": {
                                               "title": str(league_id)
                                           }
                                       }
                                   }]
                               }).execute()

    # Step 3: Clear sheet contents before writing
    sheets_api.values().clear(spreadsheetId=SPREADSHEET_ID,
                              range=f"{league_id}!A1:Z1000").execute()

    # Step 4: Build and write rows
    rows = [["Timestamp", timestamp], ["League ID", league_id], [], ["USERS"]]
    for user in users:
        rows.append([
            user.get("user_id", ""),
            user.get("display_name", ""),
            user.get("metadata", {}).get("team_name", "")
        ])
    rows.append([])
    rows.append(["ROSTERS"])
    for r in rosters:
        players = ", ".join(r.get("players", [])) if r.get("players") else ""
        starters = ", ".join(r.get("starters",
                                   [])) if r.get("starters") else ""
        rows.append([r.get("owner_id", ""), players, starters])

    sheets_api.values().update(spreadsheetId=SPREADSHEET_ID,
                               range=f"{league_id}!A1",
                               valueInputOption="RAW",
                               body={
                                   "values": rows
                               }).execute()


def load_users_and_rosters_from_sheet(league_id):
    service = get_service()
    sheet = service.spreadsheets().values()

    data = sheet.get(spreadsheetId=SPREADSHEET_ID,
                     range=f"{league_id}!A1:Z1000").execute().get(
                         "values", [])

    users = []
    rosters = []
    section = None
    for row in data:
        if not row:
            continue
        if row[0] == "USERS":
            section = "users"
            continue
        elif row[0] == "ROSTERS":
            section = "rosters"
            continue
        if section == "users" and len(row) >= 2:
            users.append({
                "user_id": row[0],
                "display_name": row[1],
                "metadata": {
                    "team_name": row[2] if len(row) > 2 else ""
                }
            })
        elif section == "rosters" and len(row) >= 3:
            rosters.append({
                "owner_id": row[0],
                "players": row[1].split(", ") if row[1] else [],
                "starters": row[2].split(", ") if row[2] else []
            })

    return users, rosters


# ======================== Global Constants ========================
SLEEPER_CACHE = {}

SALARY_DB_CACHE = None

TEAM_THEME_DATA = {
    "ARI": {
        "name": "Arizona Cardinals",
        "color": "#97233F",
        "logo": "ARI.png"
    },
    "ATL": {
        "name": "Atlanta Falcons",
        "color": "#A71930",
        "logo": "ATL.png"
    },
    "BAL": {
        "name": "Baltimore Ravens",
        "color": "#241773",
        "logo": "BAL.png"
    },
    "BUF": {
        "name": "Buffalo Bills",
        "color": "#00338D",
        "logo": "BUF.png"
    },
    "CAR": {
        "name": "Carolina Panthers",
        "color": "#0085CA",
        "logo": "CAR.png"
    },
    "CHI": {
        "name": "Chicago Bears",
        "color": "#0B162A",
        "logo": "CHI.png"
    },
    "CIN": {
        "name": "Cincinnati Bengals",
        "color": "#FB4F14",
        "logo": "CIN.png"
    },
    "CLE": {
        "name": "Cleveland Browns",
        "color": "#311D00",
        "logo": "CLE.png"
    },
    "DAL": {
        "name": "Dallas Cowboys",
        "color": "#041E42",
        "logo": "DAL.png"
    },
    "DEN": {
        "name": "Denver Broncos",
        "color": "#FB4F14",
        "logo": "DEN.png"
    },
    "DET": {
        "name": "Detroit Lions",
        "color": "#0076B6",
        "logo": "DET.png"
    },
    "GB": {
        "name": "Green Bay Packers",
        "color": "#203731",
        "logo": "GB.png"
    },
    "HOU": {
        "name": "Houston Texans",
        "color": "#03202F",
        "logo": "HOU.png"
    },
    "IND": {
        "name": "Indianapolis Colts",
        "color": "#002C5F",
        "logo": "IND.png"
    },
    "JAX": {
        "name": "Jacksonville Jaguars",
        "color": "#006778",
        "logo": "JAX.png"
    },
    "KC": {
        "name": "Kansas City Chiefs",
        "color": "#E31837",
        "logo": "KC.png"
    },
    "LAC": {
        "name": "Los Angeles Chargers",
        "color": "#0080C6",
        "logo": "LAC.png"
    },
    "LAR": {
        "name": "Los Angeles Rams",
        "color": "#003594",
        "logo": "LAR.png"
    },
    "LV": {
        "name": "Las Vegas Raiders",
        "color": "#000000",
        "logo": "LV.png"
    },
    "MIA": {
        "name": "Miami Dolphins",
        "color": "#008E97",
        "logo": "MIA.png"
    },
    "MIN": {
        "name": "Minnesota Vikings",
        "color": "#4F2683",
        "logo": "MIN.png"
    },
    "NE": {
        "name": "New England Patriots",
        "color": "#002244",
        "logo": "NE.png"
    },
    "NO": {
        "name": "New Orleans Saints",
        "color": "#D3BC8D",
        "logo": "NO.png"
    },
    "NYG": {
        "name": "New York Giants",
        "color": "#0B2265",
        "logo": "NYG.png"
    },
    "NYJ": {
        "name": "New York Jets",
        "color": "#125740",
        "logo": "NYJ.png"
    },
    "PHI": {
        "name": "Philadelphia Eagles",
        "color": "#004C54",
        "logo": "PHI.png"
    },
    "PIT": {
        "name": "Pittsburgh Steelers",
        "color": "#FFB612",
        "logo": "PIT.png"
    },
    "SEA": {
        "name": "Seattle Seahawks",
        "color": "#002244",
        "logo": "SEA.png"
    },
    "SF": {
        "name": "San Francisco 49ers",
        "color": "#AA0000",
        "logo": "SF.png"
    },
    "TB": {
        "name": "Tampa Bay Buccaneers",
        "color": "#D50A0A",
        "logo": "TB.png"
    },
    "TEN": {
        "name": "Tennessee Titans",
        "color": "#4B92DB",
        "logo": "TEN.png"
    },
    "WAS": {
        "name": "Washington Commanders",
        "color": "#5A1414",
        "logo": "WAS.png"
    }
}

# ======================== Routes ========================


## --- Login ---
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

        # ✅ Cache Sleeper players
        try:
            if not SLEEPER_CACHE.get("players"):
                resp = requests.get("https://api.sleeper.app/v1/players/nfl")
                if resp.status_code == 200:
                    SLEEPER_CACHE["players"] = resp.json()
                else:
                    raise Exception("Failed to fetch Sleeper player data.")
        except Exception as e:
            flash(f"Error caching Sleeper players: {str(e)}", "error")
            return redirect(url_for("login"))

        # ✅ Check league_id logic
        league_id = league.get("league_id")
        if not league_id:
            if session["is_admin"]:
                flash(
                    "⚠️ This league does not have a League ID configured yet. Please update it.",
                    "warning")
                return redirect(url_for("admin_page", league_name=name))
            else:
                flash(
                    "❌ This league is not set up yet. Please contact the Commissioner.",
                    "error")
                return redirect(url_for("login"))

        # ✅ Fetch league data from Sleeper
        try:
            users = get_league_users(league_id)
            rosters = get_league_rosters(league_id)
            save_league_session_to_sheet(league_id, users, rosters)
        except Exception as e:
            if session["is_admin"]:
                flash(
                    f"⚠️ League ID appears invalid or inaccessible: {str(e)}",
                    "warning")
                return redirect(url_for("admin_page", league_name=name))
            else:
                flash(
                    "❌ There was an issue accessing this league. Please contact the Commissioner.",
                    "error")
                return redirect(url_for("login"))

        # ✅ Redirect after login
        if session["is_admin"]:
            return redirect(url_for("admin_page", league_name=name))
        else:
            return redirect(url_for("league_totals", league_name=name,))

    return render_template("login.html")


## --- Logout ---
@app.route("/logout")
def logout():
    session.clear()
    SLEEPER_CACHE.clear()  # Clear the Sleeper cache too
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


## --- Root Redirect ---
@app.route("/")
def root():
    return redirect(url_for("login"))


## --- League Creation ---
@app.route("/create-league", methods=["GET", "POST"])
def create_league():
    if request.method == "POST":
        league_name = request.form.get("league_name", "").strip()
        password = request.form.get("league_password", "").strip()

        admin_password = request.form.get("admin_password", "").strip()
        league_id = request.form.get("league_id", "").strip()

        if not league_name or not password:
            flash("League name and password are required.", "error")
            return redirect(url_for("create_league"))

        leagues = load_all_leagues()
        if league_name in leagues:
            flash("❌ A league with that name already exists.", "error")
            return redirect(url_for("create_league"))

        try:
            save_new_league_to_google_sheet(league_name, password,
                                            admin_password, league_id)
            flash("✅ League created! You can now log in.", "success")
            return redirect(url_for("login"))
        except Exception as e:
            flash(f"❌ Error saving league: {str(e)}", "error")
            return redirect(url_for("create_league"))

    return render_template("create_league.html")


## --- League Summary Page ---
@app.route("/league/<league_name>")
def league_summary(league_name):
    leagues = load_all_leagues()
    config = leagues.get(league_name)
    if not config:
        return "❌ League not found."

    league_id = config.get("league_id")
    if not league_id:
        return "❌ League ID not set. Admin must configure it."
    if not SLEEPER_CACHE.get("players"):
        return "❌ Sleeper cache not loaded. Please log in again."

    try:
        df = load_flattened_salary_data()
        current_year = datetime.now().year
        next_year = current_year + 1
        prev_year = current_year - 1

        #print(f"🔎 current year= {current_year}")
        # Fetch Sleeper player database once
        sleeper_data = SLEEPER_CACHE.get("players", {})

        # Convert to quick lookup
        sleeper_lookup = {
            str(player.get("player_id")): {
                "full_name": player.get("full_name", "Unknown"),
                "position": player.get("position", "N/A"),
                "team": player.get("team") or "No Team",
                "age": player.get("age", "N/A")
            }
            for player in sleeper_data.values() if player.get("player_id")
        }

        team_data = []
        # Fetch display names
        users, rosters = load_users_and_rosters_from_sheet(league_id)

        # Create lookup: user_id → display_name
        user_lookup = {}
        team_lookup = {}

        for user in users:
            uid = user.get("user_id", "")
            display = user.get("display_name", f"User {uid}").strip()
            team_name = user.get("metadata", {}).get("team_name", "").strip()

            user_lookup[uid] = display
            team_lookup[uid] = team_name if team_name else display

            #print("LOOKUPS1:")
            #for uid in team_lookup:
            #print(f"{uid}: {team_lookup[uid]}")

        for roster in rosters:
            user_id = roster.get("owner_id")
            display_name = user_lookup.get(user_id, f"User {user_id}")
            teamname = team_lookup.get(user_id, f"User {user_id}")
            starters = roster.get("starters", []) or []
            players = roster.get("players", []) or []
            all_ids = list(
                set(
                    str(pid) for pid in (starters + players)
                    if str(pid) != "0"))

            team_players = []
            unmatched_ids = []
            total_cap = 0

            for pid in all_ids:
                pid_clean = pid.strip()

                #print(f"🔎 pid_clean= ({year})")

                matched_rows = df[df["player_id"] == pid_clean]

                if not matched_rows.empty:
                    # Prefer 2025
                    curr = matched_rows[matched_rows["Year"] == current_year]
                    if curr.empty:
                        curr = matched_rows[matched_rows["Year"] == prev_year]

                    if not curr.empty:
                        row = curr.iloc[0].to_dict()

                        # Get future year (2026) cap hit
                        future = matched_rows[matched_rows["Year"] ==
                                              next_year]
                        ny_cap = future.iloc[0][
                            "Cap Hit"] if not future.empty else ""

                        team_name = row.get("Team", "")
                        is_free_agent = team_name.strip().lower(
                        ) == "free agent"

                        if is_free_agent:
                            sleeper = sleeper_lookup.get(pid_clean, {})
                            cap = "*5,000,000"
                            cap_num = 5000000
                            total_cap += cap_num

                            team_players.append({
                                "Player":
                                sleeper.get(
                                    "full_name",
                                    row.get("Player", "Unknown Player")),
                                "sleeper_name":
                                sleeper.get("full_name", pid_clean),
                                "Cap Hit":
                                cap,
                                "Team":
                                "Free Agent",
                                "Year":
                                row.get("Year"),
                                "Next Year":
                                "",
                                "Pos":
                                sleeper.get("position", row.get("Pos", "N/A")),
                                "Age":
                                sleeper.get("age", row.get("Age", "N/A")),
                                "player_id":
                                pid_clean
                            })

                        else:
                            cap = row.get("Cap Hit", "0")
                            cap_num = float(
                                str(cap).replace("$", "").replace(
                                    ",", "").replace("-", "0") or 0)
                            total_cap += cap_num

                            team_players.append({
                                "Player":
                                row.get("Player"),
                                "sleeper_name":
                                row.get("sleeper_name", ""),
                                "Cap Hit":
                                cap,
                                "Team":
                                team_name,
                                "Year":
                                row.get("Year"),
                                "Next Year":
                                ny_cap,
                                "Pos":
                                row.get("Pos", "N/A"),
                                "Age":
                                row.get("Age", "N/A"),
                                "player_id":
                                pid_clean
                            })

                        continue

                # If not found in salary DB at all — use Sleeper fallback
                sleeper = sleeper_lookup.get(pid_clean, {})
                full_name = sleeper.get("full_name", "Unknown Player")
                team_players.append({
                    "Player": full_name,
                    "sleeper_name": full_name,
                    "Cap Hit": "*5,000,000",
                    "Team": "Free Agent",
                    "Year": current_year,
                    "Next Year": "",
                    "Pos": sleeper.get("position", "N/A"),
                    "Age": sleeper.get("age", "N/A"),
                    "player_id": pid_clean
                })
                total_cap += 5000000
                unmatched_ids.append(pid_clean)

            team_data.append({
                "user_id": display_name,
                "team_name": teamname,
                "player_count": len(all_ids),
                "matched_count": len(all_ids) - len(unmatched_ids),
                "total_cap": f"${total_cap:,.0f}",
                "players": team_players,
                "unmatched_ids": unmatched_ids
            })

        return render_template(
            "league.html",
            league_name=league_name,
            teams=team_data,
            footer_note=
            "Players with an * are not on a NFL Team, so are defaulted to 5,000,000. If this player is on a team contact StickyPicky to investigate."
        )

    except Exception as e:
        return f"❌ Error: {str(e)}"


## --- League Totals Page ---
@app.route("/league/<league_name>/totals")
def league_totals(league_name):
    leagues = load_all_leagues()
    config = leagues.get(league_name)
    if not config:
        return "❌ League not found."

    league_id = config.get("league_id")
    if not league_id:
        return "❌ League ID not set."

    try:
        df = load_flattened_salary_data()
        df["Year"] = pd.to_numeric(df["Year"], errors="coerce")

        current_year = datetime.now().year
        prev_year = current_year - 1

        # AFTER
        users, rosters = load_users_and_rosters_from_sheet(league_id)
        user_lookup = {}
        team_lookup = {}

        for user in users:
            uid = user.get("user_id", "")
            display = user.get("display_name", f"User {uid}").strip()
            team_name = user.get("metadata", {}).get("team_name", "").strip()

            user_lookup[uid] = display
            team_lookup[uid] = team_name if team_name else display

            # print("LOOKUPS2:")
            # for uid in team_lookup:
            #     print(f"{uid}: {team_lookup[uid]}")
            # print("Name")
            # for uid in team_lookup:
            #     print(f"{uid}: {display}")

        team_caps = []
        for roster in rosters:
            user_id = roster.get("owner_id")
            starters = roster.get("starters", []) or []
            players = roster.get("players", []) or []
            all_ids = list(
                set(
                    str(pid) for pid in (starters + players)
                    if str(pid) != "0"))

            total_cap = 0
            for pid in all_ids:
                matched = df[df["player_id"] == pid]
                curr = matched[matched["Year"] == current_year]
                if curr.empty:
                    curr = matched[matched["Year"] == prev_year]

                if not curr.empty:
                    row = curr.iloc[0].to_dict()
                    team_name = row.get("Team", "").strip().lower()
                    if team_name == "free agent":
                        cap_num = 5000000
                    else:
                        cap_str = row.get("Cap Hit", "0")
                        cap_num = float(
                            str(cap_str).replace("$", "").replace(
                                ",", "").replace("-", "0") or 0)
                else:
                    cap_num = 5000000  # unmatched

                total_cap += cap_num

            team_caps.append({
                "user_id":
                user_id,
                "team_name":
                team_lookup.get(user_id,
                                user_lookup.get(user_id, f"User {user_id}")),
                "total_cap":
                f"${total_cap:,.0f}"
            })

        return render_template("league_totals.html",
                               league_name=league_name,
                               teams=team_caps,
                               is_admin=session.get("is_admin", False),
                               config=config)

    except Exception as e:
        return f"❌ Error: {str(e)}"


## --- Team Detail Page ---
@app.route("/league/<league_name>/team/<user_id>")
def team_detail(league_name, user_id):
    leagues = load_all_leagues()
    config = leagues.get(league_name)
    if not config:
        return "❌ League not found."

    league_id = config.get("league_id")
    if not league_id:
        return "❌ League ID not set."

    try:
        df = load_flattened_salary_data()
        df["Year"] = pd.to_numeric(df["Year"], errors="coerce")

        current_year = datetime.now().year
        prev_year = current_year - 1
        next_year = current_year + 1

        users, rosters = load_users_and_rosters_from_sheet(league_id)

        sleeper_data = SLEEPER_CACHE.get("players", {})

        sleeper_lookup = {
            str(p.get("player_id")): {
                "full_name": p.get("full_name", "Unknown"),
                "position": p.get("position", "N/A"),
                "team": p.get("team") or "No Team",
                "age": p.get("age", "N/A")
            }
            for p in sleeper_data.values() if p.get("player_id")
        }

        user_lookup = {}
        team_lookup = {}

        for user in users:
            uid = user.get("user_id", "")
            display = user.get("display_name", f"User {uid}").strip()
            team_name = user.get("metadata", {}).get("team_name", "").strip()

            user_lookup[uid] = display
            team_lookup[uid] = team_name if team_name else display

            # print("LOOKUPS3:")
            # for uid in team_lookup:
            #     print(f"{uid}: {team_lookup[uid]}")

        display_name = team_lookup.get(user_id, f"User {user_id}")

        roster = next((r for r in rosters if r.get("owner_id") == user_id), {})
        starters = roster.get("starters", []) or []
        players = roster.get("players", []) or []
        all_ids = list(
            set(str(pid) for pid in (starters + players) if str(pid) != "0"))

        team_players = []
        total_cap = 0

        for pid in all_ids:
            matched = df[df["player_id"] == pid]
            curr = matched[matched["Year"] == current_year]
            if curr.empty:
                curr = matched[matched["Year"] == prev_year]

            if not curr.empty:
                row = curr.iloc[0].to_dict()
                future = matched[matched["Year"] == next_year]
                ny_cap = future.iloc[0]["Cap Hit"] if not future.empty else ""
                team_name = row.get("Team", "").strip().lower()
                if team_name == "free agent":
                    sleeper = sleeper_lookup.get(pid, {})
                    cap = "*5,000,000"
                    cap_num = 5000000
                    total_cap += cap_num
                    team_players.append({
                        "Player":
                        sleeper.get("full_name", row.get("Player", "Unknown")),
                        "Cap Hit":
                        cap,
                        "Team":
                        "Free Agent",
                        "Next Year":
                        "",
                        "Pos":
                        sleeper.get("position", row.get("Pos", "N/A")),
                        "Age":
                        sleeper.get("age", row.get("Age", "N/A"))
                    })
                else:
                    cap = row.get("Cap Hit", "0")
                    cap_num = float(
                        str(cap).replace("$", "").replace(",", "").replace(
                            "-", "0") or 0)
                    total_cap += cap_num
                    team_players.append({
                        "Player": row.get("Player"),
                        "Cap Hit": cap,
                        "Team": row.get("Team", "No Team"),
                        "Next Year": ny_cap,
                        "Pos": row.get("Pos", "N/A"),
                        "Age": row.get("Age", "N/A")
                    })

            else:
                sleeper = sleeper_lookup.get(pid, {})
                cap_num = 5000000
                total_cap += cap_num
                team_players.append({
                    "Player":
                    sleeper.get("full_name", "Unknown"),
                    "Cap Hit":
                    "*5,000,000",
                    "Team":
                    "Free Agent",
                    "Next Year":
                    "",
                    "Pos":
                    sleeper.get("position", "N/A"),
                    "Age":
                    sleeper.get("age", "N/A")
                })

    # Load themes and determine if this user has a theme
        themes = config.get("themes", {})
        themed_team_abbr = next(
            (abbr for abbr, uid in themes.items() if uid == user_id), None)
        theme_info = TEAM_THEME_DATA.get(themed_team_abbr)

        return render_template(
            "team_detail.html",
            league_name=league_name,
            team_name=display_name,
            players=team_players,
            footer_note=
            ("Players with an * are not on a NFL Team, so are defaulted to 5,000,000. "
             "If this player is on a team contact StickyPicky to investigate."
             ),
            user_id=user_id,
            total_cap=f"${total_cap:,.0f}",
            theme_team=themed_team_abbr,
            theme_info=theme_info,
            is_admin=session.get("is_admin", False),
            config=config)

    except Exception as e:
        return f"❌ Error: {str(e)}"


## --- Cap Simulator ---
@app.route("/league/<league_name>/team/<user_id>/simulate")
def cap_simulator(league_name, user_id):
    leagues = load_all_leagues()
    config = leagues.get(league_name)
    if not config:
        return "❌ League not found."

    league_id = config.get("league_id")
    if not league_id:
        return "❌ League ID not set."

    try:
        # Load and cache salary DB
        df = load_flattened_salary_data()
        df["Year"] = pd.to_numeric(df["Year"], errors="coerce")

        current_year = datetime.now().year
        prev_year = current_year - 1
        next_year = current_year + 1

        # Build salary lookup dict
        salary_lookup = {}
        for _, row in df.iterrows():
            pid = str(row["player_id"]).strip()
            if pid not in salary_lookup:
                salary_lookup[pid] = []
            salary_lookup[pid].append(row)

        # Load league data
        users, rosters = load_users_and_rosters_from_sheet(league_id)
        roster = next((r for r in rosters if r.get("owner_id") == user_id), {})
        all_ids = list(
            set(
                str(pid) for pid in (roster.get("starters", []) +
                                     roster.get("players", []))
                if str(pid) != "0"))

        sleeper_data = SLEEPER_CACHE.get("players", {})
        sleeper_lookup = {
            str(p.get("player_id")): {
                "full_name": p.get("full_name", "Unknown"),
                "position": p.get("position", "N/A"),
                "team": p.get("team") or "No Team",
                "age": p.get("age", "N/A")
            }
            for p in sleeper_data.values() if p.get("player_id")
        }

        # Build active player list
        players = []
        total_cap = 0
        for pid in all_ids:
            entries = salary_lookup.get(pid, [])
            row = None

            # Prioritize current year, fallback to previous
            for r in entries:
                if r["Year"] == current_year:
                    row = r.to_dict()
                    break
            if not row:
                for r in entries:
                    if r["Year"] == prev_year:
                        row = r.to_dict()
                        break

            if row:
                cap = row.get("Cap Hit", "0")
                cap_num = float(
                    str(cap).replace("$", "").replace(",", "").replace(
                        "-", "0") or 0)
                team = row.get("Team", "Free Agent")
            else:
                cap = "*5,000,000"
                cap_num = 5000000
                team = "Free Agent"

            total_cap += cap_num
            player = sleeper_lookup.get(pid, {})
            players.append({
                "Player":
                player.get("full_name",
                           row.get("Player", "Unknown") if row else "Unknown"),
                "Team":
                team,
                "Cap_Hit":
                cap,
                "Pos":
                player.get("position",
                           row.get("Pos", "N/A") if row else "N/A"),
                "Age":
                player.get("age",
                           row.get("Age", "N/A") if row else "N/A"),
                "player_id":
                pid,
                "cap_num":
                cap_num
            })

        display_name = next((u.get("display_name", f"User {user_id}")
                             for u in users if u.get("user_id") == user_id),
                            f"User {user_id}")

        # Build lookup for all Sleeper players (for adding new ones)
        for pid, info in sleeper_lookup.items():
            entries = salary_lookup.get(pid, [])
            row = None

            for r in entries:
                if r["Year"] == current_year:
                    row = r.to_dict()
                    break
            if not row:
                for r in entries:
                    if r["Year"] == prev_year:
                        row = r.to_dict()
                        break

            if row:
                team = row.get("Team", "").strip().lower()
                if team != "free agent":
                    cap_str = row.get("Cap Hit", "0")
                    cap_num = float(
                        str(cap_str).replace("$", "").replace(",", "").replace(
                            "-", "0") or 0)
                    info["cap_num"] = cap_num
                    info["cap_str"] = row.get("Cap Hit")
                else:
                    info["cap_num"] = 5000000
                    info["cap_str"] = "*5,000,000"
            else:
                info["cap_num"] = 5000000
                info["cap_str"] = "*5,000,000"

        return render_template("cap_simulator.html",
                               league_name=league_name,
                               team_name=display_name,
                               players=players,
                               total_cap=f"${total_cap:,.0f}",
                               player_ids=list(set(all_ids)),
                               sleeper_data=sleeper_lookup,
                               user_id=user_id,
                               is_admin=session.get("is_admin", False),
                               config=config)

    except Exception as e:
        return f"❌ Error: {str(e)}"

## --- Draft Room Page ---
@app.route('/draft_room/<league>/<draft_id>', methods=['GET', 'POST'])
def draft_room(league, draft_id):
    leagues = load_all_leagues()
    config = leagues.get(league)
    is_admin = session.get('is_admin', False)

    # Load salary and Sleeper data
    df = load_flattened_salary_data()
    df["Year"] = pd.to_numeric(df["Year"], errors="coerce")
    current_year = datetime.now().year
    prev_year = current_year - 1

    sleeper_data = SLEEPER_CACHE.get("players", {})
    sleeper_lookup = {
        str(p.get("player_id")): {
            "name": p.get("full_name", "Unknown"),
            "position": p.get("position", "N/A"),
            "team": p.get("team") or "No Team",
            "age": p.get("age", "N/A")
        }
        for p in sleeper_data.values() if p.get("player_id")
    }

    # Handle add-player form
    if request.method == 'POST':
        roster_id = request.form.get('roster_id')
        player_name = request.form.get('add_player_name', '').strip().lower()

        matched_ids = []
        for pid, data in sleeper_lookup.items():
            if player_name in data.get("name", "").lower():
                matched_ids.append(pid)

        if matched_ids:
            pid = matched_ids[0]  # Take best match
            added_players = session.get('added_players', {})
            added_players.setdefault(roster_id, [])
            if pid not in added_players[roster_id]:
                added_players[roster_id].append(pid)
                session['added_players'] = added_players
        return redirect(request.url)

    # Fetch draft picks
    picks = requests.get(f'https://api.sleeper.app/v1/draft/{draft_id}/picks').json()

    # Build rosters by draft pick
    rosters = {}
    for pick in picks:
        rid = pick.get('roster_id')
        pid = pick.get('player_id')
        if rid is not None and pid is not None:
            rosters.setdefault(str(rid), []).append(str(pid))

    # Merge manually added players
    added_players = session.get('added_players', {})
    for rid, extras in added_players.items():
        rosters.setdefault(str(rid), [])
        for pid in extras:
            if pid not in rosters[rid]:
                rosters[rid].append(pid)

    # Build player display data
    all_rosters = []
    for rid, pids in rosters.items():
        players = []
        total_cap = 0

        for pid in pids:
            matched = df[df["player_id"] == pid]
            curr = matched[matched["Year"] == current_year]
            if curr.empty:
                curr = matched[matched["Year"] == prev_year]

            if not curr.empty:
                row = curr.iloc[0].to_dict()
                cap_str = row.get("Cap Hit", "0")
                cap_num = float(str(cap_str).replace("$", "").replace(",", "").replace("-", "0") or 0)
                name = row.get("Player", "Unknown")
                note = ""
            else:
                cap_num = 5000000
                name = sleeper_lookup.get(pid, {}).get("name", "Unknown")
                note = "*"

            total_cap += cap_num
            players.append({
                "id": pid,
                "name": name,
                "cap": cap_num,
                "note": note
            })

        all_rosters.append({
            "roster_id": rid,
            "players": sorted(players, key=lambda x: -x["cap"]),
            "total_cap": total_cap
        })

    return render_template("draft_room.html",
                           league=league,
                           draft_id=draft_id,\
                           rosters=all_rosters,
                           is_admin=session.get("is_admin", False),
                           config=config)

@app.route('/draft_room_home/<league>')
def draft_room_home(league):
    leagues = load_all_leagues()
    config = leagues.get(league)
    if not config:
        return "❌ League not found."

    draft_is_public = config.get("draft_room_public", False)
    is_admin = session.get("is_admin", False)

    if not (is_admin or draft_is_public):
        flash("🔒 The Draft Room is currently hidden from non-admins.", "error")
        return redirect(url_for("league_summary", league_name=league))


    league_id = config.get("league_id")
    if not league_id:
        return "❌ League ID not configured."

    # Get draft_id dynamically
    draft_resp = requests.get(f"https://api.sleeper.app/v1/league/{league_id}/drafts")
    if draft_resp.status_code != 200:
        return "❌ Could not retrieve draft data."

    drafts = draft_resp.json()
    if not drafts:
        return "❌ No drafts found for this league."

    draft_id = drafts[0].get("draft_id")

    # Load draft picks
    picks = requests.get(f'https://api.sleeper.app/v1/draft/{draft_id}/picks').json()
    user_data = requests.get(f'https://api.sleeper.app/v1/league/{league_id}/users').json()

    user_lookup = {
        str(u["user_id"]): u.get("metadata", {}).get("team_name") or u.get("display_name", f"User {u['user_id']}")
        for u in user_data
    }

    df = load_flattened_salary_data()
    df["Year"] = pd.to_numeric(df["Year"], errors="coerce")
    current_year = datetime.now().year
    prev_year = current_year - 1

    rosters = {}
    for pick in picks:
        rid = str(pick.get("roster_id"))
        pid = str(pick.get("player_id"))
        picked_by = str(pick.get("picked_by"))
        if rid and pid:
            rosters.setdefault(rid, {"players": [], "owner": user_lookup.get(picked_by, f"Roster {rid}")})
            rosters[rid]["players"].append(pid)

    added_players = session.get("added_players", {})
    for rid, extras in added_players.items():
        rosters.setdefault(rid, {"players": [], "owner": f"Roster {rid}"})
        for pid in extras:
            if pid not in rosters[rid]["players"]:
                rosters[rid]["players"].append(pid)

    teams = []
    for rid, data in rosters.items():
        total_cap = 0
        for pid in data["players"]:
            matched = df[df["player_id"] == pid]
            curr = matched[matched["Year"] == current_year]
            if curr.empty:
                curr = matched[matched["Year"] == prev_year]

            if not curr.empty:
                cap_str = curr.iloc[0].get("Cap Hit", "0")
                cap_num = float(str(cap_str).replace("$", "").replace(",", "").replace("-", "0") or 0)
            else:
                cap_num = 5000000
            total_cap += cap_num

        teams.append({
            "roster_id": rid,
            "owner": data["owner"],
            "player_count": len(data["players"]),
            "total_cap": f"${total_cap:,.0f}",
            "draft_id": draft_id
        })

    teams = sorted(teams, key=lambda x: float(x["total_cap"].replace("$", "").replace(",", "")), reverse=True)

    return render_template("draft_room_home.html",
                           league=league,
                           teams=teams,
                           is_admin=session.get("is_admin", False),
                           config=config)

@app.route("/draft_room/<league>/<draft_id>/team/<roster_id>", methods=["GET", "POST"])
def draft_team_view(league, draft_id, roster_id):
    if not SLEEPER_CACHE.get("players"):
        try:
            resp = requests.get("https://api.sleeper.app/v1/players/nfl")
            if resp.status_code == 200:
                SLEEPER_CACHE["players"] = resp.json()
            else:
                flash("⚠️ Failed to load Sleeper players.", "warning")
                return redirect(url_for("login"))
        except Exception as e:
            flash(f"⚠️ Sleeper API error: {e}", "warning")
            return redirect(url_for("login"))
    is_admin = session.get("is_admin", False)
    leagues = load_all_leagues()
    config = leagues.get(league)
    league_id = config.get("league_id")

    user_data = requests.get(f"https://api.sleeper.app/v1/league/{league_id}/users").json()
    user_lookup = {
        str(u["user_id"]): u.get("metadata", {}).get("team_name") or u.get("display_name", f"User {u['user_id']}")
        for u in user_data
    }

    df = load_flattened_salary_data()
    df["Year"] = pd.to_numeric(df["Year"], errors="coerce")
    current_year = datetime.now().year
    prev_year = current_year - 1

    sleeper_data = SLEEPER_CACHE.get("players", {})
    sleeper_lookup = {}
    for p in sleeper_data.values():
        pid = str(p.get("player_id"))
        if not pid:
            continue
        name = p.get("full_name", "Unknown")
        pos = p.get("position", "N/A")
        team = p.get("team") or "No Team"
        age = p.get("age", "N/A")

        matched = df[df["player_id"] == pid]
        curr = matched[matched["Year"] == current_year]
        if curr.empty:
            curr = matched[matched["Year"] == prev_year]

        if not curr.empty:
            row = curr.iloc[0].to_dict()
            cap = row.get("Cap Hit", "$5,000,000")
            cap_str = cap
            cap_num = float(str(cap).replace("$", "").replace(",", "").replace("-", "0") or 0)
        else:
            cap_num = 5000000
            cap_str = "$5,000,000"

        sleeper_lookup[pid] = {
            "name": name,
            "position": pos,
            "team": team,
            "age": age,
            "cap_num": cap_num,
            "cap_str": cap_str
        }


    picks = requests.get(f"https://api.sleeper.app/v1/draft/{draft_id}/picks").json()
    # 🟩 Picks for this team (used for displaying active roster)
    team_active_ids = [str(p["player_id"]) for p in picks if str(p["roster_id"]) == roster_id]

    # 🧠 All drafted player IDs → team name mapping
    all_drafted_ids = []
    drafted_by_map = {}
    for p in picks:
        pid = str(p["player_id"])
        picked_by = str(p["picked_by"])
        all_drafted_ids.append(pid)
        drafted_by_map[pid] = user_lookup.get(picked_by, f"User {picked_by}")



    added_players = session.get("added_players", {})
    custom_ids = added_players.get(roster_id, [])

    if request.method == "POST":
        action = request.form.get("action")
        if action == "remove":
            pid = request.form.get("player_id")
            if roster_id in added_players and pid in added_players[roster_id]:
                added_players[roster_id].remove(pid)
                session["added_players"] = added_players
                flash("❌ Player removed.", "success")
        elif action == "add":
            pid = request.form.get("player_id", "").strip()
            name_map = {pid: info["name"] for pid, info in sleeper_lookup.items()}

            if pid:
                if pid in all_drafted_ids:
                    drafted_team = drafted_by_map.get(pid, "another team")
                    flash(f"⚠️ {name_map.get(pid)} is already drafted on {drafted_team}.", "warning")
                else:
                    added_players.setdefault(roster_id, [])
                    if pid not in added_players[roster_id]:
                        added_players[roster_id].append(pid)
                        session["added_players"] = added_players
                        flash(f"✅ Added player: {name_map.get(pid)}", "success")
            else:
                flash("⚠️ Invalid player selection.", "warning")


        return redirect(request.url)  # ✅ Moved outside the if blocks




    def build_player_rows(ids, is_custom=False):
        rows = []
        total = 0
        for pid in ids:
            matched = df[df["player_id"] == pid]
            curr = matched[matched["Year"] == current_year]
            if curr.empty:
                curr = matched[matched["Year"] == prev_year]

            if not curr.empty:
                row = curr.iloc[0].to_dict()
                cap = row.get("Cap Hit", "0")
                cap_num = float(str(cap).replace("$", "").replace(",", "").replace("-", "0") or 0)
                name = row.get("Player", "Unknown")
            else:
                cap_num = 5000000
                name = sleeper_lookup.get(pid, {}).get("name", "Unknown")

            total += cap_num
            rows.append({
                "id": pid,
                "name": name,
                "cap": cap_num
            })
        return sorted(rows, key=lambda r: -r["cap"]), total

    active_players, active_total = build_player_rows(team_active_ids)
    added_players_table, added_total = build_player_rows(custom_ids, is_custom=True)
    team_name = f"{user_lookup.get(roster_id, f'Roster {roster_id}')}"
    return render_template("draft_team_view.html",
        league=league,
        draft_id=draft_id,
        roster_id=roster_id,
        team_name=team_name,
        active_players=active_players,
        added_players=added_players_table,
        active_total=active_total,
        added_total=added_total,
        is_admin=is_admin,
        sleeper_data=sleeper_lookup,
        active_ids=all_drafted_ids
    )



## --- Admin Settings Page ---
@app.route("/admin/<league_name>", methods=["GET", "POST"])
def admin_page(league_name):
    leagues = load_all_leagues()
    if not session.get("is_admin") or session.get(
            "league_name") != league_name:
        return "🔒 Access denied."

    if request.method == "POST":
        league_id = request.form.get("league_id", "").strip()
        draft_room_public = request.form.get("draft_room_public") == "on"

        if league_id:
            update_league_config(league_name, "league_id", league_id)
        update_league_config(league_name, "draft_room_public", "TRUE" if draft_room_public else "FALSE")
        flash("✅ League settings updated.", "success")
        return redirect(url_for("admin_page", league_name=league_name))

    config = leagues[league_name]
    themes = config.get("themes", {})

    unmatched_count = 0
    try:
        df = load_flattened_salary_data()
        df["player_id"] = df["player_id"].astype(str).str.strip()

        league_id = config.get("league_id")
        _, rosters = load_users_and_rosters_from_sheet(league_id)

        all_ids = set()
        for roster in rosters:
            starters = roster.get("starters", [])
            players = roster.get("players", [])
            ids = [str(pid) for pid in (starters + players) if str(pid) != "0"]
            all_ids.update(ids)

        matched_ids = set(df["player_id"])
        unmatched_count = len(all_ids - matched_ids)

    except:
        unmatched_count = 0  # Fail silently

    return render_template("admin_settings.html",
                           config=config,
                           league_name=league_name,
                           unmatched_count=unmatched_count,
                           is_admin=session.get("is_admin", False))



## --- Admin Unmatched Players ---
@app.route("/admin/<league_name>/unmatched")
def unmatched_players(league_name):
    leagues = load_all_leagues()
    if not session.get("is_admin") or session.get(
            "league_name") != league_name:
        return "🔒 Access denied."

    config = leagues[league_name]
    unmatched_players = []

    try:
        df = load_flattened_salary_data()
        df["player_id"] = df["player_id"].astype(str).str.strip()
        matched_ids = set(df["player_id"])

        league_id = config.get("league_id")
        _, rosters = load_users_and_rosters_from_sheet(league_id)

        all_ids = set()
        for r in rosters:
            starters = r.get("starters", [])
            players = r.get("players", [])
            ids = [str(pid) for pid in (starters + players) if str(pid) != "0"]
            all_ids.update(ids)

        unmatched_ids = sorted(all_ids - matched_ids)

        all_players = SLEEPER_CACHE.get("players", {})  # Cached API call

        for pid in unmatched_ids:
            player = all_players.get(pid)
            if player:
                unmatched_players.append({
                    "player_id":
                    pid,
                    "sleeper_name":
                    player.get(
                        "full_name",
                        player.get("first_name", "") + " " +
                        player.get("last_name", "")),
                    "age":
                    player.get("age", "N/A"),
                    "position":
                    player.get("position", "N/A")
                })
            else:
                unmatched_players.append({
                    "player_id": pid,
                    "sleeper_name": "Unknown",
                    "age": "N/A",
                    "position": "N/A"
                })

    except Exception as e:
        unmatched_players = [{
            "player_id": "N/A",
            "sleeper_name": f"(Error: {str(e)})",
            "age": "N/A",
            "position": "N/A"
        }]

    return render_template("admin_unmatched.html",
                           league_name=league_name,
                           unmatched_players=unmatched_players)


## --- Admin Theme Selector ---
@app.route("/admin/<league_name>/themes", methods=["GET", "POST"])
def theme_selector(league_name):
    leagues = load_all_leagues()
    if not session.get("is_admin") or session.get(
            "league_name") != league_name:
        return "🔒 Access denied."

    config = leagues[league_name]
    league_id = config.get("league_id")
    if not league_id:
        flash("⚠️ League ID is not set.", "error")
        return redirect(url_for("admin_page", league_name=league_name))

    # Load users from league
    users = []
    try:
        raw_users, _ = load_users_and_rosters_from_sheet(league_id)
        users = []
        for u in raw_users:
            display_name = u.get("display_name", f"User {u.get('user_id')}")
            users.append({
                "user_id": u["user_id"],
                "display_name": display_name
            })

    except Exception as e:
        flash(f"❌ Error loading league users: {str(e)}", "error")

    themes = config.get("themes", {})  # e.g. {"KC": "user123"}

    if request.method == "POST":
        themes = {}
        for key, val in request.form.items():
            if key.startswith("team_") and val.strip():
                team = key.replace("team_", "")
                themes[team] = val.strip()  # This is now a user_id
        update_league_config(league_name, "themes", themes)
        flash("✅ Team themes updated.", "success")
        return redirect(url_for("theme_selector", league_name=league_name))

    # Prepare team list
    nfl_teams = [
        "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN",
        "DET", "GB", "HOU", "IND", "JAX", "KC", "LAC", "LAR", "LV", "MIA",
        "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB",
        "TEN", "WAS"
    ]

    assigned_users = set(themes.values())

    return render_template("admin_themes.html",
                           league_name=league_name,
                           users=users,
                           themes=themes,
                           nfl_teams=nfl_teams,
                           assigned_users=assigned_users)

# ======================== Admin Draft Refresh ========================
@app.route('/refresh_draft/<draft_id>')
def refresh_draft(draft_id):
    if not session.get('is_admin', False):
        return 'Unauthorized', 403
    session.pop('added_players', None)  # Reset only admin-added extras
    return redirect(url_for('draft_room', league='your_league', draft_id=draft_id))



# ======================== App Runner ========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
