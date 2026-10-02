import sqlite3
import json
import time
from datetime import datetime, date
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

DB_FILE = "room.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Pet state table
    c.execute('''
        CREATE TABLE IF NOT EXISTS pet (
            id INTEGER PRIMARY KEY,
            name TEXT DEFAULT 'Mimi',
            hunger INTEGER DEFAULT 80,
            happiness INTEGER DEFAULT 80,
            energy INTEGER DEFAULT 80,
            love_level INTEGER DEFAULT 1,
            love_points INTEGER DEFAULT 0,
            status TEXT DEFAULT 'idle',
            sleeping INTEGER DEFAULT 0,
            last_fed TIMESTAMP,
            last_petted TIMESTAMP,
            last_slept TIMESTAMP
        )
    ''')
    
    # Initialize pet if empty
    c.execute("SELECT COUNT(*) FROM pet")
    if c.fetchone()[0] == 0:
        c.execute('''
            INSERT INTO pet (name, hunger, happiness, energy, love_level, love_points, status, sleeping)
            VALUES ('Mimi', 85, 90, 80, 1, 10, 'idle', 0)
        ''')

    # Sticky notes / Diary table
    c.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT NOT NULL,
            content TEXT NOT NULL,
            color TEXT DEFAULT '#fef08a',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Checkins & Streaks
    c.execute('''
        CREATE TABLE IF NOT EXISTS checkins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT NOT NULL,
            checkin_date DATE NOT NULL,
            UNIQUE(user, checkin_date)
        )
    ''')

    # Room decorations unlocked
    c.execute('''
        CREATE TABLE IF NOT EXISTS decor (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_key TEXT UNIQUE,
            unlocked INTEGER DEFAULT 0
        )
    ''')

    # Default decor
    default_items = ['plant', 'lofi_radio', 'window_rain', 'fairy_lights', 'plushie', 'rug']
    for item in default_items:
        c.execute("INSERT OR IGNORE INTO decor (item_key, unlocked) VALUES (?, ?)", (item, 1 if item in ['plant', 'rug'] else 0))

    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def update_pet_decay():
    # Natural decay over time
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM pet WHERE id = 1")
    pet = dict(c.fetchone())
    
    # We cap between 0 and 100
    hunger = max(0, min(100, pet['hunger']))
    happiness = max(0, min(100, pet['happiness']))
    energy = max(0, min(100, pet['energy']))
    
    conn.close()
    return pet

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/api/state', methods=['GET'])
def get_state():
    conn = get_db()
    c = conn.cursor()
    
    # Pet
    c.execute("SELECT * FROM pet WHERE id = 1")
    pet = dict(c.fetchone())

    # Notes
    c.execute("SELECT * FROM notes ORDER BY id DESC LIMIT 20")
    notes = [dict(r) for r in c.fetchall()]

    # Decor
    c.execute("SELECT item_key, unlocked FROM decor")
    decor = {r['item_key']: bool(r['unlocked']) for r in c.fetchall()}

    # Checkin status today
    today = date.today().isoformat()
    c.execute("SELECT user FROM checkins WHERE checkin_date = ?", (today,))
    checked_today = [r['user'] for r in c.fetchall()]

    # Total checkin streak calculation
    c.execute("SELECT COUNT(DISTINCT checkin_date) FROM checkins")
    total_active_days = c.fetchone()[0]

    conn.close()
    return jsonify({
        "pet": pet,
        "notes": notes,
        "decor": decor,
        "checked_today": checked_today,
        "total_days": max(1, total_active_days)
    })

