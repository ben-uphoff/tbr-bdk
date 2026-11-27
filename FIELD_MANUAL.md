# The Bot Range (TBR) - Tactical Field Manual

This field manual is the authoritative gameplay specification for **The Bot Range (TBR)**. Use it alongside `openapi.yaml` and `docs/API_GUIDE.md` when developing autonomous bot agents.

---

## 1. Core Gameplay Loop

```
           [ Spawn Bot ] (POST /game/spawn)
                 │
                 ▼
           [ Survey State ] (GET /game/state)
                 │
   ┌─────────────┴─────────────┐
   ▼                           ▼
[ Combat / Loot ]       [ Navigation ]
(POST /attack, /loot)   (POST /game/move)
   │                           │
   └─────────────┬─────────────┘
                 ▼
     [ Reach Ring 0 Center ]
                 │
                 ▼
         [ Extract Vault ] (POST /game/extract)
```

1. **Deploy / Spawn**: If `player.spawned` is `false` (or after a 5s death/despawn cooldown), issue `POST /game/spawn` (0 AP). Handle `HTTP 202` (`status: "queued"`) by sleeping `retry_after_seconds` and retrying.
2. **Survey State**: Call `GET /game/state` (0 AP) to inspect coordinates (`player.zone`, `player.tile`), HP/EN/Shield, `action_limiter`, `zone.extraction_vector`, `zone.is_extraction_zone`, `current_tile`, and `operator`.
3. **Fight, Clear & Loot**: Defeat hostiles (`POST /game/attack`), clear crystalline terrain (`POST /game/clear`), excavate Personal Vaults (`POST /game/excavate`), and harvest resources (`POST /game/loot`).
4. **Extract**: Navigate to a Ring 0 Extraction Zone (`zone.is_extraction_zone == true`) and execute `POST /game/extract` to bank carried resources, artifacts, Ark components, and pending in-run Operator XP/accomplishments.

---

## 2. World Topology & Threat Rings

* **World Structure**: Default $10 \times 10$ grid of Zones ($10 \times 10$ Tiles per Zone = $100 \times 100$ global tiles; $5 \times 5$ in test environments). Always read `world.world_size`, `world.zone_size`, and `world.extraction_zones` from `GET /game/state`.
* **Center Extraction (`ring_0`)**: `[[4,4], [4,5], [5,4], [5,5]]` on a $10 \times 10$ world (`[[2,2]]` on $5 \times 5$).
* **Concentric Threat Rings** (by Manhattan zone distance $d$ to the nearest Ring 0 zone, relative to `max_d`):
  * **`fringe`** (Ring 3, **`1.0x`** risk multiplier): $d > \text{round}(\text{max\_d} \times 0.50)$. Outer perimeter; no standard enemies on outer world edge tiles.
  * **`fortified_reaches`** (Ring 2, **`1.6x`**): $\text{round}(\text{max\_d} \times 0.25) < d \le \text{round}(\text{max\_d} \times 0.50)$. Hosts Tier 1 Regional Sub-Bosses (`Level 1`).
  * **`exclusion_ring`** (Ring 1, **`2.3x`**): $0 < d \le \text{round}(\text{max\_d} \times 0.25)$. Hosts Tier 2 Regional Sub-Bosses (`Level 2`) and elevated ECM jamming.
  * **`ring_0`** (Ring 0 Extraction Perimeter, **`3.0x`**): $d = 0$. Hosts Tier 3 Regional Sub-Bosses (`Level 3`) and safe extraction.
* **Zone Transition Rule**: Crossing a zone boundary **requires `"zone_change": true`** in `POST /game/move`.

---

## 3. Action Tokens, Free Moves & Energy Economy

* **Token Pool**: Capacity **`120 AP`**, regenerating at **`1,200 AP/hr`** (`20 AP/min` = `1 AP / 3s`), with a **`200ms`** per-bot minimum action cadence floor.
* **Actions Costing 1 AP**: `POST /game/move` (unless refunded), `POST /game/attack`, `POST /game/loot`, `POST /game/excavate`, `POST /game/clear`, `POST /game/util`, `POST /game/transfer`, `POST /game/cache`, `POST /game/extract`, `GET /game/ark`, `POST /game/ark/install`, `POST /game/ark/load`.
* **Actions Costing 0 AP**: `GET /game/state`, `POST /game/spawn`, `POST /game/despawn`, `POST /game/loadout`, `GET /game/modules`, `POST /game/fabricate`, `GET /game/artifacts`, `GET /game/leaderboard`, `PATCH /game/bot/rename`, and all `/game/operator*` routes.
* **Extraction Vector Free Moves (0 AP)**:
  * Moving strictly closer to Ring 0 than your run's high-water mark (`d_new < d_old` and `d_new < min_extraction_distance`) refunds 100% of the AP cost (`"free_move": true, "free_move_reason": "extraction_vector"`).
  * Movement inside Ring 0 (`is_extraction_zone: true`), lateral moves, or backtracking costs 1 AP (unless a passive thruster/armor proc triggers).
