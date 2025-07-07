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

COMMON_HEADERS = {
    "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
    "Accept":
    "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# -------------------- Auth --------------------
def get_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
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
        first_cells = [
            td.get_text(strip=True) for td in tr.find_all(['td', 'th'])
        ]
        if len(first_cells) >= 5:
            break
    else:
        raise Exception("Couldn't find a valid row in tbody.")

    # Use thead headers if available
    thead = table.find('thead')
    if thead:
        raw_headers = [
            th.get_text(strip=True) for th in thead.find_all('th')
            if th.get_text(strip=True)
        ]
    else:
        raw_headers = []

    # Pad or trim headers to match row
    if len(raw_headers) < len(first_cells):
        raw_headers += [
            f"Column{i}" for i in range(len(raw_headers), len(first_cells))
        ]
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
            print(
                f"⚠️ Trimming row {i} on {team_abbr}: {len(cells)} vs {len(headers)}"
            )
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
        raw_headers = [
            th.get_text(" ", strip=True) for th in thead.find_all('th')
        ]
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
        raw_headers = [
            th.get_text(strip=True) for th in thead.find_all('th')
            if th.get_text(strip=True)
        ]
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
                header_h2 = table.find_previous(
                    lambda tag: tag.name == "h2" and year in tag.text)
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
                        # filename = f"raw_draft_pool_{abbr}_{year}.csv"
                        # df.to_csv(filename, index=False)
                        # print(f"📄 Saved draft pool data to {filename}")

                    # if label == "Injured Reserve":
                    #     # TEMP: Save raw draft pool data for inspection
                    #     filename = f"raw_IR_{abbr}_{year}.csv"
                    #     df.to_csv(filename, index=False)
                    #     print(f"📄 Saved IR data to {filename}")

                    else:
                        df = parse_table(table, team_abbr=abbr)
                        if df.columns.duplicated().any():
                            print(
                                f"⚠️ Duplicate columns detected in {abbr} {label} {year}:"
                            )
                            print(df.columns[df.columns.duplicated()].tolist())

                    if not df.empty:
                        df["Team"] = abbr
                        df["Section"] = label
                        df["Year"] = year  # 👈 Tag year here
                        print(
                            f"✅ {abbr} {label} {year}: {len(df)} rows parsed.")
                        all_sections.append(df)
                except Exception as e:
                    print(
                        f"⚠️ Failed to parse {abbr} table ({label}) ({year}): {e}"
                    )
                    continue

            time.sleep(0.5)

        # Free Agents for this year
        fa_url = f"https://www.spotrac.com/nfl/free-agents/_/year/{year}"
        print(f"Fetching Free Agents ({year})...")
        fa_resp = fetch_with_retries(fa_url)
        fa_soup = BeautifulSoup(fa_resp.content, 'html.parser')
        fa_tables = fa_soup.find_all('table')

        for table in fa_tables:
            headers = [
                th.get_text(strip=True).lower() for th in table.find_all('th')
            ]
            if any(h.startswith("player") for h in headers):
                fa_df = parse_fa_table(table)
                if not fa_df.empty:
                    if "To" in fa_df.columns:
                        fa_df["Team"] = fa_df["To"].where(
                            fa_df["To"].str.strip() != "", "Free Agent")
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
# -------------------- Position Normalization --------------------
def map_position(pos):
    if not isinstance(pos, str):
        return []
    pos = pos.strip().upper()

    mapping = {
        'DL': ['DL', 'DE', 'DT', 'OLB'],
        'DE': ['DL', 'DE', 'EDGE', 'OLB', 'DT','ILB'],  # EDGE is common in Sleeper
        'DT': ['DL', 'DT', 'DE', 'G', 'FB'],
        'LB': ['LB', 'ILB', 'OLB', 'MLB', 'DE', 'FB', 'DE/OLB', 'DT', 'FS', 'S'],
        'ILB': ['LB', 'ILB', 'MLB', 'DB'],
        'OLB': ['LB', 'OLB', 'EDGE'],
        'CB': ['CB', 'DB', 'S', 'FS'],
        'S': ['S', 'SS', 'FS', 'DB'],
        'SS': ['S', 'SS'],
        'FS': ['S', 'FS'],
        'DB': ['CB', 'S', 'SS', 'FS', 'DB', 'S/FS', 'S/PR', 'S/SS', 'CB/FS','CB/SS', 'CB/S', 'LB', 'ILB', 'SS/S'],
        'WR': ['WR', 'X', 'Z', 'SLOT', 'REC', 'TE'],
        'RB': ['RB', 'HB', 'FB', 'RB/CB', 'WR'],
        'FB': ['RB', 'FB', 'FB/TE'],
        'HB': ['RB', 'HB'],
        'TE': ['TE', 'H-BACK', 'WR', 'T', "RT"],
        'OL': ['OL', 'OT', 'G', 'T', 'LT', 'RT', 'C', 'G/C', 'RT/T', 'C/G','LT/T', 'RT/G', "S"],
        'OT': ['OT', 'T', 'LT', 'RT', 'G', 'C', 'G/C', 'RT/T', 'C/T', 'G/T', 'OL'],
        'OG': ['G', 'OL', 'C', "LT"],
        'NT': ['NT', 'DT', 'DE'],
        'T': ['T', 'OT', 'LT', 'RT', 'LT/T', 'RT/T', 'RT/G', 'C/T', 'G/T', 'G','C', 'TE', 'OL', 'DT'],
        'G': ['G', 'OG', 'OL', 'C', 'G/C', 'RT/G', 'C/G', 'LT/G', 'T/G', 'G/G','LT', 'T', 'RT'],
        'C': ['C', 'OC', 'G', 'OL', 'T'],
        'QB': ['WR', 'QB'],
        'K': ['K', 'PK', 'P'],
        'P': ['P', 'K', 'PK'],
        'K/P': ['K', 'P', 'PK'],
    }

    return mapping.get(pos, [pos])

# -------------------- Common Name Equivalents --------------------
# Groups of first-name equivalents
COMMON_NAME_GROUPS = [["matt", "matthew"], ["mike", "michael"],
                      ["nick", "nicky", "nicholas"], ["chris", "christopher"],
                      ["dan", "daniel", "danny"], ["joe", "joey", "joseph"],
                      ["tom", "thomas"], ["tony", "anthony"],
                      ["jim", "jimmy", "james"],
                      ["bob", "bobby", "rob", "robert", "robby"],
                      ["alex",
                       "alexander"], ["zac", "zach", "zack", "zachary"],
                      ["nate", "nathan"], ["will", "william", "bill", "billy"],
                      ["sam", "samuel"], ["steve", "steven", "stephen"],
                      ["rick", "rich", "richard", "dick"],
                      ["ken", "kenny", "kenneth"], ["fred", "frederick"],
                      ["cam", "cameron", "camryn"], ["trent", "trenton"],
                      ["kam", "kamren"], ["dee", "demarcus"],
                      ["ty", "tyrone", "tyrion", "tyreke"], ["josh", "joshua"],
                      ["julius", "julian"], ["dax", "daxton"],
                      ["cj", "chauncey"], ["tj", "tedarrell"],
                      ["pat", "patrick"], ["gabe", "gabriel"],
                      ["isaiah", "isaac"], ["jake", "jacob"],
                      ["andy", "andrew", "drew", "andres"],
                      ["shaq", "shaquill"], ["bryce", "brycen"],
                      ["dru", "andru"], ["kyle", "kyler"], ["tra", "travion"],
                      ["tim", "timothy"]]

# Expanded dictionary of { name: [variants] }
COMMON_NAME_EQUIVS = {
    name: group
    for group in COMMON_NAME_GROUPS
    for name in group
}

NICKNAME_OVERRIDES = {
    "ahmad gardner": "sauce gardner",
    "chauncey gardner-johnson": "cj gardner-johnson",
    "ogbonnia okoronkwo": "ogbo okoronkwo",
    "julius brents": "juju brents",
    "marquise brown": "hollywood brown",
    "delmar glaze": "dj glaze",
    "d'wayne eskridge": "dee eskridge",
    "dontavian jackson": "lucky jackson",
    "carlos basham jr.": "boogie basham",
    "johnny newton": "jer'zhan newton",
    "jartavius martin": "quan martin",
    "john parker romo": "parker romo",
    "anthony booker jr.": "tank booker",
    "tet mcmillan": "tetairoa mcmillan",
    "wy'kevious thomas": "bubba thomas",
    "basil okoye": "c.j. okoye",
    "john richardson": "jp richardson",
    "kyrese rowan": "kyrese white",
    "foley fatukasi": "folorunso fatukasi"
}


# -------------------- Merging --------------------
def normalize(name):
    if not isinstance(name, str):
        return ""
    name = name.lower().strip()

    # Direct override check first (raw input form)
    if name in NICKNAME_OVERRIDES:
        return normalize(NICKNAME_OVERRIDES[name])

    # Clean name
    name = name.replace("'", "").replace(".", "")
    name = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", name)
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"\s+", " ", name).strip()

    return name


