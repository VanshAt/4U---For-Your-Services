from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3, os, uuid, datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

DB_PATH = Path(__file__).resolve().parent / "database" / "business.db"
os.makedirs(DB_PATH.parent, exist_ok=True)

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE,
            title TEXT,
            description TEXT,
            starting_price TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id TEXT PRIMARY KEY,
            name TEXT,
            phone TEXT,
            address TEXT,
            pincode TEXT,
            service_id INTEGER,
            status TEXT,
            assigned_to TEXT,
            created_at TEXT
        )
    """)

    r = cur.execute("SELECT COUNT(*) as c FROM services").fetchone()

    if r and r["c"] == 0:
        services = [
            ("ac_clean", "AC Cleaning & Servicing", "Filter wash, coil clean, water drain & basic check", "₹499"),
            ("wm_clean", "Washing Machine Cleaning", "Drum sanitization & pipe check", "₹399"),
            ("fridge_clean", "Fridge Cleaning", "Coil clean, gasket check, cooling basic check", "₹349"),
            ("chimney_clean", "Chimney Deep Clean", "Degrease filters, motor check", "₹699"),
            ("fan_clean", "Fan & Exhaust Cleaning", "Blade clean, motor dust removal", "₹149"),
            ("geyser", "Geyser Repair & Service", "Heating & thermostat checks", "₹149")
        ]
        cur.executemany(
            "INSERT INTO services (key,title,description,starting_price) VALUES (?,?,?,?)",
            services
        )

    conn.commit()
    conn.close()

# ------------------------------------------------
# FLASK APP CONFIG
# ------------------------------------------------

app = Flask(__name__, static_folder="frontend", template_folder="frontend")
CORS(app)

init_db()

# --------------------------------------------
# SERVE FRONTEND (CORRECTED)
# --------------------------------------------
@app.route("/")
def home():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/<path:path>", methods=["GET"])
def static_proxy(path):
    return send_from_directory(app.static_folder, path)

# --------------------------------------------
# API ROUTES
# --------------------------------------------
@app.route("/api/services", methods=["GET"])
def services():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, key, title, description, starting_price FROM services ORDER BY id"
    ).fetchall()
    conn.close()
    return jsonify({"ok": True, "services": [dict(r) for r in rows]})

@app.route("/api/book", methods=["POST"])
def create_booking():
    data = request.get_json(force=True)

    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    address = (data.get("address") or "").strip()
    pincode = (data.get("pincode") or "").strip()
    service_id = data.get("service_id")

    if not (name and phone and address and pincode and service_id):
        return jsonify({"ok": False, "error": "Missing fields"}), 400

    bid = str(uuid.uuid4())[:8]
    now = datetime.datetime.utcnow().isoformat()

    conn = get_conn()
    conn.execute(
        "INSERT INTO bookings (id,name,phone,address,pincode,service_id,status,created_at) VALUES (?,?,?,?,?,?,?,?)",
        (bid, name, phone, address, pincode, service_id, "received", now),
    )
    conn.commit()
    conn.close()

    admin_wh = os.getenv("ADMIN_WHATSAPP", "")
    text = f"New Booking%0AName:{name}%0APhone:{phone}%0AServiceID:{service_id}%0AAddress:{address}"

    wa_link = f"https://wa.me/{admin_wh}?text={text}" if admin_wh else ""

    return jsonify({"ok": True, "id": bid, "wa_link": wa_link})

# --------------------------------------------
# START SERVER
# --------------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
