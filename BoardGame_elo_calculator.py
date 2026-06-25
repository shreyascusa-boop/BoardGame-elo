import streamlit as st
import pandas as pd
import sqlite3
import datetime
import numpy as np
import plotly.graph_objects as go

from supabase import create_client

from elo_engine import (
    pairwise_elo_update,
    START_ELO,
    K_GLOBAL,
    K_GAME,
    PROVISIONAL_GAMES
)

# ---------------------------
# --- Streamlit Setup ------
# ---------------------------
st.set_page_config(page_title="Board Game Elo", layout="wide")

st.markdown("""
<style>
body { background-color: #121212; color: white; }
</style>
""", unsafe_allow_html=True)

# ---------------------------
# --- Database -------------
# ---------------------------
conn = sqlite3.connect("league.db", check_same_thread=False)
c = conn.cursor()


# ---------------------------
# --- Supabase -------------
# ---------------------------

SUPABASE_URL = "https://bolkvlryulxbdixkreil.supabase.co"

SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

try:

    test = (
        supabase
        .table("players")
        .select("*")
        .limit(1)
        .execute()
    )

    st.sidebar.success("Supabase Connected")

except Exception as e:

    st.sidebar.error(f"Supabase Error: {e}")


# ---------------------------
# --- Helper Functions -----
# ---------------------------

def get_players():

    result = (
        supabase
        .table("players")
        .select("name")
        .order("name")
        .execute()
    )

    return [
        row["name"]
        for row in result.data
    ]

def get_games():

    result = (
        supabase
        .table("games")
        .select("name")
        .order("name")
        .execute()
    )

    return [
        row["name"]
        for row in result.data
    ]

def fetch_match_data():

    players = (
        supabase
        .table("players")
        .select("*")
        .execute()
        .data
    )

    games = (
        supabase
        .table("games")
        .select("*")
        .execute()
        .data
    )

    matches = (
        supabase
        .table("matches")
        .select("*")
        .execute()
        .data
    )

    results = (
        supabase
        .table("match_results")
        .select("*")
        .execute()
        .data
    )

    players_df = pd.DataFrame(players)
    games_df = pd.DataFrame(games)
    matches_df = pd.DataFrame(matches)
    results_df = pd.DataFrame(results)

    df = (
        results_df
        .merge(matches_df, on="match_id")
        .merge(players_df, on="player_id")
        .merge(games_df, on="game_id")
    )

    df = df.rename(columns={
        "name_x": "player",
        "name_y": "game"
    })

    return df[
        [
            "result_id",
            "match_id",
            "game",
            "player",
            "rank",
            "date_played",
            "global_elo_after"
        ]
    ].sort_values("date_played")

# ---------------------------
# --- Recalculate Elo -------
# ---------------------------

def recalc_all_elo():
    df = fetch_match_data()

    if df.empty:
        return

    players = get_players()
    games = get_games()

    global_ratings = {p: START_ELO for p in players}
    game_ratings = {g: {p: START_ELO for p in players} for g in games}
    games_played = {p: 0 for p in players}
    provisional = {p: True for p in players}

    for match_id in df['match_id'].unique():
        match = df[df['match_id'] == match_id]
        game_name = match['game'].iloc[0]
        ranks = dict(zip(match['player'], match['rank']))

        g_before = global_ratings.copy()
        global_ratings = pairwise_elo_update(
            global_ratings, ranks, games_played, provisional, K_GLOBAL
        )

        game_before = game_ratings[game_name].copy()
        game_ratings[game_name] = pairwise_elo_update(
            game_ratings[game_name], ranks,
            {p:0 for p in players},   # no provisional protection for game elo
            {p:False for p in players},
            K_GAME
        )

        for player in ranks:

            result_id = int(
                match[
                    match['player'] == player
                ]['result_id'].iloc[0]
            )

            supabase.table("match_results")\
                .update({
                    "global_elo_before": float(g_before[player]),
                    "global_elo_after": float(global_ratings[player]),
                    "game_elo_before": float(game_before[player]),
                    "game_elo_after": float(
                        game_ratings[game_name][player]
                    )
                })\
                .eq("result_id", result_id)\
                .execute()

        for p in ranks:
            games_played[p] += 1
            if games_played[p] >= PROVISIONAL_GAMES:
                provisional[p] = False

