# --- DRAFT APP: FULLY SYNCHRONIZED WITH SIM SCRIPT LOGIC ---

import streamlit as st
import pandas as pd
import numpy as np
import json
import unicodedata
import re
import random
import os
import time
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
import hashlib

st.set_page_config(page_title="Draft Simulator: AI Logic Version", layout="wide")

def generate_data_hash(data):
    """Generate a hash based on the actual data content for AgGrid keys"""
    if not data:
        return "empty"
    
    # Convert data to string and create hash
    data_str = str(data)
    return hashlib.md5(data_str.encode()).hexdigest()[:8]  # Use first 8 characters

st.markdown("""
    <style>
        .block-container { 
            padding-top: 2rem !important; 
            max-width: 100% !important;
        }
        .ag-root-wrapper { 
            min-height: 600px !important;
            height: 600px !important;
            width: 100% !important;
        }
        .ag-root {
            width: 100% !important;
            height: 100% !important;
        }
        .ag-center-cols-container {
            min-height: 500px !important;
        }
        .ag-header-row {
            background-color: #f0f2f6 !important;
        }
        /* Force the grid to be visible immediately */
        div[data-testid="stApp"] > div:first-child {
            width: 100% !important;
        }
        .main .block-container {
            padding-left: 1rem !important;
            padding-right: 1rem !important;
        }
    </style>
""", unsafe_allow_html=True)

def can_draft(manager, row, round_num):
    pos = row["Position"]
    roster = st.session_state.rosters.get(manager, {"QB":0, "RB":0, "WR":0, "TE":0})
    if not pos or not isinstance(pos, str):
        return False
    if pos == "TE" and roster["TE"] >= 2:
        return False
    if pos == "QB" and roster["QB"] >= 5:
        return False
    if pos == "RB" and roster["RB"] >= 5:
        return False
    if pos == "WR" and roster["WR"] >= 5:
        return False
    if round_num == 1 and pos == "TE":
        return False
    return True

# --- Session State Initialization ---
if "auto_drafting" not in st.session_state:
    st.session_state.auto_drafting = False
if "draft_started" not in st.session_state:
    st.session_state.draft_started = False
if "your_team" not in st.session_state:
    st.session_state.your_team = None
if "sim_step" not in st.session_state:
    st.session_state.sim_step = 0
if "current_pick_idx" not in st.session_state:
    st.session_state.current_pick_idx = 0
if "pick_number" not in st.session_state:
    st.session_state.pick_number = 0
if "drafted" not in st.session_state:
    st.session_state.drafted = set()
if "draft_results" not in st.session_state:
    st.session_state.draft_results = []
if "rosters" not in st.session_state:
    st.session_state.rosters = {}
if "mgr_type_counts" not in st.session_state:
    st.session_state.mgr_type_counts = {}
if "available_pool" not in st.session_state:
    st.session_state.available_pool = None
if "manager_drafted_players" not in st.session_state:
    st.session_state.manager_drafted_players = {}

# --- Sidebar: Draft Speed Slider ---
st.sidebar.header("Draft Settings")
draft_speed = st.sidebar.slider(
    "Auto-draft speed (seconds per pick)",
    min_value=0.1,
    max_value=2.0,
    value=0.5,
    step=0.1,
    help="How long to wait between each auto-drafted pick (lower = faster)"
)

def get_selected_row(grid_response):
    selected_rows = grid_response.get('selected_rows', [])
    return selected_rows[0] if isinstance(selected_rows, list) and len(selected_rows) > 0 else None

#-------- CONFIGURATION ---------
DRAFT_ORDER_FILE = "2025 DRAFT ORDER.csv"
ADP_FILE = "2025 ADP DATA.csv"
FRESHMAN_FILE = "2025 247 FRESHMAN RANK.csv"
PROFILES_FILE = "manager_profiles_advanced.json"

CONSENSUS_ELITE_ORDER = [
    "BRYCE UNDERWOOD", "DAKORIEN MOORE", "KEELON RUSSELL"
]
CONSENSUS_TOP3 = ["BRYCE UNDERWOOD", "DAKORIEN MOORE", "KEELON RUSSELL"]
CONSENSUS_ELITE_SET = set(CONSENSUS_ELITE_ORDER + [
    "TAVIEN ST. CLAIR", "WAYMOND JORDAN", "HARLEM BERRY",
    "KALIQ LOCKETT", "JEROME MYLES", "QUINCY PORTER", "VERNELL BROWN III", "ELYISS WILLIAMS", "TALYN TAYLOR"
])
UPSIDE_ELIGIBLE_COLLEGES = {
    "ALABAMA", "OHIO STATE", "LSU", "GEORGIA", "USC", "OKLAHOMA", "TEXAS", "FLORIDA",
    "MICHIGAN", "OREGON", "FLORIDA STATE", "WASHINGTON", "NOTRE DAME", "TENNESSEE",
    "TEXAS A&M", "OLE MISS", "MIAMI (FL)", "PENN STATE", "SOUTH CAROLINA", "ILLINOIS",
    "MISSOURI", "COLORADO", "IOWA", "ARIZONA STATE", "IOWA STATE"
}
RTC_ELIGIBLE_COLLEGES = {
    "UMASS", "NEW MEXICO", "AKRON", "FIU", "BOWLING GREEN", "KENT STATE", "BALL STATE",
    "EASTERN MICHIGAN", "BUFFALO", "NORTHERN ILLINOIS", "OLD DOMINION", "TEXAS STATE",
    "SOUTH ALABAMA", "UTEP", "LOUISIANA-MONROE", "CHARLOTTE", "NEVADA", "GEORGIA SOUTHERN",
    "SOUTHERN MISS", "ARKANSAS STATE", "SAN JOSE STATE", "HAWAII", "LOUISIANA TECH",
    "MIDDLE TENNESSEE", "WESTERN MICHIGAN", "CENTRAL MICHIGAN", "RICE", "NAVY", "ARMY",
    "AIR FORCE", "COASTAL CAROLINA", "GEORGIA STATE", "TROY", "UTSA",
    "NORTH TEXAS", "APPALACHIAN STATE", "TEMPLE", "EAST CAROLINA", "TULSA",
    "FLORIDA ATLANTIC", "LIBERTY", "SOUTH FLORIDA", "WYOMING", "UNLV",
    "UTAH STATE", "BOISE STATE", "FRESNO STATE", "SAN DIEGO STATE", "COLORADO STATE",
    "WESTERN KENTUCKY", "MARSHALL", "CONNECTICUT"
}

def normalize_name(name):
    if not isinstance(name, str):
        return ""
    name = name.upper()
    name = ''.join(c for c in unicodedata.normalize('NFD', name) if unicodedata.category(c) != 'Mn')
    name = re.sub(r'\b(JR|SR|II|III|IV|V)\b', '', name)
    name = re.sub(r'[^A-Z0-9 ]', '', name)
    name = re.sub(r'\s+', ' ', name)
    return name.strip()

def normalize_college(col):
    if not isinstance(col, str):
        return ""
    col = col.strip().upper().replace("'", "")
    col = col.replace("MIAMI FL", "MIAMI (FL)").replace("TEXAS AM", "TEXAS A&M")
    col = col.replace("OKST", "OKLAHOMA STATE").replace("OREG", "OREGON")
    col = col.replace("OREST", "OREGON STATE").replace("SOAL", "SOUTH ALABAMA")
    col = col.replace("FRES", "FRESNO STATE").replace("GA ST", "GEORGIA STATE")
    return col

