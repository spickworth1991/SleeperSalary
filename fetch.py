import requests
from bs4 import BeautifulSoup
import pandas as pd
import time, random, re, datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
import os
from rapidfuzz import fuzz, process


# -------------------- Config --------------------
SERVICE_ACCOUNT_FILE = r'C:\Users\spick\OneDrive\Desktop\nfl_salary_tracker\config\nfl-stats-ff-00a13e9db7db.json'
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_ID = '1fm6o9HFT48F1AG0A5f4te3BDK8PHVnxksUVjWTDSCiI'

YEARS = ['2024', '2025']
# -------------------- Constants --------------------
# Define the sheet names and team abbreviations
SLEEPER_SHEET = 'SleeperPlayersList'
SPOTRAC_TEAMS = {
    'ARI': 'arizona-cardinals',
    'ATL': 'atlanta-falcons',
    'BAL': 'baltimore-ravens',
    'BUF': 'buffalo-bills',
    'CAR': 'carolina-panthers',
    'CHI': 'chicago-bears',
    'CIN': 'cincinnati-bengals',
    'CLE': 'cleveland-browns',
    'DAL': 'dallas-cowboys',
    'DEN': 'denver-broncos',
    'DET': 'detroit-lions',
    'GB': 'green-bay-packers',
    'HOU': 'houston-texans',
    'IND': 'indianapolis-colts',
    'JAX': 'jacksonville-jaguars',
    'KC': 'kansas-city-chiefs',
    'LV': 'las-vegas-raiders',
    'LAC': 'los-angeles-chargers',
    'LAR': 'los-angeles-rams',
    'MIA': 'miami-dolphins',
    'MIN': 'minnesota-vikings',
    'NE': 'new-england-patriots',
    'NO': 'new-orleans-saints',
    'NYG': 'new-york-giants',
    'NYJ': 'new-york-jets',
    'PHI': 'philadelphia-eagles',
    'PIT': 'pittsburgh-steelers',
    'SEA': 'seattle-seahawks',
    'SF': 'san-francisco-49ers',
    'TB': 'tampa-bay-buccaneers',
    'TEN': 'tennessee-titans',
    'WAS': 'washington-commanders',
    # Add more if needed
}


# -------------------- Common Name Equivalents --------------------
COMMON_NAME_EQUIVS = {
    # Standard diminutives
    "matt": "matthew", "matthew": "matthew",
    "mike": "michael", "michael": "michael",
    "nick": "nicholas", "nicky": "nicholas", "nicholas": "nicholas",
    "chris": "christopher", "christopher": "christopher",
    "dan": "daniel", "daniel": "daniel",
    "joe": "joseph", "joey": "joseph", "joseph": "joseph",
    "tom": "thomas", "thomas": "thomas",
    "tony": "anthony", "anthony": "anthony",
    "jim": "james", "jimmy": "james", "james": "james",
    "bob": "robert", "bobby": "robert", "rob": "robert", "robert": "robert",
    "alex": "alexander", "alexander": "alexander",
    "zac": "zachary", "zach": "zachary", "zack": "zachary", "zachary": "zachary",
    "nate": "nathan", "nathan": "nathan",
    "will": "william", "bill": "william", "billy": "william", "william": "william",
    "sam": "samuel", "samuel": "samuel",
    "steve": "steven", "steven": "steven", "stephen": "steven",
    "rick": "richard", "richard": "richard", "rich": "richard", "dick": "richard",
    "ken": "kenneth", "kenny": "kenneth", "kenneth": "kenneth",
    "rob": "robert", "robby": "robert",
    "fred": "frederick", "frederick": "frederick",
    "damon": "damon", "donnie": "donald", "donald": "donald",
    "derrick": "derrick", "derrick": "derrick",
    "cam": "cameron",
    "camryn": "cameron",
    "trenton": "trent",
    "kam": "kamren",
    "dee": "demarcus",       # You had "larry" but it's likely "demarcus"
    "tyre": "tyreke",
    "tyrone": "ty",
    "tyrion": "ty",
    "josh": "joshua",
    "julius": "julian",       # if consistently used that way
    "daxton": "dax",
    "sam": "samuel",
    "nick": "nicholas",
    "chauncey": "cj",         # questionable—keep only if multiple uses
    "pat": "patrick",
    "tony": "anthony",
    "gabe": "gabriel",
    "isaiah": "isaac",        # if mismatch happens in real usage
    "tedarrell": "tj",
    "gabe": "gabriel",  
    "jake": "jacob",  
    "tony": "anthony",
    "danny": "daniel",
    "andrew": "andy" ,"andrew":"drew",  
    "shaquill": "shaq",
    "bryce":"brycen",
    "dru": "andru",
    "kyle":"kyler",
    "tra":"travion",
    "tim":"timothy",
    

}