if st.button("Force Recalculate"):
    recalc_all_elo()
    st.success("Recalculation Complete")

# ---------------------------
# --- Sidebar Menu ----------
# ---------------------------
menu = [
    "Home",
    "League Setup",
    "Add Match",
    "Edit Match/Match History",
    "Leaderboard",
    "Graphs",
    "Head-to-Head"
]
choice = st.sidebar.selectbox("Menu", menu)



# =========================================================
# ======================= Home ============================
# =========================================================


if choice == "Home":

    st.title("🎲 Board Game Elo Calculator")

    st.markdown("""
    Welcome to the Board Game Elo Tracker!

    This app tracks:
    - Global Elo ratings
    - Game-specific Elo ratings
    - Head-to-head statistics
    - Match history
    - Elo progression over time

    Built for multiplayer board game leagues with:
    - Provisional player protection
    - Pairwise multiplayer Elo
    - Experience weighting
    """)

    st.divider()

    # -----------------------------
    # Quick Stats
    # -----------------------------

    total_players = len(get_players())
    total_games = len(get_games())

    total_matches = c.execute(
        "SELECT COUNT(*) FROM matches"
    ).fetchone()[0]

    col1, col2, col3 = st.columns(3)

    col1.metric("Players", total_players)
    col2.metric("Games", total_games)
    col3.metric("Matches Played", total_matches)

    st.divider()

    # -----------------------------
    # Top Rated Players
    # -----------------------------

    st.subheader("🏆 Top Rated Players")

    top_players_query = """
    SELECT
        p.name,
        mr.global_elo_after AS Elo
    FROM match_results mr
    JOIN players p ON mr.player_id = p.player_id
    WHERE mr.result_id IN (
        SELECT MAX(result_id)
        FROM match_results
        GROUP BY player_id
    )
    ORDER BY mr.global_elo_after DESC
    LIMIT 6
    """

    top_players = pd.read_sql(top_players_query, conn)

    top_players["Elo"] = (
                top_players["Elo"]
                .round(0)
                .astype(int)
            )

    st.dataframe(
        top_players,
        hide_index=True,
        use_container_width=True
    )

    # -----------------------------
    # Most Played Games
    # -----------------------------

    st.subheader("🎲 Most Played Games")

    top_games_query = """
    SELECT g.name, COUNT(*) as times_played
    FROM matches m
    JOIN games g ON m.game_id = g.game_id
    GROUP BY g.name
    ORDER BY times_played DESC
    LIMIT 3
    """

    top_games = pd.read_sql(top_games_query, conn)

    st.dataframe(
        top_games,
        hide_index=True,
        use_container_width=True
    )

# =========================================================
# ================= LEAGUE SETUP ==========================
# =========================================================

elif choice == "League Setup":

    st.header("League Setup")

    col1, col2 = st.columns(2)

    # Add Player
    with col1:
        st.subheader("Add Player")
        new_player = st.text_input("Player Name")
        if st.button("Add Player"):
            if new_player:
                c.execute("INSERT OR IGNORE INTO players (name) VALUES (?)", (new_player,))
                conn.commit()
                st.success("Player added!")

        st.subheader("Current Players")
        st.write(get_players())

        st.markdown("---")
        st.subheader("✏️ Edit Player Name")

        players = get_players()

        if players:
 
            selected_player = st.selectbox(
                "Select Player",
                players,
                key="edit_player"
            )

            new_player_name = st.text_input(
                "New Name",
                value=selected_player,
                key="new_player_name"
            )

            if st.button("Update Player Name"):

                c.execute("""
                    UPDATE players
                    SET name = ?
                    WHERE name = ?
                """, (
                    new_player_name.strip(),
                    selected_player
                ))      

                conn.commit()

                st.success(
                    f"Updated {selected_player} → {new_player_name}"
                )

                st.rerun()

    # Add Game
    with col2:
        st.subheader("Add Game")
        new_game = st.text_input("Game Name")
        if st.button("Add Game"):
            if new_game:
                c.execute("INSERT OR IGNORE INTO games (name) VALUES (?)", (new_game,))
                conn.commit()
                st.success("Game added!")

        st.subheader("Current Games")
        st.write(get_games())

        st.markdown("---")
        st.subheader("🎲 Edit Game Name")

        games = get_games()

        if games:

            selected_game = st.selectbox(
                "Select Game",
                games,
                key="edit_game"
            )

            new_game_name = st.text_input(
                "New Game Name",
                value=selected_game,
                key="new_game_name"
            )

            if st.button("Update Game Name"):

                c.execute("""
                    UPDATE games
                    SET name = ?
                    WHERE name = ?
                """, (
                    new_game_name.strip(),
                    selected_game
                ))

                conn.commit()

                st.success(
                    f"Updated {selected_game} → {new_game_name}"
                )

                st.rerun()