* **Chassis & Armor Free-Move Proc**:
  * $\text{chassis\_free\_move} = \min(60.0\%, \text{effective\_move} \times 2.5\% + \text{armor\_free\_move\_pct})$.
  * $\text{total\_free\_move} = \min(85.0\%, \text{chassis\_free\_move} + \text{free\_move\_ap\_pct})$.
* **Movement Streak Energy (EN) Restoration**:
  * Each consecutive move restores $\text{prev\_consecutive\_moves} \times (5 + \text{move\_streak\_en\_bonus})$ EN (halved when entering deep crystal $\ge 500\text{m}$ unless `resonance_probe` or `ignore_deep_crystal_en_penalty` is active).
  * `consecutive_moves` resets to `0` when `en >= max_en` or when performing any non-move action.

---

## 4. Combat Dynamics & Cooperative Boss Raids

### Damage Formulas
$$\text{Damage} = \max(1, \text{round}(\text{base\_damage} \times \text{modifier}))$$
* **Player Attack** (`base_damage = 20`):
  * If $\text{ATK} \ge \text{DEF}$: $\text{modifier} = 1.0 + (\text{ATK} - \text{DEF}) \times 0.05$.
  * If $\text{DEF} > \text{ATK}$: $\text{modifier} = \frac{20}{20 + (\text{DEF} - \text{ATK})}$ (bypassed on Critical Strikes).
* **Enemy Counterattack**:
  * Base damage: `round(5 * risk_multiplier)` (standard), `round(12 * risk_multiplier)` (Sub-Boss), `50` flat (Mega World Boss).
  * Softened enemy ATK superiority: if $\text{enemy\_atk} > \text{player\_def}$, $\text{modifier} = \min(1.4, 1.0 + (\text{enemy\_atk} - \text{player\_def}) \times 0.015)$; else $\frac{20}{20 + (\text{player\_def} - \text{enemy\_atk})}$.
  * Enemies gain `+10 EN` per turn and execute a `1.5x` Heavy Strike at `30 EN` (2-turn cooldown).

### Combat Mechanics
* **Regular Attack (`"heavy": false`)**: Restores **`+5 EN`**, decrements Heavy Strike cooldown by 1, and adds the target to `engaged_enemies`.
* **Heavy Strike (`"heavy": true`)**: Requires target already in `engaged_enemies` (cannot be the opening action). Consumes **`10 EN` base** (`+5 EN` if target has `CRYSTALLIZING` and weapon is not `shock_lance`; `-2 EN/rank` from Vanguard `van_capacitor`, min `1 EN`). Deals **`1.5x`** damage (**`2.0x`** if target has `EXPOSED`), plus `heavy_strike_dmg_pct`, with a **1-turn cooldown**.
* **Critical Strikes**: $\min(75\%, 5\% + 1\% \times \text{MOVE})$. Bypasses enemy DEF and deals **`1.5x`** damage.
* **Passive Evasion**: $\min(50\%, 1.5\% \times \text{MOVE})$. Completely evades enemy counterattacks (0 damage taken).
* **Victory Recovery**: Defeating any hostile repairs $10 + 2 \times \text{LOOT}$ HP to your chassis.
* **Multi-Attacker Suppression**: When 2+ enemies counterattack in the same turn, incoming damage is scaled by **`0.80x`**.
* **Random Encounters**: Entering an empty non-rim tile can trigger an `"ephemeral_*"` ambush. It does **not** deal a free immediate hit on entry, remains agro'd on the tile, and drops `2x` resource quantities when defeated.

### Cooperative Boss Raid Rules
* **Qualifying Engagement**: Only an **active attack** (`POST /game/attack` on the Boss, Sub-Boss, or its `add_boss_*` / `add_subboss_*` escort drones) or firing **`mag_harpoon`** (`POST /game/util`) registers your bot as a contributor (`raid_telemetry.contributed == true`). Passive presence, taking hits, or activating `aux_shield` does **not** register contributor credit.
* **Engagement Radius**:
  * **Mega World Boss (`boss_*`)**: Must remain within the **`3×3` Mega-Boss aura** (`boss_aura == true`, $|\Delta tx| \le 1, |\Delta ty| \le 1$). Moving outside the aura or leaving the zone revokes contributor status.
  * **Regional Sub-Boss (`subboss_*`)**: Must remain on the **exact sub-boss tile**. Moving off the tile revokes contributor status.