NICKNAME_OVERRIDES = {
    "sean bunting": "Sean Murphy-Bunting",
    "ahmad gardner": "sauce gardner",
    "chauncey gardner-johnson": "cj gardner-johnson",
    "foley fatukasi": "olakunle fatukasi",
    "amaré barno": "Amare Barno",  
    "ogbonnia okoronkwo": "ogbo okoronkwo",
    "decobie durant": "cobie durant", 
    "trenton brown": "trent brown",
    "malcolm rodríguez": "malcolm rodriguez",
    "julius brents": "juju brents",  
    "audric estimé": "audric estime", 
    "marquise brown": "hollywood brown",  
    "christian roland-wallace":"chris roland-wallace",
    "delmar glaze": "dj glaze",  
    "david ebuka agoha": "david agoha",  
    "john shenker": "john samuel shenker",  
    "d'wayne eskridge": "dee eskridge",
    "dontavian jackson": "lucky jackson",
    "rezjohn wright": "rejzohn wright",  
    "carlos basham jr.": "boogie basham",
    "xavier newman-johnson": "xavier newman",
    "tariq woolen": "riq woolen",
    "joe tryon": "joe tryon-shoyinka",
    "iosua opeta": "sua opeta",
    "sebastian joseph": "sebastian joseph-day",
    "nick westbrook": "nick westbrook-ikhine",
    "johnny newton": "jer'zhan newton",
    "jartavius martin": "quan martin",
    "haggai chisom ndubuisi": "haggai ndubuisi",
    "quez watkins": "quez watkins",
    "frank gore": "frank gore",
    "tyreek maddox-william":"tyreek maddox-williams",
    "elerson g. smith":"elerson smith",
    "john parker romo":"parker romo",
    


}





COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# -------------------- Auth --------------------
def get_service():
    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('sheets', 'v4', credentials=creds)

# -------------------- Google Sheets --------------------
def load_sleeper_api():
    url = "https://api.sleeper.app/v1/players/nfl"
    resp = requests.get(url)
    data = resp.json()

    rows = []
    for player_id, info in data.items():
        # Skip if status is exactly 'inactive' (case-insensitive)
        #if str(info.get("status", "")).lower() == "inactive":
            #continue

        rows.append({
            "player_id": player_id,
            "full_name": info.get("full_name", ""),
            "position": info.get("position", ""),
            "team": info.get("team", ""),
            "age": info.get("age")
        })

    return pd.DataFrame(rows)



