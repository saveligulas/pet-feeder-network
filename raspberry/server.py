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
def close_db(exception):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    """Initialize tables with new feeding settings"""
    with app.app_context():
        db = get_db()
        db.execute("""
            CREATE TABLE IF NOT EXISTS pets (
                id INTEGER PRIMARY KEY, 
                name TEXT, 
                rfid_uid TEXT,
                portion_size INTEGER DEFAULT 5,    -- Motor run time in seconds
                cooldown_min INTEGER DEFAULT 60,   -- Minutes between meals
                max_daily_feeds INTEGER DEFAULT 3  -- Max meals per 24h
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS feeding_logs (
                id INTEGER PRIMARY KEY, 
                pet_id INTEGER, 
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(pet_id) REFERENCES pets(id)
            )
        """)
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
            "SELECT COUNT(*) FROM feeding_logs WHERE pet_id = ? AND timestamp >= ?",
            (pet_id, today_start.strftime('%Y-%m-%d %H:%M:%S'))
        ).fetchone()[0]

        if feed_count >= pet['max_daily_feeds']:
            print(f"DENIED: {pet_name} reached daily limit ({feed_count}/{pet['max_daily_feeds']})")
            return jsonify({
                "status": "denied",
                "message": "Daily limit reached",
                "current_feeds": feed_count,
                "max_feeds": pet['max_daily_feeds']
            }), 403

        last_feed = db.execute(
            "SELECT timestamp FROM feeding_logs WHERE pet_id = ? ORDER BY timestamp DESC LIMIT 1",
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
                print(f"DENIED: {pet_name} on diet. Wait {wait_time} min.")
                return jsonify({
                    "status": "denied",
                    "message": "Diet active",
                    "next_feed_in_minutes": wait_time
                }), 403

        # C. AUTHORIZED - Log it and Dispens
        db.execute(
            "INSERT INTO feeding_logs (pet_id, timestamp) VALUES (?, ?)",
            (pet_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f'))
        )
        db.commit()

        print(f"ACCESS GRANTED: {pet_name} | Dispensing for {pet['portion_size']}s")

        return jsonify({
            "status": "authorized",
            "message": "Feeding allowed",
            "pet_name": pet_name,
            "portion_time": pet['portion_size'],  # Hardware uses this to run motor
            "feeds_today": feed_count + 1
        }), 200
    else:
        print("Access DENIED: Unknown Tag")
        return jsonify({"status": "denied", "message": "Pet not recognized"}), 403


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
            --popover: 0 0% 100%;
            --popover-foreground: 222.2 84% 4.9%;
            --primary: 222.2 47.4% 11.2%;
            --primary-foreground: 210 40% 98%;
            --secondary: 210 40% 96.1%;
            --secondary-foreground: 222.2 47.4% 11.2%;
            --muted: 210 40% 96.1%;
            --muted-foreground: 215.4 16.3% 46.9%;
            --accent: 210 40% 96.1%;
            --accent-foreground: 222.2 47.4% 11.2%;
            --destructive: 0 84.2% 60.2%;
            --destructive-foreground: 210 40% 98%;
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

        .header {
            margin-bottom: 2rem;
        }

        h1 {
            font-size: 2rem;
            font-weight: 700;
            letter-spacing: -0.025em;
            margin-bottom: 0.5rem;
        }

        .subtitle {
            color: hsl(var(--muted-foreground));
            font-size: 0.875rem;
        }

        .card {
            background: hsl(var(--card));
            border: 1px solid hsl(var(--border));
            border-radius: var(--radius);
            margin-bottom: 1.5rem;
        }

        .card-header {
            padding: 1.5rem;
            border-bottom: 1px solid hsl(var(--border));
        }

        .card-title {
            font-size: 1.125rem;
            font-weight: 600;
            letter-spacing: -0.025em;
        }

        .card-description {
            color: hsl(var(--muted-foreground));
            font-size: 0.875rem;
            margin-top: 0.25rem;
        }

        .card-content {
            padding: 1.5rem;
        }

        .form-group {
            margin-bottom: 1.5rem;
        }

        .form-group:last-child {
            margin-bottom: 0;
        }

        label {
            display: block;
            font-size: 0.875rem;
            font-weight: 500;
            margin-bottom: 0.5rem;
            color: hsl(var(--foreground));
        }

        input[type="text"],
        input[type="number"] {
            width: 100%;
            height: 2.5rem;
            padding: 0.5rem 0.75rem;
            font-size: 0.875rem;
            border: 1px solid hsl(var(--input));
            border-radius: calc(var(--radius) - 2px);
            background: hsl(var(--background));
            transition: all 0.15s;
        }

        input:focus {
            outline: none;
            border-color: hsl(var(--ring));
            box-shadow: 0 0 0 3px hsl(var(--ring) / 0.1);
        }

        input:read-only {
            background: hsl(var(--muted));
            color: hsl(var(--muted-foreground));
            cursor: not-allowed;
        }

        .input-group {
            display: flex;
            gap: 0.5rem;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 1rem;
        }

        .button {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: calc(var(--radius) - 2px);
            font-size: 0.875rem;
            font-weight: 500;
            height: 2.5rem;
            padding: 0 1rem;
            border: none;
            cursor: pointer;
            transition: all 0.15s;
            white-space: nowrap;
        }

        .button:disabled {
            pointer-events: none;
            opacity: 0.5;
        }

        .button-primary {
            background: hsl(var(--primary));
            color: hsl(var(--primary-foreground));
        }

        .button-primary:hover {
            background: hsl(var(--primary) / 0.9);
        }

        .button-secondary {
            background: hsl(var(--secondary));
            color: hsl(var(--secondary-foreground));
        }

        .button-secondary:hover {
            background: hsl(var(--secondary) / 0.8);
        }

        .button-destructive {
            background: hsl(var(--destructive));
            color: hsl(var(--destructive-foreground));
            height: 2rem;
            padding: 0 0.75rem;
            font-size: 0.8125rem;
        }

        .button-destructive:hover {
            background: hsl(var(--destructive) / 0.9);
        }

        .button-full {
            width: 100%;
        }

        .alert {
            padding: 0.75rem 1rem;
            border-radius: calc(var(--radius) - 2px);
            font-size: 0.875rem;
            margin-bottom: 1rem;
            display: none;
            border: 1px solid;
        }

        .alert-warning {
            background: hsl(48 96% 89%);
            color: hsl(25 95% 33%);
            border-color: hsl(48 96% 76%);
        }

        .alert-success {
            background: hsl(143 85% 96%);
            color: hsl(140 100% 27%);
            border-color: hsl(145 92% 91%);
        }

        .pet-list {
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }

        .pet-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 1rem;
            border: 1px solid hsl(var(--border));
            border-radius: calc(var(--radius) - 2px);
            transition: all 0.15s;
        }

        .pet-item:hover {
            background: hsl(var(--accent));
        }

        .pet-info {
            flex: 1;
        }

        .pet-name {
            font-weight: 600;
            font-size: 1rem;
            margin-bottom: 0.25rem;
        }

        .pet-details {
            font-size: 0.8125rem;
            color: hsl(var(--muted-foreground));
            display: flex;
            flex-wrap: wrap;
            gap: 0.75rem;
            margin-bottom: 0.25rem;
        }

        .pet-uid {
            font-size: 0.75rem;
            color: hsl(var(--muted-foreground));
            font-family: monospace;
        }

        .badge {
            display: inline-flex;
            align-items: center;
            border-radius: 9999px;
            padding: 0.125rem 0.625rem;
            font-size: 0.75rem;
            font-weight: 600;
            background: hsl(var(--secondary));
            color: hsl(var(--secondary-foreground));
        }

        .empty-state {
            text-align: center;
            padding: 3rem 1rem;
            color: hsl(var(--muted-foreground));
        }

        .empty-state-icon {
            font-size: 3rem;
            margin-bottom: 0.5rem;
            opacity: 0.5;
        }

        @media (max-width: 640px) {
            .grid {
                grid-template-columns: 1fr;
            }

            .pet-item {
                flex-direction: column;
                align-items: flex-start;
                gap: 0.75rem;
            }

            .button-destructive {
                width: 100%;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🐾 Smart Pet Feeder</h1>
            <p class="subtitle">Manage portions and feeding schedules for your pets</p>
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
                            <button type="button" class="button button-secondary" onclick="startScan()">
                                📡 Scan Tag
                            </button>
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

                    <button type="submit" class="button button-primary button-full">
                        💾 Save Pet Settings
                    </button>
                </form>
            </div>
        </div>

        <div class="card">
            <div class="card-header">
                <h2 class="card-title">Registered Pets</h2>
                <p class="card-description">Manage your pets and their feeding schedules</p>
            </div>
            <div class="card-content">
                {% if pets %}
                    <div class="pet-list">
                        {% for pet in pets %}
                        <div class="pet-item" id="pet-{{ pet.id }}">
                            <div class="pet-info">
                                <div class="pet-name">{{ pet.name }}</div>
                                <div class="pet-details">
                                    <span>⏱️ {{ pet.portion_size }}s portion</span>
                                    <span>⏳ {{ pet.cooldown_min }}m cooldown</span>
                                    <span>🥣 {{ pet.max_daily_feeds }}× daily</span>
                                </div>
                                <div class="pet-uid">{{ pet.rfid_uid }}</div>
                            </div>
                            <button class="button button-destructive" onclick="deletePet({{ pet.id }})">
                                Remove
                            </button>
                        </div>
                        {% endfor %}
                    </div>
                {% else %}
                    <div class="empty-state">
                        <div class="empty-state-icon">🐕</div>
                        <div>No pets registered yet</div>
                        <div style="font-size: 0.8125rem; margin-top: 0.25rem;">Add your first pet above to get started</div>
                    </div>
                {% endif %}
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
    if(confirm('Are you sure you want to remove this pet? This will also delete their feeding history.')) {
        fetch('/delete/'+id, {method:'POST'}).then(r=>r.json()).then(d=>{ 
            if(d.success) window.location.reload(); 
        });
    }
}
</script>
</body>
</html>
"""


# --- FRONTEND ROUTES ---
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
        pending_registration["last_uid"] = None  # Consume it
        return jsonify({"uid": uid})
    return jsonify({"uid": None})


@app.post("/register")
def register_pet():
    # Capture all new form fields
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
    app.run(host="0.0.0.0", port=5000, debug=True)