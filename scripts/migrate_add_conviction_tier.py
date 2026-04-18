import sqlite3, os

db = os.getenv("DATABASE_URL", "sqlite:///data/ten31thoughts.db").replace("sqlite:///", "")
conn = sqlite3.connect(db)
cur = conn.cursor()
cur.execute("PRAGMA table_info(notes)")
cols = [r[1] for r in cur.fetchall()]
if "conviction_tier" not in cols:
    cur.execute("ALTER TABLE notes ADD COLUMN conviction_tier TEXT")
    conn.commit()
    print("Added 'conviction_tier' column to notes table")
else:
    print("'conviction_tier' column already exists")
conn.close()
