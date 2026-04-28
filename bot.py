import os
import time
import random
import requests

BASE_URL = "https://cdn.moltyroyale.com/api"
API_KEY = os.getenv("API_KEY")

SCAN_DELAY = 10
ERROR_DELAY = 20

def headers():
    return {
        "X-API-Key": API_KEY,
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

def get_rooms():
    urls = [
        "/games?status=waiting",
        "/games?status=open",
        "/games"
    ]

    for path in urls:
        try:
            r = requests.get(
                BASE_URL + path,
                headers=headers(),
                timeout=10
            )
            r.raise_for_status()

            data = r.json()

            if isinstance(data, dict):
                return data.get("data", []) or data.get("games", [])

            if isinstance(data, list):
                return data

        except Exception as e:
            print("SCAN FAIL:", path, e)

    return []

def choose_room(rooms):
    free_rooms = []

    for g in rooms:
        if g.get("entryType") == "free":
            count = g.get("agentCount", 999)
            max_count = g.get("maxAgents", 0)

            if count < max_count:
                free_rooms.append(g)

    if not free_rooms:
        return None

    free_rooms.sort(
        key=lambda x: x.get("agentCount", 999)
    )

    return free_rooms[0]

def join_room(room_id):
    try:
        r = requests.post(
            f"{BASE_URL}/games/{room_id}/agents/register",
            json={
                "name": f"BOT-{random.randint(1000,9999)}"
            },
            headers=headers(),
            timeout=10
        )

        r.raise_for_status()

        print("JOIN SUCCESS:", room_id)
        print(r.text)

        return True

    except Exception as e:
        print("JOIN FAIL:", e)
        return False

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
            print("NO EMPTY ROOM")
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
