import os
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from difflib import get_close_matches

# ======================== Google Sheets Setup ========================
SPREADSHEET_ID = "1fm6o9HFT48F1AG0A5f4te3BDK8PHVnxksUVjWTDSCiI"
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SHEET_NAME = "ADP"

if os.environ.get("RENDER") == "true":
    SERVICE_ACCOUNT_FILE = "nfl-stats-ff-00a13e9db7db.json"
else:
    SERVICE_ACCOUNT_FILE = "config/leagues.json"

creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES)
service = build('sheets', 'v4', credentials=creds)
sheet = service.spreadsheets()

# ======================== Config ========================
LEAGUE_IDS = ["1245938023556730880","1240082455893901312","1078876267329482752"]  # Add more if needed

# ======================== Helper Functions ========================
new_players_log = []
seen_new_player_keys = set()

def get_column_b_formulas():
    result = sheet.values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!B2:B1000",  # assuming up to row 1000
        valueRenderOption="FORMULA"
    ).execute()
    return [row[0] if row else "" for row in result.get("values", [])]


def get_draft_info(league_id):
    url = f"https://api.sleeper.app/v1/league/{league_id}/drafts"
    response = requests.get(url)
    response.raise_for_status()
    drafts = response.json()
    print(f"[DEBUG] Drafts for league {league_id}:", drafts)
    if drafts and "settings" in drafts[0]:
        return drafts[0]["draft_id"], int(drafts[0]["settings"]["teams"])
    return None, None


def get_draft_picks(draft_id):
    url = f"https://api.sleeper.app/v1/draft/{draft_id}/picks"
    response = requests.get(url)
    response.raise_for_status()
    picks = response.json()
    print(f"[DEBUG] Got {len(picks)} picks for draft {draft_id}")
    return picks

def get_sheet_data():
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=f"{SHEET_NAME}!A1:Z1000").execute()
    return result.get("values", [])

def write_to_sheet(row_idx, col_idx, value):
    # Convert column index to letter(s)
    col_letter = ""
    while col_idx >= 0:
        col_letter = chr(col_idx % 26 + 65) + col_letter
        col_idx = col_idx // 26 - 1
    cell = f"{SHEET_NAME}!{col_letter}{row_idx + 1}"
    sheet.values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=cell,
        valueInputOption="RAW",
        body={"values": [[value]]}
    ).execute()

# ======================== Main Logic ========================
def update_adp_sheet():
    print("=== Starting ADP update ===")
    column_b_formulas = get_column_b_formulas()

    sheet_data = get_sheet_data()
    header = sheet_data[0] if sheet_data else []
    names = [row[0] for row in sheet_data[1:] if row and len(row) > 0]

    # Map names and league IDs to their positions
    league_to_col = {lid: idx + 1 for idx, lid in enumerate(header[1:])}
    name_to_row = {name: idx + 1 for idx, name in enumerate(names)}

    updated_grid = [header] + [row[:] + [""] * (len(header) - len(row)) for row in sheet_data[1:]]

    for league_id in LEAGUE_IDS:
        draft_id, num_teams = get_draft_info(league_id)
        if not draft_id or not num_teams:
            print(f"Skipping league {league_id}")
            continue

        picks = get_draft_picks(draft_id)
        if str(league_id) not in league_to_col:
            header.append(str(league_id))
            league_to_col[str(league_id)] = len(header) - 1
            for row in updated_grid[1:]:
                row.append("")

        for pick in picks:
            meta = pick.get("metadata", {})
            first = meta.get("first_name", "").strip()
            last = meta.get("last_name", "").strip()
            full_name = f"{first} {last}".strip()
            if not full_name:
                continue
            pick_no = pick.get("pick_no")
            if not pick_no:
                continue

            rnd = (pick_no - 1) // num_teams + 1
            pick_in_round = (pick_no - 1) % num_teams + 1
            pick_str = f"{rnd}.{pick_in_round}"

           # Handle row creation or fuzzy match
            match = get_close_matches(full_name, name_to_row.keys(), n=1, cutoff=0.88)
            if match:
                matched_name = match[0]
                row_idx = name_to_row[matched_name]
                print(f"[MATCH] Matched '{full_name}' to '{matched_name}'")
            else:
                matched_name = full_name
                row_idx = len(updated_grid)
                name_to_row[matched_name] = row_idx
                new_row = [matched_name] + [""] * (len(header) - 1)
                updated_grid.append(new_row)

                if (matched_name, league_id) not in seen_new_player_keys:
                    new_players_log.append([matched_name, league_id, pick_str])
                    seen_new_player_keys.add((matched_name, league_id))

                print(f"[NEW] Added new player: {matched_name}")



            row_idx = name_to_row[matched_name]
            col_idx = league_to_col[str(league_id)]
            # Expand row if needed
            while len(updated_grid[row_idx]) <= col_idx:
                updated_grid[row_idx].append("")
            updated_grid[row_idx][col_idx] = pick_str
            print(f"[BATCH] {full_name} → {pick_str} @ row {row_idx+1}, col {col_idx+1}")

    # Final write
    print(f"[FINAL WRITE] Writing {len(updated_grid)} rows x {len(header)} columns...")
    # Strip out column B from overwrite
    final_output = []
    for row in updated_grid:
        if len(row) < 2:
            row += [""] * (2 - len(row))  # Make sure at least A and B exist
        final_output.append([row[0]] + [""] + row[2:])  # Skip B (leave it untouched)

    for i in range(1, len(final_output)):
        if i - 1 < len(column_b_formulas):
            formula = column_b_formulas[i - 1]
            if len(final_output[i]) < 2:
                final_output[i] += [""] * (2 - len(final_output[i]))
            final_output[i][1] = formula  # Restore original formula in column B



    sheet.values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": final_output}
    ).execute()


    # Write log of newly added players
    if new_players_log:
        import csv
        with open("new_players_log.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Player", "League ID", "Pick"])
            writer.writerows(new_players_log)
        print(f"[LOG] Saved {len(new_players_log)} new players to new_players_log.csv")
    else:
        print("[LOG] No new players were added.")



# ======================== Run ========================
if __name__ == "__main__":
    update_adp_sheet()
