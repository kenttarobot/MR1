from flask import Flask, request, jsonify
import json
import threading
import bot_engine

app = Flask(__name__)

BOT_THREAD = None

def load_settings():
    try:
        with open("settings.json", "r") as f:
            return json.load(f)
    except:
        return {
            "running": False,
            "mode": "auto",
            "room_id": "",
            "instances": 1
        }

def save_settings(data):
    with open("settings.json", "w") as f:
        json.dump(data, f)

@app.get("/api/settings")
def get_settings():
    return jsonify(load_settings())

@app.post("/api/settings")
def update_settings():
    data = request.json
    save_settings(data)
    return jsonify({"ok": True})

@app.post("/api/start")
def start_bot():
    global BOT_THREAD

    settings = load_settings()
    settings["running"] = True
    save_settings(settings)

    if not BOT_THREAD or not BOT_THREAD.is_alive():
        BOT_THREAD = threading.Thread(
            target=bot_engine.main_loop,
            daemon=True
        )
        BOT_THREAD.start()

    return jsonify({"ok": True})

@app.post("/api/stop")
def stop_bot():
    settings = load_settings()
    settings["running"] = False
    save_settings(settings)
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)