import sqlite3
from werkzeug.security import generate_password_hash

def setup_db():
    conn = sqlite3.connect('queue.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS counters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    name TEXT, 
                    queue_length INTEGER
                )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    token_code TEXT, 
                    customer_name TEXT, 
                    counter_id INTEGER, 
                    status TEXT, 
                    created_at TEXT
                )''')

    # Drop old users table if it has an outdated schema, then recreate it cleanly
    c.execute("DROP TABLE IF EXISTS users")
    
    c.execute('''CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    name TEXT NOT NULL,
                    active INTEGER DEFAULT 1,
                    created_at TEXT
                )''')

    # Seed default staff account
    hashed_pw = generate_password_hash('Staff@123')
    c.execute('''INSERT INTO users (username, password_hash, role, name, active, created_at)
                 VALUES (?, ?, ?, ?, 1, datetime('now'))''',
              ('staff01', hashed_pw, 'STAFF', 'Default Staff Member'))
    print("Successfully created default staff account: staff01")

    conn.commit()
    conn.close()

if __name__ == '__main__':
    setup_db()