@app.route('/api/pet/action', methods=['POST'])
def pet_action():
    data = request.json or {}
    action = data.get('action') # 'feed', 'pet', 'sleep', 'wake'
    user = data.get('user', 'Kamu')

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM pet WHERE id = 1")
    pet = dict(c.fetchone())

    msg = ""
    sound = ""
    points_added = 5

    if action == 'feed':
        if pet['hunger'] >= 100:
            return jsonify({"status": "full", "message": f"{pet['name']} sudah kenyang banget!"}), 400
        new_hunger = min(100, pet['hunger'] + 25)
        new_happy = min(100, pet['happiness'] + 10)
        c.execute("""
            UPDATE pet 
            SET hunger = ?, happiness = ?, status = 'eating', last_fed = CURRENT_TIMESTAMP, love_points = love_points + ?
            WHERE id = 1
        """, (new_hunger, new_happy, points_added))
        msg = f"{user} memberi makan {pet['name']}! Nyam nyam..."
        sound = "nom"

    elif action == 'pet':
        new_happy = min(100, pet['happiness'] + 20)
        new_energy = max(0, pet['energy'] - 5)
        c.execute("""
            UPDATE pet 
            SET happiness = ?, energy = ?, status = 'purring', last_petted = CURRENT_TIMESTAMP, love_points = love_points + ?
            WHERE id = 1
        """, (new_happy, new_energy, points_added))
        msg = f"{user} mengelus {pet['name']}! Meow~ purr purr..."
        sound = "purr"

    elif action == 'sleep':
        is_sleeping = 1 if pet['sleeping'] == 0 else 0
        status = 'sleeping' if is_sleeping else 'idle'
        new_energy = min(100, pet['energy'] + 35) if is_sleeping else pet['energy']
        c.execute("""
            UPDATE pet 
            SET sleeping = ?, status = ?, energy = ?, last_slept = CURRENT_TIMESTAMP, love_points = love_points + 2
            WHERE id = 1
        """, (is_sleeping, status, new_energy))
        msg = f"{pet['name']} {'mulai tidur nyenyak zzz' if is_sleeping else 'terbangun bangun segar!'}"
        sound = "snore" if is_sleeping else "meow"

    # Check level up
    c.execute("SELECT love_points, love_level FROM pet WHERE id = 1")
    row = c.fetchone()
    pts = row['love_points']
    lvl = row['love_level']
    new_lvl = (pts // 50) + 1
    if new_lvl > lvl:
        c.execute("UPDATE pet SET love_level = ? WHERE id = 1", (new_lvl,))
        # unlock decoration based on level
        decor_unlocks = {2: 'lofi_radio', 3: 'fairy_lights', 4: 'plushie', 5: 'window_rain'}
        if new_lvl in decor_unlocks:
            c.execute("UPDATE decor SET unlocked = 1 WHERE item_key = ?", (decor_unlocks[new_lvl],))

    conn.commit()

    # Get updated pet
    c.execute("SELECT * FROM pet WHERE id = 1")
    updated_pet = dict(c.fetchone())
    conn.close()

    # Broadcast event to all sockets
    socketio.emit('pet_updated', {
        "pet": updated_pet,
        "message": msg,
        "sound": sound,
        "actor": user
    })

    return jsonify({"success": True, "pet": updated_pet, "message": msg})

@app.route('/api/notes', methods=['POST'])
def add_note():
    data = request.json or {}
    author = data.get('author', 'Anon')
    content = (data.get('content') or '').strip()
    color = data.get('color', '#fef08a')

    if not content:
        return jsonify({"error": "Pesan tidak boleh kosong"}), 400

    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO notes (author, content, color) VALUES (?, ?, ?)", (author, content[:200], color))
    c.execute("UPDATE pet SET love_points = love_points + 10 WHERE id = 1")
    conn.commit()

    c.execute("SELECT * FROM notes ORDER BY id DESC LIMIT 20")
    notes = [dict(r) for r in c.fetchall()]
    conn.close()

    socketio.emit('notes_updated', notes)
    return jsonify({"success": True, "notes": notes})

@app.route('/api/checkin', methods=['POST'])
def checkin():
    data = request.json or {}
    user = data.get('user', 'Kamu')
    today = date.today().isoformat()

    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO checkins (user, checkin_date) VALUES (?, ?)", (user, today))
        c.execute("UPDATE pet SET love_points = love_points + 15, happiness = 100 WHERE id = 1")
        conn.commit()
        success = True
        msg = f"Check-in berhasil! {user} dapat +15 Love Points untuk Mimi."
    except sqlite3.IntegrityError:
        success = False
        msg = f"{user} sudah check-in hari ini!"

    c.execute("SELECT user FROM checkins WHERE checkin_date = ?", (today,))
    checked_today = [r['user'] for r in c.fetchall()]
    conn.close()

    socketio.emit('checkin_updated', {"checked_today": checked_today, "user": user})
    return jsonify({"success": success, "message": msg, "checked_today": checked_today})

if __name__ == '__main__':
    init_db()
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
