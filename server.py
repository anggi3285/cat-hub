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
    # Pet state table with couple tamagotchi features
    c.execute('''
        CREATE TABLE IF NOT EXISTS pet (
            id INTEGER PRIMARY KEY,
            name TEXT DEFAULT 'Mimi',
            hunger INTEGER DEFAULT 80,
            happiness INTEGER DEFAULT 80,
            energy INTEGER DEFAULT 80,
            cleanliness INTEGER DEFAULT 80,
            stage TEXT DEFAULT 'Kitten',
            love_level INTEGER DEFAULT 1,
            love_points INTEGER DEFAULT 0,
            status TEXT DEFAULT 'idle',
            sleeping INTEGER DEFAULT 0,
            parent1 TEXT DEFAULT 'Anggi',
            parent2 TEXT DEFAULT 'Sayang',
            last_fed TIMESTAMP,
            last_petted TIMESTAMP,
            last_cleaned TIMESTAMP,
            last_slept TIMESTAMP
        )
    ''')
    
    # Initialize pet if empty
    c.execute("SELECT COUNT(*) FROM pet")
    if c.fetchone()[0] == 0:
        c.execute('''
            INSERT INTO pet (name, hunger, happiness, energy, cleanliness, stage, love_level, love_points, status, sleeping, parent1, parent2)
            VALUES ('Mimi', 85, 90, 85, 80, 'Kitten', 1, 10, 'idle', 0, 'Anggi', 'Sayang')
        ''')
    else:
        # Migrate columns if not exists
        for col_def in [
            ("cleanliness", "INTEGER DEFAULT 80"),
            ("stage", "TEXT DEFAULT 'Kitten'"),
            ("parent1", "TEXT DEFAULT 'Anggi'"),
            ("parent2", "TEXT DEFAULT 'Sayang'"),
            ("last_cleaned", "TIMESTAMP")
        ]:
            try:
                c.execute(f"ALTER TABLE pet ADD COLUMN {col_def[0]} {col_def[1]}")
            except sqlite3.OperationalError:
                pass

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

    # Couple prompt answers
    c.execute('''
        CREATE TABLE IF NOT EXISTS couple_prompts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_date DATE NOT NULL,
            user TEXT NOT NULL,
            answer TEXT NOT NULL,
            UNIQUE(prompt_date, user)
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
    default_items = ['plant', 'lofi_radio', 'window_rain', 'fairy_lights', 'plushie', 'rug', 'cat_tree', 'disco_ball']
    for item in default_items:
        c.execute("INSERT OR IGNORE INTO decor (item_key, unlocked) VALUES (?, ?)", (item, 1 if item in ['plant', 'rug', 'cat_tree'] else 0))

    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

COUPLE_PROMPTS = [
    "Hal kecil apa dari pasanganmu yang bikin kamu senyum hari ini?",
    "Kalau kita liburan santai bareng Mimi, enaknya ke mana?",
    "Makanan apa yang paling pengen kamu makan bareng pasangan minggu ini?",
    "Kirim 1 kata manis atau doa buat pasanganmu hari ini!",
    "Lagu apa yang paling ngingetin kamu sama masa awal kenal?",
    "Apa momen favoritmu pas lagi santai berdua?",
    "Kalau Mimi bisa ngomong, kira-kira dia mau curhat apa tentang kita?"
]

def get_today_prompt():
    day_idx = date.today().toordinal() % len(COUPLE_PROMPTS)
    return COUPLE_PROMPTS[day_idx]

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

    # Daily couple prompt & answers
    prompt = get_today_prompt()
    c.execute("SELECT user, answer FROM couple_prompts WHERE prompt_date = ?", (today,))
    prompt_answers = {r['user']: r['answer'] for r in c.fetchall()}

    conn.close()
    return jsonify({
        "pet": pet,
        "notes": notes,
        "decor": decor,
        "checked_today": checked_today,
        "total_days": max(1, total_active_days),
        "prompt": prompt,
        "prompt_answers": prompt_answers
    })

@app.route('/api/pet/action', methods=['POST'])
def pet_action():
    data = request.json or {}
    action = data.get('action') # 'feed', 'pet', 'bath', 'play', 'sleep', 'hug'
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
            conn.close()
            return jsonify({"status": "full", "message": f"{pet['name']} sudah kenyang banget!"}), 400
        new_hunger = min(100, pet['hunger'] + 25)
        new_happy = min(100, pet['happiness'] + 10)
        c.execute("""
            UPDATE pet 
            SET hunger = ?, happiness = ?, status = 'eating', last_fed = CURRENT_TIMESTAMP, love_points = love_points + ?
            WHERE id = 1
        """, (new_hunger, new_happy, points_added))
        msg = f"{user} memberi makan {pet['name']}! Nyam nyam 🐟"
        sound = "nom"

    elif action == 'pet':
        new_happy = min(100, pet['happiness'] + 20)
        new_energy = max(0, pet['energy'] - 5)
        c.execute("""
            UPDATE pet 
            SET happiness = ?, energy = ?, status = 'purring', last_petted = CURRENT_TIMESTAMP, love_points = love_points + ?
            WHERE id = 1
        """, (new_happy, new_energy, points_added))
        msg = f"{user} mengelus {pet['name']}! Meow~ purr purr 😻"
        sound = "purr"

    elif action == 'bath':
        new_clean = min(100, (pet.get('cleanliness') or 80) + 35)
        new_happy = min(100, pet['happiness'] + 15)
        c.execute("""
            UPDATE pet 
            SET cleanliness = ?, happiness = ?, status = 'bath', last_cleaned = CURRENT_TIMESTAMP, love_points = love_points + ?
            WHERE id = 1
        """, (new_clean, new_happy, points_added))
        msg = f"{user} memandikan {pet['name']}! Segar wangi busa 🧼🛁"
        sound = "bubble"

    elif action == 'play':
        if pet['energy'] <= 15:
            conn.close()
            return jsonify({"status": "tired", "message": f"{pet['name']} kecapekan, butuh tidur dulu!"}), 400
        new_happy = min(100, pet['happiness'] + 25)
        new_energy = max(0, pet['energy'] - 20)
        new_hunger = max(0, pet['hunger'] - 10)
        c.execute("""
            UPDATE pet 
            SET happiness = ?, energy = ?, hunger = ?, status = 'playing', love_points = love_points + ?
            WHERE id = 1
        """, (new_happy, new_energy, new_hunger, points_added + 3))
        msg = f"{user} mengajak {pet['name']} main bola benang! Lompat-lompat 🧶"
        sound = "play"

    elif action == 'sleep':
        is_sleeping = 1 if pet['sleeping'] == 0 else 0
        status = 'sleeping' if is_sleeping else 'idle'
        new_energy = min(100, pet['energy'] + 35) if is_sleeping else pet['energy']
        c.execute("""
            UPDATE pet 
            SET sleeping = ?, status = ?, energy = ?, last_slept = CURRENT_TIMESTAMP, love_points = love_points + 2
            WHERE id = 1
        """, (is_sleeping, status, new_energy))
        msg = f"{pet['name']} {'mulai tidur nyenyak zzz' if is_sleeping else 'terbangun segar bugar! ☀️'}"
        sound = "snore" if is_sleeping else "meow"

    elif action == 'hug':
        partner = pet.get('parent2', 'Sayang') if user == pet.get('parent1', 'Anggi') else pet.get('parent1', 'Anggi')
        c.execute("""
            UPDATE pet 
            SET happiness = 100, love_points = love_points + 10, status = 'loving'
            WHERE id = 1
        """)
        msg = f"💌 {user} mengirim pelukan hangat virtual untuk {partner}! Mimi ikutan bahagia~ 💕"
        sound = "love"

    # Check level & stage evolution
    c.execute("SELECT love_points, love_level, stage FROM pet WHERE id = 1")
    row = c.fetchone()
    pts = row['love_points']
    lvl = row['love_level']
    new_lvl = (pts // 50) + 1
    
    # Evolution: Lvl 1-3 Kitten, Lvl 4-7 Teen Cat, Lvl 8+ Adult Cat
    new_stage = 'Kitten'
    if new_lvl >= 8:
        new_stage = 'Adult Cat'
    elif new_lvl >= 4:
        new_stage = 'Teen Cat'

    c.execute("UPDATE pet SET love_level = ?, stage = ? WHERE id = 1", (new_lvl, new_stage))

    if new_lvl > lvl:
        decor_unlocks = {2: 'lofi_radio', 3: 'fairy_lights', 4: 'plushie', 5: 'window_rain', 6: 'disco_ball'}
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

@app.route('/api/pet/parents', methods=['POST'])
def update_parents():
    data = request.json or {}
    p1 = (data.get('parent1') or 'Anggi').strip()
    p2 = (data.get('parent2') or 'Sayang').strip()
    pet_name = (data.get('pet_name') or 'Mimi').strip()

    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE pet SET parent1 = ?, parent2 = ?, name = ? WHERE id = 1", (p1, p2, pet_name))
    conn.commit()
    c.execute("SELECT * FROM pet WHERE id = 1")
    pet = dict(c.fetchone())
    conn.close()

    socketio.emit('parents_updated', pet)
    return jsonify({"success": True, "pet": pet})

@app.route('/api/prompt/answer', methods=['POST'])
def answer_prompt():
    data = request.json or {}
    user = data.get('user', 'Kamu')
    answer = (data.get('answer') or '').strip()
    today = date.today().isoformat()

    if not answer:
        return jsonify({"error": "Jawaban tidak boleh kosong"}), 400

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO couple_prompts (prompt_date, user, answer) 
        VALUES (?, ?, ?)
        ON CONFLICT(prompt_date, user) DO UPDATE SET answer = excluded.answer
    """, (today, user, answer))
    c.execute("UPDATE pet SET love_points = love_points + 8, happiness = 100 WHERE id = 1")
    conn.commit()

    c.execute("SELECT user, answer FROM couple_prompts WHERE prompt_date = ?", (today,))
    prompt_answers = {r['user']: r['answer'] for r in c.fetchall()}
    conn.close()

    msg = f"💬 {user} membalas obrolan harian!"
    socketio.emit('prompt_updated', {"prompt_answers": prompt_answers, "message": msg, "user": user})
    return jsonify({"success": True, "prompt_answers": prompt_answers, "message": msg})

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
        msg = f"Check-in berhasil! {user} dapat +15 Love Points untuk Mimi 🌟"
    except sqlite3.IntegrityError:
        success = False
        msg = f"{user} sudah check-in hari ini! 💕"

    c.execute("SELECT user FROM checkins WHERE checkin_date = ?", (today,))
    checked_today = [r['user'] for r in c.fetchall()]
    conn.close()

    socketio.emit('checkin_updated', {"checked_today": checked_today, "user": user})
    return jsonify({"success": success, "message": msg, "checked_today": checked_today})

if __name__ == '__main__':
    init_db()
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
