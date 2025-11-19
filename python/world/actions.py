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
from world.conversation_runner import WorldConversationRunner


class BaseAction(ABC):
    """Base class for all actions."""

    def __init__(self, session: Session, env_service: EnvironmentService):
        self.session = session
        self.env = env_service
        self.conv_runner = WorldConversationRunner(session)

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
            # Use day_label in hash to avoid collisions across days
            # Check for existence to avoid collisions on re-runs
            hash_key = f"reflection_{day_label}_{tick_idx}_{agent.id}"
            existing = self.session.query(Memory).filter_by(normalized_hash=hash_key).first()
            
            if not existing:
                memory = Memory(
                    agent_id=agent.id,
                    kind="reflection",
                    text=f"{agent.name} spent time {metadata['prompt']}",
                    confidence=0.6,
                    normalized_hash=hash_key,
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
            return {"action": "duo_chat", "status": "no_partner", "day_label": day_label}
        
        partner = random.choice(partners)
        
        # Generate conversation topics based on interests
        topics = [
            "recent experiences and activities",
            "weekend plans",
            "work and projects",
            "hobbies and interests",
        ]
        topic = random.choice(topics)
        
        metadata = {
            "action": "duo_chat",
            "agent_a": agent.name,
            "agent_b": partner.name,
            "location": location.name if location else "unknown",
            "hour": hour,
            "day_label": day_label,
            "topic": topic,
        }
        
        if not dry_run:
            print(f"    🗣️  {agent.name} and {partner.name} chatting about {topic}...")
            
            # Run actual Ollama conversation!
            try:
                conversation = self.conv_runner.run_duo_chat(
                    agent_a=agent,
                    agent_b=partner,
                    context=f"Have a brief friendly chat about {topic}",
                    turns=2,  # 2 exchanges (4 total messages)
                    max_words=40
                )
                
                metadata["conversation"] = conversation
                metadata["num_turns"] = len(conversation)
                print(f"    ✅ {len(conversation)} messages exchanged")
                
            except Exception as e:
                print(f"    ❌ Conversation error: {e}")
                metadata["error"] = str(e)
            
            self.log_event(agent, tick_idx, activity, location, metadata)
        
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
            participants = agents_here
        else:
            participants = [agent]
        
        metadata = {
            "action": "group_standup",
            "participants": [a.name for a in participants],
            "location": location.name if location else "unknown",
            "hour": hour,
            "day_label": day_label,
        }
        
        if not dry_run:
            # Only run group chat if there are 2+ agents
            if len(participants) >= 2:
                print(f"    👥 Group standup with {', '.join(a.name for a in participants)}...")
                
                try:
                    conversation = self.conv_runner.run_group_chat(
                        agents=list(participants),
                        context="Quick team standup: share what you're working on",
                        turns_per_agent=1,
                        max_words=30
                    )
                    
                    metadata["conversation"] = conversation
                    metadata["num_turns"] = len(conversation)
                    print(f"    ✅ {len(conversation)} updates shared")
                    
                except Exception as e:
                    print(f"    ❌ Standup error: {e}")
                    metadata["error"] = str(e)
            
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
