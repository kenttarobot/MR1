# =====================================================
# PREDATOR HYBRID FINAL
# Auto Scan + Manual Room Mode
# Railway Ready
# =====================================================

import os
import time
import json
import random
import threading
import traceback
import requests
from flask import Flask, request, jsonify

# =====================================================
# CONFIG
# =====================================================

BASE_URL = "https://cdn.moltyroyale.com/api"

API_KEY = os.getenv("API_KEY")
PORT = int(os.getenv("PORT", "5000"))

if not API_KEY:
    raise Exception("API_KEY belum diisi")

SETTINGS_FILE = "settings.json"

# =====================================================
# DEFAULT SETTINGS
# =====================================================

DEFAULT_SETTINGS = {
    "running": False,
    "mode": "auto",          # auto / manual
    "room_id": "",
    "instances": 1,
    "fast_scan": 1,
    "slow_scan": 15
}

# =====================================================
# GLOBAL
# =====================================================

lock = threading.Lock()

stats = {
    "scan": 0,
    "join": 0,
    "wins": 0,
    "deaths": 0,
    "errors": 0,
    "server_fail": 0
}

# =====================================================
# SETTINGS
# =====================================================

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

# =====================================================
# REQUEST
# =====================================================

def headers():
    return {
        "X-API-Key": API_KEY,
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://moltyroyale.com",
        "Referer": "https://moltyroyale.com/"
    }


def api_get(path):
    r = requests.get(
        f"{BASE_URL}{path}",
        headers=headers(),
        timeout=10
    )
    r.raise_for_status()
    return r.json()


def api_post(path, payload=None):
    r = requests.post(
        f"{BASE_URL}{path}",
        json=payload or {},
        headers=headers(),
        timeout=10
    )
    r.raise_for_status()
    return r.json()

# =====================================================
# AUTO SCAN ROOM
# =====================================================

def parse_games(data):
    if isinstance(data, dict):
        return data.get("data", []) or data.get("games", [])
    if isinstance(data, list):
        return data
    return []


def choose_room(games):
    rooms = []

    for g in games:
        if g.get("entryType") != "free":
            continue

        if g.get("agentCount", 999) < g.get("maxAgents", 0):
            rooms.append(g)

    if not rooms:
        return None

    rooms.sort(
        key=lambda x: (
            x.get("agentCount", 999),
            x.get("createdAt", "")
        )
    )

    return rooms[0]


def auto_find_room():
    endpoints = [
        "/games?status=waiting",
        "/games?status=open",
        "/games?status=pending",
        "/games"
    ]

    for ep in endpoints:
        try:
            data = api_get(ep)

            with lock:
                stats["scan"] += 1

            games = parse_games(data)

            room = choose_room(games)

            if room:
                print("ROOM FOUND:", room["id"])
                return room["id"]

        except Exception as e:
            with lock:
                stats["server_fail"] += 1

            print("SCAN FAIL:", ep, e)

    return None

# =====================================================
# REGISTER
# =====================================================

def register_agent(room_id):
    payload = {
        "name": f"BOT-{random.randint(1000,9999)}"
    }

    data = api_post(
        f"/games/{room_id}/agents/register",
        payload
    )

    if "data" in data:
        return data["data"]["id"]

    if "id" in data:
        return data["id"]

    raise Exception("REGISTER FAILED")

# =====================================================
# BOT LOOP
# =====================================================

def bot_loop():
    while True:
        try:
            cfg = load_settings()

            if not cfg["running"]:
                time.sleep(3)
                continue

            room_id = None

            # ------------------
            # MANUAL MODE
            # ------------------
            if cfg["mode"] == "manual":
                room_id = cfg["room_id"]

                if not room_id:
                    print("MANUAL MODE: room kosong")
                    time.sleep(5)
                    continue

            # ------------------
            # AUTO MODE
            # ------------------
            else:
                room_id = auto_find_room()

                if not room_id:
                    print("AUTO MODE: no room")
                    time.sleep(cfg["slow_scan"])
                    continue

            # ------------------
            # JOIN
            # ------------------
            print("TRY JOIN:", room_id)

            agent_id = register_agent(room_id)

            with lock:
                stats["join"] += 1

            print("JOIN SUCCESS:", agent_id)

            # placeholder play mode
            time.sleep(10)

        except Exception as e:
            with lock:
                stats["errors"] += 1

            print("BOT ERROR:", e)
            traceback.print_exc()
            time.sleep(5)

# =====================================================
# FLASK APP
# =====================================================

app = Flask(__name__)

@app.get("/")
def home():
    return jsonify({
        "name": "Predator Hybrid Final",
        "status": "online"
    })

@app.get("/api/settings")
def get_settings():
    return jsonify(load_settings())

@app.post("/api/settings")
def set_settings():
    data = request.json
    save_settings(data)
    return jsonify({"ok": True})

@app.get("/api/stats")
def get_stats():
    return jsonify(stats)

@app.post("/api/start")
def start():
    cfg = load_settings()
    cfg["running"] = True
    save_settings(cfg)
    return jsonify({"ok": True})

@app.post("/api/stop")
def stop():
    cfg = load_settings()
    cfg["running"] = False
    save_settings(cfg)
    return jsonify({"ok": True})

# =====================================================
# MAIN
# =====================================================

def start_background():
    t = threading.Thread(
        target=bot_loop,
        daemon=True
    )
    t.start()

start_background()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
