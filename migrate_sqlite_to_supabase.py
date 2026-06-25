import sqlite3
from supabase import create_client

# Replace with your values if needed
SUPABASE_URL = "https://rwhelqwagjkdllbzgtig.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJ3aGVscXdhZ2prZGxsYnpndGlnIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MTEwNzEwMywiZXhwIjoyMDk2NjgzMTAzfQ.j4h2G5bgdBxWuNM2CeZUC0I9exgo2I6c5ch_TCYBGX4"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

conn = sqlite3.connect("league.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

tables = ["players", "games", "matches", "match_results"]

for table in tables:
    rows = cur.execute(f"SELECT * FROM {table}").fetchall()

    if not rows:
        print(f"{table}: no rows")
        continue

    payload = [dict(r) for r in rows]

    # Upload in chunks
    chunk_size = 500
    for i in range(0, len(payload), chunk_size):
        chunk = payload[i:i+chunk_size]
        supabase.table(table).insert(chunk).execute()

    print(f"{table}: uploaded {len(payload)} rows")

print("Migration complete.")