* **Death vs. Despawn**: Combat death, bystander death, and extraction preserve contributor status while the zone remains active. Manual despawn (`POST /game/despawn`), inactivity timeout, or dropship impact revokes contributor status.
* **Direct-to-Depot Rewards (Once per Operator)**: Upon defeat, boss resource loot bundles, schematic unlocks, Vanguard XP, and `bosses_defeated` are awarded **once per Operator** and routed directly to the shared **Operator Depot** (`banked_resources` / `unlocked_mods`). Mega World Bosses grant a **guaranteed schematic drop** (or bonus rare ore if all schematics are already unlocked) and 2× Tier 3 resource bundles; Regional Sub-Bosses grant **graduated schematic drop chances** scaling by tier/ring alongside tiered resource bundles. Mega Bosses deploy retaliatory escort waves at `75%`, `50%`, and `25%` HP (Sub-Bosses at `50%` HP).

---

## 5. Signal Interference (`HTTP 502`) & Rate Limiting (`HTTP 429`)

* **HTTP 502 (`signal_interference`)**:
  * Occurs in dense crystal terrain (`>= 500m` +4.0% and `>= 800m` Crystalline Monolith +8.0% on a `0–1000m` depth scale) or proximities with ECM-jamming hostiles.
  * Counterplay: `resonance_probe` negates 100% of crystal resonance, `nanite_bus` halves ECM jamming (`-50%`), `subspace_turbine_t3` provides `-4.0%` flat mitigation, and Pilot skill levels reduce interference by `-0.5%/lv` (up to `-7.5%`).
  * **Zero Action Tokens are lost.** Sleep `150–400ms` and retry the exact request.
* **HTTP 429 (`rate_limited`)**:
  * Read `seconds_to_wait` from the JSON response and sleep until tokens refill.

---

## 6. Equipment & Coprocessor Catalog

### Weapons (Counter-Status Matrix)
| ID | Name | Enemy Status Counter Effect |
| :--- | :--- | :--- |
| `plasma_beam` | Plasma Beam | Ignores and pierces enemy `HARDENING` 20% damage reduction. |
| `vibro_blade` | Vibro Blade | 50% chance to break `SIPHONING` and apply 4 turns of `STAGGERED` (25% miss chance, -25% damage). |
| `kinetic_cannon` | Kinetic Cannon | 50% chance to break `CHARGING` (2x damage) and apply 4 turns of `EXPOSED` (`2.0x` Heavy Strike). |
| `shock_lance` | Shock Lance | 50% chance to break `CRYSTALLIZING` and apply 4 turns of `FRACTURED` (`+30%` damage taken); ignores `+5 EN` Heavy Strike penalty. |

### Armors
| ID | Name | Damage Reduction (`armor_dr`) | Free-Move Bonus (`armor_free_move_pct`) |
| :--- | :--- | :---: | :---: |
| `bonded_carbon` | Bonded Carbon | `0%` | `+20%` |
| `integrated_ceramic` | Integrated Ceramic | `5%` | `+15%` |
| `fused_plastanium` | Fused Plastanium | `15%` | `+5%` |
| `crystallized_amalgam` | Crystallized Amalgam | `20%` | `0%` |

### Utilities
| ID | Mode | AP / EN Cost | Effect & Modifiers |
| :--- | :--- | :---: | :--- |
| `laz_excavator` | Passive | `—` | Grants `+2 LOOT` (`loot_bonus: 2`). Cannot be activated via `/game/util`. |
| `env_scanner` | Passive + Active | `1 AP / 20 EN` base | Passive: `+10%` base Vault excavate chance (`excavate_base_bonus_pct: 10`), `vault_sensor: true` (enables cardinal `vault_hint` & detects buried caches). Active: reveals `active_vault_zone` & `boss_coordinates` (`+10` Archaeologist XP if vault active). Cost reduced by `-4 EN` at Archaeologist Lv 1 and `-3 EN/rank` via `arc_optics`. |
| `aux_shield` | Active | `1 AP / 15 EN` | Grants `+40` Shield HP barrier (up to `max_shield`, `80` base). Does not decay on activation turn. |
| `mag_harpoon` | Active | `1 AP / 10 EN` | Requires `target_id`. Applies `LOCKED` (`+15%` damage dealt, `-20%` damage taken, 5 hits). Registers boss raid contribution. |

