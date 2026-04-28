import os
import time
import random
import traceback
import threading
import requests

# =====================================================
# PREDATOR V8 - FREE ROOM SNIPER
# Fokus: masuk room FREE tercepat
# =====================================================

BASE_URL = os.getenv("BASE_URL", "https://cdn.moltyroyale.com/api")

API_KEY = os.getenv("API_KEY")
BOT_AGENT_NAME = os.getenv("BOT_AGENT_NAME", "SNIPER")
BOT_INSTANCES = int(os.getenv("BOT_INSTANCES", "3"))

# scan cepat
RETRY_DELAY = float(os.getenv("RETRY_DELAY", "0.5"))
TURN_DELAY = int(os.getenv("TURN_DELAY", "58"))
REJOIN_DELAY = int(os.getenv("REJOIN_DELAY", "2"))

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
    "errors": 0
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
# GAME SNIPER
# =====================================================

def get_free_room():
    try:
        data = api_get("/games")

        with lock:
            stats["scan"] += 1

        games = []

        if isinstance(data, dict):
            games = data.get("data", []) or data.get("games", [])

        elif isinstance(data, list):
            games = data

        # filter room free + belum penuh
        free_rooms = []

        for g in games:
            if g.get("entryType") != "free":
                continue

            count = g.get("agentCount", 999)
            max_count = g.get("maxAgents", 0)

            if count < max_count:
                free_rooms.append(g)

        if not free_rooms:
            return None

        # urut room terbaru
        free_rooms.sort(
            key=lambda x: x.get("createdAt", ""),
            reverse=True
        )

        return free_rooms[0]

    except Exception as e:
        print("SCAN ERROR:", e)
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
# SIMPLE AI
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

    # enemy nearby
    for a in state.get("visibleAgents", []):
        if a["isAlive"] and a["id"] != me["id"]:
            if a["regionId"] == me["regionId"]:
                return {
                    "type": "attack",
                    "targetId": a["id"],
                    "targetType": "agent"
                }

    # monster nearby
    for m in state.get("visibleMonsters", []):
        if m["regionId"] == me["regionId"]:
            return {
                "type": "attack",
                "targetId": m["id"],
                "targetType": "monster"
            }

    # loot
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
# THREAD LOOP
# =====================================================

def run_bot(index):
    while True:
        try:
            room = None

            while not room:
                room = get_free_room()

                if not room:
                    print(f"[BOT {index}] WAIT FREE ROOM")
                    time.sleep(RETRY_DELAY)

            gid = room["id"]

            print(
                f"[BOT {index}] FREE ROOM FOUND:",
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

            time.sleep(RETRY_DELAY)

# =====================================================
# MONITOR
# =====================================================

def monitor():
    while True:
        with lock:
            print("===================================")
            print("PREDATOR V8 FREE ROOM SNIPER")
            print("Scan   :", stats["scan"])
            print("Join   :", stats["join"])
            print("Wins   :", stats["wins"])
            print("Deaths :", stats["deaths"])
            print("Errors :", stats["errors"])
            print("===================================")

        time.sleep(30)

# =====================================================
# MAIN
# =====================================================

def main():
    print("===================================")
    print("PREDATOR V8 FREE ROOM SNIPER")
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
