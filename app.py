from flask import Flask, jsonify, request
import os
import json
import threading
import time
import random

app = Flask(__name__)

# ==========================================
# CONFIG
# ==========================================

PORT = int(os.getenv("PORT", "8080"))
SETTINGS_FILE = "settings.json"

# ==========================================
# DEFAULT SETTINGS
# ==========================================

DEFAULT_SETTINGS = {
    "running": False,
    "mode": "auto",          # auto / manual
    "room_id": "",
    "instances": 1,
    "scan_delay": 5
}

# ==========================================
# GLOBAL STATS
# ==========================================

stats = {
    "scan": 0,
    "join": 0,
    "wins": 0,
    "deaths": 0,
    "errors": 0,
    "status": "idle"
}

# ==========================================
# SETTINGS HELPER
# ==========================================

def load_settings():
    try:
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    except:
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS.copy()

def save_settings(data):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ==========================================
# BOT LOOP (SIMULASI / TEMPAT ENGINE BOT)
# ==========================================

def bot_loop():
    while True:
        cfg = load_settings()

        if not cfg["running"]:
            stats["status"] = "stopped"
            time.sleep(3)
            continue

        try:
            stats["status"] = "running"

            if cfg["mode"] == "manual":
                # join room manual
                room = cfg["room_id"]

                if room:
                    print("JOIN ROOM:", room)
                    stats["join"] += 1

            else:
                # auto scan room
                print("SCAN FREE ROOM...")
                stats["scan"] += 1

                # simulasi kadang join
                if random.randint(1, 5) == 1:
                    stats["join"] += 1

            time.sleep(cfg["scan_delay"])

        except Exception:
            stats["errors"] += 1
            time.sleep(5)

# ==========================================
# START BACKGROUND THREAD
# ==========================================

threading.Thread(
    target=bot_loop,
    daemon=True
).start()

# ==========================================
# ROUTES
# ==========================================

@app.route("/")
def home():
    return jsonify({
        "name": "Predator Hybrid Final",
        "status": "online"
    })

@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify(load_settings())

@app.route("/api/settings", methods=["POST"])
def update_settings():
    data = request.json
    save_settings(data)
    return jsonify({"success": True})

@app.route("/api/stats")
def get_stats():
    return jsonify(stats)

@app.route("/api/start", methods=["POST"])
def start_bot():
    cfg = load_settings()
    cfg["running"] = True
    save_settings(cfg)
    return jsonify({"success": True, "message": "Bot started"})

@app.route("/api/stop", methods=["POST"])
def stop_bot():
    cfg = load_settings()
    cfg["running"] = False
    save_settings(cfg)
    return jsonify({"success": True, "message": "Bot stopped"})

@app.route("/api/manual/<room_id>", methods=["POST"])
def manual_room(room_id):
    cfg = load_settings()
    cfg["mode"] = "manual"
    cfg["room_id"] = room_id
    save_settings(cfg)

    return jsonify({
        "success": True,
        "mode": "manual",
        "room_id": room_id
    })

@app.route("/api/auto", methods=["POST"])
def auto_mode():
    cfg = load_settings()
    cfg["mode"] = "auto"
    save_settings(cfg)

    return jsonify({
        "success": True,
        "mode": "auto"
    })

# ==========================================
# MAIN
# ==========================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
