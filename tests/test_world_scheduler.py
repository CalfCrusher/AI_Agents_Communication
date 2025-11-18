"""Tests for world scheduler functionality."""

import json
import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIR = PROJECT_ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from db.models import Agent, Location, Activity, WorldEvent
from db.session import get_session, init_db


def test_tick_progression():
    """Test that tick calculations work correctly."""
    start_hour = 8
    end_hour = 20
    tick_minutes = 60
    
    ticks_per_day = (end_hour - start_hour) * 60 // tick_minutes
    assert ticks_per_day == 12, f"Expected 12 ticks, got {ticks_per_day}"
    
    # Test hour calculation for each tick
    for tick_idx in range(ticks_per_day):
        current_hour = start_hour + (tick_idx * tick_minutes) // 60
        current_minute = (tick_idx * tick_minutes) % 60
        
        assert current_hour >= start_hour and current_hour < end_hour
        assert current_minute == 0  # With 60-minute ticks
    
    print("✓ Tick progression test passed")


def test_dry_run_event_logging(tmp_path):
    """Test event logging in dry-run mode."""
    db_url = f"sqlite:///{tmp_path}/test.db"
    engine = init_db(db_url)
    session = get_session(engine=engine)
    
    # Create test agent
    agent = Agent(name="TestAgent", bio="Test bio")
    session.add(agent)
    session.commit()
    
    # Create test event
    event = WorldEvent(
        agent_id=agent.id,
        tick_index=0,
        metadata_json=json.dumps({
            "action": "move",
            "day_label": "2025-11-18",
            "hour": 8,
        })
    )
    session.add(event)
    session.commit()
    
    # Verify event was created
    events = session.query(WorldEvent).filter_by(agent_id=agent.id).all()
    assert len(events) == 1
    assert events[0].tick_index == 0
    
    metadata = json.loads(events[0].metadata_json)
    assert metadata["action"] == "move"
    assert metadata["day_label"] == "2025-11-18"
    
    print("✓ Dry-run event logging test passed")


def test_schedule_generation():
    """Test schedule slot generation."""
    start_hour = 8
    end_hour = 20
    tick_minutes = 60
    
    slots = []
    for tick_idx in range((end_hour - start_hour) * 60 // tick_minutes):
        hour = start_hour + (tick_idx * tick_minutes) // 60
        slots.append(hour)
    
    assert len(slots) == 12
    assert slots[0] == 8
    assert slots[-1] == 19
    
    print("✓ Schedule generation test passed")


def test_location_and_activity_seeding(tmp_path):
    """Test that locations and activities can be seeded."""
    db_url = f"sqlite:///{tmp_path}/test.db"
    engine = init_db(db_url)
    session = get_session(engine=engine)
    
    # Seed locations
    locations = [
        Location(name="Home", kind="home", capacity=4),
        Location(name="Office", kind="office", capacity=20),
    ]
    for loc in locations:
        session.add(loc)
    session.commit()
    
    # Seed activities
    activities = [
        Activity(name="work_task", category="work", default_duration_min=120),
        Activity(name="coffee_chat", category="social", default_duration_min=30),
    ]
    for act in activities:
        session.add(act)
    session.commit()
    
    # Verify
    assert session.query(Location).count() == 2
    assert session.query(Activity).count() == 2
    
    home = session.query(Location).filter_by(name="Home").first()
    assert home.kind == "home"
    assert home.capacity == 4
    
    work = session.query(Activity).filter_by(name="work_task").first()
    assert work.category == "work"
    
    print("✓ Location and activity seeding test passed")


if __name__ == "__main__":
    import tempfile
    
    print("Running world scheduler tests...\n")
    
    test_tick_progression()
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        test_dry_run_event_logging(tmp_path)
        test_location_and_activity_seeding(tmp_path)
    
    test_schedule_generation()
    
    print("\n✅ All tests passed!")