def write_to_new_sheet(df):
    service = get_service()

    if "Team" not in df.columns or "Section" not in df.columns or "Year" not in df.columns:
        raise Exception("❌ Missing 'Team', 'Section', or 'Year' column in DataFrame.")

    final_rows = []

    years = sorted(df["Year"].dropna().unique())
    for year in years:
        year_df = df[df["Year"] == year]

        final_rows.append([])  # Blank line before year
        final_rows.append([f"{year}"])  # Year header row

        teams = year_df["Team"].dropna().unique()
        for team in teams:
            team_df = year_df[year_df["Team"] == team]

            for section in ["Active", "Practice Squad", "Injured Reserve", "Draft Pool", "PUP"]:
                section_df = team_df[team_df["Section"] == section]
                if section_df.empty:
                    continue

                final_rows.append([])  # Blank line before team section
                title = f"{team}" if section == "Active" else f"{team} {section}"
                final_rows.append([title])

                player_col = "Player"
                base_cols = [player_col, "Cap Hit", "Pos", "sleeper_name", "player_id", "Dead Cap", "Age", "Cap Hit PctLeague Cap"]
                section_cols = [col for col in base_cols if col in section_df.columns]

                final_rows.append(section_cols)
                section_df = section_df.reset_index(drop=True)
                final_rows += section_df[section_cols].fillna('').values.tolist()

        # Handle Free Agents for this year
        fa_df = year_df[year_df["Section"] == "Free Agent"]
        if not fa_df.empty:
            final_rows.append([])  # Blank line before FA
            final_rows.append(["Free Agents"])
            base_cols = ["Player", "AAV", "Pos", "sleeper_name", "player_id"]
            section_cols = [col for col in base_cols if col in fa_df.columns]
            final_rows.append(section_cols)
            final_rows += fa_df[section_cols].fillna('').values.tolist()

    # Sheet title
    now = datetime.datetime.now()
    title = f"{now.month}-{now.day}-{now.year % 100}-{now.hour}_{now.minute}"

    # Create the new sheet
    service.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"requests": [{"addSheet": {"properties": {"title": title}}}]}
    ).execute()

    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{title}!A1",
        body={"values": final_rows},
        valueInputOption="USER_ENTERED"
    ).execute()

    print(f"✅ Sheet '{title}' created and formatted by year.")

    # Apply highlighting to 'UNMATCHED'
    sheet_metadata = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    sheet_id = next(s['properties']['sheetId'] for s in sheet_metadata['sheets'] if s['properties']['title'] == title)

    highlight_request = {
        "requests": [
            {
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [{"sheetId": sheet_id}],
                        "booleanRule": {
                            "condition": {
                                "type": "TEXT_EQ",
                                "values": [{"userEnteredValue": "UNMATCHED"}]
                            },
                            "format": {
                                "backgroundColor": {"red": 1.0, "green": 1.0, "blue": 0.6}
                            }
                        }
                    },
                    "index": 0
                }
            }
        ]
    }

    service.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body=highlight_request
    ).execute()

    print(f"✅ Highlighting applied to 'UNMATCHED' values.")





# -------------------- Position Normalization --------------------
def map_position(pos):
    if not isinstance(pos, str):
        return []
    pos = pos.strip().upper()

    mapping = {
        'DL': ['DL', 'DE', 'DT','OLB'],
        'DE': ['DL', 'DE', 'EDGE', 'OLB', 'DT','ILB'],  # EDGE is common in Sleeper
        'DT': ['DL', 'DT', 'DE','OLB','G', 'FB'],

        'LB': ['LB', 'ILB', 'OLB', 'MLB', 'DE','FB','DE/OLB', 'DT','FS','S'],
        'ILB': ['LB', 'ILB', 'MLB', 'DB'],
        'OLB': ['LB', 'OLB', 'EDGE'],

        'CB': ['CB', 'DB','S','FS'],
        'S': ['S', 'SS', 'FS', 'DB'],
        'SS': ['S', 'SS'],
        'FS': ['S', 'FS'],
        'DB': ['CB', 'S', 'SS', 'FS', 'DB','S/FS','S/PR','S/SS','CB/FS','CB/SS','CB/S','LB','ILB','WR','SS/S'], 

        'WR': ['WR', 'X', 'Z', 'SLOT', 'REC', 'TE'],
        'RB': ['RB', 'HB', 'FB','RB/CB', 'WR'],
        'FB': ['RB', 'FB','FB/TE'],
        'HB': ['RB', 'HB'],
        'TE': ['TE', 'H-BACK', 'WR','T', "RT"],
        
        'OL': ['OL', 'OT', 'G', 'T', 'LT', 'RT', 'C','G/C','RT/T','C/G','LT/T','RT/G',"S"],
        'OT': ['OT', 'T', 'LT', 'RT','G', 'C', 'G/C', 'RT/T', 'C/T', 'G/T', 'OL'],
        'OG': ['G', 'OL', 'C',"LT"], 
        'NT': ['NT', 'DT','DE'], 
        'T': ['T', 'OT', 'LT', 'RT','LT/T','RT/T','RT/G','C/T','G/T','G','C', 'TE'],
        'G': ['G', 'OG', 'OL','C','G/C', 'RT/G', 'C/G', 'LT/G', 'T/G', 'G/G','LT','T', 'RT'], 
        'C': ['C', 'OC', 'G', 'OL','T'],

        'QB':['WR','QB'],

        'K': ['K', 'PK', 'P'],
        'P': ['P', 'K', 'PK'],
        'K/P': ['K', 'P', 'PK'],

        

    }

    return mapping.get(pos, [pos])