def safe_float(x):
    try:
        return float(x)
    except Exception:
        return None

def ensure_columns(df, cols):
    for col in cols:
        if col not in df.columns:
            df.loc[:, col] = None
    return df

def is_5star_freshman(row):
    try:
        if row["PickType"] == "Freshman":
            return (pd.to_numeric(row.get("Stars"), errors="coerce") or 0) >= 5.0 or (pd.to_numeric(row.get("Rating"), errors="coerce") or 0) >= 0.99
        return False
    except Exception:
        return False

def is_consensus_elite(player_name):
    return normalize_name(player_name) in CONSENSUS_ELITE_SET

def eligible_for_upside(row):
    return normalize_college(row["College"]) in UPSIDE_ELIGIBLE_COLLEGES

def eligible_for_rtc(row):
    return normalize_college(row["College"]) in RTC_ELIGIBLE_COLLEGES

def is_5star_skipper(profile):
    leaks = profile.get("freshman_value_leaks", [])
    return len(leaks) > 0

def get_manager_profile(manager):
    print(f"\nDEBUG: get_manager_profile() called for manager: '{manager}'")
    profile = manager_profiles.get(manager, {})
    print(f"DEBUG: Loaded profile for manager: {profile}")
    simprof = profile.get("simulation_profile", {})
    pick_type_weights = simprof.get("pick_type_weights", {"Freshman": 1, "Ready to Contribute": 1, "Upside": 1})
    pos_weights = simprof.get("position_weights", {"QB": 1, "RB": 1, "WR": 1, "TE": 1})
    college_weights = simprof.get("college_weights", {})
    picktype_by_year = profile.get("picktype_by_year", {})
    print(f"DEBUG: pick_type_weights: {pick_type_weights}")
    print(f"DEBUG: pos_weights: {pos_weights}")
    print(f"DEBUG: college_weights: {college_weights}")
    print(f"DEBUG: picktype_by_year: {picktype_by_year}")

    quota_fresh = int(picktype_by_year.get("2024", {}).get("Freshman", 0))
    quota_upside = int(picktype_by_year.get("2024", {}).get("Upside", 0))
    quota_rtc = int(picktype_by_year.get("2024", {}).get("Ready to Contribute", 0))
    print(f"DEBUG: Quotas for manager {manager} in 2024 - Freshman: {quota_fresh}, Upside: {quota_upside}, RTC: {quota_rtc}")

    if "rtc_with_5star_available" in profile and profile["rtc_with_5star_available"]:
        rtc_lock = int(float(profile["rtc_with_5star_available"][0].get("round", 99)))
    else:
        rtc_lock = 99
    print(f"DEBUG: rtc_lock: {rtc_lock}")

    profile_type = "mixed"
    if pick_type_weights.get("Freshman", 0) > 7:
        profile_type = "heavy_freshman"
    elif pick_type_weights.get("Upside", 0) > 7:
        profile_type = "upside"
    elif pick_type_weights.get("Ready to Contribute", 0) > 7:
        profile_type = "rtc"
    print(f"DEBUG: profile_type for manager {manager}: {profile_type}")

    print(f"DEBUG: get_manager_profile() returns: pick_type_weights={pick_type_weights}, pos_weights={pos_weights}, college_weights={college_weights}, quota_fresh={quota_fresh}, quota_upside={quota_upside}, quota_rtc={quota_rtc}, rtc_lock={rtc_lock}, profile_type={profile_type}\n")
    return pick_type_weights, pos_weights, college_weights, quota_fresh, quota_upside, quota_rtc, rtc_lock, profile, profile_type

def get_manager_drafted_list(manager):
    manager = str(manager).strip().upper()
    return st.session_state.manager_drafted_players.get(manager, [])

def should_exclude_position(profile, pos, drafted_so_far, round_num):
    pos_weights = profile.get("simulation_profile", {}).get("position_weights", {})
    num_so_far = sum([p['Position'] == pos for p in drafted_so_far])
    pos_bias = pos_weights.get(pos, 0)
    if pos == 'QB' and num_so_far >= 2 and round_num <= 5 and pos_bias < 3.5:
        return True
    if pos == 'WR' and num_so_far >= 3 and round_num <= 5 and pos_bias < 3.5:
        return True
    if pos == 'RB' and num_so_far >= 3 and round_num <= 5 and pos_bias < 3.5:
        return True
    return False

def get_years_sorted(draft_history, current_year):
    current_year_int = int(str(current_year).strip())
    years = []
    for y in draft_history.keys():
        try:
            y_int = int(str(y).strip())
        except (ValueError, TypeError):
            continue
        if y_int < current_year_int:
            years.append(y_int)
    years.sort(reverse=True)
    return [str(y) for y in years]

def get_last_position_pick(draft_history, round_num, position, current_year):
    years = get_years_sorted(draft_history, current_year)
    for year in years:
        pick = draft_history.get(year, {}).get(str(round_num))
        if pick and pick["Position"] == position:
            return year, pick["Player"]
    return None, None

def get_last_any_pick(draft_history, round_num, current_year):
    years = get_years_sorted(draft_history, current_year)
    for year in years:
        pick = draft_history.get(year, {}).get(str(round_num))
        if pick:
            return year, pick["Player"], pick["Position"]
    return None, None, None

def get_last_picktype_pick(draft_history, round_num, picktype, current_year):
    years = get_years_sorted(draft_history, current_year)
    for year in years:
        pick = draft_history.get(year, {}).get(str(round_num))
        if pick and pick["PickType"] == picktype:
            return year, pick["Player"]
    return None, None

def get_last_fivestar_freshman(draft_history, current_year):
    years = get_years_sorted(draft_history, current_year)
    for year in years:
        for rnd, pick in draft_history.get(year, {}).items():
            if pick.get("PickType") == "Freshman" and (str(pick.get("Stars", "")) == "5.0" or float(pick.get("Rating", 0)) >= 0.99):
                return year, pick["Player"]
    return None, None

def get_consecutive_position_streak(draft_history, round_num, position, current_year, max_window=3):
    years = get_years_sorted(draft_history, current_year)
    streak = []
    for year in years:
        pick = draft_history.get(year, {}).get(str(round_num))
        if pick and pick["Position"] == position:
            streak.append((year, pick["Player"]))
        else:
            break
        if len(streak) >= max_window:
            break
    return streak