### Coprocessor Modules (10 Curated Modules)
Coprocessor schematics are unlocked by defeating bosses (`unlocked_mods`) and fabricated into shared Operator Depot stock (`banked_modules`) via `POST /game/fabricate` (0 AP). Equipping a module on `POST /game/spawn` or `POST /game/loadout` draws 1 spare from `banked_modules`; unequipping returns 1 spare. On extraction or despawn, equipped modules remain fitted or return per run rules—check `player.equipped_coprocessor` and `banked_modules` via `GET /game/modules`.

| ID | Tier | Req. Boss Lv | Resource Cost | Exact Modifiers (`modifiers`) |
| :--- | :---: | :---: | :--- | :--- |
| `ap_recirculator` | 1 | 0 | `copper: 10, iron: 5` | `{"kill_ap_refund_pct": 50}` |
| `vector_sensor` | 1 | 0 | `copper: 8, scrap: 10` | `{"move_bonus": 1, "free_move_ap_pct": 8, "vault_sensor": true}` |
| `resonance_probe` | 1 | 0 | `scrap: 12, copper: 6` | `{"negate_crystal_interference": true, "ignore_deep_crystal_en_penalty": true, "clear_depth_bonus_pct": 4}` |
| `nanite_bus` | 1 | 0 | `iron: 10, scrap: 8` | `{"halve_ecm_jamming": true, "combat_start_shield_hp": 15}` |
| `kinetic_vrm` | 2 | 2 | `iron: 20, gold: 5, crystal_strands: 3` | `{"max_en_bonus": 10, "damage_to_en_pct": 25}` |
| `reactive_armor_t2` | 2 | 2 | `iron: 25, gold: 5, copper: 10` | `{"def_bonus": 2, "max_hp_bonus": 15, "max_shield_bonus": 20}` |
| `plasma_drill_t2` | 2 | 2 | `gold: 10, copper: 20, crystal_strands: 4` | `{"loot_bonus": 2, "harvest_proc_yield_bonus_pct": 25}` |
| `quantum_processor` | 3 | 3 | `circuits: 5, gold: 15, crystal_strands: 10` | `{"atk_bonus": 3, "heavy_strike_dmg_pct": 15, "kill_ap_refund_pct": 100}` |
| `subspace_turbine_t3` | 3 | 3 | `circuits: 9, gold: 15, copper: 20` | `{"move_bonus": 2, "max_en_bonus": 20, "move_streak_en_bonus": 3, "flat_interference_mitigation": 4.0}` |
| `aegis_field_t3` | 3 | 3 | `circuits: 8, gold: 18, iron: 30` | `{"max_hp_bonus": 25, "combat_start_shield_hp": 25, "aegis_cheat_death": true}` |

---

## 7. Economy, Extraction, Despawn, Transfers & Caches

### Resource Credit Valuation (on Extraction)
| Resource | Tier | Credit Value | Primary Use |
| :--- | :--- | :---: | :--- |
| `scrap` | Common | `1` | Credits, Fabrication, Ark |
| `copper` | Common | `3` | Credits, Fabrication, Ark |
| `iron` | Common | `5` | Credits, Fabrication, Ark |
| `gold` | Uncommon | `1` | Tier 2–3 Coprocessor Fabrication, Respec |
| `crystal_strands` | Uncommon | `1` | Tier 2–3 Coprocessor & Ark Fabrication |
| `circuits` | Rare | `1` | Tier 3 Coprocessor Fabrication |
| `quantum_core` | Special | `100` | High-value credit extraction |

Extracted credits = $\text{round}(\text{base\_credits} \times (1 + \text{extract\_credit\_bonus\_pct} / 100))$.

### Extraction-Gated Progression & Manual Despawn
* **Extraction-Gated XP**: Standard in-run Operator XP and accomplishments (hostile kills, looting, terrain clearing, Vault excavation, fleeing) accumulate in ephemeral run state (`run_xp`, `run_accomplishments`) and **only commit to your Operator on successful `POST /game/extract`**.
* **Manual Despawn (`POST /game/despawn`, 0 AP)**: Triggers a **5-second respawn cooldown**, preserves chassis base stats (no stat reroll), revokes boss contributor status, discards carried raw ore and unbanked run XP, protects **100% of carried artifacts** (`banked` $\to$ Depot, `personal_vault` $\to$ active Vault), and salvages **50% of raw recipe materials** from carried Ark components into `banked_resources` (**0** intact components returned).

