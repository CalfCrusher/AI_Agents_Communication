"""
Action Service - Implements agent action templates.

Provides action implementations:
- MoveAction: Navigate between locations
- SoloReflectionAction: Personal reflection/journaling
- DuoChatAction: Two-agent conversation
- GroupStandupAction: Multi-agent meeting
- TaskUpdateAction: Work task progress
"""

from __future__ import annotations

import json
import random
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from db.models import Agent, Activity, Location, WorldEvent, Memory
from world.environment import EnvironmentService


class BaseAction(ABC):
    """Base class for all actions."""

    def __init__(self, session: Session, env_service: EnvironmentService):
        self.session = session
        self.env = env_service

    @abstractmethod
    def execute(
        self, 
        agent: Agent, 
        tick_idx: int, 
        day_label: str, 
        hour: int,
        dry_run: bool = False
    ) -> Dict:
        """Execute the action and return metadata."""
        pass

    def log_event(
        self, 
        agent: Agent, 
        tick_idx: int, 
        activity: Optional[Activity], 
        location: Optional[Location],
        metadata: Dict
    ):
        """Log action event to database."""
        event = WorldEvent(
            agent_id=agent.id,
            tick_index=tick_idx,
            activity_id=activity.id if activity else None,
            location_id=location.id if location else None,
            metadata_json=json.dumps(metadata)
        )
        self.session.add(event)
        self.session.commit()


class MoveAction(BaseAction):
    """Move agent to a new location."""

    def execute(
        self, 
        agent: Agent, 
        tick_idx: int, 
        day_label: str, 
        hour: int,
        dry_run: bool = False
    ) -> Dict:
        current_loc = self.env.get_agent_current_location(agent)
        
        # Get nearby locations
        if current_loc:
            nearby = self.env.get_nearby_locations(current_loc, max_travel_minutes=30)
        else:
            # If no current location, get all locations
            nearby = self.session.query(Location).limit(5).all()
        
        if not nearby:
            return {"action": "move", "status": "no_destinations"}
        
        # Pick random open location
        open_locs = [loc for loc in nearby if self.env.is_location_open(loc, hour)]
        if not open_locs:
            return {"action": "move", "status": "all_closed"}
        
        target = random.choice(open_locs)
        
        metadata = {
            "action": "move",
            "from": current_loc.name if current_loc else "unknown",
            "to": target.name,
            "hour": hour,
            "day_label": day_label,
        }
        
        if not dry_run:
            success, error = self.env.move_agent(agent, target, datetime.utcnow())
            metadata["success"] = success
            metadata["error"] = error
            self.log_event(agent, tick_idx, None, target, metadata)
        
        return metadata


class SoloReflectionAction(BaseAction):
    """Agent performs personal reflection."""

    def execute(
        self, 
        agent: Agent, 
        tick_idx: int, 
        day_label: str, 
        hour: int,
        dry_run: bool = False
    ) -> Dict:
        activity = self.session.query(Activity).filter_by(name="reflection").first()
        location = self.env.get_agent_current_location(agent)
        
        # Generate simple reflection prompt
        prompts = [
            "reflect on recent experiences",
            "think about goals and aspirations",
            "review the day's events",
            "contemplate personal growth",
        ]
        
        metadata = {
            "action": "solo_reflection",
            "prompt": random.choice(prompts),
            "hour": hour,
            "location": location.name if location else "unknown",
            "day_label": day_label,
        }
        
        if not dry_run:
            self.log_event(agent, tick_idx, activity, location, metadata)
            
            # Optionally create a memory
            memory = Memory(
                agent_id=agent.id,
                kind="reflection",
                text=f"{agent.name} spent time {metadata['prompt']}",
                confidence=0.6,
                normalized_hash=f"reflection_{tick_idx}_{agent.id}",
                metadata_json=json.dumps({"tick": tick_idx, "day": day_label})
            )
            self.session.add(memory)
            self.session.commit()
        
        return metadata


class DuoChatAction(BaseAction):
    """Two agents have a conversation."""

    def execute(
        self, 
        agent: Agent, 
        tick_idx: int, 
        day_label: str, 
        hour: int,
        dry_run: bool = False
    ) -> Dict:
        activity = self.session.query(Activity).filter_by(name="coffee_chat").first()
        location = self.env.get_agent_current_location(agent)
        
        # Find another agent at same location
        if location:
            agents_here = self.env.get_agents_at_location(location)
            partners = [a for a in agents_here if a.id != agent.id]
        else:
            # Random partner
            partners = self.session.query(Agent).filter(Agent.id != agent.id).limit(3).all()
        
        if not partners:
            return {"action": "duo_chat", "status": "no_partner"}
        
        partner = random.choice(partners)
        
        metadata = {
            "action": "duo_chat",
            "agent_a": agent.name,
            "agent_b": partner.name,
            "location": location.name if location else "unknown",
            "hour": hour,
            "day_label": day_label,
        }
        
        if not dry_run:
            self.log_event(agent, tick_idx, activity, location, metadata)
            # TODO: In future, integrate with conversation.py for actual LLM chat
        
        return metadata


class GroupStandupAction(BaseAction):
    """Multi-agent group meeting."""

    def execute(
        self, 
        agent: Agent, 
        tick_idx: int, 
        day_label: str, 
        hour: int,
        dry_run: bool = False
    ) -> Dict:
        activity = self.session.query(Activity).filter_by(name="team_standup").first()
        location = self.env.get_agent_current_location(agent)
        
        # Find agents at same location
        if location:
            agents_here = self.env.get_agents_at_location(location)
            participants = [a.name for a in agents_here]
        else:
            participants = [agent.name]
        
        metadata = {
            "action": "group_standup",
            "participants": participants,
            "location": location.name if location else "unknown",
            "hour": hour,
            "day_label": day_label,
        }
        
        if not dry_run:
            self.log_event(agent, tick_idx, activity, location, metadata)
        
        return metadata


class TaskUpdateAction(BaseAction):
    """Agent works on tasks."""

    def execute(
        self, 
        agent: Agent, 
        tick_idx: int, 
        day_label: str, 
        hour: int,
        dry_run: bool = False
    ) -> Dict:
        activity = self.session.query(Activity).filter_by(name="work_task").first()
        location = self.env.get_agent_current_location(agent)
        
        tasks = [
            "code review",
            "feature implementation",
            "bug fixing",
            "documentation",
            "planning",
        ]
        
        metadata = {
            "action": "task_update",
            "task": random.choice(tasks),
            "location": location.name if location else "unknown",
            "hour": hour,
            "day_label": day_label,
        }
        
        if not dry_run:
            self.log_event(agent, tick_idx, activity, location, metadata)
        
        return metadata


class ActionFactory:
    """Factory for creating action instances."""

    ACTION_MAP = {
        "move": MoveAction,
        "solo_reflection": SoloReflectionAction,
        "duo_chat": DuoChatAction,
        "group_meeting": GroupStandupAction,
        "task_update": TaskUpdateAction,
    }

    @classmethod
    def create(
        cls, 
        action_type: str, 
        session: Session, 
        env_service: EnvironmentService
    ) -> Optional[BaseAction]:
        """Create action instance by type."""
        action_class = cls.ACTION_MAP.get(action_type)
        if action_class:
            return action_class(session, env_service)
        return None
