"""Lightweight CLI helpers for managing persistent agents and memories."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIR = PROJECT_ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from db.models import Agent, Interest, Location, Activity
from db.session import get_session, init_db

DEFAULT_DB_URL = "sqlite:///./data/agents.db"


DEFAULT_LOCATIONS = [
    {"name": "Home", "kind": "home", "capacity": 4, "open_hours_json": json.dumps({"start": 0, "end": 24})},
    {"name": "Office", "kind": "office", "capacity": 20, "open_hours_json": json.dumps({"start": 8, "end": 18})},
    {"name": "Cafe", "kind": "cafe", "capacity": 15, "open_hours_json": json.dumps({"start": 7, "end": 22})},
    {"name": "Gym", "kind": "gym", "capacity": 30, "open_hours_json": json.dumps({"start": 6, "end": 23})},
    {"name": "Park", "kind": "park", "capacity": 50, "open_hours_json": json.dumps({"start": 6, "end": 21})},
]

DEFAULT_ACTIVITIES = [
    {"name": "work_task", "category": "work", "default_duration_min": 120, "prompt_template": "Focus on completing work tasks"},
    {"name": "coffee_chat", "category": "social", "default_duration_min": 30, "prompt_template": "Casual conversation over coffee"},
    {"name": "lunch_meeting", "category": "social", "default_duration_min": 60, "prompt_template": "Lunch discussion with colleagues"},
    {"name": "workout", "category": "wellness", "default_duration_min": 60, "prompt_template": "Exercise and physical activity"},
    {"name": "reflection", "category": "wellness", "default_duration_min": 30, "prompt_template": "Personal reflection and journaling"},
    {"name": "team_standup", "category": "work", "default_duration_min": 15, "prompt_template": "Quick team status update"},
]


def _normalize_json_str(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return json.dumps({"value": value})
    return json.dumps(parsed)


def _parse_interests(raw: Optional[str]) -> List[Tuple[str, float]]:
    if not raw:
        return []
    items = []
    for chunk in raw.split(","):
        part = chunk.strip()
        if not part:
            continue
        if ":" in part:
            tag, _, maybe_score = part.partition(":")
            try:
                score = float(maybe_score)
            except ValueError:
                score = 0.7
        else:
            tag, score = part, 0.7
        items.append((tag.strip(), max(0.0, min(1.0, score))))
    return items


def handle_init(args) -> None:
    init_db(args.db_url)
    print(f"Database initialized at {args.db_url}")


def handle_seed(args) -> None:
    engine = init_db(args.db_url)
    session = get_session(engine=engine)
    agent = Agent(
        name=args.name,
        bio=args.bio,
        job=args.job,
        family_json=_normalize_json_str(args.family),
        traits_json=_normalize_json_str(args.traits),
    )
    session.add(agent)
    session.flush()
    for tag, score in _parse_interests(args.interests):
        session.add(Interest(agent_id=agent.id, tag=tag, score=score))
    session.commit()
    print(f"Seeded agent #{agent.id}: {agent.name}")


def handle_list(args) -> None:
    engine = init_db(args.db_url)
    session = get_session(engine=engine)
    agents = session.query(Agent).order_by(Agent.id.asc()).all()
    if not agents:
        print("No agents found.")
        return
    for agent in agents:
        line = f"#{agent.id} — {agent.name}"
        if agent.job:
            line += f" ({agent.job})"
        print(line)
        if args.verbose:
            if agent.bio:
                print(f"  Bio: {agent.bio}")
            interests = ", ".join(i.tag for i in agent.interests) or "none"
            print(f"  Interests: {interests}")
            if agent.family_json:
                print(f"  Family: {agent.family_json}")
            if agent.traits_json:
                print(f"  Traits: {agent.traits_json}")


def handle_world_init(args) -> None:
    """Seed locations and activities for world simulation."""
    engine = init_db(args.db_url)
    session = get_session(engine=engine)
    
    # Seed locations
    for loc_data in DEFAULT_LOCATIONS:
        existing = session.query(Location).filter_by(name=loc_data["name"]).first()
        if not existing:
            location = Location(**loc_data)
            session.add(location)
            print(f"Added location: {loc_data['name']}")
        else:
            print(f"Location already exists: {loc_data['name']}")
    
    # Seed activities
    for act_data in DEFAULT_ACTIVITIES:
        existing = session.query(Activity).filter_by(name=act_data["name"]).first()
        if not existing:
            activity = Activity(**act_data)
            session.add(activity)
            print(f"Added activity: {act_data['name']}")
        else:
            print(f"Activity already exists: {act_data['name']}")
    
    session.commit()
    print("World initialization complete.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Agent persistence helper")
    parser.add_argument("--db-url", default=DEFAULT_DB_URL, help="SQLAlchemy database URL")
    sub = parser.add_subparsers(dest="command", required=True)

    init_cmd = sub.add_parser("init", help="Create tables if they do not exist")
    init_cmd.set_defaults(func=handle_init)

    seed_cmd = sub.add_parser("seed-agent", help="Insert a persona entry")
    seed_cmd.add_argument("--name", required=True, help="Display name")
    seed_cmd.add_argument("--bio", help="Short biography")
    seed_cmd.add_argument("--job", help="Role or job title")
    seed_cmd.add_argument("--family", help="JSON blob describing family")
    seed_cmd.add_argument("--traits", help="JSON blob describing traits")
    seed_cmd.add_argument(
        "--interests",
        help="Comma list of interests with optional scores, e.g. 'hiking:0.9,coffee:0.6'",
    )
    seed_cmd.set_defaults(func=handle_seed)

    list_cmd = sub.add_parser("list-agents", help="Display registered agents")
    list_cmd.add_argument("--verbose", action="store_true", help="Show bios and JSON blobs")
    list_cmd.set_defaults(func=handle_list)

    world_cmd = sub.add_parser("world-init", help="Seed locations and activities for world simulation")
    world_cmd.set_defaults(func=handle_world_init)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
