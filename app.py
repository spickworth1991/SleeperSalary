import json
import re
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
import pandas as pd
import requests
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, g

app = Flask(__name__,
            static_folder='static',
            template_folder='templates')
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

TEAM_THEME_DATA = {
    "ARI": {"name": "Arizona Cardinals", "color": "#97233F", "logo": "ari.png"},
    "ATL": {"name": "Atlanta Falcons", "color": "#A71930", "logo": "atl.png"},
    "BAL": {"name": "Baltimore Ravens", "color": "#241773", "logo": "bal.png"},
    "BUF": {"name": "Buffalo Bills", "color": "#00338D", "logo": "buf.png"},
    "CAR": {"name": "Carolina Panthers", "color": "#0085CA", "logo": "car.png"},
    "CHI": {"name": "Chicago Bears", "color": "#0B162A", "logo": "chi.png"},
    "CIN": {"name": "Cincinnati Bengals", "color": "#FB4F14", "logo": "cin.png"},
    "CLE": {"name": "Cleveland Browns", "color": "#311D00", "logo": "cle.png"},
    "DAL": {"name": "Dallas Cowboys", "color": "#041E42", "logo": "dal.png"},
    "DEN": {"name": "Denver Broncos", "color": "#FB4F14", "logo": "den.png"},
    "DET": {"name": "Detroit Lions", "color": "#0076B6", "logo": "det.png"},
    "GB": {"name": "Green Bay Packers", "color": "#203731", "logo": "gb.png"},
    "HOU": {"name": "Houston Texans", "color": "#03202F", "logo": "hou.png"},
    "IND": {"name": "Indianapolis Colts", "color": "#002C5F", "logo": "ind.png"},
    "JAX": {"name": "Jacksonville Jaguars", "color": "#006778", "logo": "jax.png"},
    "KC": {"name": "Kansas City Chiefs", "color": "#E31837", "logo": "kc.png"},
    "LAC": {"name": "Los Angeles Chargers", "color": "#0080C6", "logo": "lac.png"},
    "LAR": {"name": "Los Angeles Rams", "color": "#003594", "logo": "lar.png"},
    "LV": {"name": "Las Vegas Raiders", "color": "#000000", "logo": "lv.png"},
    "MIA": {"name": "Miami Dolphins", "color": "#008E97", "logo": "mia.png"},
    "MIN": {"name": "Minnesota Vikings", "color": "#4F2683", "logo": "min.png"},
    "NE": {"name": "New England Patriots", "color": "#002244", "logo": "ne.png"},
    "NO": {"name": "New Orleans Saints", "color": "#D3BC8D", "logo": "no.png"},
    "NYG": {"name": "New York Giants", "color": "#0B2265", "logo": "nyg.png"},
    "NYJ": {"name": "New York Jets", "color": "#125740", "logo": "nyj.png"},
    "PHI": {"name": "Philadelphia Eagles", "color": "#004C54", "logo": "phi.png"},
    "PIT": {"name": "Pittsburgh Steelers", "color": "#FFB612", "logo": "pit.png"},
    "SEA": {"name": "Seattle Seahawks", "color": "#002244", "logo": "sea.png"},
    "SF": {"name": "San Francisco 49ers", "color": "#AA0000", "logo": "sf.png"},
    "TB": {"name": "Tampa Bay Buccaneers", "color": "#D50A0A", "logo": "tb.png"},
    "TEN": {"name": "Tennessee Titans", "color": "#4B92DB", "logo": "ten.png"},
    "WAS": {"name": "Washington Commanders", "color": "#5A1414", "logo": "was.png"}
}


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
            return redirect(url_for("league_totals", league_name=name))

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

        current_year = datetime.now().year
        next_year = current_year + 1
        prev_year = current_year - 1

        print(f"🔎 current year= {current_year}")
        # Fetch Sleeper player database once
        sleeper_url = "https://api.sleeper.app/v1/players/nfl"
        sleeper_data = requests.get(sleeper_url).json()

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

        rosters = get_league_rosters(league_id)
        team_data = []
        # Fetch display names
        users_url = f"https://api.sleeper.app/v1/league/{league_id}/users"
        users_resp = requests.get(users_url)
        users = users_resp.json()

        # Create lookup: user_id → display_name
        user_lookup = {
            user["user_id"]: user.get("display_name",
                                      f"User {user['user_id']}")
            for user in users
        }
        team_lookup = {
            user["user_id"]:
            user.get("metadata", {}).get(
                "team_name", user.get("display_name",
                                      f"User {user['user_id']}"))
            for user in users
        }

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

    unmatched_count = 0
    try:
        df = load_flattened_salary_data()
        df["player_id"] = df["player_id"].astype(str).str.strip()

        league_id = config.get("league_id")
        rosters = get_league_rosters(league_id)

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
                           unmatched_count=unmatched_count)



SLEEPER_CACHE = {}

def get_sleeper_players():
    """Cache the player DB in memory, not in session."""
    if not SLEEPER_CACHE.get("players"):
        resp = requests.get("https://api.sleeper.app/v1/players/nfl")
        if resp.status_code == 200:
            SLEEPER_CACHE["players"] = resp.json()
        else:
            raise Exception("Failed to fetch Sleeper player data.")
    return SLEEPER_CACHE["players"]