### Same-Operator Tactical Inventory Handoff (`POST /game/transfer`)
* **Scope**: Transfers carried raw resources (`inventory` only; excludes Artifacts, Ark components, and Recipes) to another spawned bot belonging to the **same Operator** (`current_tile.players` entry with `same_operator: true`) on the **exact same tile**.
* **Cost & Combat**: `-1 AP` for sender, `0 AP` for receiver, `0%` tax, `0` XP/wealth awarded. Allowed while agro enemies are present, but provokes a standard enemy counterattack against the sender.

### Bare-Ground Deployable Tile Caches (`POST /game/cache`)
* **Bare-Ground Rule (`0m`)**: Can only be deployed or accessed when tile `crystal_depth == 0m` (clear with `POST /game/clear` first). Blocked inside Ring 0 Extraction Zones.
* **Creation & Limits**: Raw resources only (`>= 10` total units minimum). Max **1 active cache per bot** (deploying elsewhere returns `409 existing_cache_active` unless `"replace_existing": true`) and **1 cache per tile** (additional drops merge). 24-hour TTL; 100% immune to Ark dropship blasts and Mega-Boss effects.
* **Crystal Concealment & Plundering**: As crystal regrows (`crystal_depth > 0m`), caches are hidden from rival `GET /game/state` scans unless the rival has `env_scanner`, `vector_sensor`, or `vault_sensor`. Owner bots retrieve **100%** and remove the cache; rival bots plunder **`ceil(qty / 2)`** per stack (**100%** when `qty <= 2`), **strictly once per rival bot**.

---

## 8. Personal Vault Triangulation & Excavation Streaks

1. **Locate the Vault Zone**:
   * Call `GET /game/artifacts` (`0 AP`) to read `active_vault_zone` (`{"zone_x": x, "zone_y": y}`), or activate `env_scanner` via `POST /game/util` (`1 AP`, `20 EN` base).
   * Personal Vaults operate on a **90-minute cooldown** after extraction (`-10 min/rank` via Archaeologist `arc_chronometer`, floor 10m).
2. **Navigate & Triangulate Inside the Zone**:
   * If you have `env_scanner`, `vector_sensor`, or `vault_sensor` (`Archaeologist` sensor), `GET /game/state` (`player.vault_hint`) and `POST /game/excavate` (`vault_hint`: `"N" | "S" | "E" | "W"`) return cardinal direction hints toward your Vault tile.
   * When your bot is standing on the exact Vault tile, `vault_hint` becomes `null`. (With Archaeologist `arc_echo_locator` Rank 2, `env_scanner` reveals exact tile coordinates inside the zone.)
3. **Excavation Streak Mechanics**:
   * Consecutive `POST /game/excavate` calls on the same tile build a streak $n \ge 1$:
     $$\text{Chance}(n) = \min\left(100\%, 10\% + \text{excavate\_base\_bonus\_pct} + (n - 1) \times (10\% + \text{excavate\_streak\_bonus\_pct})\right)$$
   * Note: `env_scanner` grants `+10%` (`excavate_base_bonus_pct`). Any non-excavate action (`move`, `attack`, `loot`, `transfer`, `cache`, or non-scanner `util`) **resets** the streak to 0.
   * **Important**: Opening a Vault checkpoints the carried artifact immediately. If you die or despawn before extracting, a `personal_vault` artifact returns to your active Personal Vault (`status: "active"`) on that tile.

---

## 9. Co-op Ark Component Catalog & Construction Lifecycle

### Ark Rocket Components (6 Canonical IDs)
| `component_id` | Name | Credit Value | Fabrication Recipe | 50% Despawn Salvage |
| :--- | :--- | :---: | :--- | :--- |
| `ark_internal_frame` | Internal Frame Truss | `500` | `iron: 50, copper: 25, scrap: 25` | `iron: 25, copper: 12, scrap: 12` |
| `ark_heat_shield` | Thermal Heat Shielding | `1,000` | `iron: 40, scrap: 60` | `iron: 20, scrap: 30` |
| `ark_launch_structure` | Launch Gantry Connector | `1,500` | `iron: 60, copper: 50, scrap: 40` | `iron: 30, copper: 25, scrap: 20` |
| `ark_onboard_computer` | Onboard Guidance Computer | `2,500` | `copper: 100, crystal_strands: 50` | `copper: 50, crystal_strands: 25` |
| `ark_nav_sensor` | Navigation Radar Probe | `2,500` | `scrap: 100, crystal_strands: 60` | `scrap: 50, crystal_strands: 30` |
| `ark_fuel_pod` | Plasma Fuel Containment Cell | `10,000` | `copper: 250, crystal_strands: 150` | `copper: 125, crystal_strands: 75` |