# -------------------- Spotrac Scraping --------------------
def fetch_with_retries(url, retries=3):
    for _ in range(retries):
        resp = requests.get(url, headers=COMMON_HEADERS)
        if resp.status_code == 200:
            return resp
        time.sleep(1 + random.random())
    raise Exception(f"Failed to fetch {url}")

def parse_table(table, team_abbr=None):
    tbody_rows = table.find('tbody').find_all('tr')

    # Find first valid data row to determine real column count
    for tr in tbody_rows:
        first_cells = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
        if len(first_cells) >= 5:
            break
    else:
        raise Exception("Couldn't find a valid row in tbody.")

    # Use thead headers if available
    thead = table.find('thead')
    if thead:
        raw_headers = [th.get_text(strip=True) for th in thead.find_all('th') if th.get_text(strip=True)]
    else:
        raw_headers = []

    # Pad or trim headers to match row
    if len(raw_headers) < len(first_cells):
        raw_headers += [f"Column{i}" for i in range(len(raw_headers), len(first_cells))]
    elif len(raw_headers) > len(first_cells):
        raw_headers = raw_headers[:len(first_cells)]

    headers = raw_headers
    rows = []

    for i, tr in enumerate(tbody_rows):
        raw_cells = tr.find_all(['td', 'th'])
        cells = []
        idx = 0

        name = ""
        name_idx = -1
        if raw_cells:
            for idx_try in (1, 2):
                if len(raw_cells) > idx_try:
                    cell = raw_cells[idx_try]
                    a = cell.find('a')
                    if a and a.text.strip():
                        name = a.text.strip()
                        name_idx = idx_try
                        break
                    else:
                        text = cell.get_text(strip=True)
                        if text:
                            name = text
                            name_idx = idx_try
                            break

        if not name:
            continue

        cells.append(name)
        idx = max(name_idx + 1, 2)

        while idx < len(raw_cells):
            text = raw_cells[idx].get_text(strip=True)
            cells.append(text)
            idx += 1

        if all(cell == '' for cell in cells):
            continue

        if len(cells) < len(headers):
            cells += [''] * (len(headers) - len(cells))
        elif len(cells) > len(headers):
            print(f"⚠️ Trimming row {i} on {team_abbr}: {len(cells)} vs {len(headers)}")
            cells = cells[:len(headers)]

        rows.append(cells)

    if not rows:
        raise Exception("No valid rows found after header adjustment.")

    df = pd.DataFrame(rows, columns=headers)
    # Rename the first column to just "Player" immediately
    df = df.rename(columns={df.columns[0]: "Player"})
    return df

def parse_fa_table(table, team_abbr=None):
    tbody_rows = table.find('tbody').find_all('tr')

    # Extract and clean headers
    thead = table.find('thead')
    if thead:
        raw_headers = [th.get_text(" ", strip=True) for th in thead.find_all('th')]
    else:
        raw_headers = []

    rows = []

    for i, tr in enumerate(tbody_rows):
        raw_cells = tr.find_all('td')
        if len(raw_cells) < 5:
            continue  # Skip short/incomplete rows

        # Extract name from <a> in first cell
        a = raw_cells[1].find('a') or raw_cells[0].find('a')
        name = a.text.strip() if a else raw_cells[0].get_text(strip=True)
        if not name:
            continue

        # Full row: name + rest of data
        cells = [name] + [td.get_text(strip=True) for td in raw_cells[1:]]

        # Enforce consistent headers
        headers = ["Player"] + raw_headers[1:]
        if len(cells) > len(headers):
            cells = cells[:len(headers)]
        elif len(cells) < len(headers):
            headers = headers[:len(cells)]

        rows.append(cells)

    if not rows:
        raise Exception("No valid rows found in FA table.")

    df = pd.DataFrame(rows, columns=headers)

    # Optional: strip/rename AAV if it's mislabeled
    for col in df.columns:
        if "aav" in col.lower():
            df = df.rename(columns={col: "AAV"})
            break

    return df

