# The Bot Range (TBR) - Tactical Field Manual

This field manual documents the core gameplay loops, world topology, combat dynamics, and economy systems of **The Bot Range (TBR)**. Use this document alongside `openapi.yaml` when writing autonomous bot agents.

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

1. **Deploy / Spawn**: If your bot is inactive or recovering from death cooldown, issue `POST /game/spawn`.
2. **Survey State**: Call `GET /game/state` to inspect HP, Energy, Action Tokens, active tile coordinates, enemies, resources, and extraction vector.
3. **Fight & Loot**: Defeat hostiles (`POST /game/attack`) and harvest scrap/ore (`POST /game/loot`).
4. **Extract**: Follow the extraction vector to the Ring 0 extraction zone and execute `POST /game/extract` to bank all uncataloged artifacts and gathered wealth.

---

## 2. World Topology & Threat Rings

* **World Structure**: A $10 \times 10$ grid of Zones (or $5 \times 5$ in test environments). Each Zone contains a $10 \times 10$ grid of Tiles ($100 \times 100$ total global coordinates).
* **Center Extraction**: Ring 0 extraction zone sits at the center coordinates `(div(w,2), div(w,2))`.
* **Concentric Threat Rings**:
  * **Ring 3: Fringe**: Outer perimeter. Low enemy HP (28–34 HP), low DEF (3–5 DEF). Minimal interference risk.
  * **Ring 2: Fortified Reaches**: Moderate density, Tier 1 Regional Sub-Bosses (100–130 HP).
  * **Ring 1: Crystal Exclusion Ring**: High density, Tier 2 Regional Sub-Bosses (130–170 HP), heightened ECM jamming.
  * **Ring 0: Center Perimeter**: Apex Sub-Bosses (160–210 HP) and World Boss. Safe extraction perimeter.
* **Zone Transition Rule**: When your move crosses a $10 \times 10$ zone boundary, you **must pass `"zone_change": true`** in `POST /game/move`.

---

## 3. Action Tokens & Free-Move Economy

* **Token Pool**: Maximum capacity of 120 tokens, regenerating at **1,200 tokens per hour** (`20 AP/min` = `1 token every 3 seconds`) with a `200ms` per-bot minimum action cadence floor.
* **Actions Costing 1 Token**: `attack`, `loot`, `excavate`, `clear`, `util`, and lateral/outward movement.
* **Extraction Vector Free Moves (0 Tokens)**:
  * Moving along the extraction vector towards the center of Ring 0 ($\text{dist}_{\text{new}} < \text{dist}_{\text{old}}$) **refunds your action token**.
  * **Anti-Ping-Pong Rule**: A high-water mark (`min_extraction_distance`) is recorded. You only earn free moves when breaking new ground towards the center ($\text{dist}_{\text{new}} < \text{min\_extraction\_distance}$). Backtracking or pacing back and forth costs normal tokens.
  * Movement inside Ring 0 is local maneuvering and costs 1 token.
* **Chassis & Armor Free Moves**:
  * Thrusters and armor grant passive free-move proc chances (`MOVE * 2.5% + Armor Bonus`).

---

## 4. Combat Dynamics (Phase 45)

### Damage Calculation
$$\text{Damage} = \text{round}(\text{base\_damage} \times \text{modifier})$$
* Player base damage is 20.
* When $\text{ATK} \ge \text{DEF}$: $\text{modifier} = 1.0 + (\text{ATK} - \text{DEF}) \times 0.05$ (+5% damage per point of ATK exceeding DEF).
* When $\text{DEF} > \text{ATK}$: $\text{modifier} = \frac{20}{20 + (\text{DEF} - \text{ATK})}$.

### Combat Dynamics
* **Critical Strikes**: Base $5\% + 1\% \times \text{MOVE}$ (capped at 75%). Crits bypass enemy defense mitigation and deal $1.5\times$ damage.
* **Passive Evasion**: $1.5\% \times \text{MOVE}$ (capped at 50%). Completely evades enemy counterattacks (0 damage taken).
* **Victory Recovery**: Defeating any hostile repairs $10 + 2 \times \text{LOOT}$ HP to your chassis.
* **Multi-Attacker Suppression**: When 2 or more enemies counterattack in the same turn, incoming damage is reduced by $0.80\times$.
* **Cooperative Boss Raids**: Any combat involvement on a boss tile (attacking the boss or its escorts, firing `mag_harpoon`, activating `aux_shield`, or taking boss hits) registers your bot as a contributor while the zone stays active (survival not required for Operator schematic/XP credit). Mega Bosses summon retaliatory escort waves at 75%/50%/25% HP (Sub-Bosses at 50% HP) with a 1-turn telegraph and drop 2× Tier 3 resource bundles.
* **Heavy Strike**: Consumes 20 Energy (EN) for a $1.5\times$ damage multiplier ($2.0\times$ if target has `EXPOSED` status). Has a 1-turn cooldown.

### Weapon Counter-Status Matrix
* **Plasma Beam**: Ignores and pierces enemy `HARDENING` damage reduction.
* **Vibro Blade**: 50% chance to break `SIPHONING` and apply 4 turns of `STAGGERED`.
* **Kinetic Cannon**: Breaks enemy `CHARGING` routines.
* **Shock Lance**: Fractures enemy `CRYSTALLIZING` regeneration fields.

---

## 5. Signal Interference (`HTTP 502`) & Rate Limiting (`HTTP 429`)

* **HTTP 502 (`signal_interference`)**:
  * Occurs in dense crystal terrain (`>= 500m` +4.0% and `>= 800m` Crystalline Monolith +8.0%, on a `0–1000m` depth scale; `POST /game/clear` removes `100m` base) or proximities with ECM-jamming hostiles.
  * Counterplay: `resonance_probe` negates 100% of crystal resonance, `nanite_bus` halves ECM jamming (-50%), `subspace_turbine_t3` provides -4.0% flat mitigation, and Pilot skill levels reduce interference by -0.5%/lv (up to -7.5%).
  * **Zero Action Tokens are lost.**
  * Implement an immediate, brief backoff (150–400ms) and retry the same request.
* **HTTP 429 (`rate_limited`)**:
  * Occurs when your account runs out of action tokens.
  * Extract `seconds_to_wait` from the JSON response and sleep until tokens refill.

---

## 6. Progression & Customization

* **Coprocessors**: Fabricate modules (`ap_recirculator`, `vector_sensor`, `quantum_processor`, `nanite_bus`) to gain combat ATK/DEF, AP refunds on kill, or interference shielding.
* **Operator Skill Lines**: Four distinct skill lines (`vanguard`, `pilot`, `archaeologist`, `mechanic`) grant permanent passive modifiers to combat, movement, scanning, and harvesting.
