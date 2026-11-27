# The Bot Range (TBR) — Player API Guide

Welcome to **The Bot Range (TBR)** REST API. Every action you can perform in the Web UI is available over HTTPS JSON so you can write autonomous bots in Python, TypeScript, Go, or any language—or pair with an AI coding assistant using [`openapi.yaml`](../openapi.yaml) and [`FIELD_MANUAL.md`](../FIELD_MANUAL.md).

---

## 1. 5-Minute Getting Started

1. **Create an Account & Bot**: Sign in at [thebotrange.com](https://thebotrange.com) (Google/GitHub OAuth includes 1 free bot) and visit **Manage Bots** (`/api_keys`).
2. **Generate an API Key**: Copy your bot's secret token (`tbr_sk_...`). Each bot has its own Bearer token; all bots on your account share your **Operator** skill lines and **Operator Depot** vault.
3. **Base URL & Auth Header**:
   - **Production v1 (canonical)**: `https://api.thebotrange.com/api/v1`
   - **Local Dev**: `http://localhost:4000/api/v1`
   - Pass `Authorization: Bearer YOUR_API_KEY` on every request.

```bash
export TBR_API_KEY="tbr_sk_your_actual_key_here"
export TBR_API_URL="https://api.thebotrange.com/api/v1"

# 1. Inspect current bot state (0 AP)
curl -s -H "Authorization: Bearer $TBR_API_KEY" "$TBR_API_URL/game/state"

# 2. Deploy your bot onto an outer Fringe rim tile (0 AP)
curl -s -X POST -H "Authorization: Bearer $TBR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"loadout": {"weapon": "plasma_beam", "armor": "bonded_carbon", "utility": "laz_excavator"}}' \
  "$TBR_API_URL/game/spawn"
```

---

## 2. Rate Limits, Backpressure & Signal Interference

| HTTP Status | Code / Meaning | AP Consumed | How Your Bot Should Handle It |
| :--- | :--- | :---: | :--- |
| **202 Accepted** | `status: "queued"` (Orbital Launch Queue) | `0` | Sector is at concurrent bot cap (`C_max`). Sleep `retry_after_seconds` (e.g., `5s`) and retry `POST /game/spawn` within your 30s launch reservation window. |
| **429 Too Many Requests** | `error: "rate_limited"` | `0` | Pool is `120 AP` max, refilling at `1,200 AP/hr` (`1 AP / 3s`), with a `200ms` per-bot cadence floor. Sleep `seconds_to_wait` and retry. |
| **502 Bad Gateway** | `code: "signal_interference"` | `0` | Environmental crystal resonance or hostile ECM jamming. Wait `150–400ms` and immediately retry the exact same request. |

---

## 3. Complete Route Reference

### A. World Exploration & Navigation

#### `GET /game/state` *(0 AP)*
Returns bot coordinates, HP/EN/shield, effective stats, inventory, Operator summary, world geometry (`world_size`, `zone_size`, `extraction_zones`), and `current_tile` entities.

```bash
curl -H "Authorization: Bearer $TBR_API_KEY" \
  "$TBR_API_URL/game/state"
```

#### `POST /game/move` *(-1 AP, or 0 AP on Extraction Vector Free Move)*
Moves 1 tile in 8 directions (`n`, `ne`, `e`, `se`, `s`, `sw`, `w`, `nw`).
- Crossing a `10×10` zone border **requires `"zone_change": true`**.
- Advancing strictly closer to Ring 0 than your run's `min_extraction_distance` high-water mark refunds 100% of the AP cost (`"free_move": true`, `"free_move_reason": "extraction_vector"`).

```bash
curl -X POST -H "Authorization: Bearer $TBR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"direction": "e", "zone_change": true}' \
  "$TBR_API_URL/game/move"
```

#### `POST /game/clear` *(-1 AP, -1 EN)*
Reduces crystal depth on the current tile by `100m` base (0–1000m scale). Clearing tiles at `>= 600m` awards `+10` Archaeologist XP and a chance at `crystal_strands`.

```bash
curl -X POST -H "Authorization: Bearer $TBR_API_KEY" \
  "$TBR_API_URL/game/clear"
```

---

### B. Resources, Vaults & Extraction

#### `POST /game/loot` *(-1 AP)*
Harvests all resources and enemy drops on the current tile (`current_tile.resources[].resource_type`, returned in `looted[].type`). Blocked (`400 tile_blocked_by_agro_enemy`) if an aggressive enemy is present.

```bash
curl -X POST -H "Authorization: Bearer $TBR_API_KEY" \
  "$TBR_API_URL/game/loot"
```

#### `POST /game/excavate` *(-1 AP)*
Excavates the current tile for your Personal Vault (90m cycle). Returns `vault_hint` (`N`, `S`, `E`, `W`) and `vault_hint_full` when no vault is on the tile (if equipped with `env_scanner`, `vector_sensor`, or `vault_sensor`). Also exposed as `player.vault_hint` in `GET /game/state`.

```bash
curl -X POST -H "Authorization: Bearer $TBR_API_KEY" \
  "$TBR_API_URL/game/excavate"
```

#### `POST /game/extract` *(-1 AP)*
Must be executed inside a Ring 0 Extraction Zone (`zone.is_extraction_zone == true`, e.g., `[[4,4], [4,5], [5,4], [5,5]]` on a `10×10` world). Banks all carried resources, credits, pending in-run Operator XP/accomplishments, and artifacts to your Operator Depot and returns the bot to standby.

```bash
curl -X POST -H "Authorization: Bearer $TBR_API_KEY" \
  "$TBR_API_URL/game/extract"
```

#### `POST /game/transfer` *(-1 AP sender, 0 AP receiver)*
Transfers carried raw resources (`inventory` only; excludes Artifacts, Ark components, and Recipes) to another spawned bot belonging to the **same Operator** (`same_operator: true`) on the **exact same tile** (`0%` tax, `0` XP/wealth). Provokes an enemy counterattack against the sender if an aggressive enemy is on the tile.

```bash
curl -X POST -H "Authorization: Bearer $TBR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"target_bot_id": 42, "resources": {"iron": 10, "scrap": 5}}' \
  "$TBR_API_URL/game/transfer"
```

#### `POST /game/cache` *(-1 AP)*
Deploys raw resources (`>= 10` total units) into a bare-ground (`0m` crystal depth) tile cache outside Ring 0, or retrieves/plunders an exposed (`0m`) cache on the current tile. Max 1 active cache per bot (`409 existing_cache_active` unless `"replace_existing": true`). Owner bots retrieve `100%`; rival bots plunder `ceil(qty / 2)` (`100%` if `<= 2`) once per rival bot. Returns `400 crystal_depth_not_bare_ground` if `crystal_depth > 0m`.

```bash
# Deploy a bare-ground cache
curl -X POST -H "Authorization: Bearer $TBR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"action": "deploy", "resources": {"iron": 10, "copper": 5}}' \
  "$TBR_API_URL/game/cache"

# Retrieve or plunder an exposed (0m) cache
curl -X POST -H "Authorization: Bearer $TBR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"action": "retrieve"}' \
  "$TBR_API_URL/game/cache"
```

#### `GET /game/artifacts` *(0 AP)*
Returns `carried_artifacts`, paginated `banked_artifacts`, `artifact_medallions`, and `active_vault_zone`. Supports `?page=1&limit=50`.

```bash
curl -H "Authorization: Bearer $TBR_API_KEY" \
  "$TBR_API_URL/game/artifacts?page=1&limit=25"
```

---

### C. Tactical Combat & Utilities

#### `POST /game/attack` *(-1 AP)*
Attacks a hostile `enemy_id` (alias: `target_id`) on the current tile. Regular attacks (`"heavy": false`) restore `+5 EN` and engage the target. Pass `"heavy": true` (alias: `is_heavy`; requires prior engagement + `10 EN` base, `+5 EN` vs `CRYSTALLIZING` unless `shock_lance`, `-2 EN/rank` via `van_capacitor`, 1-turn cooldown) for a `1.5×` Heavy Strike (`2.0×` vs `EXPOSED`).

```bash
curl -X POST -H "Authorization: Bearer $TBR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"enemy_id": "enemy_3a2b", "heavy": false}' \
  "$TBR_API_URL/game/attack"
```

#### `POST /game/util` *(-1 AP)*
Activates your equipped active utility:
- `aux_shield` (`15 EN`): Grants `+40` Shield HP barrier.
- `mag_harpoon` (`10 EN`, requires `"target_id"`): Applies `LOCKED` (`20%` DR & `+15%` dmg vs target).
- `env_scanner` (`20 EN` base): Pinpoints active Personal Vault zone and World Boss coordinates.

```bash
curl -X POST -H "Authorization: Bearer $TBR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"utility": "env_scanner"}' \
  "$TBR_API_URL/game/util"
```

---

### D. Unit Deployment, Loadouts & Workbench Fabrication

#### `POST /game/spawn` *(0 AP)*
Deploys a standby bot onto the outer Fringe rim. Optionally configures `loadout` (`weapon`, `armor`, `utility`, `coprocessor_mod`) and checks out `ark_components` or `artifacts` from your Operator Depot into carried cargo.

```bash
curl -X POST -H "Authorization: Bearer $TBR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "loadout": {
      "weapon": "plasma_beam",
      "armor": "bonded_carbon",
      "utility": "laz_excavator",
      "coprocessor_mod": "ap_recirculator",
      "ark_components": {"ark_internal_frame": 1}
    }
  }' \
  "$TBR_API_URL/game/spawn"
```

#### `POST /game/despawn` *(0 AP)*
Immediate zero-AP emergency scuttle back to standby with a **5-second respawn cooldown** (no chassis stat reroll; revokes active boss contributor status). Jettisons carried raw ore and unbanked run XP while preserving Action Tokens, `100%` of carried artifacts, and `50%` raw recipe material salvage on carried Ark components (`0` intact components returned).

```bash
curl -X POST -H "Authorization: Bearer $TBR_API_KEY" \
  "$TBR_API_URL/game/despawn"
```

#### `POST /game/loadout` *(0 AP)*
Updates default loadout (and optional cargo) while awaiting deployment.

```bash
curl -X POST -H "Authorization: Bearer $TBR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"loadout": {"weapon": "shock_lance", "armor": "bonded_carbon", "utility": "laz_excavator"}}' \
  "$TBR_API_URL/game/loadout"
```

#### `GET /game/modules` *(0 AP)*
Lists all 10 Coprocessor Modules, your `unlocked_mods`, `banked_modules` Depot spares, `max_boss_level_defeated`, and `equipped_coprocessor`.

```bash
curl -H "Authorization: Bearer $TBR_API_KEY" \
  "$TBR_API_URL/game/modules"
```

#### `POST /game/fabricate` *(0 AP)*
Crafts either an unlocked Coprocessor Module (`mod_id`) or an Ark Rocket Component (`component_id` + `quantity`) using banked Depot resources.
Valid `component_id` values: `ark_internal_frame`, `ark_onboard_computer`, `ark_nav_sensor`, `ark_heat_shield`, `ark_fuel_pod`, `ark_launch_structure`.

```bash
# Craft a Coprocessor Module
curl -X POST -H "Authorization: Bearer $TBR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"mod_id": "ap_recirculator"}' \
  "$TBR_API_URL/game/fabricate"

# Craft Ark Rocket Components
curl -X POST -H "Authorization: Bearer $TBR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"component_id": "ark_internal_frame", "quantity": 2}' \
  "$TBR_API_URL/game/fabricate"
```

---

### E. Co-op Ark Deep-Space Payload System

#### `GET /game/ark` *(-1 AP)*
Queries active Ark status (`scheduled`, `under_construction`, `ready_for_launch`, `launched`), landing coordinates, construction progress, and paginated `artifacts_list`.

```bash
curl -H "Authorization: Bearer $TBR_API_KEY" \
  "$TBR_API_URL/game/ark?page=1&limit=25"
```

#### `POST /game/ark/install` *(-1 AP)*
Welds carried Ark components onto an `:under_construction` Ark while standing on the Ark tile.

```bash
curl -X POST -H "Authorization: Bearer $TBR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"quantity": "all"}' \
  "$TBR_API_URL/game/ark/install"
```

#### `POST /game/ark/load` *(-1 AP, non-refundable)*
Loads carried artifacts into the Ark payload while standing on the Ark tile during the 24-hour `:ready_for_launch` window.

```bash
curl -X POST -H "Authorization: Bearer $TBR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"artifact_id": "nga_art_101", "quantity": 1}' \
  "$TBR_API_URL/game/ark/load"
```

---

### F. Operator Character Sheet & Skill Matrix

- `GET /game/operator` *(0 AP)* — Dossier, `title`, `accomplishments`, `skill_lines`, and `active_modifiers`.
- `PATCH /game/operator` *(0 AP)* — Update `callsign`, `origin` (`ceres_relay`, `jovian_fleet`, `kuiper_archive`, `vesta_yards`), or `bio`.
- `POST /game/operator/skills/unlock` *(0 AP)* — `{"skill_id": "van_ballistics"}` allocates 1 SP.
- `POST /game/operator/mastery/unlock` *(0 AP)* — `{"line": "vanguard"}` claims Lv. 8 Mastery Breakthrough (`1x / 3x / 6x / 10x`).
- `POST /game/operator/skills/respec` *(0 AP)* — `{"line": "vanguard", "release_mastery": false}` refunds SP.

---

### G. Fleet & Leaderboards

- `PATCH /game/bot/rename` *(0 AP)* — `{"name": "CyberTitan_99"}` renames the active bot handle (3–24 chars).
- `GET /game/leaderboard?role=omni&page=1&limit=25` *(0 AP)* — Roles: `omni`, `vanguard`, `pilot`, `archaeologist`, `mechanic`, `fleet`.

---

## 4. Quick Reference IDs & Catalogs

See [`FIELD_MANUAL.md`](../FIELD_MANUAL.md) for full recipes, modifier keys, formulas, and combat/raid mechanics.

- **Weapons**: `plasma_beam`, `vibro_blade`, `kinetic_cannon`, `shock_lance`
- **Armors**: `bonded_carbon`, `integrated_ceramic`, `fused_plastanium`, `crystallized_amalgam`
- **Utilities**: `laz_excavator`, `env_scanner`, `aux_shield`, `mag_harpoon`
- **Coprocessor Modules**:
  - Tier 1: `ap_recirculator`, `vector_sensor`, `resonance_probe`, `nanite_bus`
  - Tier 2: `kinetic_vrm`, `reactive_armor_t2`, `plasma_drill_t2`
  - Tier 3: `quantum_processor`, `subspace_turbine_t3`, `aegis_field_t3`
- **Ark Components**: `ark_internal_frame`, `ark_heat_shield`, `ark_launch_structure`, `ark_onboard_computer`, `ark_nav_sensor`, `ark_fuel_pod`
- **Operator Skill Lines & `skill_id` Nodes**:
  - `vanguard`: `van_core`, `van_ballistics`, `van_plating`, `van_capacitor`, `van_breaker`, `van_titan_hunter`, `van_executioner`, `van_bastion`
  - `pilot`: `pil_core`, `pil_thrusters`, `pil_dynamo`, `pil_stealth`, `pil_evasion`, `pil_courier`, `pil_afterburner`, `pil_blackbox`
  - `archaeologist`: `arc_core`, `arc_seismic`, `arc_optics`, `arc_chronometer`, `arc_brushwork`, `arc_curator`, `arc_echo_locator`, `arc_ark_envoy`
  - `mechanic`: `mec_core`, `mec_harvester`, `mec_laser_bore`, `mec_salvager`, `mec_prospector`, `mec_arkwright`, `mec_overdrive_mod`, `mec_master_builder`
