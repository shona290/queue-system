import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'smartqueue_super_secret_production_key')

def init_db():
    try:
        conn = sqlite3.connect('queue.db', timeout=20)
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

        c.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        role TEXT NOT NULL,
                        name TEXT NOT NULL,
                        active INTEGER DEFAULT 1,
                        created_at TEXT
                    )''')

        c.execute("SELECT id FROM users WHERE username = ?", ('staff01',))
        if not c.fetchone():
            hashed_pw = generate_password_hash('Staff@123')
            c.execute('''INSERT INTO users (username, password_hash, role, name, active, created_at)
                         VALUES (?, ?, ?, ?, 1, datetime('now'))''',
                      ('staff01', hashed_pw, 'STAFF', 'Default Staff Member'))

        for d in ["Cash Deposit", "Account Opening", "Customer Inquiry"]:
            c.execute("SELECT id FROM counters WHERE name=?", (d,))
            if not c.fetchone():
                c.execute("INSERT INTO counters (name, queue_length) VALUES (?, 0)", (d,))

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Database Init Error: {e}")

init_db()

def get_db_connection():
    conn = sqlite3.connect('queue.db', timeout=20)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        try:
            name = request.form.get('customer_name', 'Guest')
            purpose = request.form.get('purpose', '').lower()
            
            if any(word in purpose for word in ['cash', 'deposit', 'withdraw', 'money', 'pay', 'cheque']):
                dept = "Cash Deposit"
            elif any(word in purpose for word in ['open', 'new', 'account', 'sign up']):
                dept = "Account Opening"
            else:
                dept = "Customer Inquiry"
                
            conn = get_db_connection()
            c = conn.cursor()

            c.execute("SELECT id FROM counters WHERE name=?", (dept,))
            counter = c.fetchone()
            
            if counter:
                counter_id = counter['id']
            else:
                c.execute("INSERT INTO counters (name, queue_length) VALUES (?, 0)", (dept,))
                conn.commit()
                c.execute("SELECT id FROM counters WHERE name=?", (dept,))
                counter_id = c.fetchone()['id']

            token_code = f"T-{counter_id}-{os.urandom(2).hex().upper()}"
            
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            c.execute("INSERT INTO tokens (token_code, customer_name, counter_id, status, created_at) VALUES (?, ?, ?, 'Waiting', ?)", (token_code, name, counter_id, now_str))
            c.execute("UPDATE counters SET queue_length = queue_length + 1 WHERE id=?", (counter_id,))
            
            c.execute("SELECT name, queue_length FROM counters ORDER BY queue_length ASC LIMIT 1")
            fastest = c.fetchone()
            
            conn.commit()
            conn.close()
            
            return render_template('token.html', token_code=token_code, dept=dept, name=name, fastest=fastest)
        except Exception as e:
            return f"Database Error during token creation: {e}", 500
        
    return render_template('index.html')

@app.route('/staff/login', methods=['GET', 'POST'])
def staff_login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            error = "Please fill in all fields."
            return render_template('login.html', error=error)
            
        try:
            conn = get_db_connection()
            user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            conn.close()
            
            if user and check_password_hash(user['password_hash'], password):
                if user['active'] != 1:
                    error = "This staff account is inactive."
                elif user['role'] not in ['STAFF', 'ADMIN']:
                    error = "Access denied."
                else:
                    session.clear()
                    session['user_id'] = user['id']
                    session['username'] = user['username']
                    session['role'] = user['role']
                    session['name'] = user['name']
                    return redirect(url_for('staff_console'))
            else:
                error = "Invalid username or password."
        except Exception as e:
            error = f"Login system error: {e}"
            
    return render_template('login.html', error=error)

@app.route('/staff')
def staff_console():
    if not session.get('user_id') or session.get('role') not in ['STAFF', 'ADMIN']:
        return redirect(url_for('staff_login'))

    try:
        conn = get_db_connection()
        raw_waiting = conn.execute("""
            SELECT t.id, t.token_code, t.customer_name, c.name, t.created_at
            FROM tokens t 
            JOIN counters c ON t.counter_id = c.id 
            WHERE t.status = 'Waiting'
            ORDER BY t.id ASC
        """).fetchall()
        conn.close()

        waiting = []
        now = datetime.now()
        for row in raw_waiting:
            wait_mins = 0
            if row['created_at']:
                try:
                    created_time = datetime.strptime(row['created_at'], '%Y-%m-%d %H:%M:%S')
                    wait_mins = int((now - created_time).total_seconds() / 60)
                except Exception:
                    wait_mins = 0
            waiting.append((row['id'], row['token_code'], row['customer_name'], row['name'], max(0, wait_mins)))

        return render_template('staff.html', waiting=waiting, staff_name=session.get('name'))
    except Exception as e:
        return f"Staff Console Error: {e}", 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/complete/<int:token_id>')
def complete_service(token_id):
    if not session.get('user_id') or session.get('role') not in ['STAFF', 'ADMIN']:
        return redirect(url_for('staff_login'))
    
    try:
        conn = get_db_connection()
        row = conn.execute("SELECT counter_id FROM tokens WHERE id=?", (token_id,)).fetchone()
        if row:
            conn.execute("UPDATE tokens SET status='Completed' WHERE id=?", (token_id,))
            conn.execute("UPDATE counters SET queue_length = MAX(0, queue_length - 1) WHERE id=?", (row['counter_id'],))
            conn.commit()
        conn.close()
    except Exception:
        pass
        
    return redirect(url_for('staff_console'))

@app.route('/track')
def track_queue():
    try:
        conn = get_db_connection()
        counters = conn.execute("SELECT name, queue_length FROM counters").fetchall()
        conn.close()
        return render_template('track.html', counters=counters)
    except Exception as e:
        return f"Tracking Error: {e}", 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)