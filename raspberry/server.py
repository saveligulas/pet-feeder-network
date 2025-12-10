from flask import Flask, request, g, render_template_string, jsonify
import sqlite3
from datetime import datetime

DB = "pets.db"

app = Flask(__name__)

pending_registration = {"active": False, "timestamp": None}


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db():
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    with app.app_context():
        db = get_db()
        db.execute("""
            CREATE TABLE IF NOT EXISTS pets (
                id INTEGER PRIMARY KEY, 
                name TEXT, 
                rfid_uid TEXT,
                portion_size INTEGER DEFAULT 5,
                cooldown_min INTEGER DEFAULT 60,
                max_daily_feeds INTEGER DEFAULT 3
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS feeding_logs (
                id INTEGER PRIMARY KEY, 
                pet_id INTEGER,
                pet_name TEXT,
                event_type TEXT,
                details TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(pet_id) REFERENCES pets(id)
            )
        """)
        db.commit()


def log_event(pet_id, pet_name, event_type, details):
    db = get_db()
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
    db.execute(
        "INSERT INTO feeding_logs (pet_id, pet_name, event_type, details, timestamp) VALUES (?, ?, ?, ?, ?)",
        (pet_id, pet_name, event_type, details, timestamp)
    )
    db.commit()


@app.route('/tag', methods=['POST'])
def scan():
    data = request.get_json(silent=True)
    if not data or 'uid' not in data:
        return jsonify({"error": "UID missing"}), 400

    tag_id = data.get('uid')
    print(f"Received scan for UID: {tag_id}")

    if pending_registration["active"]:
        pending_registration["active"] = False
        db = get_db()
        existing_pet = db.execute("SELECT * FROM pets WHERE rfid_uid = ?", (tag_id,)).fetchone()

        if existing_pet:
            pending_registration["error"] = f"Tag already belongs to {existing_pet['name']}"
            return jsonify({"status": "error", "message": "Tag already registered"}), 409

        pending_registration["last_uid"] = tag_id
        return jsonify({"status": "registration", "message": "Tag captured", "uid": tag_id}), 200

    db = get_db()
    pet = db.execute("SELECT * FROM pets WHERE rfid_uid = ?", (tag_id,)).fetchone()

    if pet:
        pet_id = pet['id']
        pet_name = pet['name']

        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        feed_count = db.execute(
            "SELECT COUNT(*) FROM feeding_logs WHERE pet_id = ? AND event_type = 'Dispensed' AND timestamp >= ?",
            (pet_id, today_start.strftime('%Y-%m-%d %H:%M:%S'))
        ).fetchone()[0]

        if feed_count >= pet['max_daily_feeds']:
            log_event(pet_id, pet_name, "Denied", "Daily limit reached")
            return jsonify({
                "status": "denied",
                "message": "Daily limit reached"
            }), 403

        last_feed = db.execute(
            "SELECT timestamp FROM feeding_logs WHERE pet_id = ? AND event_type = 'Dispensed' ORDER BY timestamp DESC LIMIT 1",
            (pet_id,)
        ).fetchone()

        if last_feed:
            try:
                last_time = datetime.strptime(last_feed['timestamp'], '%Y-%m-%d %H:%M:%S')
            except ValueError:
                last_time = datetime.strptime(last_feed['timestamp'], '%Y-%m-%d %H:%M:%S.%f')

            minutes_since = (datetime.now() - last_time).total_seconds() / 60

            if minutes_since < pet['cooldown_min']:
                wait_time = int(pet['cooldown_min'] - minutes_since)
                log_event(pet_id, pet_name, "Denied", f"Cooldown active ({wait_time}m left)")
                return jsonify({
                    "status": "denied",
                    "message": "Diet active"
                }), 403

        log_event(pet_id, pet_name, "Dispensed", f"{pet['portion_size']}s portion")

        return jsonify({
            "status": "authorized",
            "message": "Feeding allowed",
            "pet_name": pet_name,
            "portion_time": pet['portion_size']
        }), 200
    else:
        log_event(None, "Unknown", "Denied", f"Unknown Tag: {tag_id}")
        return jsonify({"status": "denied", "message": "Pet not recognized"}), 403


@app.route('/api/logs')
def get_logs():
    db = get_db()
    raw_logs = db.execute("""
        SELECT pet_name, event_type, details, timestamp 
        FROM feeding_logs 
        ORDER BY timestamp DESC 
        LIMIT 100
    """).fetchall()

    grouped_logs = []

    for row in raw_logs:
        current_log = dict(row)
        current_log['count'] = 1

        if grouped_logs:
            last_log = grouped_logs[-1]
            if (last_log['pet_name'] == current_log['pet_name'] and
                    last_log['event_type'] == current_log['event_type'] and
                    last_log['details'] == current_log['details']):
                # Increment count on the displayed log (the most recent one)
                last_log['count'] += 1
                continue

        grouped_logs.append(current_log)

    return jsonify(grouped_logs[:20])


