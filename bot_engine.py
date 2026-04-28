import time
import json

def load_settings():
    with open("settings.json", "r") as f:
        return json.load(f)

def main_loop():
    while True:
        cfg = load_settings()

        if not cfg["running"]:
            time.sleep(3)
            continue

        if cfg["mode"] == "manual":
            print("JOIN ROOM:", cfg["room_id"])
            # panggil API join room

        else:
            print("SCAN FREE ROOM...")
            # panggil API scan

        time.sleep(5)