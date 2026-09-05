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
        
        c.execute("DROP TABLE IF EXISTS tokens")
        c.execute("DROP TABLE IF EXISTS counters")
        c.execute("DROP TABLE IF EXISTS users")
        
        c.execute('''CREATE TABLE counters (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, 
                        name TEXT, 
                        queue_length INTEGER,
                        avg_service_time INTEGER DEFAULT 8
                    )''')
        
        c.execute('''CREATE TABLE tokens (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, 
                        token_code TEXT, 
                        customer_name TEXT, 
                        counter_id INTEGER, 
                        status TEXT, 
                        created_at TEXT
                    )''')

        c.execute('''CREATE TABLE users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        role TEXT NOT NULL,
                        name TEXT NOT NULL,
                        active INTEGER DEFAULT 1,
                        created_at TEXT
                    )''')

        hashed_pw = generate_password_hash('Staff@123')
        c.execute('''INSERT INTO users (username, password_hash, role, name, active, created_at)
                     VALUES (?, ?, ?, ?, 1, datetime('now'))''',
                  ('staff01', hashed_pw, 'STAFF', 'Default Staff Member'))
                  
        admin_pw = generate_password_hash('Admin@123')
        c.execute('''INSERT INTO users (username, password_hash, role, name, active, created_at)
                     VALUES (?, ?, ?, ?, 1, datetime('now'))''',
                  ('admin01', admin_pw, 'ADMIN', 'System Administrator'))

        counters_seed = [
            ("Cash Deposit", 0, 5),
            ("Account Opening", 0, 12),
            ("Customer Inquiry", 0, 7)
        ]
        for name, q_len, avg_time in counters_seed:
            c.execute("INSERT INTO counters (name, queue_length, avg_service_time) VALUES (?, ?, ?)", (name, q_len, avg_time))

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
    error = None
    if request.method == 'POST':
        try:
            name = request.form.get('customer_name', '').strip()
            purpose = request.form.get('purpose', '').lower()
            
            if not name:
                error = "Please enter your full name."
                return render_template('index.html', error=error)
                
            conn = get_db_connection()
            c = conn.cursor()

            existing = c.execute("SELECT token_code FROM tokens WHERE customer_name = ? AND status = 'Waiting'", (name,)).fetchone()
            if existing:
                conn.close()
                return render_template('index.html', error=f"You already have an active token: {existing['token_code']}")

            if any(word in purpose for word in ['cash', 'deposit', 'withdraw', 'money', 'pay', 'cheque']):
                dept = "Cash Deposit"
            elif any(word in purpose for word in ['open', 'new', 'account', 'sign up']):
                dept = "Account Opening"
            else:
                dept = "Customer Inquiry"

            counters_raw = c.execute("SELECT * FROM counters").fetchall()
            
            counters_evaluated = []
            target_counter_id = None
            
            for cnt in counters_raw:
                est_wait = cnt['queue_length'] * cnt['avg_service_time']
                is_target = (cnt['name'] == dept)
                if is_target:
                    target_counter_id = cnt['id']
                counters_evaluated.append({
                    'id': cnt['id'],
                    'name': cnt['name'],
                    'queue_length': cnt['queue_length'],
                    'avg_service_time': cnt['avg_service_time'],
                    'est_wait': est_wait,
                    'is_target': is_target
                })

            if not target_counter_id:
                target_counter_id = counters_evaluated[0]['id']

            recommended = min(counters_evaluated, key=lambda x: x['est_wait'])

            token_code = f"T-{target_counter_id}-{os.urandom(2).hex().upper()}"
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            c.execute("INSERT INTO tokens (token_code, customer_name, counter_id, status, created_at) VALUES (?, ?, ?, 'Waiting', ?)", (token_code, name, target_counter_id, now_str))
            c.execute("UPDATE counters SET queue_length = queue_length + 1 WHERE id=?", (target_counter_id,))
            
            conn.commit()
            conn.close()
            
            return render_template('token.html', 
                                   token_code=token_code, 
                                   dept=dept, 
                                   name=name, 
                                   recommended=recommended, 
                                   all_counters=counters_evaluated)
        except Exception as e:
            return f"Engine Error: {e}", 500
        
    return render_template('index.html', error=error)

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
                    error = "This account is inactive."
                elif user['role'] not in ['STAFF', 'ADMIN']:
                    error = "Access denied."
                else:
                    session.clear()
                    session['user_id'] = user['id']
                    session['username'] = user['username']
                    session['role'] = user['role']
                    session['name'] = user['name']
                    if user['role'] == 'ADMIN':
                        return redirect(url_for('admin_dashboard'))
                    return redirect(url_for('staff_console'))
            else:
                error = "Invalid username or password."
        except Exception as e:
            error = f"Login system error: {e}"
            
    return render_template('login.html', error=error)