# =========================================================
# ================= ADD MATCH =============================
# =========================================================

elif choice == "Add Match":

    st.header("Add Match")

    games = get_games()
    players = get_players()

    if not games or not players:
        st.warning("Please add players and games first in League Setup.")
        st.stop()

    game_name = st.selectbox("Select Game", games)
    selected_players = st.multiselect("Select Players", players)

    ranks = {}
    scores = {}

    for p in selected_players:
        ranks[p] = st.number_input(
            f"Rank for {p}",
            min_value=1,
            max_value=len(selected_players),
            step=1,
            key=f"rank_{p}"
        )
	
        scores[p] = st.number_input(
    	    f"Score for {p} (optional)",
            value=0.0,
            step=1.0,
            key=f"score_{p}"
        )

    date_played = st.date_input("Date", datetime.date.today())

    if st.button("Submit Match"):
        game_id = c.execute(
            "SELECT game_id FROM games WHERE name=?",
            (game_name,)
        ).fetchone()[0]

        c.execute(
            "INSERT INTO matches (game_id, date_played) VALUES (?,?)",
            (game_id, date_played)
        )
        match_id = c.lastrowid

        for p in selected_players:
            player_id = c.execute(
                "SELECT player_id FROM players WHERE name=?",
                (p,)
            ).fetchone()[0]

            c.execute("""
                INSERT INTO match_results
                (match_id, player_id, rank,score)
                VALUES (?,?,?,?)
            """, (match_id, player_id, ranks[p], scores[p]))

        conn.commit()
        recalc_all_elo()
        st.success("Match Added & Elo Recalculated!")

# =========================================================
# =============== EDIT MATCH/MATCH HISTORY ================
# =========================================================

