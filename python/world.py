"""
World Scheduler - Autonomous agent simulation coordinator.

This module orchestrates multi-agent daily life over timeboxed "day" runs,
driving autonomous actions (move, activities, chats, reflections) using
existing personas, interests, and relationships.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PYTHON_DIR = PROJECT_ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from db.models import Agent, AgentLocation, AgentSchedule, WorldEvent, Location, Activity
from db.session import get_session, init_db
from world.environment import EnvironmentService
from world.actions import ActionFactory
from world.reporting import ReportingService

DEFAULT_DB_URL = "sqlite:///./data/agents.db"
DEFAULT_CONFIG = PROJECT_ROOT / "world_config.yaml"
REPORTS_DIR = PROJECT_ROOT / "reports"


class WorldScheduler:
    """Orchestrates world simulation ticks and agent actions."""

    def __init__(
        self,
        db_url: str,
        config_path: Path,
        days: int = 1,
        agents: Optional[int] = None,
        tick_minutes: int = 60,
        start_hour: int = 8,
        end_hour: int = 20,
        persist: bool = True,
        dry_run: bool = False,
        max_concurrent_chats: int = 1,
        report_format: str = "markdown",
    ):
        self.db_url = db_url
        self.config = self._load_config(config_path)
        self.days = days
        self.max_agents = agents
        self.tick_minutes = tick_minutes
        self.start_hour = start_hour
        self.end_hour = end_hour
        self.persist = persist
        self.dry_run = dry_run
        self.max_concurrent_chats = max_concurrent_chats
        self.report_format = report_format

        self.engine = init_db(db_url)
        self.session = get_session(engine=self.engine)
        
        REPORTS_DIR.mkdir(exist_ok=True)
        
        # Initialize services
        location_graph = self.config.get("location_graph", {})
        self.env_service = EnvironmentService(self.session, location_graph)
        self.reporting_service = ReportingService(self.session, REPORTS_DIR)

    def _load_config(self, path: Path) -> Dict:
        """Load world configuration from YAML."""
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def get_active_agents(self) -> List[Agent]:
        """Retrieve agents for simulation."""
        query = self.session.query(Agent).order_by(Agent.id)
        if self.max_agents:
            query = query.limit(self.max_agents)
        return query.all()

    def run(self):
        """Execute the simulation."""
        print(f"Starting world simulation for {self.days} day(s)")
        print(f"Tick: {self.tick_minutes} minutes, Hours: {self.start_hour}-{self.end_hour}")
        print(f"DB: {self.db_url}, Persist: {self.persist}, Dry-run: {self.dry_run}")
        
        agents = self.get_active_agents()
        if not agents:
            print("No agents found. Please seed agents first.")
            return

        print(f"Active agents: {', '.join(a.name for a in agents)}")

        for day in range(self.days):
            day_label = (datetime.now() + timedelta(days=day)).strftime("%Y-%m-%d")
            print(f"\n{'='*60}")
            print(f"Day {day + 1}: {day_label}")
            print(f"{'='*60}")
            
            self._run_day(day_label, agents)

        print(f"\n{'='*60}")
        print("Simulation complete!")
        print(f"{'='*60}")

    def _run_day(self, day_label: str, agents: List[Agent]):
        """Run a single simulated day."""
        ticks_per_day = (self.end_hour - self.start_hour) * 60 // self.tick_minutes
        tick_events = []
        
        for tick_idx in range(ticks_per_day):
            current_hour = self.start_hour + (tick_idx * self.tick_minutes) // 60
            current_minute = (tick_idx * self.tick_minutes) % 60
            
            print(f"\nTick {tick_idx + 1}/{ticks_per_day} - {current_hour:02d}:{current_minute:02d}")
            
            # Select random agents for actions this tick
            active_agents = random.sample(agents, min(len(agents), random.randint(1, 3)))
            
            for agent in active_agents:
                event_meta = self._dispatch_action(agent, tick_idx, day_label, current_hour)
                tick_events.append(event_meta)
        
        # Generate daily report
        if self.persist and not self.dry_run:
            report_path = self.reporting_service.generate_daily_report(
                day_label, 
                self.report_format
            )
            print(f"\nReport saved to: {report_path}")

    def _dispatch_action(self, agent: Agent, tick_idx: int, day_label: str, hour: int) -> Dict:
        """Dispatch an action for an agent."""
        action_weights = self.config.get("action_weights", {
            "move": 0.15,
            "solo_reflection": 0.20,
            "duo_chat": 0.30,
            "group_meeting": 0.20,
            "task_update": 0.15,
        })
        
        action_type = random.choices(
            list(action_weights.keys()),
            weights=list(action_weights.values()),
            k=1
        )[0]
        
        print(f"  {agent.name} -> {action_type}")
        
        # Create and execute action
        action = ActionFactory.create(action_type, self.session, self.env_service)
        if action:
            metadata = action.execute(agent, tick_idx, day_label, hour, self.dry_run)
            return metadata
        
        return {"action": action_type, "status": "not_implemented"}


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    parser = argparse.ArgumentParser(description="World simulation scheduler")
    parser.add_argument("--db-url", default=DEFAULT_DB_URL, help="Database URL")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Config YAML path")
    parser.add_argument("--days", type=int, default=1, help="Number of days to simulate")
    parser.add_argument("--agents", type=int, help="Maximum number of agents (default: all)")
    parser.add_argument("--tick-minutes", type=int, default=60, help="Minutes per tick")
    parser.add_argument("--start-hour", type=int, default=8, help="Start hour (0-23)")
    parser.add_argument("--end-hour", type=int, default=20, help="End hour (0-23)")
    parser.add_argument("--persist", action="store_true", default=True, help="Persist events to DB")
    parser.add_argument("--no-persist", dest="persist", action="store_false", help="Don't persist")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without LLM calls")
    parser.add_argument("--max-concurrent-chats", type=int, default=1, help="Max concurrent chats")
    parser.add_argument("--report-format", choices=["markdown", "json", "both"], default="markdown")
    return parser


def main():
    """Main entrypoint."""
    parser = build_parser()
    args = parser.parse_args()
    
    scheduler = WorldScheduler(
        db_url=args.db_url,
        config_path=args.config,
        days=args.days,
        agents=args.agents,
        tick_minutes=args.tick_minutes,
        start_hour=args.start_hour,
        end_hour=args.end_hour,
        persist=args.persist,
        dry_run=args.dry_run,
        max_concurrent_chats=args.max_concurrent_chats,
        report_format=args.report_format,
    )
    
    scheduler.run()


if __name__ == "__main__":
    main()
