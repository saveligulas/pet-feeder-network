from flask import Flask, request, g, render_template_string, jsonify
import sqlite3

DB = "pets.db"

app = Flask(__name__)

@app.route('/tag', methods=['POST'])
def scan():
    tag_id = request.json.get('uid')
    print("Received UID:", tag_id)

    # Process the tag here:
    # e.g. check against a database, unlock a door, write to file, etc.

    return {"status": "ok"}

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
        body { font-family: Arial; max-width: 500px; margin: 30px; }
        input, button { padding: 10px; margin: 5px 0; width: 100%; }
        .pet { padding: 10px; border: 1px solid #ccc; margin-top: 10px; }
    </style>
</head>
<body>
<h2>Add New Pet</h2>

<form method="POST" action="/register">
    <input name="name" placeholder="Pet Name">
    <input name="uid" placeholder="RFID Chip UID">
    <button type="submit">Save</button>
</form>

<h2>Registered Pets</h2>
{% for pet in pets %}
<div class="pet">
    <strong>{{ pet.name }}</strong><br>
    UID: {{ pet.rfid_uid }}
</div>
{% endfor %}

</body>
</html>
"""

@app.route("/")
def index():
    db = get_db()
    pets = db.execute("SELECT * FROM pets").fetchall()
    return render_template_string(HTML_PAGE, pets=pets)

@app.post("/register")
def register_pet():
    name = request.form.get("name")
    uid = request.form.get("uid")

    if not name or not uid:
        return "Missing name or UID", 400

    db = get_db()
    db.execute("INSERT INTO pets (name, rfid_uid) VALUES (?, ?)", (name, uid))
    db.commit()

    return ("<script>window.location='/'</script>")

@app.get("/feed_check")
def feed_check():
    uid = request.args.get("uid")

    if not uid:
        return jsonify({"status": "error", "message": "missing uid"})

    db = get_db()
    pet = db.execute("SELECT * FROM pets WHERE rfid_uid = ?", (uid,)).fetchone()

    if pet:
        return jsonify({
            "status": "ok",
            "pet": pet["name"]
        })
    else:
        return jsonify({
            "status": "unknown"
        })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
