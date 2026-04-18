import sqlite3, os

db = os.getenv("DATABASE_URL", "sqlite:///data/ten31thoughts.db").replace("sqlite:///", "")
conn = sqlite3.connect(db)
cur = conn.cursor()
cur.execute("PRAGMA table_info(digests)")
cols = [r[1] for r in cur.fetchall()]
if "opening" not in cols:
    cur.execute("ALTER TABLE digests ADD COLUMN opening TEXT")
    conn.commit()
    print("Added 'opening' column to digests table")
else:
    print("'opening' column already exists")
conn.close()