elif choice == "Edit Match/Match History":

    st.header("📜 Match History")

    matches = pd.read_sql("""
        SELECT
            m.match_id,
            g.name AS game_name,
            m.date_played,
            COUNT(mr.player_id) AS players
        FROM matches m
        JOIN games g
            ON m.game_id = g.game_id
        LEFT JOIN match_results mr
            ON m.match_id = mr.match_id
        GROUP BY m.match_id
        ORDER BY m.date_played DESC,
                 m.match_id DESC
    """, conn)

    if matches.empty:
        st.info("No matches found.")
        st.stop()

    # -----------------------------------------------------
    # Match History List
    # -----------------------------------------------------

    for _, match in matches.iterrows():

        elo_preview = pd.read_sql("""
            SELECT
                p.name,
                ROUND(
                    mr.global_elo_after - mr.global_elo_before,
                    1
                ) AS elo_change
            FROM match_results mr
            JOIN players p
                ON mr.player_id = p.player_id
            WHERE mr.match_id = ?
            ORDER BY mr.rank
        """, conn, params=(int(match["match_id"]),))

        col1, col2 = st.columns([6, 1])

        with col1:

            st.markdown(
                f"""
                **🎲 {match['game_name']} | 📅 {match['date_played']} | 👥 {match['players']} P**
                """
            )

            preview_text = []

            for _, player in elo_preview.iterrows():

                change = player["elo_change"]

                if pd.isna(change):
                    continue

                first_name = player["name"].split()[0]

                if change >= 0:
                    preview_text.append(
                        f"<span style='color:lightgreen'>{first_name} ▲{change:.0f}</span>"
                    )
                else:
                    preview_text.append(
                        f"<span style='color:#ff6b6b'>{first_name} ▼{abs(change):.0f}</span>"
                    )
 
            st.markdown(
                "  |  ".join(preview_text),
                unsafe_allow_html=True
            )

        with col2:

            if st.button(
                "✏️",
                key=f"edit_match_{match['match_id']}"
            ):
                st.session_state["selected_match"] = int(
                    match["match_id"]
                )

        st.markdown("---")

    # -----------------------------------------------------
    # Match Editor
    # -----------------------------------------------------

    if "selected_match" in st.session_state:

        match_id = st.session_state["selected_match"]

        st.subheader(f"✏️ Editing Match #{match_id}")

        df = pd.read_sql("""
            SELECT
                mr.result_id,
                p.name,
                mr.rank,
                mr.score,
                mr.global_elo_before,
                mr.global_elo_after
            FROM match_results mr
            JOIN players p
                ON mr.player_id = p.player_id
            WHERE mr.match_id = ?
            ORDER BY mr.rank
        """, conn, params=(match_id,))

        if df.empty:
            st.warning("Match not found.")
            st.stop()

        df["elo_change"] = (
            df["global_elo_after"]
            - df["global_elo_before"]
        )

        current_date = c.execute("""
            SELECT date_played
            FROM matches
            WHERE match_id = ?
        """, (match_id,)).fetchone()[0]

        new_date = st.date_input(
            "Match Date",
            value=pd.to_datetime(current_date),
            key=f"date_{match_id}"
        )

        st.markdown("---")

        new_ranks = {}
        new_scores = {}

        for _, row in df.iterrows():

            col1, col2, col3 = st.columns([4, 1, 1])

            with col1:

                if pd.notna(row["elo_change"]):

                    if row["elo_change"] >= 0:
                        st.markdown(
                            f"**{row['name']}** 📈 +{row['elo_change']:.1f}"
                        )
                    else:
                        st.markdown(
                            f"**{row['name']}** 📉 {row['elo_change']:.1f}"
                        )

                else:
                    st.markdown(
                        f"**{row['name']}**"
                    )

            with col2:

                new_ranks[row["result_id"]] = st.number_input(
                    "Rank",
                    value=int(row["rank"]),
                    min_value=1,
                    max_value=len(df),
                    step=1,
                    key=f"rank_{match_id}_{row['result_id']}"
                )

            with col3:

                new_scores[row["result_id"]] = st.number_input(
                    "Score",
                    value=float(row["score"])
                    if pd.notna(row["score"])
                    else 0.0,
                    step=1.0,
                    key=f"score_{match_id}_{row['result_id']}"
                )

        st.markdown("---")

        if st.button(
            "💾 Save Changes",
            key=f"save_match_{match_id}"
        ):

            c.execute("""
                UPDATE matches
                SET date_played = ?
                WHERE match_id = ?
            """, (
                new_date,
                match_id
            ))

            for result_id in new_ranks:

                c.execute("""
                    UPDATE match_results
                    SET rank = ?,
                        score = ?
                    WHERE result_id = ?
                """, (
                    int(new_ranks[result_id]),
                    float(new_scores[result_id]),
                    int(result_id)
                ))

            conn.commit()

            recalc_all_elo()

            st.success(
                "Match Updated & Elo Recalculated!"
            )

            st.rerun()

        st.markdown("---")

        st.subheader("⚠️ Delete Match")

        confirm_delete = st.checkbox(
            "I understand this will permanently delete this match.",
            key=f"delete_confirm_{match_id}"
        )

        if st.button(
            "🗑 Delete Match",
            key=f"delete_match_{match_id}"
        ):

            if confirm_delete:

                c.execute(
                    "DELETE FROM match_results WHERE match_id=?",
                    (match_id,)
                )

                c.execute(
                    "DELETE FROM matches WHERE match_id=?",
                    (match_id,)
                )

                conn.commit()

                recalc_all_elo()

                del st.session_state["selected_match"]

                st.success(
                    "Match deleted successfully."
                )

                st.rerun()

            else:
                st.warning(
                    "Please confirm deletion first."
                )        
