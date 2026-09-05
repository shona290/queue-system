import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'smartqueue_super_secret_production_key')

def get_db_connection():
    conn = sqlite3.connect('queue.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        name = request.form.get('customer_name')
        purpose = request.form.get('purpose', '').lower()
        
        if any(word in purpose for word in ['cash', 'deposit', 'withdraw', 'money', 'pay', 'cheque']):
            dept = "Cash Deposit"
        elif any(word in purpose for word in ['open', 'new', 'account', 'sign up']):
            dept = "Account Opening"
        else:
            dept = "Customer Inquiry"
            
        conn = get_db_connection()
        c = conn.cursor()
        
        for d in ["Cash Deposit", "Account Opening", "Customer Inquiry"]:
            c.execute("SELECT id FROM counters WHERE name=?", (d,))
            if not c.fetchone():
                c.execute("INSERT INTO counters (name, queue_length) VALUES (?, 0)", (d,))
                conn.commit()

        c.execute("SELECT id FROM counters WHERE name=?", (dept,))
        counter = c.fetchone()
        counter_id = counter['id']
        token_code = f"T-{counter_id}-{os.urandom(2).hex().upper()}"
        
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        c.execute("INSERT INTO tokens (token_code, customer_name, counter_id, status, created_at) VALUES (?, ?, ?, 'Waiting', ?)", (token_code, name, counter_id, now_str))
        c.execute("UPDATE counters SET queue_length = queue_length + 1 WHERE id=?", (counter_id,))
        
        c.execute("SELECT name, queue_length FROM counters ORDER BY queue_length ASC LIMIT 1")
        fastest = c.fetchone()
        
        conn.commit()
        conn.close()
        
        return render_template('token.html', token_code=token_code, dept=dept, name=name, fastest=fastest)
        
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
            
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            if user['active'] != 1:
                error = "This staff account is inactive. Contact your administrator."
            elif user['role'] not in ['STAFF', 'ADMIN']:
                error = "Access denied. Insufficient privileges."
            else:
                session.clear()
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = user['role']
                session['name'] = user['name']
                return redirect(url_for('staff_console'))
        else:
            error = "Invalid username or password."
            
    return render_template('login.html', error=error)

@app.route('/staff')
def staff_console():
    if not session.get('user_id') or session.get('role') not in ['STAFF', 'ADMIN']:
        return redirect(url_for('staff_login'))

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

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/complete/<int:token_id>')
def complete_service(token_id):
    if not session.get('user_id') or session.get('role') not in ['STAFF', 'ADMIN']:
        return redirect(url_for('staff_login'))
    
    conn = get_db_connection()
    row = conn.execute("SELECT counter_id FROM tokens WHERE id=?", (token_id,)).fetchone()
    if row:
        conn.execute("UPDATE tokens SET status='Completed' WHERE id=?", (token_id,))
        conn.execute("UPDATE counters SET queue_length = MAX(0, queue_length - 1) WHERE id=?", (row['counter_id'],))
        conn.commit()
    conn.close()
    return redirect(url_for('staff_console'))

@app.route('/track')
def track_queue():
    conn = get_db_connection()
    counters = conn.execute("SELECT name, queue_length FROM counters").fetchall()
    conn.close()
    return render_template('track.html', counters=counters)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)