def get_round_reference(profile, round_num, current_year, current_position, current_picktype, current_stars=None, max_window=3):
    draft_history = profile.get("draft_history", {})
    streak = get_consecutive_position_streak(
        draft_history, round_num, current_position, current_year, max_window
    )
    if streak and len(streak) > 1:
        ordinal = {2: "second", 3: "third", 4: "fourth", 5: "fifth"}
        ord_word = ordinal.get(len(streak) + 1, f"{len(streak)+1}th")
        names_and_years = [f"{p[1]} ({p[0]})" for p in streak]
        return (
            f" He takes a {current_position} in Round {round_num} for the {ord_word} straight year, "
            f"following {', '.join(names_and_years)}."
        )

    last_year, last_player = get_last_position_pick(
        draft_history, round_num, current_position, current_year
    )
    if last_year:
        try:
            last_year_int = int(str(last_year).strip())
            current_year_int = int(str(current_year).strip())
            if last_year_int == current_year_int - 1:
                return (
                    f" He takes a {current_position} in Round {round_num}, "
                    f"for the second straight year ({last_player} in {last_year_int})."
                )
        except (TypeError, ValueError):
            pass

        last_any_year, last_any_player, last_any_pos = get_last_any_pick(
            draft_history, round_num, current_year
        )
        if last_any_year and last_any_year != last_year:
            return (
                f" He takes a {current_position} in Round {round_num}, reverting to his {last_year} selection of {last_player}, "
                f"after last year's {last_any_pos} ({last_any_player}) pick."
            )
        else:
            return (
                f" He takes a {current_position} in Round {round_num}, "
                f"his first time since {last_year} ({last_player})."
            )

    last_any_year, last_any_player, last_any_pos = get_last_any_pick(
        draft_history, round_num, current_year
    )
    if last_any_year and last_any_pos and last_any_pos != current_position:
        return (
            f" He takes a {current_position} in Round {round_num}, "
            f"contrary to last year when he took a {last_any_pos} ({last_any_player})."
        )

    if current_picktype == "Freshman":
        last_year, last_player = get_last_picktype_pick(
            draft_history, round_num, "Freshman", current_year
        )
        if last_year:
            return (
                f" He takes a Freshman in Round {round_num}, just as he did in {last_year} ({last_player})."
            )
        if current_stars and float(current_stars) >= 5.0:
            last5_year, last5_player = get_last_fivestar_freshman(
                draft_history, current_year
            )
            if last5_year:
                return (
                    f" He takes a 5-star Freshman, as he did in {last5_year} with {last5_player}."
                )

    years = get_years_sorted(draft_history, current_year)
    if not years:
        return ""
    oldest = years[-1]
    return (
        f" This is his first {current_position} in Round {round_num} since {oldest}, or possibly ever."
    )

def format_adp_phrase(adp, round_num=None):
    if adp and adp != "" and not str(adp).lower() == "nan":
        return f"ADP {adp}"
    if round_num is not None:
        return f"his selection in round {round_num}"
    else:
        return "his draft capital"

# --- TEMPLATES ---