### End-to-End Ark Lifecycle
1. **Monitor (`GET /game/ark`, -1 AP)**: Check `ark.status` (`scheduled`, `under_construction`, `ready_for_launch`, `launched`), `zone`, `tile`, `drive_survived`, and `construction` (`current_credits` / `target_credits`).
2. **Site Prep (`scheduled` $\to$ `under_construction`)**: When the dropship lands, if landing tile `crystal_depth < 200m`, the Quantum Drive survives; otherwise it shatters (`drive_survived: false`) and resets after 1h. Landing clears non-boss enemies and despawns bots in the `3×3` blast zone.
3. **Fabricate (`POST /game/fabricate`, 0 AP)**: Craft components from Depot `banked_resources` into `banked_ark_components` (`{"component_id": "...", "quantity": 1}`).
4. **Checkout (`POST /game/spawn` or `/game/loadout`, 0 AP)**: Pass `loadout.ark_components: {"ark_internal_frame": 1}` to move components into carried cargo.
5. **Clear & Install (`POST /game/ark/install`, -1 AP)**: Stand on the Ark tile. Installation efficiency scales with the average crystal depth of the 8 adjacent tiles:
   $$\text{efficiency} = \max\left(0.0, 1.0 - \frac{\text{avg\_adjacent\_depth} \times (1 - \text{ark\_crystal\_penalty\_ignore\_pct}/100)}{1000.0}\right)$$
   Launching requires `current_credits >= target_credits` **and** `avg_adjacent_depth < 200.0m`.
6. **Load Artifacts (`POST /game/ark/load`, -1 AP, non-refundable)**: During the 24-hour `:ready_for_launch` window, check out banked artifacts via `spawn` (`loadout.artifacts`) or carry excavated artifacts to the Ark tile and load them for permanent deep-space medallions.

---

## 10. Operator Skill Trees, Mastery Gates & XP Triggers

### Level Curve & Respecs
* **XP Formula**: $\text{XP}(L) = 100 \times L^2$ for Levels `1..15` (`Lv. 1 = 100`, `Lv. 8 = 6,400`, `Lv. 15 = 22,500`). Each level grants 1 Skill Point (SP) in that line.
* **Mastery Gate (Level 8)**: Progression pauses at **Lv. 8** until you claim `POST /game/operator/mastery/unlock` (`{"line": "..."}`).
* **Respec Cost (`POST /game/operator/skills/respec`)**: Free at `<= Lv. 5`; at `Lv. 6+`, costs `15 * (level - 4) scrap + 10 * (level - 4) copper` (`+5 gold` if `release_mastery: true`).

### Escalating Mastery Ladder (`1x / 3x / 6x / 10x`)
| Skill Line | 1st Mastery (`1x`) | 2nd Mastery (`3x`) | 3rd Mastery (`6x`) | 4th Mastery (`10x`) |
| :--- | :--- | :--- | :--- | :--- |
| `vanguard` | `1` boss, `25` hostiles | `3` bosses, `75` hostiles | `6` bosses, `150` hostiles | `10` bosses, `300` hostiles |
| `pilot` | `5` extracts, `2,500` cr | `15` extracts, `10,000` cr | `30` extracts, `25,000` cr | `50` extracts, `60,000` cr |
| `archaeologist` | `3` vaults, `1` ark artifact | `8` vaults, `3` ark artifacts | `15` vaults, `6` ark artifacts | `25` vaults, `10` ark artifacts |
| `mechanic` | `2` ark installs, `3` fabs, `10` clears | `6` installs, `8` fabs, `30` clears | `12` installs, `15` fabs, `60` clears | `20` installs, `25` fabs, `100` clears |