@app.route('/api/logs/clear', methods=['POST'])
def clear_logs():
    db = get_db()
    db.execute("DELETE FROM feeding_logs")
    db.commit()
    return jsonify({"success": True})


HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Smart Pet Feeder</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        :root {
            --background: 0 0% 100%;
            --foreground: 222.2 84% 4.9%;
            --card: 0 0% 100%;
            --card-foreground: 222.2 84% 4.9%;
            --primary: 222.2 47.4% 11.2%;
            --primary-foreground: 210 40% 98%;
            --secondary: 210 40% 96.1%;
            --secondary-foreground: 222.2 47.4% 11.2%;
            --destructive: 0 84.2% 60.2%;
            --destructive-foreground: 210 40% 98%;
            --muted: 210 40% 96.1%;
            --muted-foreground: 215.4 16.3% 46.9%;
            --accent: 210 40% 96.1%;
            --border: 214.3 31.8% 91.4%;
            --input: 214.3 31.8% 91.4%;
            --ring: 222.2 84% 4.9%;
            --radius: 0.5rem;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: hsl(var(--background));
            color: hsl(var(--foreground));
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
        }

        .container {
            max-width: 48rem;
            margin: 0 auto;
            padding: 2rem 1rem;
        }

        .header { margin-bottom: 2rem; }
        h1 { font-size: 2rem; font-weight: 700; margin-bottom: 0.5rem; }
        .subtitle { color: hsl(var(--muted-foreground)); font-size: 0.875rem; }

        .card {
            background: hsl(var(--card));
            border: 1px solid hsl(var(--border));
            border-radius: var(--radius);
            margin-bottom: 1.5rem;
        }

        .card-header { padding: 1.5rem; border-bottom: 1px solid hsl(var(--border)); }
        .card-title { font-size: 1.125rem; font-weight: 600; }
        .card-description { color: hsl(var(--muted-foreground)); font-size: 0.875rem; margin-top: 0.25rem; }
        .card-content { padding: 1.5rem; }

        .form-group { margin-bottom: 1.5rem; }
        label { display: block; font-size: 0.875rem; font-weight: 500; margin-bottom: 0.5rem; }

        input[type="text"], input[type="number"] {
            width: 100%; height: 2.5rem; padding: 0.5rem 0.75rem;
            border: 1px solid hsl(var(--input)); border-radius: calc(var(--radius) - 2px);
            background: hsl(var(--background));
        }

        input:focus { outline: none; border-color: hsl(var(--ring)); box-shadow: 0 0 0 3px hsl(var(--ring) / 0.1); }
        input:read-only { background: hsl(var(--muted)); cursor: not-allowed; }

        .input-group { display: flex; gap: 0.5rem; }
        .grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 1rem; }

        .button {
            display: inline-flex; align-items: center; justify-content: center;
            border-radius: calc(var(--radius) - 2px); font-size: 0.875rem; font-weight: 500;
            height: 2.5rem; padding: 0 1rem; border: none; cursor: pointer;
        }

        .button-primary { background: hsl(var(--primary)); color: hsl(var(--primary-foreground)); }
        .button-secondary { background: hsl(var(--secondary)); color: hsl(var(--secondary-foreground)); }
        .button-destructive { background: hsl(var(--destructive)); color: hsl(var(--destructive-foreground)); height: 2rem; }
        .button-full { width: 100%; }

        .alert {
            padding: 0.75rem 1rem; border-radius: calc(var(--radius) - 2px);
            font-size: 0.875rem; margin-bottom: 1rem; display: none; border: 1px solid;
        }
        .alert-warning { background: hsl(48 96% 89%); color: hsl(25 95% 33%); border-color: hsl(48 96% 76%); }
        .alert-success { background: hsl(143 85% 96%); color: hsl(140 100% 27%); border-color: hsl(145 92% 91%); }

        .pet-list { display: flex; flex-direction: column; gap: 0.75rem; }

        .pet-item {
            display: flex; align-items: center; justify-content: space-between;
            padding: 1rem; border: 1px solid hsl(var(--border));
            border-radius: calc(var(--radius) - 2px);
        }

        .pet-info { flex: 1; }
        .pet-name { font-weight: 600; font-size: 0.95rem; margin-bottom: 0.25rem; }
        .pet-details { font-size: 0.8125rem; color: hsl(var(--muted-foreground)); }

        .badge {
            display: inline-flex; align-items: center; border-radius: 9999px;
            padding: 0.125rem 0.625rem; font-size: 0.75rem; font-weight: 600;
        }
        .badge-success { background: hsl(143 85% 96%); color: hsl(140 100% 27%); border: 1px solid hsl(145 92% 91%); }
        .badge-destructive { background: hsl(0 84% 96%); color: hsl(0 84% 60%); border: 1px solid hsl(0 84% 90%); }

        .empty-state { text-align: center; padding: 3rem 1rem; color: hsl(var(--muted-foreground)); }
        .empty-state-icon { font-size: 3rem; margin-bottom: 0.5rem; opacity: 0.5; }

        @media (max-width: 640px) {
            .grid { grid-template-columns: 1fr; }
            .pet-item { flex-direction: column; align-items: flex-start; gap: 0.75rem; }
            .button-destructive, .badge { align-self: flex-start; }
            .pet-item .badge { margin-top: 0.5rem; }
        }

        .counter-badge {
            background: hsl(var(--secondary)); color: hsl(var(--secondary-foreground));
            font-size: 0.7rem; padding: 2px 8px; border-radius: 12px; margin-left: 8px;
            font-weight: 700; border: 1px solid hsl(var(--border));
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Smart Pet Feeder</h1>
            <p class="subtitle">Manage feeding schedules for your pets</p>
        </div>

        <div class="card">
            <div class="card-header">
                <h2 class="card-title">Add New Pet</h2>
                <p class="card-description">Register a new pet with their RFID tag</p>
            </div>
            <div class="card-content">
                <form method="POST" action="/register">
                    <div class="form-group">
                        <label for="name">Pet Name</label>
                        <input type="text" id="name" name="name" placeholder="e.g. Rex" required>
                    </div>
                    <div class="form-group">
                        <label for="petUID">RFID Tag UID</label>
                        <div class="input-group">
                            <input type="text" name="uid" id="petUID" placeholder="Scan tag..." required readonly style="flex: 1;">
                            <button type="button" class="button button-secondary" onclick="startScan()">Scan Tag</button>
                        </div>
                    </div>
                    <div id="status" class="alert"></div>
                    <div class="grid">
                        <div class="form-group">
                            <label for="portion">Portion (Seconds)</label>
                            <input type="number" id="portion" name="portion" value="5" min="1" max="30" required>
                        </div>
                        <div class="form-group">
                            <label for="cooldown">Cooldown (Minutes)</label>
                            <input type="number" id="cooldown" name="cooldown" value="60" min="0" required>
                        </div>
                    </div>
                    <div class="form-group">
                        <label for="max_feeds">Maximum Meals per Day</label>
                        <input type="number" id="max_feeds" name="max_feeds" value="3" min="1" required>
                    </div>
                    <button type="submit" class="button button-primary button-full">Save Pet Settings</button>
                </form>
            </div>
        </div>

        <div class="card">
            <div class="card-header">
                <h2 class="card-title">Registered Pets</h2>
                <p class="card-description">Manage your pets</p>
            </div>
            <div class="card-content">
                {% if pets %}
                    <div class="pet-list">
                        {% for pet in pets %}
                        <div class="pet-item" id="pet-{{ pet.id }}">
                            <div class="pet-info">
                                <div class="pet-name">{{ pet.name }}</div>
                                <div class="pet-details">
                                    <span>⏱️ {{ pet.portion_size }}s</span>
                                    <span> • ⏳ {{ pet.cooldown_min }}m</span>
                                    <span> • 🥣 {{ pet.max_daily_feeds }}×</span>
                                    <br>
                                    <span style="font-family: monospace; font-size: 0.75rem;">ID: {{ pet.rfid_uid }}</span>
                                </div>
                            </div>
                            <button class="button button-destructive" onclick="deletePet({{ pet.id }})">Remove</button>
                        </div>
                        {% endfor %}
                    </div>
                {% else %}
                    <div class="empty-state">
                        <div class="empty-state-icon">🐕</div>
                        <div>No pets registered yet</div>
                    </div>
                {% endif %}
            </div>
        </div>

        <div class="card">
            <div class="card-header">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <div style="display:flex; align-items:center; gap: 0.5rem;">
                            <h2 class="card-title">Live Activity Log</h2>
                            <span id="live-indicator" style="height: 8px; width: 8px; background: #22c55e; border-radius: 50%; display: inline-block;"></span>
                        </div>
                        <p class="card-description">Real-time feeding events and denials</p>
                    </div>
                    <button class="button button-destructive" onclick="clearLogs()">Delete</button>
                </div>
            </div>
            <div class="card-content">
                <div id="log-list" class="pet-list">
                    <div class="empty-state" style="padding: 1rem;">Loading logs...</div>
                </div>
            </div>
        </div>
    </div>

<script>
let checkInt;

function startScan() {
    fetch('/start_registration', { method: 'POST' }).then(r => r.json()).then(d => {
        const st = document.getElementById('status');
        st.className = 'alert alert-warning';
        st.style.display = 'block';
        st.innerText = '⏳ Waiting for RFID tag scan...';
        checkInt = setInterval(checkUID, 500);
    });
}

function checkUID() {
    fetch('/get_captured_uid').then(r => r.json()).then(d => {
        if (d.uid) {
            clearInterval(checkInt);
            document.getElementById('petUID').value = d.uid;
            const st = document.getElementById('status');
            st.className = 'alert alert-success';
            st.innerText = '✓ Tag captured successfully!';
        }
    });
}

function deletePet(id) {
    if(confirm('Are you sure you want to remove this pet?')) {
        fetch('/delete/'+id, {method:'POST'}).then(r=>r.json()).then(d=>{ 
            if(d.success) window.location.reload(); 
        });
    }
}

function clearLogs() {
    if(confirm('Clear all logs?')) {
        fetch('/api/logs/clear', {method: 'POST'}).then(r => r.json()).then(d => {
            if(d.success) fetchLogs();
        });
    }
}

function fetchLogs() {
    fetch('/api/logs')
    .then(response => response.json())
    .then(data => {
        const container = document.getElementById('log-list');
        if (data.length === 0) {
            container.innerHTML = '<div class="empty-state" style="padding: 1rem;">No recent activity</div>';
            return;
        }

        let html = '';
        data.forEach(log => {
            const isSuccess = log.event_type === 'Dispensed';
            const badgeClass = isSuccess ? 'badge-success' : 'badge-destructive';
            const timeStr = log.timestamp.split('.')[0]; 

            // Logic for the counter badge
            let counterHtml = '';
            if (log.count > 1) {
                counterHtml = `<span class="counter-badge">× ${log.count}</span>`;
            }

            html += `
            <div class="pet-item">
                <div class="pet-info">
                    <div style="display: flex; align-items: center;">
                        <div class="pet-name">${log.pet_name}</div>
                        ${counterHtml}
                    </div>
                    <div class="pet-details">
                        <span>${timeStr}</span> • <span>${log.details}</span>
                    </div>
                </div>
                <span class="badge ${badgeClass}">${log.event_type}</span>
            </div>
            `;
        });
        container.innerHTML = html;

        const indicator = document.getElementById('live-indicator');
        indicator.style.opacity = '0.5';
        setTimeout(() => indicator.style.opacity = '1', 200);
    });
}

setInterval(fetchLogs, 2000);
fetchLogs();
</script>
</body>
</html>
"""


@app.route("/")
def index():
    init_db()
    db = get_db()
    pets = db.execute("SELECT * FROM pets").fetchall()
    return render_template_string(HTML_PAGE, pets=pets)


@app.post("/start_registration")
def start_registration():
    pending_registration["active"] = True
    pending_registration["last_uid"] = None
    return jsonify({"status": "ready"})


@app.get("/get_captured_uid")
def get_captured_uid():
    uid = pending_registration.get("last_uid")
    if uid:
        pending_registration["last_uid"] = None
        return jsonify({"uid": uid})
    return jsonify({"uid": None})


@app.post("/register")
def register_pet():
    name = request.form.get("name")
    uid = request.form.get("uid")
    portion = request.form.get("portion")
    cooldown = request.form.get("cooldown")
    max_feeds = request.form.get("max_feeds")

    if not name or not uid:
        return "Missing Data", 400

    db = get_db()
    try:
        db.execute("""
            INSERT INTO pets (name, rfid_uid, portion_size, cooldown_min, max_daily_feeds) 
            VALUES (?, ?, ?, ?, ?)
        """, (name, uid, portion, cooldown, max_feeds))
        db.commit()
    except Exception as e:
        return f"Error: {e}", 500

    return ("<script>window.location='/'</script>")


@app.post("/delete/<int:pet_id>")
def delete_pet(pet_id):
    db = get_db()
    db.execute("DELETE FROM pets WHERE id = ?", (pet_id,))
    db.execute("DELETE FROM feeding_logs WHERE pet_id = ?", (pet_id,))
    db.commit()
    return jsonify({"success": True})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)