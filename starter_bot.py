# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "httpx",
# ]
# ///
"""
The Bot Range (TBR) - Official Agent-Ready Starter Bot
Run with uv:
    uv run starter_bot.py
Or run directly with python3 (using standard library fallback):
    python3 starter_bot.py
"""
import os
import sys
import json
import time

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    import urllib.request
    import urllib.error
    HAS_HTTPX = False

API_KEY = os.environ.get("TBR_API_KEY", "").strip()
API_URL = os.environ.get("TBR_API_URL", "https://api.thebotrange.com/api/v1").rstrip("/")

if not API_KEY:
    print("[ERROR] TBR_API_KEY environment variable is required.")
    print("Export your API key: export TBR_API_KEY=\"your_key_here\"")
    sys.exit(1)

def api_call(method: str, path: str, payload: dict | None = None) -> dict | None:
    url = f"{API_URL}{path}"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    status_code = None
    data = None

    if HAS_HTTPX:
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.request(method, url, headers=headers, json=payload)
                status_code = res.status_code
                try:
                    data = res.json()
                except Exception:
                    data = res.text
        except Exception as e:
            print(f"[HTTP Error] Network exception reaching {url}: {e}")
            return None
    else:
        req = urllib.request.Request(url, headers=headers, method=method)
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        try:
            with urllib.request.urlopen(req, data=body, timeout=10) as res:
                status_code = res.status
                raw = res.read().decode("utf-8")
                try:
                    data = json.loads(raw)
                except Exception:
                    data = raw
        except urllib.error.HTTPError as e:
            status_code = e.code
            raw = e.read().decode("utf-8")
            try:
                data = json.loads(raw)
            except Exception:
                data = raw
        except Exception as e:
            print(f"[HTTP Error] Network exception reaching {url}: {e}")
            return None

    match status_code:
        case 200 | 201 | 202:
            return data if isinstance(data, dict) else {"raw": data}
        case 429:
            print(f"[429 Rate Limited] Action token limit reached: {data}")
            # TODO (MISSION 01): Inspect data.get('seconds_to_wait') and sleep until token refills.
            return None
        case 502:
            print(f"[502 Signal Interference] Transmission jammed: {data}")
            # TODO (MISSION 01): Handle environmental/ECM interference.
            # No action tokens are lost on 502. Implement a momentary backoff (150-400ms) and retry.
            return None
        case _:
            print(f"[HTTP {status_code}] Unexpected API response on {method} {path}: {data}")
            return None

def run_tick():
    state = api_call("GET", "/game/state")
    if not state:
        return

    player = state.get("player") or {}
    zone = state.get("zone") or {}
    tile = state.get("current_tile") or {}
    limiter = state.get("action_limiter") or {}

    # 1. Auto-spawn if offline/despawned
    if not player.get("spawned", False) or state.get("status") in ["inactive", "despawned"]:
        print("[Status] Bot is offline. Calling POST /game/spawn ...")
        spawn_res = api_call("POST", "/game/spawn")
        if spawn_res and spawn_res.get("status") == "queued":
            wait_secs = spawn_res.get("retry_after_seconds", 5)
            print(f"[Spawn Queued] Position {spawn_res.get('queue_position')} — retrying in {wait_secs}s ...")
            time.sleep(wait_secs)
        else:
            print(f"[Spawn] {spawn_res}")
        return

    hp = player.get("hp", 0)
    max_hp = player.get("max_hp", 100)
    tokens = limiter.get("tokens", player.get("action_tokens", 0))
    p_zone = player.get("zone") or zone.get("coords") or [0, 0]
    p_tile = player.get("tile") or [0, 0]
    zx, zy = p_zone[0], p_zone[1]
    tx, ty = p_tile[0], p_tile[1]
    enemies = tile.get("enemies") or []
    resources = tile.get("resources") or []
    in_extract = zone.get("is_extraction_zone", False)
    vector = zone.get("extraction_vector") or {}

    print(f"[Telemetry] Zone ({zx},{zy}) Tile ({tx},{ty}) | HP: {hp}/{max_hp} | Tokens: {tokens} | Vector: {vector.get('direction') or 'none'}")

    # TODO (MISSION 01): If hp / max_hp < 0.5, prioritize retreating towards extraction or using emergency defenses.

    # 2. Extract if inside Ring 0 extraction zone
    if in_extract:
        print("[Extraction Zone] Triggering POST /game/extract ...")
        res = api_call("POST", "/game/extract")
        print(f"[Extracted] {res}")
        return

    # 3. Combat: Attack hostiles present on the tile
    if enemies:
        target = enemies[0]
        target_id = target.get("id")
        target_name = target.get("name", "Hostile")
        print(f"[Combat] Attacking {target_name} ({target_id}) ...")
        # TODO (MISSION 01): Select target priority (e.g. boss escort adds first) or pass "heavy": True
        res = api_call("POST", "/game/attack", {"enemy_id": target_id, "heavy": False})
        print(f"[Attack Result] {res.get('combat_log') if res else 'Failed'}")
        return

    # 4. Looting: Collect resources on tile
    if resources:
        print(f"[Looting] Collecting {len(resources)} resource caches ...")
        res = api_call("POST", "/game/loot")
        print(f"[Loot Result] {res}")
        return

    # 5. Move: Follow the extraction vector towards Ring 0 center (Free Move when reducing distance!)
    direction = vector.get("direction") or "s"
    print(f"[Nav] Advancing {direction.upper()} towards extraction zone ...")
    res = api_call("POST", "/game/move", {"direction": direction, "zone_change": True})
    if res:
        free_move = res.get("free_move", False)
        reason = res.get("free_move_reason", "none")
        print(f"[Move Success] New Position: Zone {res.get('zone')} Tile {res.get('tile')} | Free Move: {free_move} ({reason})")

if __name__ == "__main__":
    print(f"=== Starting TBR Starter Bot against {API_URL} ===")
    try:
        while True:
            run_tick()
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[Stopped] Bot loop terminated by user.")