### XP & Accomplishment Triggers
| Action | Skill Line | XP Awarded | Accomplishment | Commit Timing |
| :--- | :--- | :---: | :--- | :--- |
| Defeat standard hostile | `vanguard` | `25` (Fringe), `30` (Reaches), `35` (Exclusion), `45` (Ring 0) | `hostiles_defeated +1` | Extraction-gated |
| Defeat Sub-Boss (`Lv 1 / 2 / 3`) | `vanguard` | `100 / 175 / 250` | `bosses_defeated +1` | Immediate (1/Op) |
| Defeat Mega World Boss | `vanguard` | `500` | `bosses_defeated +1` | Immediate (1/Op) |
| Flee tile with agro enemy | `pilot` | `15` | `—` | Extraction-gated |
| Extract at Ring 0 | `pilot` | `min(150, 40 + credits/25) + ring_bonus` (`0/30/60/100`) | `extractions_completed +1`, `credits_extracted` | Immediate |
| Activate `env_scanner` (active vault) | `archaeologist` | `10` | `—` | Extraction-gated |
| Clear deep crystal (`>= 600m`) | `archaeologist` | `10` | `—` | Extraction-gated |
| Open Personal Vault | `archaeologist` | `120` (`+60` if global first) | `vaults_opened +1` | Extraction-gated |
| Load artifact onto Ark | `archaeologist` | `80 * qty` | `—` | Immediate |
| Loot tile resources | `mechanic` | `12 * resource_stacks` | `—` | Extraction-gated |
| Clear crystal terrain (`POST /clear`) | `mechanic` | `15` | `crystal_clears +1` | Extraction-gated |
| Fabricate Coprocessor (T1 / T2–3) | `mechanic` | `50 / 100` | `items_fabricated +1` | Immediate |
| Fabricate Ark Component | `mechanic` | `100 * qty` | `items_fabricated +qty` | Immediate |
| Install Ark Component | `mechanic` | `80 * qty` | `ark_components_installed +qty` | Immediate |

### Complete Skill Node Catalog (32 Nodes)
Each line has 8 nodes: Tier 0 Core (auto-unlocked at Lv 1), Tier 1-A/B (`Lv 1+`, 3R), Tier 2-A/B (`Lv 4+`, 3R, req 2R in T1), Tier 3 (`Lv 9+`, 3R, req Mastery + 1R in T2-A or T2-B), Tier 4-A/B (`Lv 11+`, 2R, req Mastery + 3R in T2).

#### Vanguard (`vanguard`)
| `skill_id` | Tier | Max Rank | Prereqs | Effect per Rank (`active_modifiers` key) |
| :--- | :---: | :---: | :--- | :--- |
| `van_core` | 0 | 1 (auto) | `Lv 1` | `+2 ATK`, `+1 DEF` (`atk_bonus`, `def_bonus`) |
| `van_ballistics` | 1 | 3 | `Lv 1` | `+1 ATK`, `+5 Max HP` (`atk_bonus`, `max_hp_bonus`) |
| `van_plating` | 1 | 3 | `Lv 1` | `+1 DEF`, `+5%` DR while shielded/locked (`def_bonus`, `defend_dr_pct`) |
| `van_capacitor` | 2 | 3 | `Lv 4, van_ballistics:2` | `-2 EN` Heavy Strike cost, `+10%` Heavy Strike dmg (`heavy_strike_en_reduction`, `heavy_strike_dmg_pct`) |
| `van_breaker` | 2 | 3 | `Lv 4, van_plating:2` | `+8%` dmg vs buffed hostiles (`buffed_enemy_dmg_pct`) |
| `van_titan_hunter` | 3 | 3 | `Lv 9, Mastery, van_capacitor:1 \| van_breaker:1` | `+10%` Boss dmg, `-5%` Boss dmg taken (`boss_dmg_pct`, `boss_dr_pct`) |
| `van_executioner` | 4 | 2 | `Lv 11, Mastery, van_capacitor:3` | `+8 HP`, `+5 EN` on kill (`kill_heal_hp`, `kill_restore_en`) |
| `van_bastion` | 4 | 2 | `Lv 11, Mastery, van_breaker:3` | `+12` combat-start Shield HP (`combat_start_shield_hp`) |

#### Pilot (`pilot`)
| `skill_id` | Tier | Max Rank | Prereqs | Effect per Rank (`active_modifiers` key) |
| :--- | :---: | :---: | :--- | :--- |
| `pil_core` | 0 | 1 (auto) | `Lv 1` | `+2 MOVE`, `+10 Max EN` (`move_bonus`, `max_en_bonus`) |
| `pil_thrusters` | 1 | 3 | `Lv 1` | `+1 MOVE`, `+4%` free-move AP chance (`move_bonus`, `free_move_ap_pct`) |
| `pil_dynamo` | 1 | 3 | `Lv 1` | `+10 Max EN`, `+2 EN` per move streak step (`max_en_bonus`, `move_streak_en_bonus`) |
| `pil_stealth` | 2 | 3 | `Lv 4, pil_thrusters:2` | `-10%` enemy agro trigger (`agro_reduction_pct`) |
| `pil_evasion` | 2 | 3 | `Lv 4, pil_dynamo:2` | `+20%` parting hit dodge on flee (`flee_dodge_pct`) |
| `pil_courier` | 3 | 3 | `Lv 9, Mastery, pil_stealth:1 \| pil_evasion:1` | `+8%` extract credits, `+10%` extract Pilot XP (`extract_credit_bonus_pct`, `extract_pilot_xp_pct`) |
| `pil_afterburner` | 4 | 2 | `Lv 11, Mastery, pil_stealth:3` | `+15 EN` & `25%` AP refund on zone change (`zone_change_en_restore`, `zone_change_ap_refund_pct`) |
| `pil_blackbox` | 4 | 2 | `Lv 11, Mastery, pil_evasion:3` | Rescues `15%` carried standard resources on death (`death_bank_rescue_pct`) |

