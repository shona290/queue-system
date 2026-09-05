from flask import Flask, render_template, request, redirect, jsonify
import sqlite3
import os

app = Flask(__name__)

def init_db():
    conn = sqlite3.connect('queue.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS departments (id INTEGER PRIMARY KEY, name TEXT, prefix TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS counters (id INTEGER PRIMARY KEY, name TEXT, department_id INT, wait_time INT, queue_length INT)')
    c.execute('CREATE TABLE IF NOT EXISTS tokens (id INTEGER PRIMARY KEY, department_id INT, counter_id INT, token_code TEXT, status TEXT)')
    
    c.execute('SELECT COUNT(*) FROM departments')
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO departments (name, prefix) VALUES ('Cash Deposit', 'C')")
        c.execute("INSERT INTO departments (name, prefix) VALUES ('Loan Inquiry', 'L')")
        c.execute("INSERT INTO counters (name, department_id, wait_time, queue_length) VALUES ('Counter 1 (Fast)', 1, 2, 0)")
        c.execute("INSERT INTO counters (name, department_id, wait_time, queue_length) VALUES ('Counter 2 (Normal)', 2, 4, 0)")
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def customer_portal():
    conn = sqlite3.connect('queue.db')
    c = conn.cursor()
    c.execute('SELECT id, name FROM departments')
    depts = c.fetchall()
    conn.close()
    return render_template('index.html', depts=depts)

@app.route('/join', methods=['POST'])
def join_queue():
    dept_id = int(request.form['department_id'])
    conn = sqlite3.connect('queue.db')
    c = conn.cursor()
    
    # Fetch department prefix and matching counters
    c.execute('SELECT prefix FROM departments WHERE id=?', (dept_id,))
    prefix = c.fetchone()[0]
    
    c.execute('SELECT id, name, wait_time, queue_length FROM counters WHERE department_id=?', (dept_id,))
    counters = c.fetchall()
    
    if not counters:
        conn.close()
        return "Error: No counters available for this department."
        
    # Intelligent Recommendation Engine
    best_counter = min(counters, key=lambda x: x[3] * x[2])
    best_id, best_name, wait_time, queue_length = best_counter
    est_wait = wait_time * queue_length
    
    # Insert Token
    c.execute("INSERT INTO tokens (department_id, counter_id, token_code, status) VALUES (?, ?, ?, 'Waiting')", (dept_id, best_id, prefix + "-10"))
    token_id = c.lastrowid
    token_code = f"{prefix}-{100 + token_id}"
    c.execute("UPDATE tokens SET token_code=? WHERE id=?", (token_code, token_id))
    
    # Update counter queue length
    c.execute("UPDATE counters SET queue_length = queue_length + 1 WHERE id = ?", (best_id,))
    conn.commit()
    conn.close()
    
    return redirect(f'/track/{token_id}?wait={est_wait}&counter={best_name}&code={token_code}')

@app.route('/track/<int:token_id>')
def track_token(token_id):
    est_wait = request.args.get('wait', 0)
    counter_name = request.args.get('counter', 'Unknown')
    token_code = request.args.get('code', 'A-000')
    return render_template('track.html', token_id=token_id, wait=est_wait, counter=counter_name, code=token_code)

@app.route('/api/status/<int:token_id>')
def check_status(token_id):
    conn = sqlite3.connect('queue.db')
    c = conn.cursor()
    c.execute("SELECT status FROM tokens WHERE id=?", (token_id,))
    row = c.fetchone()
    conn.close()
    return jsonify({'status': row[0] if row else 'Unknown'})

@app.route('/staff')
def staff_console():
    conn = sqlite3.connect('queue.db')
    c = conn.cursor()
    c.execute("SELECT t.id, t.token_code, c.name FROM tokens t JOIN counters c ON t.counter_id = c.id WHERE t.status='Waiting'")
    waiting = c.fetchall()
    conn.close()
    return render_template('staff.html', waiting=waiting)

@app.route('/complete/<int:token_id>')
def complete_service(token_id):
    conn = sqlite3.connect('queue.db')
    c = conn.cursor()
    c.execute("SELECT counter_id FROM tokens WHERE id=?", (token_id,))
    row = c.fetchone().
    if row:
        c.execute("UPDATE tokens SET status ='Completed' WHERE id=?", (token_id,))
        c.execute("UPDATE counters SET queue_length = queue_length = 1 WHERE id=?", (row[0],))
    conn.commit()
    conn.close()
    return redirect('/staff')
if __name__ == '__main__':
port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
