from flask import Flask, request, g, render_template_string, jsonify
import sqlite3
from datetime import datetime

DB = "pets.db"

app = Flask(__name__)

pending_registration = {"active": False, "timestamp": None}


@app.route('/tag', methods=['POST'])
def scan():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    tag_id = data.get('uid')
    print(f"Received scan for UID: {tag_id}")

    if not tag_id:
        return jsonify({"error": "UID missing"}), 400

    # Check if we're in registration mode
    if pending_registration["active"]:
        pending_registration["active"] = False

        # Check if tag is already registered
        db = get_db()
        existing_pet = db.execute("SELECT * FROM pets WHERE rfid_uid = ?", (tag_id,)).fetchone()

        if existing_pet:
            pending_registration["last_uid"] = None
            pending_registration["error"] = f"Tag already registered to {existing_pet['name']}"
            print(f"Registration failed: Tag already belongs to {existing_pet['name']}")
            return jsonify({
                "status": "error",
                "message": f"Tag already registered to {existing_pet['name']}",
                "uid": tag_id
            }), 409

        pending_registration["last_uid"] = tag_id
        pending_registration["error"] = None
        print(f"Tag captured for registration: {tag_id}")
        return jsonify({
            "status": "registration",
            "message": "Tag captured for registration",
            "uid": tag_id
        }), 200

    db = get_db()
    pet = db.execute("SELECT * FROM pets WHERE rfid_uid = ?", (tag_id,)).fetchone()

    if pet:
        # TODO: add logic for timing interval
        print(f"Access GRANTED for {pet['name']}")
        return jsonify({
            "status": "authorized",
            "message": "Feeding allowed",
            "pet_name": pet['name']
        }), 200
    else:
        print("Access DENIED: Unknown Tag")
        return jsonify({
            "status": "denied",
            "message": "Pet not recognized"
        }), 403


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


HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Pet Feeder Manager</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        :root {
            --background: 0 0% 100%;
            --foreground: 222.2 84% 4.9%;
            --card: 0 0% 100%;
            --card-foreground: 222.2 84% 4.9%;
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

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: hsl(var(--background));
            color: hsl(var(--foreground));
            line-height: 1.5;
            padding: 2rem 1rem;
        }

        .container {
            max-width: 600px;
            margin: 0 auto;
        }

        h1 {
            font-size: 2rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
            letter-spacing: -0.025em;
        }

        .subtitle {
            color: hsl(var(--muted-foreground));
            margin-bottom: 2rem;
        }

        .card {
            background-color: hsl(var(--card));
            border: 1px solid hsl(var(--border));
            border-radius: var(--radius);
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1);
        }

        .card-title {
            font-size: 1.25rem;
            font-weight: 600;
            margin-bottom: 1rem;
        }

        .form-group {
            margin-bottom: 1rem;
        }

        label {
            display: block;
            font-size: 0.875rem;
            font-weight: 500;
            margin-bottom: 0.5rem;
        }

        input[type="text"] {
            width: 100%;
            padding: 0.625rem 0.75rem;
            font-size: 0.875rem;
            border: 1px solid hsl(var(--input));
            border-radius: calc(var(--radius) - 2px);
            background-color: hsl(var(--background));
            transition: all 0.2s;
        }

        input[type="text"]:focus {
            outline: none;
            border-color: hsl(var(--ring));
            box-shadow: 0 0 0 3px hsl(var(--ring) / 0.1);
        }

        input[type="text"]:disabled,
        input[type="text"]:read-only {
            background-color: hsl(var(--muted));
            cursor: not-allowed;
            opacity: 0.7;
        }

        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 0.625rem 1rem;
            font-size: 0.875rem;
            font-weight: 500;
            border-radius: calc(var(--radius) - 2px);
            border: none;
            cursor: pointer;
            transition: all 0.2s;
            white-space: nowrap;
            width: 100%;
        }

        .btn:disabled {
            pointer-events: none;
            opacity: 0.5;
        }

        .btn-primary {
            background-color: hsl(var(--primary));
            color: hsl(var(--primary-foreground));
        }

        .btn-primary:hover:not(:disabled) {
            background-color: hsl(var(--primary) / 0.9);
        }

        .btn-secondary {
            background-color: hsl(var(--secondary));
            color: hsl(var(--secondary-foreground));
            border: 1px solid hsl(var(--border));
        }

        .btn-secondary:hover:not(:disabled) {
            background-color: hsl(var(--accent));
        }

        .btn-secondary.active {
            background-color: hsl(36 100% 50%);
            color: white;
            border-color: hsl(36 100% 50%);
            animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
        }

        .btn-destructive {
            background-color: hsl(var(--destructive));
            color: hsl(var(--destructive-foreground));
        }

        .btn-destructive:hover:not(:disabled) {
            background-color: hsl(var(--destructive) / 0.9);
        }

        .btn-icon {
            width: auto;
            padding: 0.5rem;
        }

        @keyframes pulse {
            0%, 100% {
                opacity: 1;
            }
            50% {
                opacity: 0.7;
            }
        }

        .alert {
            padding: 1rem;
            border-radius: calc(var(--radius) - 2px);
            font-size: 0.875rem;
            display: none;
            animation: slideIn 0.3s ease-out;
        }

        .alert.show {
            display: block;
        }

        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(-10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .alert-warning {
            background-color: hsl(48 96% 89%);
            border: 1px solid hsl(48 96% 76%);
            color: hsl(25 95% 27%);
        }

        .alert-success {
            background-color: hsl(142 76% 87%);
            border: 1px solid hsl(142 76% 73%);
            color: hsl(142 71% 20%);
        }

        .alert-error {
            background-color: hsl(0 93% 94%);
            border: 1px solid hsl(0 93% 82%);
            color: hsl(0 84% 37%);
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
            background-color: hsl(var(--card));
            transition: all 0.2s;
        }

        .pet-item:hover {
            border-color: hsl(var(--ring));
            box-shadow: 0 2px 8px 0 rgb(0 0 0 / 0.1);
        }

        .pet-info {
            flex: 1;
        }

        .pet-name {
            font-weight: 600;
            font-size: 1rem;
            margin-bottom: 0.25rem;
        }

        .pet-uid {
            font-size: 0.75rem;
            color: hsl(var(--muted-foreground));
            font-family: 'Courier New', monospace;
        }

        .badge {
            display: inline-flex;
            align-items: center;
            padding: 0.125rem 0.625rem;
            font-size: 0.75rem;
            font-weight: 600;
            border-radius: 9999px;
            background-color: hsl(var(--secondary));
            color: hsl(var(--secondary-foreground));
            margin-left: 0.5rem;
        }

        .empty-state {
            text-align: center;
            padding: 3rem 1rem;
            color: hsl(var(--muted-foreground));
        }

        .empty-state-icon {
            font-size: 3rem;
            margin-bottom: 1rem;
            opacity: 0.5;
        }

        @media (max-width: 640px) {
            body {
                padding: 1rem 0.5rem;
            }

            .card {
                padding: 1rem;
            }

            h1 {
                font-size: 1.5rem;
            }
        }

        .icon {
            display: inline-block;
            margin-right: 0.5rem;
        }

        .button-group {
            display: flex;
            flex-direction: column;
            row-gap: 0.75rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🐾 Pet Feeder Manager</h1>
        <p class="subtitle">Manage RFID-enabled pet access control</p>

        <div class="card">
            <h2 class="card-title">Add New Pet</h2>

            <form id="petForm" method="POST" action="/register">
                <div class="form-group">
                    <label for="petName">Pet Name</label>
                    <input type="text" name="name" id="petName" placeholder="Enter pet name" required>
                </div>

                <div class="form-group">
                    <label for="petUID">RFID Chip UID</label>
                    <input type="text" name="uid" id="petUID" placeholder="Scan tag to capture UID" required readonly>
                </div>

                <div class="button-group">
                    <button type="button" class="btn btn-secondary" id="registerTagBtn" onclick="startRegistration()">
                        <span class="icon">📡</span> Register Tag (Scan Next)
                    </button>

                    <div id="status" class="alert"></div>

                    <button type="submit" class="btn btn-primary" id="saveBtn">
                        <span class="icon">💾</span> Save Pet
                    </button>
                </div>
            </form>
        </div>

        <div class="card">
            <h2 class="card-title">Registered Pets <span class="badge" id="petCount">{{ pets|length }}</span></h2>

            {% if pets %}
            <div class="pet-list">
                {% for pet in pets %}
                <div class="pet-item" id="pet-{{ pet.id }}">
                    <div class="pet-info">
                        <div class="pet-name">{{ pet.name }}</div>
                        <div class="pet-uid">{{ pet.rfid_uid }}</div>
                    </div>
                    <button class="btn btn-destructive btn-icon" onclick="deletePet({{ pet.id }}, '{{ pet.name }}')" title="Delete {{ pet.name }}">
                        🗑️
                    </button>
                </div>
                {% endfor %}
            </div>
            {% else %}
            <div class="empty-state">
                <div class="empty-state-icon">🐕</div>
                <p>No pets registered yet</p>
                <p style="font-size: 0.875rem; margin-top: 0.5rem;">Add your first pet to get started!</p>
            </div>
            {% endif %}
        </div>
    </div>

<script>
let checkInterval;

function startRegistration() {
    const btn = document.getElementById('registerTagBtn');
    const status = document.getElementById('status');
    const uidInput = document.getElementById('petUID');

    fetch('/start_registration', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            btn.classList.add('active');
            btn.innerHTML = '<span class="icon">⏳</span> Waiting for tag scan...';
            btn.disabled = true;

            status.className = 'alert alert-warning show';
            status.textContent = '⚡ Please scan the RFID tag now...';

            checkInterval = setInterval(checkForUID, 500);

            setTimeout(() => {
                if (checkInterval) {
                    clearInterval(checkInterval);
                    resetRegistration();
                    status.className = 'alert alert-error show';
                    status.textContent = '⏱️ Registration timeout. Please try again.';
                }
            }, 30000);
        });
}

function checkForUID() {
    fetch('/get_captured_uid')
        .then(r => r.json())
        .then(data => {
            if (data.uid) {
                clearInterval(checkInterval);
                checkInterval = null;

                const uidInput = document.getElementById('petUID');
                const status = document.getElementById('status');

                uidInput.value = data.uid;

                status.className = 'alert alert-success show';
                status.textContent = '✅ Tag captured: ' + data.uid;

                resetRegistration();
            }
        });
}

function resetRegistration() {
    const btn = document.getElementById('registerTagBtn');
    btn.classList.remove('active');
    btn.innerHTML = '<span class="icon">📡</span> Register Tag (Scan Next)';
    btn.disabled = false;
}

function deletePet(petId, petName) {
    if (!confirm(`Are you sure you want to delete ${petName}?`)) {
        return;
    }

    fetch(`/delete/${petId}`, { 
        method: 'POST'
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            const petElement = document.getElementById(`pet-${petId}`);
            petElement.style.transition = 'all 0.3s ease-out';
            petElement.style.opacity = '0';
            petElement.style.transform = 'translateX(-20px)';

            setTimeout(() => {
                petElement.remove();
                updatePetCount();
            }, 300);
        } else {
            alert('Failed to delete pet: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(err => {
        alert('Error deleting pet: ' + err);
    });
}

function updatePetCount() {
    const petList = document.querySelectorAll('.pet-item');
    const countBadge = document.getElementById('petCount');
    if (countBadge) {
        countBadge.textContent = petList.length;
    }
}
</script>

</body>
</html>
"""


@app.route("/")
def index():
    db = get_db()
    db.execute("CREATE TABLE IF NOT EXISTS pets (id INTEGER PRIMARY KEY, name TEXT, rfid_uid TEXT)")

    pets = db.execute("SELECT * FROM pets").fetchall()
    return render_template_string(HTML_PAGE, pets=pets)


@app.post("/start_registration")
def start_registration():
    pending_registration["active"] = True
    pending_registration["timestamp"] = datetime.now()
    pending_registration["last_uid"] = None
    print("Registration mode activated")
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

    if not name or not uid:
        return "Missing name or UID", 400

    db = get_db()
    db.execute("CREATE TABLE IF NOT EXISTS pets (id INTEGER PRIMARY KEY, name TEXT, rfid_uid TEXT)")

    db.execute("INSERT INTO pets (name, rfid_uid) VALUES (?, ?)", (name, uid))
    db.commit()

    return ("<script>window.location='/'</script>")


@app.post("/delete/<int:pet_id>")
def delete_pet(pet_id):
    try:
        db = get_db()

        pet = db.execute("SELECT * FROM pets WHERE id = ?", (pet_id,)).fetchone()
        if not pet:
            return jsonify({"success": False, "error": "Pet not found"}), 404

        db.execute("DELETE FROM pets WHERE id = ?", (pet_id,))
        db.commit()

        print(f"Deleted pet: {pet['name']} (ID: {pet_id})")
        return jsonify({"success": True, "message": f"Pet {pet['name']} deleted"})

    except Exception as e:
        print(f"Error deleting pet: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)