#### Archaeologist (`archaeologist`)
| `skill_id` | Tier | Max Rank | Prereqs | Effect per Rank (`active_modifiers` key) |
| :--- | :---: | :---: | :--- | :--- |
| `arc_core` | 0 | 1 (auto) | `Lv 1` | `+5%` base excavate floor, `-4 EN` scanner cost (`excavate_base_bonus_pct`, `scanner_en_reduction`) |
| `arc_seismic` | 1 | 3 | `Lv 1` | `+4%` excavate base, `+3%` streak gain (`excavate_base_bonus_pct`, `excavate_streak_bonus_pct`) |
| `arc_optics` | 1 | 3 | `Lv 1` | `-3 EN` scanner cost, adds Distance Bracket (`scanner_en_reduction`, `scanner_distance_bracket`) |
| `arc_chronometer` | 2 | 3 | `Lv 4, arc_seismic:2` | `-10 min` Personal Vault cooldown (`personal_vault_cd_reduction_min`) |
| `arc_brushwork` | 2 | 3 | `Lv 4, arc_optics:2` | `20%` no-agro excavate, `-10%` counterattack dmg (`excavate_no_agro_pct`, `excavate_counter_dr_pct`) |
| `arc_curator` | 3 | 3 | `Lv 9, Mastery, arc_chronometer:1 \| arc_brushwork:1` | `+25%` Vault XP, `+1 gold / +1 crystal_strands` (`vault_xp_bonus_pct`, `vault_bonus_gold_and_strands`) |
| `arc_echo_locator` | 4 | 2 | `Lv 11, Mastery, arc_chronometer:3` | `25%` AP refund on miss; R2 reveals exact Vault tile (`excavate_inconclusive_ap_refund_pct`, `scanner_exact_vault_tile`) |
| `arc_ark_envoy` | 4 | 2 | `Lv 11, Mastery, arc_brushwork:3` | `50%` AP refund on Ark load, `+1` Medallion (`ark_load_ap_refund_pct`, `ark_launch_bonus_medallions`) |

#### Mechanic (`mechanic`)
| `skill_id` | Tier | Max Rank | Prereqs | Effect per Rank (`active_modifiers` key) |
| :--- | :---: | :---: | :--- | :--- |
| `mec_core` | 0 | 1 (auto) | `Lv 1` | `+2 LOOT`, `+3%` crystal clear power (`loot_bonus`, `clear_depth_bonus_pct`) |
| `mec_harvester` | 1 | 3 | `Lv 1` | `+1 LOOT`, `+15%` harvest proc yield (`loot_bonus`, `harvest_proc_yield_bonus_pct`) |
| `mec_laser_bore` | 1 | 3 | `Lv 1` | `+4%` clear power, `33%` (`100%` at R3) 0-EN clear (`clear_depth_bonus_pct`, `clear_zero_en_pct`) |
| `mec_salvager` | 2 | 3 | `Lv 4, mec_harvester:2` | `-8%` Workbench fabrication cost (`fabrication_cost_discount_pct`) |
| `mec_prospector` | 2 | 3 | `Lv 4, mec_laser_bore:2` | `20%` chance on clear to sift 1–2 bonus ore (`clear_sift_resource_pct`) |
| `mec_arkwright` | 3 | 3 | `Lv 9, Mastery, mec_salvager:1 \| mec_prospector:1` | `-25%` Ark crystal penalty, `+8%` install credit (`ark_crystal_penalty_ignore_pct`, `ark_install_credit_bonus_pct`) |
| `mec_overdrive_mod` | 4 | 2 | `Lv 11, Mastery, mec_salvager:3` | `+10 HP/EN` w/ Coprocessor; R2 `-1` Boss tier gate (`coprocessor_hp_bonus`, `coprocessor_en_bonus`, `fabrication_boss_tier_reduction`) |
| `mec_master_builder` | 4 | 2 | `Lv 11, Mastery, mec_prospector:3` | `20%` AP refund & `+15%` credit on Ark install (`ark_install_ap_refund_pct`, `ark_install_extra_credit_pct`) |
