import os
import time
import random
import traceback
import threading
import requests

# =====================================================
# PREDATOR FINAL - DEBUG MODE
# =====================================================

BASE_URL = os.getenv("BASE_URL", "https://cdn.moltyroyale.com/api")

API_KEY = os.getenv("API_KEY")
BOT_AGENT_NAME = os.getenv("BOT_AGENT_NAME", "PREDATOR")
BOT_INSTANCES = int(os.getenv("BOT_INSTANCES", "1"))

TURN_DELAY = int(os.getenv("TURN_DELAY", "58"))
RETRY_DELAY = int(os.getenv("RETRY_DELAY", "5"))
REJOIN_DELAY = int(os.getenv("REJOIN_DELAY", "10"))

if not API_KEY:
    raise Exception("API_KEY belum diisi")

# =====================================================
# GLOBAL
# =====================================================

lock = threading.Lock()

stats = {
    "games": 0,
    "wins": 0,
    "deaths": 0,
    "actions": 0,
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
        timeout=20
    )

    r.raise_for_status()
    return r.json()


def api_post(path, payload=None):
    r = requests.post(
        f"{BASE_URL}{path}",
        json=payload or {},
        headers=headers(),
        timeout=20
    )

    r.raise_for_status()
    return r.json()

# =====================================================
# DEBUG GAME FINDER
# =====================================================

def get_waiting_game():
    try:
        data = api_get("/games")

        print("===================================")
        print("DEBUG /games RESPONSE:")
        print(data)
        print("===================================")

        # format 1
        if isinstance(data, dict) and "data" in data:
            if data["data"]:
                return data["data"][0]

        # format 2
        if isinstance(data, dict) and "games" in data:
            if data["games"]:
                return data["games"][0]

        # format 3
        if isinstance(data, list):
            if data:
                return data[0]

    except Exception as e:
        print("DEBUG ERROR:", e)

    return None

# =====================================================
# REGISTER
# =====================================================

def register_agent(game_id, index):
    data = api_post(
        f"/games/{game_id}/agents/register",
        {
            "name": f"{BOT_AGENT_NAME}-{index}-{random.randint(1000,9999)}"
        }
    )

    # kemungkinan format berbeda
    if "data" in data and "id" in data["data"]:
        return data["data"]["id"]

    if "id" in data:
        return data["id"]

    raise Exception("REGISTER RESPONSE UNKNOWN")

# =====================================================
# HELPERS
# =====================================================

def best_weapon(inv):
    weapons = [x for x in inv if x.get("category") == "weapon"]

    if not weapons:
        return None

    return max(weapons, key=lambda x: x.get("atkBonus", 0))


def heal_item(inv):
    heals = [x for x in inv if x.get("category") == "recovery"]

    if not heals:
        return None

    return heals[0]


def safest_region(state):
    region = state["currentRegion"]
    cons = region.get("connections", [])

    if not cons:
        return None

    def score(region_id):
        danger = 0

        for a in state.get("visibleAgents", []):
            if a["isAlive"] and a["regionId"] == region_id:
                danger += 5

        for m in state.get("visibleMonsters", []):
            if m["regionId"] == region_id:
                danger += 1

        return danger

    return sorted(cons, key=score)[0]

# =====================================================
# AI
# =====================================================

def decide_action(state):
    me = state["self"]

    hp = me["hp"]
    ep = me["ep"]

    same_agents = [
        a for a in state.get("visibleAgents", [])
        if a["isAlive"]
        and a["id"] != me["id"]
        and a["regionId"] == me["regionId"]
    ]

    same_monsters = [
        m for m in state.get("visibleMonsters", [])
        if m["regionId"] == me["regionId"]
    ]

    if state["currentRegion"].get("isDeathZone"):
        safe = safest_region(state)

        if safe:
            return {"type": "move", "regionId": safe}

    if hp <= 35:
        item = heal_item(me["inventory"])

        if item:
            return {"type": "use_item", "itemId": item["id"]}

    if ep <= 1:
        return {"type": "rest"}

    bw = best_weapon(me["inventory"])

    if bw:
        eq = me.get("equippedWeapon")

        if not eq or eq["id"] != bw["id"]:
            return {"type": "equip", "itemId": bw["id"]}

    if same_agents:
        target = min(same_agents, key=lambda x: x["hp"])

        return {
            "type": "attack",
            "targetId": target["id"],
            "targetType": "agent"
        }

    if same_monsters:
        target = min(same_monsters, key=lambda x: x.get("hp", 999))

        return {
            "type": "attack",
            "targetId": target["id"],
            "targetType": "monster"
        }

    for item in state.get("visibleItems", []):
        if item["regionId"] == me["regionId"]:
            return {
                "type": "pickup",
                "itemId": item["item"]["id"]
            }

    safe = safest_region(state)

    if safe:
        return {"type": "move", "regionId": safe}

    return {"type": "explore"}

# =====================================================
# PLAY GAME
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

                with lock:
                    if result.get("isWinner"):
                        stats["wins"] += 1

                print(f"[BOT {index}] FINISHED")
                return

            action = decide_action(state)

            api_post(
                f"/games/{game_id}/agents/{agent_id}/action",
                {
                    "action": action,
                    "thought": {
                        "reasoning": "Debug Mode",
                        "plannedAction": action["type"]
                    }
                }
            )

            with lock:
                stats["actions"] += 1

            print(f"[BOT {index}] {action['type']}")

        except Exception as e:
            with lock:
                stats["errors"] += 1

            print(f"[BOT {index}] TURN ERROR:", e)

        time.sleep(TURN_DELAY)

# =====================================================
# BOT LOOP
# =====================================================

def run_bot(index):
    while True:
        try:
            game = None

            while not game:
                game = get_waiting_game()

                if not game:
                    print(f"[BOT {index}] NO GAME FOUND")
                    time.sleep(RETRY_DELAY)

            game_id = game["id"]

            print(f"[BOT {index}] JOIN:", game.get("name", game_id))

            agent_id = register_agent(game_id, index)

            print(f"[BOT {index}] REGISTERED:", agent_id)

            with lock:
                stats["games"] += 1

            play_game(game_id, agent_id, index)

            print(f"[BOT {index}] REJOIN IN {REJOIN_DELAY}s")

            time.sleep(REJOIN_DELAY)

        except Exception as e:
            with lock:
                stats["errors"] += 1

            print(f"[BOT {index}] MAIN ERROR:", e)
            traceback.print_exc()

            time.sleep(RETRY_DELAY)

# =====================================================
# STATS
# =====================================================

def stats_monitor():
    while True:
        with lock:
            print("===================================")
            print("PREDATOR DEBUG LIVE STATS")
            print("Games   :", stats["games"])
            print("Wins    :", stats["wins"])
            print("Deaths  :", stats["deaths"])
            print("Actions :", stats["actions"])
            print("Errors  :", stats["errors"])
            print("===================================")

        time.sleep(60)

# =====================================================
# MAIN
# =====================================================

def main():
    print("===================================")
    print("PREDATOR FINAL DEBUG MODE")
    print("Instances:", BOT_INSTANCES)
    print("===================================")

    threading.Thread(
        target=stats_monitor,
        daemon=True
    ).start()

    for i in range(1, BOT_INSTANCES + 1):
        threading.Thread(
            target=run_bot,
            args=(i,),
            daemon=True
        ).start()

        time.sleep(2)

    while True:
        time.sleep(9999)

# =====================================================

if __name__ == "__main__":
    main()
