# The Bot Range (TBR) - Bot Development Kit (BDK)

The public companion repository for **[The Bot Range (TBR)](https://thebotrange.com)**, a text- and REST API-driven extraction strategy game on an expandable world grid.

This repository is designed for developers building automated bot agents using **AI coding assistants** (Gemini CLI / Antigravity, Claude Code, Cursor, Windsurf, Copilot, etc.).

---

## ⚡ Quickstart

### 1. Prerequisites
- Python 3.10+
- Recommended: [`uv`](https://docs.astral.sh/uv/) (fast Python package runner) or standard `python3`

### 2. Set Your API Key
Generate an API Key from the **[Manage Bots / API Keys](https://thebotrange.com/api_keys)** dashboard:
```bash
export TBR_API_KEY="tbr_sk_your_actual_key_here"
export TBR_API_URL="https://api.thebotrange.com/api/v1" # Optional, defaults to production v1
```

### 3. Run the Starter Bot
Using `uv` (automatically installs PEP 723 dependencies):
```bash
uv run starter_bot.py
```
Or with standard Python 3 (zero dependencies, standard library fallback):
```bash
python3 starter_bot.py
```

Or open directly in Google Colab:
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/ben-uphoff/tbr-bdk/blob/main/starter_bot.ipynb)

---

## 🎯 Mission 01 Challenge

Give this prompt to your AI coding assistant (Gemini, Claude, Cursor):

```text
Read openapi.yaml, FIELD_MANUAL.md, and starter_bot.py.

Improve starter_bot.py to accomplish Mission 01:
1. Handle HTTP 502 (signal_interference): implement a 250ms backoff and retry without consuming tokens.
2. Handle HTTP 429 (rate_limited): extract seconds_to_wait and sleep until tokens refill.
3. Retreat & Extract: When HP drops below 50% (hp / max_hp < 0.5), prioritize moving along the extraction vector towards Ring 0 to extract.
4. Combat Tactics: When multiple hostiles are present, prioritize low-HP adds or trigger Heavy Strike when energy permits.
```

---

## 📂 Repository Contents

| File | Description |
| :--- | :--- |
| **[`starter_bot.py`](starter_bot.py)** | Single-file runnable bot loop with PEP 723 metadata & standard library fallback. |
| **[`openapi.yaml`](openapi.yaml)** | Official OpenAPI 3.0 specification for all TBR game endpoints. |
| **[`docs/API_GUIDE.md`](docs/API_GUIDE.md)** | Player API quickstart and cURL examples for every major game endpoint. |
| **[`FIELD_MANUAL.md`](FIELD_MANUAL.md)** | Tactical guide covering world topology, combat damage math, and free move mechanics. |
| **[`GEMINI.md`](GEMINI.md)** | Strict `< 40` line rulebook for Gemini / Antigravity coding agents. |
| **[`CLAUDE.md`](CLAUDE.md)** | Strict `< 40` line rulebook for Claude Code / Cursor / Windsurf coding agents. |
| **[`starter_bot.ipynb`](starter_bot.ipynb)** | Zero-install Google Colab notebook. |

---

## 📡 Core API Overview

* `GET /game/state` - Comprehensive telemetry: bot HP/energy/loadout, active tile, hostiles, resources, and extraction vector.
* `POST /game/spawn` - Deploys bot to the perimeter grid (Fringe ring).
* `POST /game/move` - Moves bot directionally (`"n"`, `"s"`, `"e"`, `"w"`, `"ne"`, `"nw"`, `"se"`, `"sw"`). Advancing toward Ring 0 is a **Free Move** (0 tokens). Include `"zone_change": true` for cross-zone navigation.
* `POST /game/attack` - Executes attack or Heavy Strike on a hostile target on the active tile.
* `POST /game/loot` - Harvests resource caches on the active tile.
* `POST /game/extract` - Extracts carried spoils and banked artifacts when inside the Ring 0 extraction zone.
* `POST /game/despawn` - Zero-AP emergency scuttle back to standby (5s cooldown, 100% artifact retention, 50% Ark component raw material salvage).
* `POST /game/transfer` - Transfers carried raw resources between same-Operator bots on the exact same tile (`-1 AP` sender, `0 AP` receiver).
* `POST /game/cache` - Deploys (`>= 10` raw units) or retrieves/plunders a bare-ground (`0m`) tile resource cache outside Ring 0.
