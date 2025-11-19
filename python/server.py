import sqlite3
import json
import os
import sys
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
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

# Mount visualizer directory to serve HTML/JS
VISUALIZER_DIR = os.path.join(BASE_DIR, "../visualizer")
if os.path.exists(VISUALIZER_DIR):
    app.mount("/visualizer", StaticFiles(directory=VISUALIZER_DIR), name="visualizer")
    print(f"✅ Serving visualizer at http://localhost:8000/visualizer/index.html")
else:
    print(f"⚠️  Visualizer directory not found at {VISUALIZER_DIR}")

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
                        
                        # Extract conversation if available
                        conversation = meta.get("conversation", [])
                        if conversation:
                            # Get the last message spoken by THIS agent
                            my_msgs = [m for m in conversation if m.get("role") == name]
                            if my_msgs:
                                last_msg = my_msgs[-1].get("content", "...")
                            else:
                                last_msg = "..."
                        else:
                            last_msg = None
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
                "status": status,
                "last_message": locals().get("last_msg", None)
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