templates_freshman_heavy = [
    "True to form, {manager} leans on youth by selecting {player}, a {stars}-star freshman from {college} whose athletic spark suggests growth beyond his {adp_phrase}.",
    "Even without top-tier hype, {player} fits {manager}'s rookie‑first approach: a {stars}-star newcomer with impact potential for round {round}.",
    "{manager} doubles down on raw talent, grabbing {player}, a {stars}-star freshman whose upside could outpace expectations as the season unfolds.",
    "With the blue‑chip names gone, {manager} pivots to {player}, whose blend of athleticism and field vision outperforms his {adp_phrase}.",
    "Refusing to stray from a youth‑heavy strategy, {manager} takes {player}, a {stars}-star rookie whose projection promises long‑term ROI.",
    "It's a foundational pick for {manager}, who adds {player}, a high-motor, {stars}-star rookie whose developmental curve fits their long-term, freshman-focused strategy.",
    "No surprise here. {manager} continues to build through the draft, grabbing {player}, a toolsy {stars}-star whose potential is valued more than a veteran's floor.",
    "This is a classic {manager} move: ignore the safe bet and invest in raw talent. {player} from {college} is a prototypical project pick for them in round {round}.",
    "Following the selection of {past_pick}, {manager} doubles down on the youth movement, adding {player}, a {stars}-star freshman poised to be a future building block.",
    "Chalk it up. {manager} goes back to the well for another high-upside freshman, grabbing {player} and betting that his traits will translate faster than the market expects.",
    "While others fill immediate needs, {manager} invests in the future with {player}. His {stars}-star pedigree and raw skills make him an ideal fit for this roster's philosophy.",
    "{manager} sees something they like in the {college} pipeline, grabbing {player}. This pick screams developmental upside, a hallmark of their drafting style.",
    "The board fell perfectly for {manager} to snag {player}, a {stars}-star talent who might have a low floor but possesses a ceiling that aligns with a youth-first approach.",
]
templates_freshman_mixed = [
    "Balancing veterans and prospects, {manager} adds {player}, a {stars}-star freshman from {college} whose versatility pairs well with established pieces.",
    "In a hybrid maneuver, {manager} opts for {player}—a mid‑tier rookie whose growth potential won't break the bank.",
    "{player} isn't a household name, but for a balanced roster, {manager} sees his {stars}-star ceiling and {adp_phrase} as ideal filler.",
    "Seeking stability with a dash of upside, {manager} picks {player}, a freshman whose future role justifies the pick in round {round}.",
    "True to their mixed blueprint, {manager} secures {player}, a freshman with a solid base and room to grow—especially at {adp_phrase}.",
    "This is a portfolio pick for {manager}. {player} offers a dash of upside without forcing a full rebuild, complementing their hybrid roster construction.",
    "Seeking stability with a hint of upside, {manager} picks {player}, a {stars}-star freshman whose future role justifies the selection in round {round}.",
    "{player} isn't a headline-grabber, but for a balanced roster, {manager} sees his ceiling and reasonable {adp_phrase} as an ideal, low-risk investment.",
    "With their core set, {manager} takes a shot on {player}. The {stars}-star rookie provides valuable depth and a potential future starter without disrupting the team's win-now focus.",
    "This selection is all about measured upside. {manager} eschews older players to add {player}, a freshman whose long-term potential could pay dividends.",
    "{manager} hedges their bets with {player}, a promising {stars}-star from {college} who can develop behind veterans and potentially emerge as a key contributor down the line.",
]
templates_freshman_elite = [
    "When talent like {player}—a 5‑star from {college}—drops to the board, {manager} snaps him up, locking in franchise upside at {adp_phrase}.",
    "Elite recruits don't last: {manager} wastes no time drafting {player}, a 5‑star rookie primed for immediate impact.",
    "This is a can't‑miss pick: {player} offers size, skill, and college production, and {manager} seals the deal in round {round}.",
    "Consensus agrees on {player}'s ceiling—5‑star status and proven tape—so {manager} adds him without hesitation.",
    "Franchise upside is on the table, so {manager} grabs {player}, a 5‑star talent whose projection smokes his {adp_phrase}.",
    "When talent like {player}—a 5-star from {college}—is on the board, you take him. {manager} snaps up a potential franchise cornerstone, locking in elite upside at {adp_phrase}.",
    "This is a no-brainer. {manager} wastes no time drafting {player}, a 5-star rookie primed for immediate, game-changing impact from day one.",
    "Sometimes the pick makes itself. {player} was the best player available by a mile, and {manager} wisely secures a blue-chip talent to build around.",
    "Consensus agrees on {player}'s ceiling—5-star status and dominant tape—so {manager} adds him without hesitation, instantly upgrading their roster's potential.",
    "It's a gift at this spot in round {round}. {manager} lands {player}, a 5-star prospect from {college} who brings a rare combination of size, skill, and polish.",
    "This is how championships are built. {manager} grabs {player}, a transcendent 5-star talent whose projection smokes his {adp_phrase}.",
    "No need to overthink it. {player} is an elite, plug-and-play prospect, and {manager} makes the obvious, high-value choice to anchor their team for years to come.",
    "The league was put on notice with this pick. {manager} secures the most coveted prize on the board in {player}, a 5-star dynamo with league-winning potential.",
]
templates_upside = [
    "Swinging for the fences, {manager} pulls the trigger on {player}, a high‑variance prospect whose {adp_phrase} will look like a steal if he breaks out.",
    "Floor is secondary to ceiling here: {manager} bets on {player}'s raw tools to ignite big returns.",
    "With championship aspirations, {manager} reaches for {player}, banking on upside over safety.",
    "This pick screams upside: {player} brings explosive traits and high ceiling—perfect for a bold gamble.",
    "{manager} takes a coin‑flip chance on {player}, a boom‑or‑bust rookie who could redefine this draft.",
    "This pick is all about potential energy. {manager} bets on {player}'s raw, explosive tools, ignoring the low floor for a shot at a massive return.",
    "With championship aspirations, {manager} reaches for {player}, banking on game-breaking upside over a safer, lower-impact alternative.",
    "This is a classic lottery ticket. {manager} takes a coin-flip chance on {player}, a boom-or-bust prospect who could either redefine this team or be a total bust.",
    "Forget the safe play; {manager} is hunting for a league-winner. {player} has a questionable floor but possesses the kind of ceiling that can single-handedly win a title.",
    "Some will call it a reach, but {manager} sees superstar potential. They grab {player}, a raw but athletically gifted player they believe can be molded into a dominant force.",
    "This pick could define their season. {manager} bypasses several higher-floor players to gamble on the immense, unpolished upside of {player}.",
]
templates_rtc_profile = [
    "Staying on script, {manager} selects {player}, a dependable talent whose track record and {adp_phrase} align perfectly with round {round} norms.",
    "No surprises: {manager} locks in value with {player}, a balanced prospect meeting expectations for this stage.",
    "Right player, right round—{player} offers a safe floor and moderate upside, matching the pick's profile.",
    "By‑the‑book selection: {player} delivers consistency and fits {manager}'s plan for round {round}.",
    "{player} slots seamlessly into the roster, hitting the sweet spot of risk and reward that {manager} targets in this round.",
    "No surprises here. {manager} locks in solid value with {player}, a balanced prospect who meets all expectations for this stage of the draft.",
    "This is a bread-and-butter selection. {player} offers a safe floor and moderate upside, perfectly matching the pick's profile and {manager}'s steady approach.",
    "Right player, right price, right round. {manager} makes the logical choice in {player}, a player who slots seamlessly into the roster without unnecessary risk.",
    "By-the-book drafting from {manager}. {player} delivers consistency and fills a need, hitting the sweet spot of risk and reward they target in this round.",
    "After a risky pick like {past_pick}, {manager} smartly pivots to a high-floor player in {player}, bringing balance back to their draft.",
    "{player} is exactly the kind of solid, unspectacular value you look for here. {manager} continues a disciplined draft by taking the best available player who fits their system.",
]
templates_forced = [
    "With ideal targets gone, {manager} begrudgingly takes {player}, a fallback option that fills the need but clashes with their blueprint.",
    "Plan A evaporated, so {manager} scraps the board and swings on {player}, a second‑tier choice born of necessity.",
    "Out of better options, {manager} pivots to {player}, hoping this stopgap pick can overdeliver.",
    "Draft day chaos forces {manager} into {player}, an off‑scheme selection that serves as a temporary patch.",
    "Favorites off the board, {manager} settles for {player}, praying this unplanned choice pays off.",
    "With their primary targets gone, {manager} begrudgingly takes {player}, a fallback option that fills an immediate need but clashes with their preferred blueprint.",
    "Plan A clearly evaporated. {manager} is forced to scrap the board and swing on {player}, a second-tier choice born of draft-day necessity.",
    "You can feel the frustration. After being sniped on their preferred players, {manager} settles for {player}, hoping this stopgap pick can overdeliver.",
    "This feels like a panic move. Draft day chaos forces {manager} into selecting {player}, an off-scheme choice that serves as a temporary patch rather than a strategic fit.",
    "The board did not fall {manager}'s way. Out of better options, they pivot to {player}, a pick that feels more like a concession than a conviction.",
    "A clear departure from their strategy. With the players they coveted off the board, {manager} takes {player} in a move that screams \"making the best of a bad situation.\"",
    "{manager} was backed into a corner here and had to take {player}. It's a pick that prevents a total disaster at the position but strays far from their game plan.",
]
templates_rtc_outlier = [
    "Defying convention, {manager} pounces on {player} at pick {round}, leaping past {adp_phrase} to snatch high potential.",
    "Shock move: {manager} vaults for {player} rounds early, trading draft capital for breakout upside.",
    "In a bold twist, {manager} overpays for {player}, drafting him well ahead of market expectations.",
    "Ignoring the script, {manager} pulls the trigger on {player} early, convinced his ceiling warrants the risk.",
    "This pick breaks the mold: {manager} jumps the ADP and secures {player} in a surprise move that could shift the league.",
    "Defying convention, {manager} pounces on {player} at pick {round}, leaping past his {adp_phrase} to snatch a player they clearly believe in.",
    "This is a shocker! {manager} vaults for {player} rounds earlier than expected, signaling a massive conviction in his potential and ignoring market value.",
    "In a bold, head-turning twist, {manager} overpays for {player}, drafting him well ahead of his {adp_phrase}. This is a \"my guy\" pick, through and through.",
    "Tearing up the script! {manager} pulls the trigger on {player} now, convinced his ceiling warrants the aggressive reach and unwilling to risk him being taken later.",
    "This pick breaks the mold and could shift the league. {manager} jumps the ADP queue to secure {player}, sending a message that they see something others don't.",
    "Wow, what a reach! {manager} plants their flag on {player}, drafting him far ahead of consensus rankings. Time will tell if this was visionary or reckless.",
    "Ignoring all mock drafts and projections, {manager} aggressively targets and lands {player} in round {round}. This is a high-risk, high-conviction move that will be debated all season.",
]

def human_explain_pick(manager, row, round_num, profile_type, outlier=False, quota_exceeded=False, quotas=None, counts=None, rtc_lock=None, profile=None, current_year="2025"):
    player = row['Player']
    college = row['College']
    picktype = row['PickType']
    stars = row.get('Stars', '')
    rating = row.get('Rating', '')
    adp = row.get('ADP', '')
    adp_phrase = format_adp_phrase(adp, round_num)
    position = row['Position']
    past_ref = ""
    if profile is not None and round_num <= 3 and position in ["WR","RB","QB","TE"]:
        past_ref = get_round_reference(profile, round_num, current_year, position, picktype, current_stars=stars, max_window=3)
    template = None
    if outlier or (quota_exceeded and quotas and counts and picktype in quotas and counts.get(picktype,0) > quotas.get(picktype,99)):
        template = random.choice(templates_forced)
    elif picktype == "RTC" and rtc_lock and round_num < rtc_lock:
        template = random.choice(templates_rtc_outlier)
    elif picktype == "Freshman" and (is_consensus_elite(player) or (stars and float(stars) >= 5.0)):
        template = random.choice(templates_freshman_elite)
    elif picktype == "Freshman" and profile_type == "heavy_freshman":
        template = random.choice(templates_freshman_heavy)
    elif picktype == "Freshman":
        template = random.choice(templates_freshman_mixed)
    elif picktype == "Upside":
        template = random.choice(templates_upside)
    elif picktype == "RTC":
        template = random.choice(templates_rtc_profile)
    else:
        template = "{manager} made a pragmatic pick with {player}, adapting to how the draft was unfolding."
    explanation = template.format(
        manager=manager, player=player, stars=stars, college=college, adp_phrase=adp_phrase, round=round_num, rating=rating,
        past_pick=""
    )
    if past_ref:
        explanation = explanation.rstrip('.') + "." + past_ref
    return explanation