@app.route('/staff')
def staff_console():
    if not session.get('user_id') or session.get('role') not in ('STAFF', 'ADMIN'):
        return redirect(url_for('staff_login'))

    try:
        conn = get_db_connection()
        waiting_tokens = conn.execute("""
            SELECT t.id, t.token_code, t.customer_name, c.name as counter_name, t.status, t.created_at
            FROM tokens t 
            JOIN counters c ON t.counter_id = c.id 
            WHERE t.status IN ('Waiting', 'Serving', 'On_Hold')
            ORDER BY t.id ASC
        """).fetchall()

        completed_count = conn.execute("SELECT COUNT(*) as cnt FROM tokens WHERE status = 'Completed'").fetchone()['cnt']
        conn.close()

        return render_template('staff.html', waiting=waiting_tokens, staff_name=session.get('name'), completed_count=completed_count)
    except Exception as e:
        return f"Staff Console Error: {e}", 500

@app.route('/admin')
def admin_dashboard():
    if not session.get('user_id') or session.get('role') != 'ADMIN':
        return redirect(url_for('staff_login'))

    try:
        conn = get_db_connection()
        counters = conn.execute("SELECT * FROM counters").fetchall()
        total_tokens = conn.execute("SELECT COUNT(*) as cnt FROM tokens").fetchone()['cnt']
        completed_tokens = conn.execute("SELECT COUNT(*) as cnt FROM tokens WHERE status='Completed'").fetchone()['cnt']
        active_users = conn.execute("SELECT * FROM users").fetchall()
        conn.close()

        return render_template('admin.html', counters=counters, total_tokens=total_tokens, completed_tokens=completed_tokens, users=active_users, admin_name=session.get('name'))
    except Exception as e:
        return f"Admin Dashboard Error: {e}", 500

@app.route('/staff/action/<action_type>/<int:token_id>')
def staff_action(action_type, token_id):
    if not session.get('user_id') or session.get('role') not in ('STAFF', 'ADMIN'):
        return redirect(url_for('staff_login'))
    
    try:
        conn = get_db_connection()
        token = conn.execute("SELECT * FROM tokens WHERE id=?", (token_id,)).fetchone()
        
        if token:
            if action_type == 'serve':
                conn.execute("UPDATE tokens SET status='Serving' WHERE id=?", (token_id,))
            elif action_type == 'complete':
                conn.execute("UPDATE tokens SET status='Completed' WHERE id=?", (token_id,))
                conn.execute("UPDATE counters SET queue_length = MAX(0, queue_length - 1) WHERE id=?", (token['counter_id'],))
            elif action_type == 'hold':
                conn.execute("UPDATE tokens SET status='On_Hold' WHERE id=?", (token_id,))
            elif action_type == 'skip':
                conn.execute("UPDATE tokens SET status='Skipped' WHERE id=?", (token_id,))
                conn.execute("UPDATE counters SET queue_length = MAX(0, queue_length - 1) WHERE id=?", (token['counter_id'],))
            conn.commit()
        conn.close()
    except Exception:
        pass
        
    if session.get('role') == 'ADMIN':
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('staff_console'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/track')
def track_queue():
    try:
        conn = get_db_connection()
        counters = conn.execute("SELECT name, queue_length, avg_service_time FROM counters").fetchall()
        conn.close()
        return render_template('track.html', counters=counters)
    except Exception as e:
        return f"Tracking Error: {e}", 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)