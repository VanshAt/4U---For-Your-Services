from flask import Flask, request, jsonify, send_from_directory, render_template
from flask_cors import CORS
import sqlite3, os, uuid, datetime
from pathlib import Path
from dotenv import load_dotenv

# Optional Twilio import (if installed/configured)
try:
    from twilio.rest import Client as TwilioClient
except Exception:
    TwilioClient = None

# load .env
load_dotenv(dotenv_path=Path(__file__).parent / ".env")

# Database path
DB_PATH = Path(__file__).resolve().parent / "database" / "business.db"
os.makedirs(DB_PATH.parent, exist_ok=True)

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # services table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE,
            title TEXT,
            description TEXT,
            starting_price TEXT
        )
    """)

    # bookings table
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

    # technicians (if needed)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS technicians (
            id TEXT PRIMARY KEY,
            name TEXT,
            phone TEXT,
            areas_csv TEXT,
            services_csv TEXT,
            owner_name TEXT,
            created_at TEXT
        )
    """)

    # seed services: update as requested
    r = cur.execute("SELECT COUNT(*) as c FROM services").fetchone()
    if r and r["c"] == 0:
        services = [
            ("ac_clean", "AC Cleaning & Servicing", "Filter wash, coil clean, water drain & basic check", "₹399"),
            ("wm_clean", "Washing Machine Cleaning", "Drum sanitization & pipe check", "₹399"),
            ("fridge_clean", "Fridge Cleaning", "Coil clean, gasket check, cooling basic check", "₹349"),
            ("chimney_clean", "Chimney Deep Clean", "Degrease filters, motor check", "₹699"),
            # removed fan_clean & exhaust as per request (do not seed)
            ("geyser", "Geyser Repair & Service", "Heating & thermostat checks", "₹249"),
            ("microwave", "Microwave Repair & Service", "Heating element, magnetron check, door & control fix", "₹299")
        ]
        cur.executemany("INSERT INTO services (key,title,description,starting_price) VALUES (?,?,?,?)", services)

    conn.commit()
    conn.close()

# Initialize DB
init_db()

# Flask app config
app = Flask(__name__, static_folder="frontend", template_folder="frontend")
CORS(app)

# Twilio setup (optional)
TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "")  # e.g., 'whatsapp:+1415xxxxxx'
BRAND_LOGO_URL = os.getenv("BRAND_LOGO_URL", "")  # optional image url to send

twilio_client = None
if TWILIO_SID and TWILIO_TOKEN and TwilioClient:
    try:
        twilio_client = TwilioClient(TWILIO_SID, TWILIO_TOKEN)
    except Exception:
        twilio_client = None

def send_whatsapp_via_twilio(to_number, text=None, media_url=None):
    """
    Send a WhatsApp message via Twilio if configured.
    to_number must be like 'whatsapp:+91xxxxxxxxxx' or 'whatsapp:+1...'
    Returns True if sent, else False (or raises error).
    """
    if not twilio_client:
        return False
    try:
        msg_data = {"body": text, "from_": TWILIO_WHATSAPP_FROM, "to": to_number}
        if media_url:
            msg_data["media_url"] = [media_url]
        twilio_client.messages.create(**msg_data)
        return True
    except Exception as e:
        # log if needed
        print("Twilio send error:", e)
        return False

def check_admin_token(req):
    token = req.headers.get("x-admin-token") or request.args.get("token")
    return token and token == os.getenv("ADMIN_TOKEN", "")

# Serve index
@app.route("/")
def home():
    return send_from_directory(app.static_folder, "index.html")

# Serve static files + SPA fallback
@app.route("/<path:path>", methods=["GET"])
def static_proxy(path):
    # serve static frontend files
    if (Path(app.static_folder) / path).exists():
        return send_from_directory(app.static_folder, path)
    # fallback
    return send_from_directory(app.static_folder, "index.html")

# Public API: get services
@app.route("/api/services", methods=["GET"])
def services():
    conn = get_conn()
    rows = conn.execute("SELECT id,key,title,description,starting_price FROM services ORDER BY id").fetchall()
    conn.close()
    return jsonify({"ok": True, "services": [dict(r) for r in rows]})