def draft_pick(
    manager,
    available,
    round_num,
    already_drafted,
    pick_number,
    quotas,
    rtc_lock,
    picktype_weights,
    counts,
    profile_type,
    profile,
    current_year="2025"
):
    picktype_weights, pos_weights, college_weights, _, _, _, _, _, _ = get_manager_profile(manager)
    avail = available.copy()
    if avail.empty:
        return None, "No eligible player found."

    # Score formula: manager profile-based, rating/star dominant, now with ADP factor
    avail["stars_num"]    = pd.to_numeric(avail["Stars"], errors="coerce").fillna(0)
    avail["rating_num"]   = pd.to_numeric(avail["Rating"], errors="coerce").fillna(0)
    avail["pos_bias"]     = avail["Position"].map(lambda pos: pos_weights.get(pos, 0))
    avail["college_bias"] = avail["NormCollege"].map(lambda col: college_weights.get(col, 0))
    avail["score"] = (
        avail["rating_num"] * 1.0 +
        avail["stars_num"] * 0.8 +
        avail["pos_bias"].fillna(0) * 0.08 +
        avail["college_bias"].fillna(0) * 0.008 +
        (-pd.to_numeric(avail["ADP"], errors="coerce").fillna(1000) * 0.03)
    )

    for picktype in ["Freshman", "Upside"]:
        if counts.get(picktype, 0) < quotas.get(picktype, 0):
            avail_type = avail[avail["PickType"] == picktype]
            if not avail_type.empty:
                if picktype == "Freshman" and not is_5star_skipper(profile):
                    forced = avail_type[avail_type.apply(is_5star_freshman, axis=1)]
                    if not forced.empty:
                        top_n = forced.sort_values("score", ascending=False).head(5)
                        pick_row = top_n.sample(n=1).iloc[0] if len(top_n) > 0 else forced.iloc[0]
                        expl = human_explain_pick(
                            manager, pick_row, round_num, profile_type, False, False,
                            quotas, counts, rtc_lock, profile, current_year=current_year
                        )
                        return pick_row, expl
                # Otherwise, random pick from top 5 scored Freshmen
                top_n = avail_type.sort_values("score", ascending=False).head(5)
                pick_row = top_n.sample(n=1).iloc[0] if len(top_n) > 0 else avail_type.iloc[0]
                expl = human_explain_pick(
                    manager, pick_row, round_num, profile_type, False, False,
                    quotas, counts, rtc_lock, profile, current_year=current_year
                )
                return pick_row, expl

    # Early rounds lock logic (manager profile-based, random from top 3)
    if round_num < rtc_lock:
        avail_fu = avail[avail["PickType"].isin(["Freshman", "Upside"])]
        if not avail_fu.empty:
            top_n = avail_fu.sort_values("score", ascending=False).head(5)
            pick_row = top_n.sample(n=1).iloc[0] if len(top_n) > 0 else avail_fu.iloc[0]
            expl = human_explain_pick(
                manager, pick_row, round_num, profile_type, outlier=True,
                quotas=quotas, counts=counts, rtc_lock=rtc_lock, profile=profile, current_year=current_year
            )
            return pick_row, expl
        avail_rtc = avail[avail["PickType"] == "RTC"]
        if not avail_rtc.empty:
            top_n = avail_rtc.sort_values("score", ascending=False).head(5)
            pick_row = top_n.sample(n=1).iloc[0] if len(top_n) > 0 else avail_rtc.iloc[0]
            expl = human_explain_pick(
                manager, pick_row, round_num, profile_type, outlier=True,
                quotas=quotas, counts=counts, rtc_lock=rtc_lock, profile=profile, current_year=current_year
            )
            return pick_row, expl

    # RTC quota logic
    if counts.get("RTC", 0) < quotas.get("RTC", 0):
        avail_rtc = avail[avail["PickType"] == "RTC"]
        if not avail_rtc.empty:
            top_n = avail_rtc.sort_values("score", ascending=False).head(5)
            pick_row = top_n.sample(n=1).iloc[0] if len(top_n) > 0 else avail_rtc.iloc[0]
            expl = human_explain_pick(
                manager, pick_row, round_num, profile_type, False, False,
                quotas, counts, rtc_lock, profile, current_year=current_year
            )
            return pick_row, expl

    # If manager still has no TE by round 6+, force Freshman TE if available
    if round_num >= 6 and not any([p["Position"] == "TE" for p in get_manager_drafted_list(manager)]):
        te_candidates = avail[(avail["PickType"]=="Freshman") & (avail["Position"]=="TE")].copy()
        if not te_candidates.empty:
            top_n = te_candidates.sort_values("score", ascending=False).head(5)
            pick_row = top_n.sample(n=1).iloc[0] if len(top_n) > 0 else te_candidates.iloc[0]
            expl = human_explain_pick(
                manager, pick_row, round_num, profile_type, True, False,
                quotas, counts, rtc_lock, profile, current_year=current_year
            )
            return pick_row, expl

    # Final fallback: random pick from top 3 overall scored
    top_n = avail.sort_values("score", ascending=False).head(5)
    pick_row = top_n.sample(n=1).iloc[0] if len(top_n) > 0 else avail.iloc[0]
    expl = human_explain_pick(
        manager, pick_row, round_num, profile_type, outlier=True,
        quotas=quotas, counts=counts, rtc_lock=rtc_lock, profile=profile, current_year=current_year
    )
    return pick_row, expl