def parse_draft_pool_table(table, team_abbr=None):
    tbody_rows = table.find('tbody').find_all('tr')

    thead = table.find('thead')
    if thead:
        raw_headers = [th.get_text(strip=True) for th in thead.find_all('th') if th.get_text(strip=True)]
    else:
        raw_headers = []

    rows = []

    for i, tr in enumerate(tbody_rows):
        raw_cells = tr.find_all('td')
        if len(raw_cells) < 3:
            continue

        # Extract player name from <a> tag or plain text
        a = raw_cells[1].find('a')
        name = a.text.strip() if a else raw_cells[1].get_text(strip=True)
        if not name:
            continue

        # Pos should be in column 0, Cap Hit in column 2
        pos = raw_cells[2].get_text(strip=True)
        cap_hit = raw_cells[3].get_text(strip=True)

        rows.append([name, pos, cap_hit])

    if not rows:
        raise Exception("No valid rows found in Draft Pool table.")

    df = pd.DataFrame(rows, columns=["Player", "Pos", "Cap Hit"])
    return df





# -------------------- Spotrac Data Fetching --------------------
def dedupe_columns(cols):
    seen = {}
    result = []
    for col in cols:
        if col not in seen:
            seen[col] = 1
            result.append(col)
        else:
            count = seen[col]
            new_col = f"{col}.{count}"
            while new_col in seen:
                count += 1
                new_col = f"{col}.{count}"
            seen[col] = count + 1
            seen[new_col] = 1
            result.append(new_col)
    return result


def get_spotrac_data():
    all_sections = []

    for year in YEARS:
        for abbr, slug in SPOTRAC_TEAMS.items():
            url = f"https://www.spotrac.com/nfl/{slug}/cap/overview/_/year/{year}"
            print(f"Fetching {abbr} ({year})...")
            resp = fetch_with_retries(url)
            soup = BeautifulSoup(resp.content, 'html.parser')
            tables = soup.find_all('table')

            if not tables:
                print(f"⚠️ No tables found for {abbr} ({year})")
                continue

            for table in tables:
                label = None
                header_h2 = table.find_previous(lambda tag: tag.name == "h2" and year in tag.text)
                if header_h2:
                    text = header_h2.text.strip().lower()
                    if "injured reserve" in text:
                        label = "Injured Reserve"
                    elif "practice squad" in text:
                        label = "Practice Squad"
                    elif "active roster" in text:
                        label = "Active"
                    elif "draft pool" in text:
                        label = "Draft Pool"
                    elif "reserve/pup" in text:
                        label = "PUP"

                if not label:
                    print(f"🔎 Skipping unlabeled table for {abbr} ({year})")
                    continue

                try:
                    if label == "Draft Pool":
                        df = parse_draft_pool_table(table, team_abbr=abbr)

                        # TEMP: Save raw draft pool data for inspection
                        #filename = f"raw_draft_pool_{abbr}_{year}.csv"
                        #df.to_csv(filename, index=False)
                        #print(f"📄 Saved draft pool data to {filename}")

                        
                    else:
                        df = parse_table(table, team_abbr=abbr)
                        if df.columns.duplicated().any():
                            print(f"⚠️ Duplicate columns detected in {abbr} {label} {year}:")
                            print(df.columns[df.columns.duplicated()].tolist())

                    if not df.empty:
                        df["Team"] = abbr
                        df["Section"] = label
                        df["Year"] = year  # 👈 Tag year here
                        print(f"✅ {abbr} {label} {year}: {len(df)} rows parsed.")
                        all_sections.append(df)
                except Exception as e:
                    print(f"⚠️ Failed to parse {abbr} table ({label}) ({year}): {e}")
                    continue

            time.sleep(0.5)

        # Free Agents for this year
        fa_url = f"https://www.spotrac.com/nfl/free-agents/_/year/{year}"
        print(f"Fetching Free Agents ({year})...")
        fa_resp = fetch_with_retries(fa_url)
        fa_soup = BeautifulSoup(fa_resp.content, 'html.parser')
        fa_tables = fa_soup.find_all('table')

        for table in fa_tables:
            headers = [th.get_text(strip=True).lower() for th in table.find_all('th')]
            if any(h.startswith("player") for h in headers):
                fa_df = parse_fa_table(table)
                if not fa_df.empty:
                    if "To" in fa_df.columns:
                        fa_df["Team"] = fa_df["To"].where(fa_df["To"].str.strip() != "", "Free Agent")
                    else:
                        fa_df["Team"] = "Free Agent"
                    fa_df["Section"] = "Free Agent"
                    fa_df["Year"] = year  # 👈 Tag year here too
                    print(f"✅ Free Agents {year}: {len(fa_df)} rows parsed.")
                    all_sections.append(fa_df)
                break

    final_df = pd.concat(all_sections, ignore_index=True)
    first_col = final_df.columns[0]
    if first_col != "Player":
        final_df = final_df.rename(columns={first_col: "Player"})
    # Ensure unique column names
    final_df.columns = dedupe_columns(final_df.columns)

    return final_df



