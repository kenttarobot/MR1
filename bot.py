import os
import time
import random
import traceback
import threading
import requests

# =====================================================
# PREDATOR FINAL - AUTO FIND + ANTI 403 + ANTI 426
# =====================================================

BASE_URL = os.getenv("BASE_URL", "https://cdn.moltyroyale.com/api")

API_KEY = os.getenv("API_KEY")
BOT_AGENT_NAME = os.getenv("BOT_AGENT_NAME", "PREDATOR")
BOT_INSTANCES = int(os.getenv("BOT_INSTANCES", "1"))

TURN_DELAY = int(os.getenv("TURN_DELAY", "58"))
RETRY_DELAY = int(os.getenv("RETRY_DELAY", "5"))
REJOIN_DELAY = int(os.getenv("REJOIN_DELAY", "10"))

if not API_KEY:
    raise Exception("API_KEY belum diisi di Railway Variables")

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
# HEADERS (ANTI 426)
# =====================================================

def headers():
    return {
        "X-API-Key": API_KEY,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://moltyroyale.com",
        "Referer": "https://moltyroyale.com/",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache"
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
# FIND GAME
# =====================================================

def get_waiting_game():
    statuses = [
        "waiting",
        "open",
        "pending",
        "available"
    ]

    for status in statuses:
        try:
            data = api_get(f"/games?status={status}")
            games = data.get("data", [])

            if games:
                print("FOUND GAME STATUS:", status)
                return games[0]

        except:
            pass

    # fallback semua game
    try:
        data = api_get("/games")
        games = data.get("data", [])

        if games:
            print("FOUND GAME FROM /games")
            return games[0]

    except:
        pass

    return None

# =====================================================
# REGISTER AGENT
# =====================================================

def register_agent(game_id, index):
    payload = {
        "name": f"{BOT_AGENT_NAME}-{index}-{random.randint(1000,9999)}"
    }

    data = api_post(
        f"/games/{game_id}/agents/register",
        payload
    )

    return data["data"]["id"]

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
# AI ENGINE
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
        target = min(same_agents, key=lambda x: x["hp"])

        return {
            "type": "attack",
            "targetId": target["id"],
            "targetType": "agent"
        }

    # attack monster
    if same_monsters:
        target = min(same_monsters, key=lambda x: x.get("hp", 999))

        return {
            "type": "attack",
            "targetId": target["id"],
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

def play_game(game_id, agent_id, index):
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
                        "reasoning": "Predator Final",
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
# LIVE STATS
# =====================================================

def stats_monitor():
    while True:
        with lock:
            print("===================================")
            print("PREDATOR LIVE STATS")
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
    print("PREDATOR FINAL - ANTI 426")
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
