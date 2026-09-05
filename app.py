import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

def init_db():
    conn = sqlite3.connect('queue.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS counters (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, queue_length INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tokens (id INTEGER PRIMARY KEY AUTOINCREMENT, token_code TEXT, counter_id INTEGER, status TEXT)''')
    conn.commit()
    conn.close()

init_db()

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        dept = request.form.get('department')
        conn = sqlite3.connect('queue.db')
        c = conn.cursor()
        c.execute("SELECT id FROM counters WHERE name=?", (dept,))
        counter = c.fetchone()
        if not counter:
            c.execute("INSERT INTO counters (name, queue_length) VALUES (?, 1)", (dept,))
            conn.commit()
            c.execute("SELECT id FROM counters WHERE name=?", (dept,))
            counter = c.fetchone()
        counter_id = counter[0]
        c.execute("INSERT INTO tokens (token_code, counter_id, status) VALUES (?, ?, 'Waiting')", (f"T-{counter_id}", counter_id))
        c.execute("UPDATE counters SET queue_length = queue_length + 1 WHERE id=?", (counter_id,))
        conn.commit()
        conn.close()
        return redirect('/track')
    return render_template('index.html')

@app.route('/staff')
def staff_console():
    # Security: Customers are blocked unless they use the secret key
    key = request.args.get('key')
    if key != 'mysecretstaffkey':
        return "Access Denied. Customers cannot view this page.", 403

    conn = sqlite3.connect('queue.db')
    c = conn.cursor()
    c.execute("SELECT t.id, t.token_code, c.name FROM tokens t JOIN counters c ON t.counter_id = c.id WHERE t.status = 'Waiting'")
    waiting = c.fetchall()
    conn.close()
    return render_template('staff.html', waiting=waiting)

@app.route('/complete/<int:token_id>')
def complete_service(token_id):
    conn = sqlite3.connect('queue.db')
    c = conn.cursor()
    c.execute("SELECT counter_id FROM tokens WHERE id=?", (token_id,))
    row = c.fetchone()
    if row:
        c.execute("UPDATE tokens SET status='Completed' WHERE id=?", (token_id,))
        c.execute("UPDATE counters SET queue_length = queue_length - 1 WHERE id=?", (row[0],))
        conn.commit()
    conn.close()
    return redirect('/staff?key=mysecretstaffkey')

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