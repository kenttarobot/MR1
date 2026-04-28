import os
import time
import random
import threading
import traceback
import requests

# =====================================================
# PREDATOR V9 SMART SNIPER
# - Fokus room FREE
# - Anti 500
# - Smart Backoff
# - Multi Endpoint
# - Railway Stable
# =====================================================

BASE_URL = os.getenv("BASE_URL", "https://cdn.moltyroyale.com/api")

API_KEY = os.getenv("API_KEY")
BOT_AGENT_NAME = os.getenv("BOT_AGENT_NAME", "SNIPER")
BOT_INSTANCES = int(os.getenv("BOT_INSTANCES", "1"))

TURN_DELAY = int(os.getenv("TURN_DELAY", "58"))
REJOIN_DELAY = int(os.getenv("REJOIN_DELAY", "3"))

# scan cepat saat sehat
FAST_SCAN = float(os.getenv("FAST_SCAN", "0.5"))

# backoff saat server rusak
SLOW_SCAN = int(os.getenv("SLOW_SCAN", "15"))

if not API_KEY:
    raise Exception("API_KEY belum diisi")

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
# HEADERS
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

# =====================================================
# REQUEST
# =====================================================

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
# SMART ROOM FINDER
# =====================================================

def parse_games(data):
    if isinstance(data, dict):
        return data.get("data", []) or data.get("games", [])

    if isinstance(data, list):
        return data

    return []


def choose_best_room(games):
    rooms = []

    for g in games:
        if g.get("entryType") != "free":
            continue

        count = g.get("agentCount", 999)
        max_count = g.get("maxAgents", 0)

        if count < max_count:
            rooms.append(g)

    if not rooms:
        return None

    # pilih paling kosong lalu paling baru
    rooms.sort(
        key=lambda x: (
            x.get("agentCount", 999),
            x.get("createdAt", "")
        )
    )

    return rooms[0]


def get_room():
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

            room = choose_best_room(games)

            if room:
                print("ROOM FOUND:", ep)
                return room

        except Exception as e:
            with lock:
                stats["server_fail"] += 1

            print("FAILED:", ep, e)

    return None

# =====================================================
# REGISTER
# =====================================================

def register_agent(game_id, index):
    payload = {
        "name": f"{BOT_AGENT_NAME}-{index}-{random.randint(1000,9999)}"
    }

    data = api_post(
        f"/games/{game_id}/agents/register",
        payload
    )

    if "data" in data:
        return data["data"]["id"]

    if "id" in data:
        return data["id"]

    raise Exception("REGISTER FAILED")

# =====================================================
# AI SIMPLE
# =====================================================

def decide_action(state):
    me = state["self"]

    # heal
    if me["hp"] <= 35:
        for item in me["inventory"]:
            if item.get("category") == "recovery":
                return {
                    "type": "use_item",
                    "itemId": item["id"]
                }

    # attack player
    for a in state.get("visibleAgents", []):
        if a["isAlive"] and a["id"] != me["id"]:
            if a["regionId"] == me["regionId"]:
                return {
                    "type": "attack",
                    "targetId": a["id"],
                    "targetType": "agent"
                }

    # attack monster
    for m in state.get("visibleMonsters", []):
        if m["regionId"] == me["regionId"]:
            return {
                "type": "attack",
                "targetId": m["id"],
                "targetType": "monster"
            }

    # pickup
    for item in state.get("visibleItems", []):
        if item["regionId"] == me["regionId"]:
            return {
                "type": "pickup",
                "itemId": item["item"]["id"]
            }

    return {"type": "explore"}

# =====================================================
# PLAY
# =====================================================

def play_game(game_id, agent_id, index):
    while True:
        try:
            state = api_get(
                f"/games/{game_id}/agents/{agent_id}/state"
            )

            if "data" in state:
                state = state["data"]

            if not state["self"]["isAlive"]:
                with lock:
                    stats["deaths"] += 1

                print(f"[BOT {index}] DEAD")
                return

            if state.get("gameStatus") == "finished":
                result = state.get("result", {})

                if result.get("isWinner"):
                    with lock:
                        stats["wins"] += 1

                print(f"[BOT {index}] FINISHED")
                return

            action = decide_action(state)

            api_post(
                f"/games/{game_id}/agents/{agent_id}/action",
                {"action": action}
            )

            print(f"[BOT {index}] {action['type']}")

        except Exception as e:
            print(f"[BOT {index}] TURN ERROR:", e)

        time.sleep(TURN_DELAY)

# =====================================================
# BOT LOOP
# =====================================================

def run_bot(index):
    fail_streak = 0

    while True:
        try:
            room = get_room()

            if not room:
                fail_streak += 1

                # smart backoff
                if fail_streak >= 3:
                    print(f"[BOT {index}] SERVER BAD, WAIT {SLOW_SCAN}s")
                    time.sleep(SLOW_SCAN)
                else:
                    print(f"[BOT {index}] WAIT ROOM")
                    time.sleep(FAST_SCAN)

                continue

            fail_streak = 0

            gid = room["id"]

            print(
                f"[BOT {index}] JOIN TARGET:",
                room.get("name", gid),
                f"{room.get('agentCount',0)}/{room.get('maxAgents',0)}"
            )

            agent_id = register_agent(gid, index)

            with lock:
                stats["join"] += 1

            print(f"[BOT {index}] JOIN SUCCESS:", agent_id)

            play_game(gid, agent_id, index)

            time.sleep(REJOIN_DELAY)

        except Exception as e:
            with lock:
                stats["errors"] += 1

            print(f"[BOT {index}] MAIN ERROR:", e)
            traceback.print_exc()

            time.sleep(SLOW_SCAN)

# =====================================================
# MONITOR
# =====================================================

def monitor():
    while True:
        with lock:
            print("===================================")
            print("PREDATOR V9 SMART SNIPER")
            print("Scan       :", stats["scan"])
            print("Join       :", stats["join"])
            print("Wins       :", stats["wins"])
            print("Deaths     :", stats["deaths"])
            print("Errors     :", stats["errors"])
            print("ServerFail :", stats["server_fail"])
            print("===================================")

        time.sleep(30)

# =====================================================
# MAIN
# =====================================================

def main():
    print("===================================")
    print("PREDATOR V9 SMART SNIPER")
    print("Instances:", BOT_INSTANCES)
    print("===================================")

    threading.Thread(
        target=monitor,
        daemon=True
    ).start()

    for i in range(1, BOT_INSTANCES + 1):
        threading.Thread(
            target=run_bot,
            args=(i,),
            daemon=True
        ).start()

        time.sleep(0.2)

    while True:
        time.sleep(9999)

# =====================================================

if __name__ == "__main__":
    main()
