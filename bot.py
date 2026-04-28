import os
import time
import random
import requests

# ==========================================
# CONFIG
# ==========================================

BASE_URL = "https://cdn.moltyroyale.com/api"
API_KEY = os.getenv("API_KEY")

SCAN_DELAY = 10
ERROR_DELAY = 20

if not API_KEY:
    raise Exception("API_KEY belum diisi")

# ==========================================
# SESSION
# ==========================================

session = requests.Session()

# ==========================================
# HEADERS (ANTI 403)
# ==========================================

def headers():
    return {
        "X-API-Key": API_KEY,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://www.moltyroyale.com",
        "Referer": "https://www.moltyroyale.com/",
        "Connection": "keep-alive"
    }

# ==========================================
# GET ROOM LIST
# ==========================================

def get_rooms():
    endpoints = [
        "/games?status=waiting",
        "/games?status=open",
        "/games"
    ]

    for path in endpoints:
        try:
            r = session.get(
                BASE_URL + path,
                headers=headers(),
                timeout=15
            )

            r.raise_for_status()

            data = r.json()

            # dict format
            if isinstance(data, dict):
                if "data" in data:
                    return data["data"]

                if "games" in data:
                    return data["games"]

            # list format
            if isinstance(data, list):
                return data

        except Exception as e:
            print("SCAN FAIL:", path, e)

    return []

# ==========================================
# CHOOSE ROOM
# ==========================================

def choose_room(rooms):
    free_rooms = []

    for room in rooms:
        if room.get("entryType") != "free":
            continue

        count = room.get("agentCount", 999)
        max_count = room.get("maxAgents", 0)

        if count < max_count:
            free_rooms.append(room)

    if not free_rooms:
        return None

    # pilih room paling kosong
    free_rooms.sort(
        key=lambda x: x.get("agentCount", 999)
    )

    return free_rooms[0]

# ==========================================
# JOIN ROOM
# ==========================================

def join_room(room_id):
    try:
        payload = {
            "name": f"BOT-{random.randint(1000,9999)}"
        }

        r = session.post(
            f"{BASE_URL}/games/{room_id}/agents/register",
            json=payload,
            headers=headers(),
            timeout=15
        )

        r.raise_for_status()

        print("JOIN SUCCESS:", room_id)
        print(r.text)

        return True

    except Exception as e:
        print("JOIN FAIL:", e)
        return False

# ==========================================
# MAIN LOOP
# ==========================================

print("===================================")
print("AUTO SCAN ROOM + AUTO JOIN")
print("ANTI 403 FINAL")
print("===================================")

while True:
    try:
        print("SCAN ROOM...")

        rooms = get_rooms()

        if not rooms:
            print("NO ROOM FOUND")
            time.sleep(ERROR_DELAY)
            continue

        room = choose_room(rooms)

        if not room:
            print("NO EMPTY FREE ROOM")
            time.sleep(SCAN_DELAY)
            continue

        room_id = room["id"]

        print(
            "TARGET:",
            room.get("name", room_id),
            f"{room.get('agentCount',0)}/{room.get('maxAgents',0)}"
        )

        join_room(room_id)

        time.sleep(SCAN_DELAY)

    except Exception as e:
        print("MAIN ERROR:", e)
        time.sleep(ERROR_DELAY)