def get_league_users(league_id):
    """Fetch users from a Sleeper league."""
    url = f"https://api.sleeper.app/v1/league/{league_id}/users"
    resp = requests.get(url)
    if resp.status_code != 200:
        raise Exception(f"Failed to fetch users: {resp.text}")
    return resp.json()



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
        next_year = current_year + 1

        rosters = get_league_rosters(league_id)
        users = requests.get(
            f"https://api.sleeper.app/v1/league/{league_id}/users").json()

        team_lookup = {
            user["user_id"]:
            user.get("metadata", {}).get(
                "team_name", user.get("display_name",
                                      f"User {user['user_id']}"))
            for user in users
        }

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
                team_lookup.get(user_id, f"User {user_id}"),
                "total_cap":
                f"${total_cap:,.0f}"
            })

        return render_template("league_totals.html",
                               league_name=league_name,
                               teams=team_caps)

    except Exception as e:
        return f"❌ Error: {str(e)}"


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

        rosters = get_league_rosters(league_id)
        users = requests.get(
            f"https://api.sleeper.app/v1/league/{league_id}/users").json()

        sleeper_data = requests.get(
            "https://api.sleeper.app/v1/players/nfl").json()
        sleeper_lookup = {
            str(p.get("player_id")): {
                "full_name": p.get("full_name", "Unknown"),
                "position": p.get("position", "N/A"),
                "team": p.get("team") or "No Team",
                "age": p.get("age", "N/A")
            }
            for p in sleeper_data.values() if p.get("player_id")
        }

        team_lookup = {
            user["user_id"]:
            user.get("metadata", {}).get(
                "team_name", user.get("display_name",
                                      f"User {user['user_id']}"))
            for user in users
        }

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
        themed_team_abbr = next((abbr for abbr, uid in themes.items() if uid == user_id), None)
        theme_info = TEAM_THEME_DATA.get(themed_team_abbr)

# You already have `display_name` from user lookup earlier





        return render_template(
            "team_detail.html",
            league_name=league_name,
            team_name=display_name,
            players=team_players,
            footer_note=(
                "Players with an * are not on a NFL Team, so are defaulted to 5,000,000. "
                "If this player is on a team contact StickyPicky to investigate."
            ),
            user_id=user_id,
            total_cap=f"${total_cap:,.0f}",
            theme_team=themed_team_abbr,
            theme_info=theme_info
        )


    except Exception as e:
        return f"❌ Error: {str(e)}"
    
@app.route("/admin/<league_name>/unmatched")
def unmatched_players(league_name):
    leagues = load_all_leagues()
    if not session.get("is_admin") or session.get("league_name") != league_name:
        return "🔒 Access denied."

    config = leagues[league_name]
    unmatched_players = []

    try:
        df = load_flattened_salary_data()
        df["player_id"] = df["player_id"].astype(str).str.strip()
        matched_ids = set(df["player_id"])

        league_id = config.get("league_id")
        rosters = get_league_rosters(league_id)

        all_ids = set()
        for r in rosters:
            starters = r.get("starters", [])
            players = r.get("players", [])
            ids = [str(pid) for pid in (starters + players) if str(pid) != "0"]
            all_ids.update(ids)

        unmatched_ids = sorted(all_ids - matched_ids)

        all_players = get_sleeper_players()  # Cached API call

        for pid in unmatched_ids:
            player = all_players.get(pid)
            if player:
                unmatched_players.append({
                    "player_id": pid,
                    "sleeper_name": player.get("full_name", player.get("first_name", "") + " " + player.get("last_name", "")),
                    "age": player.get("age", "N/A"),
                    "position": player.get("position", "N/A")
                })
            else:
                unmatched_players.append({
                    "player_id": pid,
                    "sleeper_name": "Unknown",
                    "age": "N/A",
                    "position": "N/A"
                })

    except Exception as e:
        unmatched_players = [{"player_id": "N/A", "sleeper_name": f"(Error: {str(e)})", "age": "N/A", "position": "N/A"}]

    return render_template("admin_unmatched.html",
                           league_name=league_name,
                           unmatched_players=unmatched_players)

    
@app.route("/admin/<league_name>/themes", methods=["GET", "POST"])
def theme_selector(league_name):
    leagues = load_all_leagues()
    if not session.get("is_admin") or session.get("league_name") != league_name:
        return "🔒 Access denied."

    config = leagues[league_name]
    league_id = config.get("league_id")
    if not league_id:
        flash("⚠️ League ID is not set.", "error")
        return redirect(url_for("admin_page", league_name=league_name))

    # Load users from league
    users = []
    try:
        raw_users = get_league_users(league_id)
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
        leagues[league_name]["themes"] = themes
        with open(CONFIG_FILE, "w") as f:
            json.dump(leagues, f, indent=2)
        flash("✅ Team themes updated.", "success")
        return redirect(url_for("theme_selector", league_name=league_name))


    # Prepare team list
    nfl_teams = [
        "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
        "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
        "LAC", "LAR", "LV", "MIA", "MIN", "NE", "NO", "NYG",
        "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS"
    ]

    assigned_users = set(themes.values())

    return render_template("admin_themes.html",
                           league_name=league_name,
                           users=users,
                           themes=themes,
                           nfl_teams=nfl_teams,
                           assigned_users=assigned_users)


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


@app.route("/")
def root():
    return redirect(url_for("login"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