# -------------------- Merging --------------------
def normalize(name):
    if not isinstance(name, str):
        return ""
    original = name.lower().strip()

    # Remove punctuation and suffixes
    name = name.lower().strip()
    name = name.replace("'", "").replace(".", "")
    name = re.sub(r"\b(jr|sr|iii|ii|iv|v)\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[^\w\s]", "", name)
    name = re.sub(r"\s+", " ", name).strip()

        # First name canonicalization
    parts = name.split(" ")
    if parts and parts[0] in COMMON_NAME_EQUIVS:
        parts[0] = COMMON_NAME_EQUIVS[parts[0]]
        name = " ".join(parts)

    # Direct override (nickname mapping)
    if original in NICKNAME_OVERRIDES:
        mapped = NICKNAME_OVERRIDES[original]
        if mapped != original:  # Prevent infinite recursion
            return normalize(mapped)

    return name



def merge_spotrac_and_sleeper(spotrac_df, sleeper_df):
    player_col = "Player"
    #print("🔎 Spotrac columns at start of merge:", spotrac_df.columns.tolist())
    spotrac_df['name_original'] = spotrac_df[player_col].astype(str)

    
    if not player_col:
        raise Exception("Could not find a Player column in Spotrac data.")

    spotrac_df['name_norm'] = spotrac_df[player_col].map(normalize)
    sleeper_df['name_norm'] = sleeper_df['full_name'].map(normalize)

    # spotrac_df[['Player', 'Pos', 'name_norm']].drop_duplicates().sort_values('name_norm').to_csv("spotrac_normalized_names.csv", index=False)
    # sleeper_df[['full_name', 'position', 'name_norm']].drop_duplicates().sort_values('name_norm').to_csv("sleeper_normalized_names.csv", index=False)

    # print("✅ Normalized name CSVs saved: spotrac_normalized_names.csv & sleeper_normalized_names.csv")


    # Create new columns for player_id and sleeper position
    player_ids = []
    sleeper_positions = []
    sleeper_names = []
    unmatched_log = []


    for _, row in spotrac_df.iterrows():
        norm_name = row['name_norm']
        spotrac_pos = row.get('Pos', '').strip().upper()
        section = row.get("Section", "")
        original_name = row.get("name_original", row.get(player_col, "")).strip()
        matched_player = None
        possible_matches = sleeper_df[sleeper_df['name_norm'] == norm_name].to_dict('records')

        if not possible_matches:
            print(f"❌ No sleeper match for: Spotrac '{row.get(player_col)}' → norm '{norm_name}'")
        # else:
        #     if len(possible_matches) > 1:
        #         print(f"⚠️ Multiple matches for '{norm_name}': {[p['full_name'] for p in possible_matches]}")

        # Special handling for Draft Pool and Free Agent – skip age matching
        if section in ["Draft Pool", "Free Agent"]:
            # Try position-only match
            for sleeper_entry in possible_matches:
                sleeper_pos = sleeper_entry.get('position', '')
                valid_spotrac_equivs = map_position(sleeper_pos)
                if spotrac_pos in valid_spotrac_equivs:
                    matched_player = sleeper_entry
                    break
            # Fallback to first name match
            if not matched_player and possible_matches:
                matched_player = possible_matches[0]

        else:
            # Standard Matching (Position + Age)
            age_val = row.get('Age', '')
            spotrac_age = float(age_val) if str(age_val).strip().replace('.', '', 1).isdigit() else None

            for sleeper_entry in possible_matches:
                sleeper_pos = sleeper_entry.get('position', '')
                valid_spotrac_equivs = map_position(sleeper_pos)
                sleeper_age = sleeper_entry.get('age')
                if spotrac_pos in valid_spotrac_equivs and sleeper_age and spotrac_age:
                    if abs(sleeper_age - spotrac_age) <= 1:
                        matched_player = sleeper_entry
                        break

            if not matched_player:
                for sleeper_entry in possible_matches:
                    sleeper_pos = sleeper_entry.get('position', '')
                    valid_spotrac_equivs = map_position(sleeper_pos)
                    if spotrac_pos in valid_spotrac_equivs:
                        matched_player = sleeper_entry
                        break

            if not matched_player and possible_matches and spotrac_age:
                best_diff = float('inf')
                best_match = None
                for sleeper_entry in possible_matches:
                    sleeper_age = sleeper_entry.get('age')
                    if sleeper_age:
                        diff = abs(sleeper_age - spotrac_age)
                        if diff < best_diff:
                            best_diff = diff
                            best_match = sleeper_entry
                if best_diff <= 1:
                    matched_player = best_match

            if not matched_player:
                fallback_name = NICKNAME_OVERRIDES.get(norm_name)
                if fallback_name:
                    fallback_norm = normalize(fallback_name)
                    fallback_matches = sleeper_df[sleeper_df['name_norm'] == fallback_norm].to_dict('records')
                    if fallback_matches:
                        matched_player = fallback_matches[0]
                        print(f"🔁 Fallback override used for '{row.get(player_col)}' → '{fallback_name}'")

            # fallback: try splitting hyphenated last names
            # Hyphen fallback
            if matched_player is None and "-" in original_name:
                try:
                    first, last_hyphenated = original_name.split(" ", 1)
                except ValueError:
                    first, last_hyphenated = original_name, ""

                last_parts = last_hyphenated.split("-")

                # 1. Full spaced last name
                print("step 1")
                full_spaced = normalize(f"{first} {' '.join(last_parts)}")
                trial_df = sleeper_df[sleeper_df['name_norm'] == full_spaced]
                if not trial_df.empty:
                    matched_player = trial_df.iloc[0]
                    print(f"🔁 Matched with spaced hyphen: '{original_name}' → '{matched_player['full_name']}'")

                # 2. Try each last name individually
                if matched_player is None:
                    print("step 2")
                    for part in last_parts:
                        partial_name = normalize(f"{first} {part}")
                        trial_df = sleeper_df[sleeper_df['name_norm'] == partial_name]
                        if not trial_df.empty:
                            matched_player = trial_df.iloc[0]
                            print(f"🔁 Matched with partial hyphen: '{original_name}' → '{matched_player['full_name']}' via '{part}'")
                            break

                # 3. Fuzzy match on combined options
                if matched_player is None:
                    print("step 3")
                    combo_names = [
                        normalize(f"{first} {''.join(last_parts)}"),         # coloncastillo
                        normalize(f"{first} {last_parts[0]}"),               # colon
                        normalize(f"{first} {last_parts[1]}") if len(last_parts) > 1 else "",
                        normalize(f"{first} {' '.join(last_parts)}"),        # colon castillo
                    ]
                    candidate_names = sleeper_df['name_norm'].tolist()
                    for trial in combo_names:
                        if not trial:
                            continue
                        best_match = process.extractOne(trial, candidate_names, scorer=fuzz.ratio)
                        if best_match and best_match[1] >= 90:
                            trial_matches_df = sleeper_df[sleeper_df['name_norm'] == best_match[0]]
                            if not trial_matches_df.empty:
                                matched_player = trial_matches_df.iloc[0]
                                print(f"🧪 Fuzzy hyphen match '{original_name}' → '{matched_player['full_name']}' (score: {best_match[1]}) via '{trial}'")
                                break

                # 4. Fuzzy match against each part with first name
                if matched_player is None:
                    print("step 4")
                    for part in last_parts:
                        fuzzy_name = normalize(f"{first} {part}")
                        best_match = process.extractOne(fuzzy_name, candidate_names, scorer=fuzz.ratio)
                        if best_match and best_match[1] >= 90:
                            trial_matches_df = sleeper_df[sleeper_df['name_norm'] == best_match[0]]
                            if not trial_matches_df.empty:
                                matched_player = trial_matches_df.iloc[0]
                                print(f"🧪 Fuzzy part match '{original_name}' → '{matched_player['full_name']}' (score: {best_match[1]}) via '{fuzzy_name}'")
                                break


        if matched_player is None:
            # 🔍 Try fuzzy match as last resort
            FUZZY_MATCH_THRESHOLD = 90
            candidate_names = sleeper_df['name_norm'].tolist()

            best_match = process.extractOne(norm_name, candidate_names, scorer=fuzz.ratio)

            if best_match and best_match[1] >= FUZZY_MATCH_THRESHOLD:
                match_name = best_match[0]
                score = best_match[1]

                trial_matches_df = sleeper_df[sleeper_df['name_norm'] == match_name]

                if not trial_matches_df.empty:
                    matched_player = trial_matches_df.iloc[0]
                    print(f"🧪 Fuzzy matched '{row.get(player_col)}' → '{matched_player['full_name']}' (score: {score})")





        if matched_player is not None:
            player_ids.append(matched_player['player_id'])
            sleeper_positions.append(matched_player['position'])
            sleeper_names.append(matched_player['full_name'])
        else:
            player_ids.append("UNMATCHED")
            sleeper_positions.append("")
            sleeper_names.append("UNMATCHED")
            unmatched_log.append(row.to_dict())  # Include full row for debugging



    # Add to DataFrame
    spotrac_df['player_id'] = player_ids
    spotrac_df['position'] = sleeper_positions
    spotrac_df['sleeper_name'] = sleeper_names

    print(f"✅ Merged data: {len(spotrac_df)} rows after join with mapped position match")
    #print(spotrac_df[['name_norm', 'player_id', 'position']].head(5))

    if unmatched_log:
        print(f"🔎 {len(unmatched_log)} unmatched players:")
        # for name in unmatched_log[:2]:  # Show first 10 to avoid spam
        #     print(f"   - {name}")
        # if len(unmatched_log) > 2:
        #     print(f"   ... and {len(unmatched_log) - 2} more.")
    else:
        print("✅ All players matched.")


    return spotrac_df





# -------------------- Main --------------------
if __name__ == "__main__":
    try:
        # Delete existing file if it exists
        if os.path.exists("SalaryDB.csv"):
            os.remove("SalaryDB.csv")
            print("🗑️ Existing SalaryDB.csv deleted.")

        if os.path.exists("unmatched_spotrac_players.csv"):
            os.remove("unmatched_spotrac_players.csv")
            print("🗑️ Existing unmatched_spotrac_players.csv deleted.")

        spotrac_df = get_spotrac_data()
        sleeper_df = load_sleeper_api()
        merged_df = merge_spotrac_and_sleeper(spotrac_df, sleeper_df)

        unmatched = merged_df[merged_df['player_id'] == "UNMATCHED"]
        unmatched.to_csv("unmatched_spotrac_players.csv", index=False)

        merged_df = merged_df.loc[:, ~merged_df.columns.duplicated()]
        merged_df = merged_df.reset_index(drop=True)

        print(f"✅ Duplicated? {merged_df.columns.duplicated().any()}")

        # Always write with header since file was deleted
        merged_df.to_csv("SalaryDB.csv", index=False)
        print("✅ Fresh SalaryDB.csv written.")

    except Exception as e:
        print(f"❌ Error: {e}")