# =========================================================
# ================= LEADERBOARD ===========================
# =========================================================

elif choice == "Leaderboard":

    st.header("🏆 Leaderboard")

    leaderboard_query = """
    SELECT
        p.name,

        (
            SELECT global_elo_after
            FROM match_results mr2
            WHERE mr2.player_id = p.player_id
            ORDER BY mr2.result_id DESC
            LIMIT 1
        ) as current_elo,

        MAX(mr.global_elo_after) as peak_elo,

        COUNT(mr.result_id) as games_played

    FROM match_results mr
    JOIN players p
        ON mr.player_id = p.player_id

    GROUP BY p.player_id
    """

    df = pd.read_sql(leaderboard_query, conn)

    if df.empty:
        st.info("No matches played yet.")

    else:

        # Determine provisional status
        df["Status"] = np.where(
            df["games_played"] < PROVISIONAL_GAMES,
            "Provisional",
            "Permanent"
        )

        df["current_elo"] = (
            df["current_elo"]
            .round(0)
            .astype(int)
        )

        df["peak_elo"] = (
            df["peak_elo"]
            .round(0)
            .astype(int)
        )

        # Sort by CURRENT Elo
        df = df.sort_values(
            by="current_elo",
            ascending=False
        )

        # -------------------------
        # Permanent Players
        # -------------------------

        permanent_df = df[df["Status"] == "Permanent"].copy()

        if not permanent_df.empty:

            permanent_df.insert(
                0,
                "Rank",
                range(1, len(permanent_df)+1)
            )

            st.subheader("🏆 Official Rankings")

            st.dataframe(
                permanent_df[
                    [
                        "Rank",
                        "name",
                        "current_elo",
                        "peak_elo",
                        "games_played"
                    ]
                ],
                use_container_width=True,
                hide_index=True
            )

        # -------------------------
        # Provisional Players
        # -------------------------

        provisional_df = df[df["Status"] == "Provisional"].copy()

        if not provisional_df.empty:

            st.subheader("🟡 Provisional Players")

            st.caption(
                f"Players become ranked after {PROVISIONAL_GAMES} matches."
            )

            st.dataframe(
                provisional_df[
                    [
                        "name",
                        "current_elo",
                        "peak_elo",
                        "games_played"
                    ]
                ],
                use_container_width=True,
                hide_index=True
            )

    # =========================================================
    # ============ GAME SPECIFIC LEADERBOARD ==================
    # =========================================================
    
    st.markdown("---")
    
    st.subheader("🎲 Game Specific Elo")
    
    games = get_games()
    
    if games:
    
        selected_game = st.selectbox(
            "Select Game",
            games,
            key="game_specific_leaderboard"
        )
    
        game_df = pd.read_sql("""
            SELECT
                p.player_id,
                p.name,
    
                (
                    SELECT mr2.game_elo_after
                    FROM match_results mr2
                    JOIN matches m2
                        ON mr2.match_id = m2.match_id
                    JOIN games g2
                        ON m2.game_id = g2.game_id
                    WHERE mr2.player_id = p.player_id
                      AND g2.name = ?
                    ORDER BY mr2.result_id DESC
                    LIMIT 1
                ) AS current_game_elo,
    
                (
                    SELECT MAX(mr2.game_elo_after)
                    FROM match_results mr2
                    JOIN matches m2
                        ON mr2.match_id = m2.match_id
                    JOIN games g2
                        ON m2.game_id = g2.game_id
                    WHERE mr2.player_id = p.player_id
                      AND g2.name = ?
                ) AS peak_game_elo,
    
                (
                    SELECT COUNT(*)
                    FROM match_results mr3
                    JOIN matches m3
                        ON mr3.match_id = m3.match_id
                    JOIN games g3
                        ON m3.game_id = g3.game_id
                    WHERE mr3.player_id = p.player_id
                      AND g3.name = ?
                ) AS games_played
    
            FROM players p
        """, conn, params=(selected_game, selected_game,selected_game))
    
        # Remove players who have never played this game
        game_df = game_df[
            game_df["games_played"] > 0
        ].copy()
    
        if game_df.empty:
   
            st.info(
                f"No matches found for {selected_game}."
            )

        else:

            game_df["Status"] = np.where(
                game_df["games_played"] < PROVISIONAL_GAMES,
                "Provisional",
                "Permanent"
            )

            game_df["current_game_elo"] = (
                game_df["current_game_elo"]
                .round(0)
                .astype(int)
            )

            game_df["peak_game_elo"] = (
                game_df["peak_game_elo"]
                .round(0)
                .astype(int)
            )

            game_df = game_df.sort_values(
                by="current_game_elo",
                ascending=False
            )

            # -------------------------------------
            # Permanent Players
            # -------------------------------------

            permanent_game_df = game_df[
                game_df["Status"] == "Permanent"
            ].copy()

            if not permanent_game_df.empty:
    
                permanent_game_df.insert(
                    0,
                    "Rank",
                    range(
                        1,
                        len(permanent_game_df) + 1
                    )
                )

                st.markdown(
                    f"### 🏆 {selected_game} Rankings"
                )

                st.dataframe(
                    permanent_game_df[
                        [
                            "Rank",
                            "name",
                            "current_game_elo",
                            "peak_game_elo",
                            "games_played"
                        ]
                    ],
                    hide_index=True,
                    use_container_width=True
                )

            # -------------------------------------
            # Provisional Players
            # -------------------------------------

            provisional_game_df = game_df[
                game_df["Status"] == "Provisional"
            ].copy()

            if not provisional_game_df.empty:
   
                st.markdown(
                    f"### 🟡 {selected_game} Provisional"
                )

                st.dataframe(
                    provisional_game_df[
                        [
                            "name",
                            "current_game_elo",
                            "peak_game_elo",
                            "games_played"
                        ]
                    ],
                    hide_index=True,
                    use_container_width=True
                )
   