# Create booking
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

    # create booking id
    bid = "4U-" + str(uuid.uuid4())[:8]
    now = datetime.datetime.utcnow().isoformat()

    conn = get_conn()
    conn.execute(
        "INSERT INTO bookings (id,name,phone,address,pincode,service_id,status,created_at) VALUES (?,?,?,?,?,?,?,?)",
        (bid, name, phone, address, pincode, service_id, "received", now),
    )
    conn.commit()
    conn.close()

    # create whatsapp link for admin (manual)
    admin_wh = os.getenv("ADMIN_WHATSAPP", "")  # should be like '9198xxxxxxx' without plus
    # format the message to be human-friendly and url-encoded
    text = (
        f"🔔 NEW BOOKING\n\n"
        f"Job ID: {bid}\n"
        f"Name: {name}\n"
        f"Phone: {phone}\n"
        f"Service ID: {service_id}\n"
        f"Address: {address}\n"
        f"Pincode: {pincode}\n"
    )
    text_enc = text.replace("\n", "%0A")
    wa_link = f"https://wa.me/{admin_wh}?text={text_enc}" if admin_wh else ""

    # --- Send auto messages via Twilio if configured ---
    twilio_sent = False
    try:
        if twilio_client and TWILIO_WHATSAPP_FROM:
            # Compose two messages
            # Message 1: Confirmation to user
            msg1 = (
                "✅ Your service is booked via 4U.\n"
                "For safety & 7-day guarantee, please communicate only through this number."
            )
            # Message 2: Job ID notification (follow-up)
            msg2 = f"📋 Your service (Job ID: {bid}) is recorded. If any issue arises, reply here."

            # To user number: ensure format 'whatsapp:+<country><number>'
            # if user sent without country prefix, try to assume +91
            user_phone_raw = phone
            if user_phone_raw.startswith("+"):
                user_to = "whatsapp:" + user_phone_raw
            elif user_phone_raw.startswith("91") and len(user_phone_raw) >= 10:
                user_to = "whatsapp:+" + user_phone_raw
            else:
                # assume India if not provided
                user_to = "whatsapp:+91" + user_phone_raw

            # send first message (optionally with brand logo as media)
            media = BRAND_LOGO_URL if BRAND_LOGO_URL else None
            sent1 = send_whatsapp_via_twilio(user_to, text=msg1, media_url=media)
            # send second follow-up
            sent2 = send_whatsapp_via_twilio(user_to, text=msg2, media_url=None)

            twilio_sent = bool(sent1 or sent2)
    except Exception as e:
        print("Error sending Twilio messages:", e)
        twilio_sent = False

    return jsonify({"ok": True, "id": bid, "wa_link": wa_link, "twilio_sent": twilio_sent})

# Admin endpoints (protected)
@app.route("/admin/bookings", methods=["GET"])
def admin_bookings():
    if not check_admin_token(request):
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    conn = get_conn()
    rows = conn.execute(
        "SELECT b.*, s.title as service_name FROM bookings b LEFT JOIN services s ON b.service_id=s.id ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return jsonify({"ok": True, "bookings": [dict(r) for r in rows]})

@app.route("/admin/technicians", methods=["GET", "POST"])
def admin_techs():
    if not check_admin_token(request):
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    conn = get_conn()
    if request.method == "POST":
        data = request.get_json(force=True)
        tid = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO technicians (id,name,phone,areas_csv,services_csv,owner_name,created_at) VALUES (?,?,?,?,?,?,?)",
            (tid, data.get("name"), data.get("phone"), data.get("areas_csv", ""), data.get("services_csv", ""), data.get("owner_name", ""), datetime.datetime.utcnow().isoformat())
        )
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "id": tid})
    rows = conn.execute("SELECT * FROM technicians ORDER BY created_at DESC").fetchall()
    conn.close()
    return jsonify({"ok": True, "techs": [dict(r) for r in rows]})

@app.route("/admin/assign", methods=["POST"])
def admin_assign():
    if not check_admin_token(request):
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    data = request.get_json(force=True)
    booking_id = data.get("booking_id")
    technician_id = data.get("technician_id")
    if not (booking_id and technician_id):
        return jsonify({"ok": False, "error": "Missing fields"}), 400
    conn = get_conn()
    conn.execute("UPDATE bookings SET status=?, assigned_to=? WHERE id=?", ("assigned", technician_id, booking_id))
    conn.commit()
    # fetch booking & tech for wa link
    b = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
    t = conn.execute("SELECT * FROM technicians WHERE id=?", (technician_id,)).fetchone()
    conn.close()

    tech_phone = t["phone"] if t else ""
    text = f"New job:%0ABooking:{b['id']}%0AName:{b['name']}%0APhone:{b['phone']}%0AAddress:{b['address']}"
    wa_link = f"https://wa.me/{tech_phone}?text={text}" if tech_phone else ""
    return jsonify({"ok": True, "wa_link": wa_link})

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"Server running at http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)
