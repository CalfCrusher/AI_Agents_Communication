# VISUALIZATION_PLAN.md

## Overview
This plan details the exact steps to add an isometric "Sims-style" viewer to your AI Agents project. It requires creating two new files (`python/server.py` and `visualizer/index.html`) and running a simple API server.

---

## 1. Dependencies
Open your terminal and install the required web server libraries:

```bash
pip install fastapi uvicorn
```

---

## 2. Backend: Create `python/server.py`
Create a new file named `server.py` inside your `python/` directory and paste the following code. This API reads the agent locations from your SQLite database.

```python
import sqlite3
import json
import os
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Allow browser to access local API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Robust database path finding
# Tries to find agents.db in ../data or ./data relative to this script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POSSIBLE_DB_PATHS = [
    os.path.join(BASE_DIR, "../data/agents.db"),
    os.path.join(BASE_DIR, "data/agents.db"),
    os.path.join(BASE_DIR, "../data/test_agents.db"), # Fallback for testing
]

DB_PATH = None
for path in POSSIBLE_DB_PATHS:
    if os.path.exists(path):
        DB_PATH = path
        break

# Isometric Grid Mapping (Hardcoded coordinates for the visualizer)
LOCATION_MAP = {
    "Home":   {"x": 0, "y": 0},
    "Gym":    {"x": 0, "y": 4},
    "Park":   {"x": 2, "y": 2},
    "Office": {"x": 4, "y": 0},
    "Cafe":   {"x": 4, "y": 4}
}

@app.get("/state")
def get_world_state():
    if not DB_PATH:
        return {"error": "Database not found. Run world.py first.", "agents": []}

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Query: Active agents + Location + Last Event Metadata
        query = """
        SELECT 
            a.name, 
            a.job, 
            l.name as location, 
            l.kind,
            (SELECT metadata_json FROM world_events we 
             WHERE we.agent_id = a.id 
             ORDER BY we.tick_index DESC LIMIT 1) as last_event
        FROM agents a
        JOIN agent_locations al ON a.id = al.agent_id
        JOIN locations l ON al.location_id = l.id
        WHERE al.until_ts IS NULL
        """
        
        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()
        
        agents = []
        for r in rows:
            name, job, loc_name, loc_kind, last_event_json = r
            
            # Default status
            status = "Idle"
            
            # Parse rich status from event metadata
            if last_event_json:
                try:
                    meta = json.loads(last_event_json)
                    action = meta.get("action", "Idle")
                    
                    if action == "duo_chat":
                        partner = meta.get("agent_b") if meta.get("agent_a") == name else meta.get("agent_a")
                        status = f"Chatting w/ {partner}" if partner else "Chatting"
                    elif action == "group_standup":
                        status = "Meeting"
                    elif action == "move":
                        status = "Moving"
                    elif action == "solo_reflection":
                        status = "Reflecting"
                    elif action == "task_update":
                        status = "Working"
                    else:
                        status = action
                except:
                    pass

            # Map location name to grid coordinates
            coords = LOCATION_MAP.get(loc_name, {"x": 2, "y": 2})

            agents.append({
                "name": name,
                "job": job,
                "location": loc_name,
                "coordinates": coords,
                "status": status
            })
            
        return {"agents": agents}
    
    except Exception as e:
        return {"error": str(e), "agents": []}

if __name__ == "__main__":
    import uvicorn
    if not DB_PATH:
        print("⚠️  WARNING: Database not found. Run 'python world.py' to create it.")
    else:
        print(f"✅ Serving world state from: {DB_PATH}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

## 3. Frontend: Create `visualizer/index.html`
Create a new folder named `visualizer` in your project root. Inside it, create `index.html` and paste this code.

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Agent Sandbox Viewer</title>
    <script src="[https://cdn.jsdelivr.net/npm/phaser@3.55.2/dist/phaser.js](https://cdn.jsdelivr.net/npm/phaser@3.55.2/dist/phaser.js)"></script>
    <style>
        body { margin: 0; background: #1e1e1e; overflow: hidden; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        #ui-layer { position: absolute; top: 20px; left: 20px; color: white; pointer-events: none; }
        h1 { margin: 0; font-size: 24px; text-shadow: 2px 2px 0 #000; }
        .status-box { background: rgba(0,0,0,0.5); padding: 10px; border-radius: 8px; display: inline-block; margin-top: 10px; }
    </style>
</head>
<body>

<div id="ui-layer">
    <h1>🤖 Autonomous Agents World</h1>
    <div class="status-box">
        System: <span id="connection-status" style="color: yellow;">Connecting...</span>
    </div>
</div>

<script>
const config = {
    type: Phaser.AUTO,
    width: window.innerWidth,
    height: window.innerHeight,
    pixelArt: true, // Essential for the pixel art look
    backgroundColor: '#1e1e1e',
    scene: { preload: preload, create: create, update: update }
};

const game = new Phaser.Game(config);

// Isometric Configuration
const TILE_W = 64;
const TILE_H = 32;
const MAP_SIZE = 6; 
const OFFSET_X = window.innerWidth / 2;
const OFFSET_Y = 150;

let agentSprites = {};

function preload() {
    // Load assets from Phaser labs (internet required)
    // You can download these images to an 'assets' folder for offline use
    this.load.image('tile', '[https://labs.phaser.io/assets/tilemaps/iso/tile.png](https://labs.phaser.io/assets/tilemaps/iso/tile.png)');
    this.load.image('agent', '[https://labs.phaser.io/assets/sprites/phaser-dude.png](https://labs.phaser.io/assets/sprites/phaser-dude.png)');
}

function create() {
    // 1. Draw the Environment
    const locations = {
        "0,0": { color: 0xe74c3c, name: "Home" },   // Red
        "4,0": { color: 0x3498db, name: "Office" }, // Blue
        "4,4": { color: 0xf1c40f, name: "Cafe" },   // Yellow
        "0,4": { color: 0x2ecc71, name: "Gym" },    // Green
        "2,2": { color: 0x9b59b6, name: "Park" }    // Purple
    };

    // Draw Grid
    for (let x = 0; x < MAP_SIZE; x++) {
        for (let y = 0; y < MAP_SIZE; y++) {
            const isoX = (x - y) * TILE_W + OFFSET_X;
            const isoY = (x + y) * TILE_H + OFFSET_Y;
            
            let tile = this.add.image(isoX, isoY, 'tile');
            
            let key = `${x},${y}`;
            if (locations[key]) {
                tile.setTint(locations[key].color);
                this.add.text(isoX, isoY + 10, locations[key].name, { fontSize: '12px', color: '#fff', stroke: '#000', strokeThickness: 2 }).setOrigin(0.5);
            } else {
                tile.setTint(0x95a5a6); // Grey floor
            }
        }
    }

    // 2. Start Data Polling
    this.time.addEvent({ delay: 1000, callback: fetchState, callbackScope: this, loop: true });
}

function update() {
    // Phaser handles animations automatically
}

async function fetchState() {
    const statusSpan = document.getElementById('connection-status');
    try {
        const response = await fetch('http://localhost:8000/state');
        const data = await response.json();
        
        if(data.error) {
            statusSpan.innerText = "Waiting for DB...";
            statusSpan.style.color = "orange";
        } else {
            statusSpan.innerText = "LIVE";
            statusSpan.style.color = "#2ecc71";
            updateAgents(data.agents);
        }
    } catch (e) { 
        statusSpan.innerText = "Server Offline";
        statusSpan.style.color = "#e74c3c";
    }
}

function updateAgents(agents) {
    // Remove agents who are gone
    const currentNames = agents.map(a => a.name);
    Object.keys(agentSprites).forEach(name => {
        if (!currentNames.includes(name)) {
            agentSprites[name].container.destroy();
            delete agentSprites[name];
        }
    });

    // Update or Create agents
    agents.forEach(agent => {
        const gridX = agent.coordinates.x;
        const gridY = agent.coordinates.y;
        
        // Convert Grid -> Screen Coordinates
        // -30 Y offset to make them stand ON the tile
        const targetX = (gridX - gridY) * TILE_W + OFFSET_X;
        const targetY = (gridX + gridY) * TILE_H + OFFSET_Y - 20;

        if (agentSprites[agent.name]) {
            // MOVEMENT: Smoothly slide existing agent
            const entity = agentSprites[agent.name];
            game.scene.scenes[0].tweens.add({
                targets: entity.container,
                x: targetX,
                y: targetY,
                duration: 800,
                ease: 'Power2'
            });
            
            // Update Label
            entity.label.setText(`${agent.name}\n<${agent.status}>`);
            
        } else {
            // SPAWN: Create new agent group
            const scene = game.scene.scenes[0];
            const container = scene.add.container(targetX, targetY);
            
            const sprite = scene.add.image(0, 0, 'agent');
            sprite.setTint(0xffffff);
            
            const label = scene.add.text(0, -40, `${agent.name}\n<${agent.status}>`, { 
                fontSize: '12px', 
                fill: '#fff', 
                align: 'center',
                stroke: '#000',
                strokeThickness: 3
            }).setOrigin(0.5);
            
            container.add([sprite, label]);
            
            agentSprites[agent.name] = { container, sprite, label };
        }
    });
}
</script>
</body>
</html>
```

---

## 4. How to Run

You need two terminals open.

**Terminal 1: Run the Simulation**
(This generates the data)
```bash
cd python
python world.py --days 1 --persist
```

**Terminal 2: Run the Visualizer API**
(This serves data to the browser)
```bash
cd python
python server.py
```

**View It:**
Open `visualizer/index.html` in your web browser (drag and drop the file into Chrome/Firefox).
