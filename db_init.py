import sqlite3

conn = sqlite3.connect("league.db")
c = conn.cursor()

import os
print("INIT DB:", os.path.abspath("league.db"))

# --- Create tables ---
c.execute('''
CREATE TABLE IF NOT EXISTS players (
    player_id INTEGER PRIMARY KEY,
    name TEXT UNIQUE
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS games (
    game_id INTEGER PRIMARY KEY,
    name TEXT UNIQUE
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS matches (
    match_id INTEGER PRIMARY KEY,
    game_id INTEGER,
    date_played DATE,
    final_score TEXT
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS match_results (
    result_id INTEGER PRIMARY KEY,
    match_id INTEGER,
    player_id INTEGER,
    rank INTEGER,
    score REAL,
    global_elo_before REAL,
    global_elo_after REAL,
    game_elo_before REAL,
    game_elo_after REAL
)
''')

conn.commit()
conn.close()
print("Database initialized successfully.")
