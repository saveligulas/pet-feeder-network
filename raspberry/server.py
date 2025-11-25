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
        pending_registration["last_uid"] = tag_id
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
    <style>
        * {box-sizing: border-box}
        body { font-family: Arial; max-width: 500px; margin: 30px; }
        input, button { padding: 10px; margin: 5px 0; width: 100%; }
        .pet { 
            padding: 10px; 
            border: 1px solid #ccc; 
            margin-top: 10px; 
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-radius: 5px;
        }
        .pet-info {
            flex-grow: 1;
        }
        .delete-btn {
            background-color: #dc3545;
            color: white;
            border: none;
            padding: 8px 15px;
            border-radius: 5px;
            cursor: pointer;
            margin-left: 10px;
            font-size: 14px;
        }
        .delete-btn:hover {
            background-color: #c82333;
        }
        .register-btn { background-color: #4CAF50; color: white; border: none; cursor: pointer; }
        .register-btn.active { background-color: #ff9800; animation: pulse 1s infinite; }
        .register-btn:disabled { background-color: #ccc; cursor: not-allowed; }
        .status { padding: 10px; margin: 10px 0; border-radius: 5px; display: none; }
        .status.show { display: block; }
        .status.waiting { background-color: #fff3cd; border: 1px solid #ffc107; }
        .status.success { background-color: #d4edda; border: 1px solid #28a745; }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.7; }
        }
    </style>
</head>
<body>
<h2>Add New Pet</h2>

<form id="petForm" method="POST" action="/register">
    <input name="name" id="petName" placeholder="Pet Name" required>
    <input name="uid" id="petUID" placeholder="RFID Chip UID" required readonly>
    <button type="button" class="register-btn" id="registerTagBtn" onclick="startRegistration()">
        Register Tag (Scan Next)
    </button>
    <div id="status" class="status"></div>
    <button type="submit" id="saveBtn">Save Pet</button>
</form>

<h2>Registered Pets</h2>
{% for pet in pets %}
<div class="pet" id="pet-{{ pet.id }}">
    <div class="pet-info">
        <strong>{{ pet.name }}</strong><br>
        UID: {{ pet.rfid_uid }}
    </div>
    <button class="delete-btn" onclick="deletePet({{ pet.id }}, '{{ pet.name }}')">
        Delete
    </button>
</div>
{% endfor %}

<script>
let checkInterval;

function startRegistration() {
    const btn = document.getElementById('registerTagBtn');
    const status = document.getElementById('status');
    const uidInput = document.getElementById('petUID');

    // Activate registration mode on server
    fetch('/start_registration', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            btn.classList.add('active');
            btn.textContent = 'Waiting for tag scan...';
            btn.disabled = true;

            status.className = 'status waiting show';
            status.textContent = 'Please scan the RFID tag now...';

            // Poll for the captured UID
            checkInterval = setInterval(checkForUID, 500);

            // Timeout after 30 seconds
            setTimeout(() => {
                if (checkInterval) {
                    clearInterval(checkInterval);
                    resetRegistration();
                    status.className = 'status show';
                    status.style.backgroundColor = '#f8d7da';
                    status.style.borderColor = '#dc3545';
                    status.textContent = 'Registration timeout. Please try again.';
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

                status.className = 'status success show';
                status.textContent = 'Tag captured: ' + data.uid;

                resetRegistration();
            }
        });
}

function resetRegistration() {
    const btn = document.getElementById('registerTagBtn');
    btn.classList.remove('active');
    btn.textContent = '📡 Register Tag (Scan Next)';
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
            // Remove the pet element from the DOM
            const petElement = document.getElementById(`pet-${petId}`);
            petElement.style.transition = 'opacity 0.3s';
            petElement.style.opacity = '0';
            setTimeout(() => {
                petElement.remove();
            }, 300);
        } else {
            alert('Failed to delete pet: ' + (data.error || 'Unknown error'));
        }
    })
    .catch(err => {
        alert('Error deleting pet: ' + err);
    });
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