# =========================================================
# ================= GRAPHS ================================
# =========================================================

elif choice == "Graphs":

    st.header("📈 Elo Over Time")

    df = fetch_match_data()

    if df.empty:
        st.info("No data available.")
        st.stop()

    player = st.selectbox(
        "Select Player",
        sorted(df["player"].unique())
    )

    player_df = df[df["player"] == player].copy()

    player_df = player_df.sort_values(
        by="date_played"
    )

    player_df["Match Number"] = range(
        1,
        len(player_df) + 1
    )

    elo_min = player_df["global_elo_after"].min() - 20
    elo_max = player_df["global_elo_after"].max() + 20

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=player_df["Match Number"],
            y=player_df["global_elo_after"],
            mode="lines+markers",
            name="Global Elo"
        )
    )

    fig.update_layout(
        title=f"{player} Elo Progression",
        xaxis_title="Match Number",
        yaxis_title="Global Elo",
        yaxis=dict(
            range=[elo_min, elo_max]
        ),
        template="plotly_dark"
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )
# =========================================================
# ================= HEAD TO HEAD ==========================
# =========================================================

elif choice == "Head-to-Head":

    st.header("Head to Head Win %")

    df = fetch_match_data()
    players = df['player'].unique()

    matrix = pd.DataFrame(index=players, columns=players, data=0.0)

    for p1 in players:
        for p2 in players:
            if p1 == p2:
                continue

            matches = df[df['player'].isin([p1, p2])]['match_id'].value_counts()
            common = matches[matches == 2].index

            if len(common) == 0:
                continue

            wins = 0
            for m in common:
                ranks = df[df['match_id'] == m].set_index('player')['rank']
                if ranks[p1] < ranks[p2]:
                    wins += 1
                elif ranks[p1] == ranks[p2]:
                    wins += 0.5

            matrix.loc[p1, p2] = round(wins / len(common) * 100, 1)

    st.dataframe(matrix)