def merge_spotrac_and_sleeper(spotrac_df, sleeper_df):
    from rapidfuzz import fuzz, process

    debug_logs = []
    player_col = "Player"

    # Normalize names
    spotrac_df['name_original'] = spotrac_df[player_col].astype(str)
    spotrac_df['name_norm'] = spotrac_df[player_col].map(normalize)
    sleeper_df['name_norm'] = sleeper_df['full_name'].map(normalize)

    # Save for debugging
    spotrac_df[['Player', 'Pos', 'name_norm']].sort_values('name_norm').to_csv(
        "spotrac_normalized_names.csv", index=False)
    sleeper_df[['full_name', 'position',
                'name_norm']].sort_values('name_norm').to_csv(
                    "sleeper_normalized_names.csv", index=False)

    player_ids = []
    sleeper_positions = []
    sleeper_names = []
    unmatched_log = []
    # DEBUG: Check how many "dj turner" entries exist
    # spotrac = spotrac_df[spotrac_df['name_norm'] == 'kyle williams']
    # debug_logs.append(
    #     f"🧾 Found {len(spotrac)} rows for 'kyle wiliams' in Spotrac")
    # print(spotrac[['Player', 'Pos', 'Age', 'Section']])
    # # DEBUG: Check how many "dj turner" entries exist
    # sleeper = sleeper_df[sleeper_df['name_norm'] == 'kyle williams']
    # debug_logs.append(
    #     f"🧾 Found {len(sleeper)} rows for 'kyle wiliams' in Spotrac")
    # print(sleeper[['full_name', 'position']])

    for _, row in spotrac_df.iterrows():
        try:
            norm_name = row['name_norm']
            original_name = row['name_original']
            spotrac_pos = str(row.get('Pos', '')).upper().strip()
            section = str(row.get("Section", "")).strip()
            matched_player = None

            # Split compound positions like RB/CB
            spotrac_pos_parts = [
                p.strip() for p in spotrac_pos.replace('/', ',').split(',')
                if p.strip()
            ]
            skip_age = section in ["Draft Pool", "Free Agent"]
            spotrac_age = float(row['Age']) if str(row.get('Age')).replace(
                '.', '', 1).isdigit() else None

            # STEP 1: Common name substitution
            first = norm_name.split(" ")[0]
            variants = COMMON_NAME_EQUIVS.get(first, [first])
            variant_names = set()
            for alt in variants:
                alt_name = norm_name.replace(first, alt, 1)
                variant_names.add(alt_name)
            variant_names.add(norm_name)

            possible_matches = sleeper_df[sleeper_df['name_norm'].isin(
                variant_names)].to_dict('records')

            # STEP 2: Rank all matches by name/pos/age (improved logic)
            best_match = None
            best_score = -1

            for entry in possible_matches:
                sleeper_name = entry.get('full_name', '')
                sleeper_norm = normalize(sleeper_name)
                sleeper_pos = entry.get('position', '')
                sleeper_age = entry.get('age')
                sleeper_id = entry.get('player_id', '')

                # Reject candidates with mismatched last names
                spot_last = norm_name.split()[-1]
                sleep_last = sleeper_norm.split()[-1]
                if spot_last != sleep_last:
                    continue

                # Reject mismatched first-letter of first name (optional tightening)
                spot_first = norm_name.split()[0]
                sleep_first = sleeper_norm.split()[0]
                if spot_first[0] != sleep_first[0]:
                    continue

            
                # Compute match scores
                name_score = fuzz.ratio(norm_name, sleeper_norm)
                if spot_first != sleep_first:
                    name_score -= 10

                valid_pos = map_position(sleeper_pos)
                pos_score = 25 if any(pos in valid_pos for pos in spotrac_pos_parts) else 0

                if skip_age:
                    age_score = 20
                elif sleeper_age and spotrac_age:
                    age_diff = abs(sleeper_age - spotrac_age)
                    age_score = max(0, 20 - age_diff * 10)  # stronger penalty
                else:
                    age_score = 0

                spotrac_team = str(row.get("Team", "")).upper()
                sleeper_team = str(entry.get("team", "")).upper()
                team_score = 20 if sleeper_team == spotrac_team else 0

                score = name_score + pos_score + age_score + team_score


                if score > best_score:
                    best_score = score
                    best_match = entry

                if spotrac_df['name_norm'].value_counts().get(norm_name, 0) > 1:
                    debug_logs.append(
                        f"🧪 CANDIDATE for '{original_name}' → {sleeper_name} | Pos={sleeper_pos} | Age={sleeper_age} | ID={sleeper_id} | Score={score}"
                    )

            # STEP 3: Accept best match if score is strong enough
            if best_match and best_score >= 80:
                matched_player = best_match
                if norm_name == "dj turner":
                    debug_logs.append(
                        f"✅ DJ TURNER FINAL MATCH: {matched_player['full_name']} | ID={matched_player['player_id']} | Score={best_score}"
                    )
                else:
                    debug_logs.append(
                        f"✅ Matched '{original_name}' → '{matched_player['full_name']}' (score: {best_score})"
                    )

            # STEP 3: Match by name + pos only
            if not matched_player:
                for entry in possible_matches:
                    sleeper_pos = entry.get('position', '')
                    valid_pos = map_position(sleeper_pos)
                    if any(pos in valid_pos for pos in spotrac_pos_parts):
                        matched_player = entry
                        break

            # STEP 4: Try middle-name or suffix trimming (e.g. "john samuel shenker" → "john shenker")
            if not matched_player and len(norm_name.split()) > 2:
                two_part = f"{norm_name.split()[0]} {norm_name.split()[-1]}"
                match_row = sleeper_df[sleeper_df['name_norm'] == two_part]
                if not match_row.empty:
                    matched_player = match_row.iloc[0].to_dict()
                    debug_logs.append(
                        f"✂️ Trimmed match '{original_name}' → '{matched_player['full_name']}'"
                    )

            # STEP 5: Hyphen-smart fuzzy match (full name and part variations)
            if not matched_player:
                spot_parts = norm_name.replace("-", " ").split()
                best_score = 0
                best_match = None

                for _, s_row in sleeper_df.iterrows():
                    sleeper_norm = s_row.get('name_norm', "")
                    sleeper_parts = sleeper_norm.replace("-", " ").split()

                    # Match if both names share 2+ parts
                    shared = set(spot_parts).intersection(sleeper_parts)
                    if len(shared) >= 2:
                        matched_player = s_row.to_dict()
                        debug_logs.append(
                            f"🔗 Hyphen-parts matched '{original_name}' → '{matched_player['full_name']}'"
                        )
                        break

                    # Also try fuzzy match on reduced forms (drop middle names)
                    spot_reduced = f"{spot_parts[0]} {spot_parts[-1]}" if len(
                        spot_parts) >= 2 else norm_name
                    sleep_reduced = f"{sleeper_parts[0]} {sleeper_parts[-1]}" if len(
                        sleeper_parts) >= 2 else sleeper_norm

                    # Try fuzzy on:
                    for a, b in [(norm_name, sleeper_norm),
                                 (spot_reduced, sleep_reduced)]:
                        score = fuzz.ratio(a, b)
                        if score > best_score:
                            best_score = score
                            best_match = s_row.to_dict()

                if not matched_player and best_score >= 90:
                    matched_player = best_match
                    debug_logs.append(
                        f"🧪 Fuzzy full-name fallback '{original_name}' → '{matched_player['full_name']}' (score: {best_score})"
                    )

            # STEP 6: Final fuzzy match
            if not matched_player:
                candidate_names = sleeper_df['name_norm'].tolist()
                fuzzy_try = process.extractOne(norm_name,
                                               candidate_names,
                                               scorer=fuzz.ratio)
                if fuzzy_try and fuzzy_try[1] >= 90:
                    match_row = sleeper_df[sleeper_df['name_norm'] ==
                                           fuzzy_try[0]]
                    if not match_row.empty:
                        matched_player = match_row.iloc[0].to_dict()
                        debug_logs.append(
                            f"🧪 Fuzzy matched '{original_name}' → '{matched_player['full_name']}' (score: {fuzzy_try[1]})"
                        )

            # STEP 7: Log suggestions
            if not matched_player:
                candidates = process.extract(norm_name,
                                             sleeper_df['name_norm'].tolist(),
                                             scorer=fuzz.ratio,
                                             limit=3)
                suggestion_str = ", ".join(
                    [f"{c[0]} ({c[1]})" for c in candidates])
                debug_logs.append(
                    f"🔍 Suggestions for '{original_name}' → {suggestion_str}")

            # Final assignment
            if matched_player:
                player_ids.append(matched_player.get('player_id', ''))
                sleeper_positions.append(matched_player.get('position', ''))
                sleeper_names.append(matched_player.get('full_name', ''))
            else:
                player_ids.append("UNMATCHED")
                sleeper_positions.append("")
                sleeper_names.append("UNMATCHED")
                unmatched_log.append(row.to_dict())

        except Exception as e:
            debug_logs.append(f"❌ Error matching '{row.get('Player')}' — {e}")
            player_ids.append("UNMATCHED")
            sleeper_positions.append("")
            sleeper_names.append("UNMATCHED")
            unmatched_log.append(row.to_dict())

    # Final output
    spotrac_df['player_id'] = player_ids
    spotrac_df['position'] = sleeper_positions
    spotrac_df['sleeper_name'] = sleeper_names

    if unmatched_log:
        pd.DataFrame(unmatched_log).to_csv("unmatched_spotrac_players.csv",
                                           index=False)
        debug_logs.append(
            f"🔎 {len(unmatched_log)} unmatched players written to unmatched_spotrac_players.csv"
        )

    if debug_logs:
        pd.DataFrame({
            'Log': debug_logs
        }).to_csv("merge_debug_log.csv", index=False)

    return spotrac_df


# -------------------- Main --------------------
if __name__ == "__main__":
    try:
        # Delete existing file if it exists
        if os.path.exists("SalaryDB.csv", ):
            os.remove("SalaryDB.csv")
            print("🗑️ Existing SalaryDB.csv deleted.")

        if os.path.exists("unmatched_spotrac_players.csv"):
            os.remove("unmatched_spotrac_players.csv")
            print("🗑️ Existing unmatched_spotrac_players.csv deleted.")

        if os.path.exists("merge_debug_log.csv"):
            os.remove("merge_debug_log.csv")
            print("🗑️ Existing merge_debug_log.csv deleted.")

        if os.path.exists("sleeper_normalized_names.csv"):
            os.remove("sleeper_normalized_names.csv")
            print("🗑️ Existing sleeper_normalized_names.csv deleted.")

        if os.path.exists("spotrac_normalized_names.csv"):
            os.remove("spotrac_normalized_names.csv")
            print("🗑️ spotrac_normalized_names.csv deleted.")

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
