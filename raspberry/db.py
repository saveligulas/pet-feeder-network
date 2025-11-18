import sqlite3
db = sqlite3.connect("pets.db")
db.execute("""
CREATE TABLE pets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    rfid_uid TEXT UNIQUE NOT NULL
)
""")
db.commit()
db.close()