# --- DATA PREP ---
@st.cache_data
def load_data():
    for file in [DRAFT_ORDER_FILE, ADP_FILE, FRESHMAN_FILE, PROFILES_FILE]:
        if not os.path.exists(file):
            st.error(f"Missing required file: {file}")
            st.stop()
    draft_order = pd.read_csv(DRAFT_ORDER_FILE, sep=";")
    draft_order["Manager"] = draft_order["Manager"].astype(str).apply(lambda m: str(m).strip().upper() if str(m).strip().upper() != "NAN" else "")
    adp = pd.read_csv(ADP_FILE, sep=";")
    adp["NormPlayer"] = adp["Player"].apply(normalize_name)
    adp["NormCollege"] = adp["College"].apply(normalize_college)
    adp["ADP"] = adp["ADP"].apply(safe_float)
    adp["PickType"] = "RTC"
    adp = ensure_columns(adp, ["Stars", "Rating"])
    adp_clean = adp.dropna(axis=1, how="all").copy()
    adp_clean = ensure_columns(adp_clean, ["Stars", "Rating"])
    freshman = pd.read_csv(FRESHMAN_FILE, sep=";", encoding="latin1")
    freshman["NormPlayer"] = freshman["Name"].apply(normalize_name)
    freshman["NormCollege"] = freshman["School"].apply(normalize_college)
    freshman = ensure_columns(freshman, ["ADP", "Stars", "Rating"])
    freshman["PickType"] = "Freshman"
    freshman_clean = freshman.dropna(axis=1, how="all").copy()
    freshman_clean = ensure_columns(freshman_clean, ["ADP", "Stars", "Rating"])
    freshman_clean = freshman_clean.rename(
        columns={"Name": "Player", "School": "College", "NormCollege": "NormCollege"}
    )
    required_cols = ["NormPlayer", "Player", "College", "NormCollege", "Position", "ADP", "Stars", "Rating", "PickType"]
    with open(PROFILES_FILE, encoding="utf-8") as f:
        global manager_profiles
        manager_profiles = json.load(f)
    manager_profiles = {str(k).strip().upper(): v for k, v in manager_profiles.items()}
    freshman_part = ensure_columns(freshman_clean, required_cols)[required_cols].dropna(axis=1, how="all")
    adp_part = ensure_columns(adp_clean, required_cols)[required_cols].dropna(axis=1, how="all")
    pool = pd.concat([freshman_part, adp_part], ignore_index=True)
    pool = pool.sort_values(["NormPlayer", "PickType"], ascending=[True, True])
    pool = pool.drop_duplicates("NormPlayer", keep="first").reset_index(drop=True)
    upside_idx = (pool["PickType"] == "RTC") & (pool["NormCollege"].isin(UPSIDE_ELIGIBLE_COLLEGES)) & (pd.to_numeric(pool["ADP"], errors="coerce").fillna(9999) > 45)
    pool.loc[upside_idx, "PickType"] = "Upside"
    return draft_order, pool, manager_profiles

def initialize_state(draft_order, pool):
    st.session_state.drafted = set()
    st.session_state.draft_results = []
    st.session_state.rosters = {}
    st.session_state.mgr_type_counts = {}
    st.session_state.current_pick_idx = 0
    st.session_state.available_pool = pool.copy()
    st.session_state.pick_number = 0
    st.session_state.sim_step = 0
    st.session_state.manager_drafted_players = {}

st.title("Draft Simulator: AI Logic Version")

draft_order, pool, manager_profiles = load_data()
draft_order["Overall Pick"] = range(1, len(draft_order) + 1)
manager_choices = sorted([k for k in manager_profiles.keys() if k in draft_order["Manager"].unique()])

# --- DRAFT CONTROLS ABOVE THE BOARD ---
st.markdown("### Simulation Controls")
sim_col1, sim_col2, sim_col3 = st.columns([1,1,1])
with sim_col1:
    step_button = st.button("Sim Next Pick ▶️", key="step_button")
with sim_col2:
    skip_button = st.button("Sim Until User Pick ⏩", key="skip_button")
with sim_col3:
    auto_button = st.button("Auto-Draft Until User Pick 🤖", key="auto_button")

# --- START DRAFT ---
if not st.session_state.draft_started:
    st.header("Welcome to the Draft Simulator!")
    st.session_state.your_team = st.selectbox("Choose your team to control:", manager_choices, index=0)
    st.session_state.your_team = normalize_name(st.session_state.your_team)
    if st.button("Start Draft"):
        initialize_state(draft_order, pool)
        st.session_state.draft_started = True
        st.session_state.sim_step = 0
        st.rerun()
    st.stop()
if "your_team" not in st.session_state:
    st.session_state.your_team = manager_choices[0]
if "sim_step" not in st.session_state:
    st.session_state.sim_step = 0

st.header("Draft Board")

if st.session_state.draft_started:
    # Auto-refresh to ensure AgGrid renders properly
    if 'grid_refresh_count' not in st.session_state:
        st.session_state.grid_refresh_count = 0
    
    if st.session_state.grid_refresh_count < 3:
        st.session_state.grid_refresh_count += 1
        time.sleep(0.1)  
        st.rerun()

# Use a wide main column for both the board and user pool
main_col, _ = st.columns([7, 1])

# Add this fix right after the AgGrid component in both parts of your code

# Replace the AgGrid section in your draft board with this:
with main_col:
    # --- Draft Board ---
    board_cols = ["Round", "Overall Pick", "Manager", "Player", "Position", "College", "PickType", "Stars", "Rating", "ADP", "Explanation"]
    df_board = pd.DataFrame(st.session_state.draft_results, columns=board_cols)
    df_board = df_board.iloc[::-1].reset_index(drop=True) if not df_board.empty else pd.DataFrame(columns=board_cols)
    for col in ["Stars", "Rating", "ADP"]:
        if col in df_board.columns:
            df_board[col] = pd.to_numeric(df_board[col], errors="coerce")
    
    # Show AgGrid for the draft board
    gb = GridOptionsBuilder.from_dataframe(df_board)
    gb.configure_selection('single', use_checkbox=True)
    gb.configure_default_column(filterable=True, sortable=True, resizable=True)
    gridOptions = gb.build()

    # Generate unique key based on actual draft results data
    draft_data_hash = generate_data_hash(st.session_state.draft_results)

    # Add this JavaScript to force proper rendering
    st.markdown("""
        <script>
        // Force AgGrid to resize after page load
        setTimeout(function() {
            window.dispatchEvent(new Event('resize'));
        }, 100);
        
        // Additional resize events with delays
        setTimeout(function() {
            window.dispatchEvent(new Event('resize'));
        }, 500);
        
        setTimeout(function() {
            window.dispatchEvent(new Event('resize'));
        }, 1000);
        </script>
    """, unsafe_allow_html=True)

    grid_response = AgGrid(
        df_board,
        gridOptions=gridOptions,
        update_mode=GridUpdateMode.SELECTION_CHANGED,
        allow_unsafe_jscode=False,
        fit_columns_on_grid_load=True,
        enable_enterprise_modules=False,
        reload_data=True,
        height=600,
        theme="streamlit",
        key=f"draft_board_{draft_data_hash}_{len(df_board)}",
        custom_css={
            "#gridToolBar": {"padding-bottom": "0px !important"},
            ".ag-root-wrapper": {"min-height": "600px !important", "height": "600px !important"},
            ".ag-center-cols-container": {"min-height": "500px !important"}
        }
    )
    
    # Force another resize after AgGrid renders
    st.markdown("""
        <script>
        setTimeout(function() {
            window.dispatchEvent(new Event('resize'));
            // Try to force AgGrid API resize if available
            if (window.agGridInstances) {
                Object.values(window.agGridInstances).forEach(function(gridApi) {
                    if (gridApi && gridApi.sizeColumnsToFit) {
                        gridApi.sizeColumnsToFit();
                    }
                });
            }
        }, 200);
        </script>
    """, unsafe_allow_html=True)
    
    if not df_board.empty:
        selected_pick = get_selected_row(grid_response)
        if selected_pick:
            st.subheader(f"Explanation for {selected_pick['Player']}:")
            st.text_area("Explanation", selected_pick['Explanation'], height=120)
    else:
        st.info("Draft results will appear here as the draft progresses.")

