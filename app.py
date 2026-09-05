import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = 'super_secret_session_key'

def init_db():
    conn = sqlite3.connect('queue.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS counters (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, queue_length INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    token_code TEXT, 
                    customer_name TEXT, 
                    counter_id INTEGER, 
                    status TEXT, 
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    conn.commit()
    conn.close()

init_db()

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        name = request.form.get('customer_name')
        purpose = request.form.get('purpose', '').lower()
        
        # Intelligent Service Recommendation & Routing
        if any(word in purpose for word in ['cash', 'deposit', 'withdraw', 'money', 'pay', 'cheque']):
            dept = "Cash Deposit"
        elif any(word in purpose for word in ['open', 'new', 'account', 'sign up']):
            dept = "Account Opening"
        else:
            dept = "Customer Inquiry"
            
        conn = sqlite3.connect('queue.db')
        c = conn.cursor()
        
        # Ensure counters exist
        for d in ["Cash Deposit", "Account Opening", "Customer Inquiry"]:
            c.execute("SELECT id FROM counters WHERE name=?", (d,))
            if not c.fetchone():
                c.execute("INSERT INTO counters (name, queue_length) VALUES (?, 0)", (d,))
                conn.commit()

        c.execute("SELECT id FROM counters WHERE name=?", (dept,))
        counter = c.fetchone()
        counter_id = counter[0]
        token_code = f"T-{counter_id}-{os.urandom(2).hex().upper()}"
        
        c.execute("INSERT INTO tokens (token_code, customer_name, counter_id, status) VALUES (?, ?, ?, 'Waiting')", (token_code, name, counter_id))
        c.execute("UPDATE counters SET queue_length = queue_length + 1 WHERE id=?", (counter_id,))
        
        # Find fastest alternative department recommendation
        c.execute("SELECT name, queue_length FROM counters ORDER BY queue_length ASC LIMIT 1")
        fastest = c.fetchone()
        
        conn.commit()
        conn.close()
        
        return render_template('token.html', token_code=token_code, dept=dept, name=name, fastest=fastest)
        
    return render_template('index.html')

@app.route('/staff-login', methods=['GET', 'POST'])
def staff_login():
    error = None
    if request.method == 'POST':
        password = request.form.get('password')
        if password == 'Admin@123':
            session['logged_in'] = True
            return redirect('/staff')
        else:
            error = "Invalid password. Access denied."
    return render_template('login.html', error=error)

@app.route('/staff')
def staff_console():
    if not session.get('logged_in'):
        return redirect('/staff-login')

    conn = sqlite3.connect('queue.db')
    c = conn.cursor()
    # Fetch waiting tokens and compute wait time in minutes
    c.execute("""
        SELECT t.id, t.token_code, t.customer_name, c.name, 
               (strftime('%s', 'now') - strftime('%s', t.created_at)) / 60 as wait_time
        FROM tokens t 
        JOIN counters c ON t.counter_id = c.id 
        WHERE t.status = 'Waiting'
        ORDER BY t.created_at ASC
    """)
    waiting = c.fetchall()
    conn.close()
    return render_template('staff.html', waiting=waiting)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect('/')

@app.route('/complete/<int:token_id>')
def complete_service(token_id):
    if not session.get('logged_in'):
        return redirect('/staff-login')
    
    conn = sqlite3.connect('queue.db')
    c = conn.cursor()
    c.execute("SELECT counter_id FROM tokens WHERE id=?", (token_id,))
    row = c.fetchone()
    if row:
        c.execute("UPDATE tokens SET status='Completed' WHERE id=?", (token_id,))
        c.execute("UPDATE counters SET queue_length = MAX(0, queue_length - 1) WHERE id=?", (row[0],))
        conn.commit()
    conn.close()
    return redirect('/staff')

@app.route('/track')
def track_queue():
    conn = sqlite3.connect('queue.db')
    c = conn.cursor()
    c.execute("SELECT name, queue_length FROM counters")
    counters = c.fetchall()
    conn.close()
    return render_template('track.html', counters=counters)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)