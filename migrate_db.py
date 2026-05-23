"""
Run this ONCE before starting app.py to update your database.
Command: python migrate_db.py
"""
import sqlite3, os

DB = 'database.db'
conn = sqlite3.connect(DB)

# New votes table for multi-election support
conn.execute('''CREATE TABLE IF NOT EXISTS votes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    voter_id     TEXT NOT NULL,
    election_id  INTEGER NOT NULL,
    candidate_id INTEGER NOT NULL,
    voted_for    TEXT NOT NULL,
    voted_at     TEXT NOT NULL,
    block_hash   TEXT,
    UNIQUE(voter_id, election_id)
)''')

# New columns
for sql in [
    "ALTER TABLE candidates ADD COLUMN election_id INTEGER DEFAULT 1",
    "ALTER TABLE candidates ADD COLUMN photo       TEXT    DEFAULT NULL",
    "ALTER TABLE election   ADD COLUMN created_at  TEXT    DEFAULT CURRENT_TIMESTAMP",
    "ALTER TABLE voters     ADD COLUMN is_blocked  INTEGER DEFAULT 0",
    "ALTER TABLE voters     ADD COLUMN aadhar      TEXT    DEFAULT NULL",
    "ALTER TABLE voters     ADD COLUMN dob         TEXT    DEFAULT NULL",
    "ALTER TABLE voters     ADD COLUMN age         INTEGER DEFAULT NULL",
    "ALTER TABLE voters     ADD COLUMN phone       TEXT    DEFAULT NULL",
    "ALTER TABLE election   ADD COLUMN start_time  TEXT    DEFAULT NULL",
    "ALTER TABLE election   ADD COLUMN end_time    TEXT    DEFAULT NULL",
]:
    try:
        conn.execute(sql)
        print(f"✅ {sql.split('ADD COLUMN')[1].strip().split()[0]}")
    except Exception as e:
        print(f"⏭  Already exists: {sql.split('ADD COLUMN')[1].strip().split()[0] if 'ADD COLUMN' in sql else sql[:40]}")

# Create uploads directory
os.makedirs(os.path.join('static', 'uploads', 'candidates'), exist_ok=True)
print('✅ uploads/candidates/ folder created')

conn.commit()
conn.close()
print('\n✅ Migration complete! Now run: python app.py')