if st.session_state.current_pick_idx < len(draft_order):
    pick_row = draft_order.iloc[st.session_state.current_pick_idx]
    round_num = int(pick_row["Round"])
    manager = normalize_name(pick_row["Manager"])
    overall_pick = pick_row["Overall Pick"]

    if manager == "":
        st.session_state.draft_results.append({
            "Round": round_num,
            "Manager": "",
            "Overall Pick": overall_pick,
            "Player": "Pick Skipped",
            "Position": "",
            "College": "",
            "PickType": "",
            "Stars": "",
            "Rating": "",
            "ADP": "",
            "Explanation": "Skipped pick (comp/empty in draft order)."
        })
        st.session_state.current_pick_idx += 1
        st.session_state.pick_number += 1
        st.rerun()

    st.markdown(f"### On the clock: **{manager}** (Round {round_num})")

    # --- USER PICK ---
    if manager == st.session_state.your_team:
        st.session_state.auto_drafting = False
        
        with main_col:
            st.subheader("Your Player Pool")
            show_cols = ["Player", "Position", "College", "PickType", "Stars", "Rating", "ADP", "NormPlayer"]
            
            # User picks: show ALL undrafted players, NO can_draft filtering!
            available = pool[~pool["NormPlayer"].isin(st.session_state.drafted)].copy()
            
            for col in ["Stars", "Rating", "ADP"]:
                if col in available.columns:
                    available[col] = pd.to_numeric(available[col], errors="coerce")
            available = available.sort_values("ADP", ascending=True)
            
            gb_pool = GridOptionsBuilder.from_dataframe(available[show_cols])
            gb_pool.configure_selection('single', use_checkbox=True)
            gb_pool.configure_default_column(filterable=True, sortable=True, resizable=True)
            gb_pool.configure_column("NormPlayer", hide=True)
            gridOptions_pool = gb_pool.build()

            # Generate unique key based on available players and drafted set
            pool_data_hash = generate_data_hash(list(st.session_state.drafted))

            grid_response_pool = AgGrid(
                available[show_cols],
                gridOptions=gridOptions_pool,
                update_mode=GridUpdateMode.SELECTION_CHANGED,
                allow_unsafe_jscode=False,
                fit_columns_on_grid_load=True,
                enable_enterprise_modules=False,
                reload_data=True,
                height=400,
                theme="streamlit",
                key=f"player_pool_{pool_data_hash}_{len(available)}"
            )
            
            selected_row = get_selected_row(grid_response_pool)
            if selected_row:
                st.write(f"Selected: **{selected_row['Player']} ({selected_row['Position']})**")
            
            draft_button = st.button("Draft Selected Player", disabled=not selected_row)
            
            if draft_button and selected_row:
                st.session_state.drafted.add(selected_row["NormPlayer"])
                # update_roster for user
                pos = selected_row["Position"]
                if manager not in st.session_state.rosters:
                    st.session_state.rosters[manager] = {"QB":0, "RB":0, "WR":0, "TE":0}
                if pos in st.session_state.rosters[manager]:
                    st.session_state.rosters[manager][pos] += 1
                if manager not in st.session_state.mgr_type_counts:
                    st.session_state.mgr_type_counts[manager] = {"Freshman": 0, "RTC": 0, "Upside": 0}
                ptype = selected_row["PickType"]
                if ptype not in st.session_state.mgr_type_counts[manager]:
                    st.session_state.mgr_type_counts[manager][ptype] = 0
                st.session_state.mgr_type_counts[manager][ptype] += 1
                # for manager_drafted_players
                if manager not in st.session_state.manager_drafted_players:
                    st.session_state.manager_drafted_players[manager] = []
                st.session_state.manager_drafted_players[manager].append({
                    "Player": selected_row["Player"],
                    "Position": selected_row["Position"],
                    "NormPlayer": selected_row["NormPlayer"],
                    "College": selected_row["College"],
                    "PickType": selected_row.get("PickType", ""),
                    "Stars": selected_row.get("Stars", ""),
                    "Rating": selected_row.get("Rating", ""),
                    "ADP": selected_row.get("ADP", "")
                })
                st.session_state.draft_results.append({
                    "Round": round_num,
                    "Manager": manager,
                    "Overall Pick": overall_pick,
                    "Player": selected_row["Player"],
                    "Position": selected_row["Position"],
                    "College": selected_row["College"],
                    "PickType": selected_row["PickType"],
                    "Stars": selected_row.get("Stars", ""),
                    "Rating": selected_row.get("Rating", ""),
                    "ADP": selected_row.get("ADP", ""),
                    "Explanation": "Manual pick."
                })
                st.session_state.current_pick_idx += 1
                st.session_state.pick_number += 1
                st.rerun()
            
            st.info("Select a player row and click 'Draft Selected Player'.")

    # --- CPU PICKS: use simulation script logic ---
    else:
        def simulate_next_pick(idx):
            pick_row = draft_order.iloc[idx]
            round_num = int(pick_row["Round"])
            manager = normalize_name(pick_row["Manager"])
            overall_pick = pick_row["Overall Pick"]
            if manager == "":
                st.session_state.draft_results.append({
                    "Round": round_num,
                    "Manager": "",
                    "Overall Pick": overall_pick,
                    "Player": "Pick Skipped",
                    "Position": "",
                    "College": "",
                    "PickType": "",
                    "Stars": "",
                    "Rating": "",
                    "ADP": "",
                    "Explanation": "Skipped pick (comp/empty in draft order)."
                })
                return True
            available = pool[~pool["NormPlayer"].isin(st.session_state.drafted)].copy()
            available = available[[can_draft(manager, row, round_num) for _, row in available.iterrows()]]
            # Force Top 100 ADP for LA CHOSIA NCAA MTF at Round 1, Pick 5
            if manager == "LA CHOSIA NCAA MTF" and round_num == 1 and idx == 4:
                available = available[pd.to_numeric(available["ADP"], errors="coerce") <= 100]
                available = available[available["ADP"].notnull()]
            # Consensus Top 3 picks logic
            if round_num == 1 and idx < 3:
                remaining_top3 = [p for p in CONSENSUS_TOP3 if normalize_name(p) in available["NormPlayer"].tolist()]
                if remaining_top3:
                    avail_top3 = available[available["NormPlayer"].isin([normalize_name(p) for p in remaining_top3])]
                    avail_top3 = avail_top3.copy()
                    pt_weights, pos_weights, col_weights, quota_fresh, quota_upside, quota_rtc, rtc_lock, profile, profile_type = get_manager_profile(manager)
                    avail_top3.loc[:, "pos_bias"] = avail_top3["Position"].map(lambda pos: pos_weights.get(pos, 0))
                    avail_top3.loc[:, "college_bias"] = avail_top3["NormCollege"].map(lambda col: col_weights.get(col, 0))
                    avail_top3.loc[:, "score"] = avail_top3["pos_bias"].fillna(0) * 0.08 + avail_top3["college_bias"].fillna(0) * 0.008 + \
                        pd.to_numeric(avail_top3["Rating"], errors="coerce").fillna(0) * 1.0 + \
                        pd.to_numeric(avail_top3["Stars"], errors="coerce").fillna(0) * 0.8
                    top_n = avail_top3.sort_values("score", ascending=False).head(5)
                    pick_row_out = top_n.sample(n=1).iloc[0] if len(top_n) > 0 else avail_top3.iloc[0]
                    st.session_state.drafted.add(pick_row_out["NormPlayer"])
                    # update_roster for CPU
                    pos = pick_row_out["Position"]
                    if manager not in st.session_state.rosters:
                        st.session_state.rosters[manager] = {"QB":0, "RB":0, "WR":0, "TE":0}
                    if pos in st.session_state.rosters[manager]:
                        st.session_state.rosters[manager][pos] += 1
                    if manager not in st.session_state.mgr_type_counts:
                        st.session_state.mgr_type_counts[manager] = {"Freshman": 0, "RTC": 0, "Upside": 0}
                    ptype = pick_row_out["PickType"]
                    if ptype not in st.session_state.mgr_type_counts[manager]:
                        st.session_state.mgr_type_counts[manager][ptype] = 0
                    st.session_state.mgr_type_counts[manager][ptype] += 1
                    # for manager_drafted_players
                    if manager not in st.session_state.manager_drafted_players:
                        st.session_state.manager_drafted_players[manager] = []
                    st.session_state.manager_drafted_players[manager].append({
                        "Player": pick_row_out["Player"],
                        "Position": pick_row_out["Position"],
                        "NormPlayer": pick_row_out["NormPlayer"],
                        "College": pick_row_out["College"],
                        "PickType": pick_row_out.get("PickType", ""),
                        "Stars": pick_row_out.get("Stars", ""),
                        "Rating": pick_row_out.get("Rating", ""),
                        "ADP": pick_row_out.get("ADP", "")
                    })
                    expl = human_explain_pick(
                        manager, pick_row_out, round_num, profile_type, False, False,
                        {"Freshman": 0, "Upside": 0, "RTC": 0},
                        {"Freshman": 0, "Upside": 0, "RTC": 0},
                        99, profile, "2025"
                    )
                    st.session_state.draft_results.append({
                        "Round": round_num,
                        "Manager": manager,
                        "Overall Pick": overall_pick,
                        "Player": pick_row_out["Player"],
                        "Position": pick_row_out["Position"],
                        "College": pick_row_out["College"],
                        "PickType": pick_row_out["PickType"],
                        "Stars": pick_row_out.get("Stars", ""),
                        "Rating": pick_row_out.get("Rating", ""),
                        "ADP": pick_row_out.get("ADP", ""),
                        "Explanation": expl
                    })
                    return True
            if available.empty:
                st.session_state.draft_results.append({
                    "Round": round_num, "Manager": manager, "Overall Pick": overall_pick,
                    "Player": "No eligible players left", "Position": "", "College": "",
                    "PickType": "", "Stars": "", "Rating": "", "ADP": "", "Explanation": "No eligible players"
                })
                return True
            pt_weights, pos_weights, col_weights, quota_fresh, quota_upside, quota_rtc, rtc_lock, profile, profile_type = get_manager_profile(manager)
            quotas = {"Freshman": quota_fresh, "Upside": quota_upside, "RTC": quota_rtc}
            counts = st.session_state.mgr_type_counts.get(manager, {"Freshman": 0, "RTC": 0, "Upside": 0})
            for t in ["Freshman", "RTC", "Upside"]:
                if t not in counts:
                    counts[t] = 0
            # Position exclusions
            for pos in ['QB', 'WR', 'RB']:
                if should_exclude_position(profile, pos, get_manager_drafted_list(manager), round_num):
                    available = available[available['Position'] != pos]
            pick_row_out, expl = draft_pick(manager, available, round_num,
                st.session_state.drafted, st.session_state.pick_number, quotas, rtc_lock, pt_weights, counts, profile_type, profile)
            if pick_row_out is None:
                st.session_state.draft_results.append({
                    "Round": round_num, "Manager": manager, "Overall Pick": overall_pick,
                    "Player": "No eligible players left", "Position": "", "College": "",
                    "PickType": "", "Stars": "", "Rating": "", "ADP": "", "Explanation": "No eligible players"
                })
                return True
            st.session_state.drafted.add(pick_row_out["NormPlayer"])
            # update_roster for CPU
            pos = pick_row_out["Position"]
            if manager not in st.session_state.rosters:
                st.session_state.rosters[manager] = {"QB":0, "RB":0, "WR":0, "TE":0}
            if pos in st.session_state.rosters[manager]:
                st.session_state.rosters[manager][pos] += 1
            if manager not in st.session_state.mgr_type_counts:
                st.session_state.mgr_type_counts[manager] = {"Freshman": 0, "RTC": 0, "Upside": 0}
            ptype = pick_row_out["PickType"]
            if ptype not in st.session_state.mgr_type_counts[manager]:
                st.session_state.mgr_type_counts[manager][ptype] = 0
            st.session_state.mgr_type_counts[manager][ptype] += 1
            # for manager_drafted_players
            if manager not in st.session_state.manager_drafted_players:
                st.session_state.manager_drafted_players[manager] = []
            st.session_state.manager_drafted_players[manager].append({
                "Player": pick_row_out["Player"],
                "Position": pick_row_out["Position"],
                "NormPlayer": pick_row_out["NormPlayer"],
                "College": pick_row_out["College"],
                "PickType": pick_row_out.get("PickType", ""),
                "Stars": pick_row_out.get("Stars", ""),
                "Rating": pick_row_out.get("Rating", ""),
                "ADP": pick_row_out.get("ADP", "")
            })
            st.session_state.draft_results.append({
                "Round": round_num,
                "Manager": manager,
                "Overall Pick": overall_pick,
                "Player": pick_row_out["Player"],
                "Position": pick_row_out["Position"],
                "College": pick_row_out["College"],
                "PickType": pick_row_out["PickType"],
                "Stars": pick_row_out.get("Stars", ""),
                "Rating": pick_row_out.get("Rating", ""),
                "ADP": pick_row_out.get("ADP", ""),
                "Explanation": expl
            })
            return True

        # Step Button
        if step_button:
            simulate_next_pick(st.session_state.current_pick_idx)
            st.session_state.current_pick_idx += 1
            st.session_state.pick_number += 1
            st.rerun()
        # Skip Button
        if skip_button:
            while st.session_state.current_pick_idx < len(draft_order):
                manager = normalize_name(draft_order.iloc[st.session_state.current_pick_idx]["Manager"])
                if manager == st.session_state.your_team:
                    break
                simulate_next_pick(st.session_state.current_pick_idx)
                st.session_state.current_pick_idx += 1
                st.session_state.pick_number += 1
            st.rerun()
        # Auto Button
        if auto_button:
            st.session_state.auto_drafting = True
        if st.session_state.auto_drafting:
            manager = normalize_name(draft_order.iloc[st.session_state.current_pick_idx]["Manager"])
            if manager == st.session_state.your_team:
                st.session_state.auto_drafting = False
            else:
                simulate_next_pick(st.session_state.current_pick_idx)
                st.session_state.current_pick_idx += 1
                st.session_state.pick_number += 1
                time.sleep(draft_speed)
                st.rerun()
        st.info("Use simulation controls above the board.")

if st.session_state.current_pick_idx >= len(draft_order):
    st.success("Draft complete!")
    if 'df_board' in locals() and not df_board.empty:
        st.download_button(
            label="Download draft results as CSV",
            data=df_board.to_csv(index=False),
            file_name="draft_results.csv",
            mime="text/csv"
        )
