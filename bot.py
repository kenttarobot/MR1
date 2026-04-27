import os
import time
import random
import traceback
import threading
import requests

# =====================================================
# PREDATOR V5 PROFESSIONAL MULTI THREAD
# =====================================================

BASE_URL = os.getenv("BASE_URL", "https://cdn.moltyroyale.com/api")

BOT_ACCOUNT_NAME = os.getenv("BOT_ACCOUNT_NAME", "PredatorV5")
BOT_AGENT_NAME = os.getenv("BOT_AGENT_NAME", "THREAD-HUNTER")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS", "0xYourWallet")

BOT_INSTANCES = int(os.getenv("BOT_INSTANCES", "5"))

TURN_DELAY = int(os.getenv("TURN_DELAY", "58"))
RETRY_DELAY = int(os.getenv("RETRY_DELAY", "5"))
REJOIN_DELAY = int(os.getenv("REJOIN_DELAY", "10"))

# =====================================================
# GLOBAL LOCK + STATS
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
# API
# =====================================================

def api_get(path):
    r = requests.get(f"{BASE_URL}{path}", timeout=15)
    r.raise_for_status()
    return r.json()


def api_post(path, payload=None, api_key=None):
    headers = {}

    if api_key:
        headers["X-API-Key"] = api_key

    r = requests.post(
        f"{BASE_URL}{path}",
        json=payload or {},
        headers=headers,
        timeout=15
    )

    r.raise_for_status()
    return r.json()

# =====================================================
# HELPERS
# =====================================================

def create_account(index):
    data = api_post("/accounts", {
        "name": f"{BOT_ACCOUNT_NAME}-{index}",
        "wallet_address": WALLET_ADDRESS
    })["data"]

    return data["accountId"], data["apiKey"]


def get_waiting_game():
    games = api_get("/games?status=waiting")["data"]

    if not games:
        return None

    return games[0]


def register_agent(game_id, api_key, index):
    data = api_post(
        f"/games/{game_id}/agents/register",
        {"name": f"{BOT_AGENT_NAME}-{index}"},
        api_key
    )["data"]

    return data["id"]


def safest_region(state):
    region = state["currentRegion"]
    cons = region.get("connections", [])

    if not cons:
        return None

    def score(r):
        s = 0

        for a in state.get("visibleAgents", []):
            if a["isAlive"] and a["regionId"] == r:
                s += 5

        return s

    return sorted(cons, key=score)[0]


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

# =====================================================
# AI
# =====================================================

def decide_action(state):
    me = state["self"]
    hp = me["hp"]
    ep = me["ep"]

    visible_agents = [
        a for a in state.get("visibleAgents", [])
        if a["isAlive"] and a["id"] != me["id"]
    ]

    same_agents = [
        a for a in visible_agents
        if a["regionId"] == me["regionId"]
    ]

    same_monsters = [
        m for m in state.get("visibleMonsters", [])
        if m["regionId"] == me["regionId"]
    ]

    # death zone
    if state["currentRegion"].get("isDeathZone"):
        safe = safest_region(state)
        if safe:
            return {"type": "move", "regionId": safe}

    # heal
    if hp <= 35:
        item = heal_item(me["inventory"])
        if item:
            return {"type": "use_item", "itemId": item["id"]}

    # rest
    if ep <= 1:
        return {"type": "rest"}

    # equip
    bw = best_weapon(me["inventory"])
    if bw:
        eq = me.get("equippedWeapon")

        if not eq or eq["id"] != bw["id"]:
            return {"type": "equip", "itemId": bw["id"]}

    # attack player
    if same_agents:
        t = min(same_agents, key=lambda x: x["hp"])

        return {
            "type": "attack",
            "targetId": t["id"],
            "targetType": "agent"
        }

    # attack monster
    if same_monsters:
        t = min(same_monsters, key=lambda x: x.get("hp", 999))

        return {
            "type": "attack",
            "targetId": t["id"],
            "targetType": "monster"
        }

    # loot
    for item in state.get("visibleItems", []):
        if item["regionId"] == me["regionId"]:
            return {
                "type": "pickup",
                "itemId": item["item"]["id"]
            }

    # move
    safe = safest_region(state)
    if safe:
        return {"type": "move", "regionId": safe}

    return {"type": "explore"}

# =====================================================
# PLAY GAME
# =====================================================

def play_game(game_id, agent_id, api_key, index):
    while True:
        try:
            state = api_get(
                f"/games/{game_id}/agents/{agent_id}/state"
            )["data"]

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
                        "reasoning": "Professional Multi Thread",
                        "plannedAction": action["type"]
                    }
                },
                api_key
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
# BOT THREAD
# =====================================================

def run_bot(index):
    while True:
        try:
            account_id, api_key = create_account(index)

            print(f"[BOT {index}] ACCOUNT:", account_id)

            game = None

            while not game:
                game = get_waiting_game()

                if not game:
                    print(f"[BOT {index}] WAITING GAME...")
                    time.sleep(RETRY_DELAY)

            game_id = game["id"]

            agent_id = register_agent(game_id, api_key, index)

            with lock:
                stats["games"] += 1

            print(f"[BOT {index}] JOINED:", game["name"])

            play_game(game_id, agent_id, api_key, index)

            print(f"[BOT {index}] REJOIN IN {REJOIN_DELAY}s")

            time.sleep(REJOIN_DELAY)

        except Exception as e:
            with lock:
                stats["errors"] += 1

            print(f"[BOT {index}] MAIN ERROR:", e)
            traceback.print_exc()

            time.sleep(RETRY_DELAY)

# =====================================================
# LIVE STATS THREAD
# =====================================================

def stats_monitor():
    while True:
        with lock:
            print("===================================")
            print(" LIVE STATS")
            print(" Games  :", stats["games"])
            print(" Wins   :", stats["wins"])
            print(" Deaths :", stats["deaths"])
            print(" Actions:", stats["actions"])
            print(" Errors :", stats["errors"])
            print("===================================")

        time.sleep(60)

# =====================================================
# MAIN
# =====================================================

def main():
    print("===================================")
    print("PREDATOR PROFESSIONAL MULTI THREAD")
    print("Instances:", BOT_INSTANCES)
    print("===================================")

    # stats thread
    threading.Thread(target=stats_monitor, daemon=True).start()

    # bot threads
    threads = []

    for i in range(1, BOT_INSTANCES + 1):
        t = threading.Thread(target=run_bot, args=(i,), daemon=True)
        t.start()
        threads.append(t)

        time.sleep(2)

    # keep main alive
    while True:
        time.sleep(9999)

# =====================================================

if __name__ == "__main__":
    main()