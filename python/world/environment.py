"""
Environment Service - Manages locations and agent movement.

Handles:
- Location tracking and occupancy rules
- Travel cost and time calculations
- Location availability based on open hours
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from db.models import Agent, Location, AgentLocation


class EnvironmentService:
    """Manages locations, occupancy, and movement."""

    def __init__(self, session: Session, location_graph: Dict[str, Dict[str, int]]):
        """
        Initialize environment service.
        
        Args:
            session: Database session
            location_graph: Dict mapping location names to travel times
        """
        self.session = session
        self.location_graph = location_graph
        self._location_cache: Dict[int, Location] = {}

    def get_location(self, location_id: int) -> Optional[Location]:
        """Get location by ID with caching."""
        if location_id not in self._location_cache:
            loc = self.session.query(Location).filter_by(id=location_id).first()
            if loc:
                self._location_cache[location_id] = loc
        return self._location_cache.get(location_id)

    def get_location_by_name(self, name: str) -> Optional[Location]:
        """Get location by name."""
        return self.session.query(Location).filter_by(name=name).first()

    def get_agent_current_location(self, agent: Agent) -> Optional[Location]:
        """Get agent's current location."""
        agent_loc = (
            self.session.query(AgentLocation)
            .filter_by(agent_id=agent.id, until_ts=None)
            .order_by(AgentLocation.since_ts.desc())
            .first()
        )
        if agent_loc:
            return self.get_location(agent_loc.location_id)
        return None

    def is_location_open(self, location: Location, hour: int) -> bool:
        """Check if location is open at given hour."""
        if not location.open_hours_json:
            return True  # Always open if no hours specified
        
        try:
            hours = json.loads(location.open_hours_json)
            start = hours.get("start", 0)
            end = hours.get("end", 24)
            return start <= hour < end
        except (json.JSONDecodeError, KeyError):
            return True

    def get_location_occupancy(self, location: Location) -> int:
        """Get current number of agents at location."""
        return (
            self.session.query(AgentLocation)
            .filter_by(location_id=location.id, until_ts=None)
            .count()
        )

    def can_enter_location(self, location: Location, hour: int) -> bool:
        """Check if location has capacity and is open."""
        if not self.is_location_open(location, hour):
            return False
        
        current_occupancy = self.get_location_occupancy(location)
        return current_occupancy < location.capacity

    def get_travel_time(self, from_location: Location, to_location: Location) -> int:
        """Get travel time in minutes between two locations."""
        if from_location.name == to_location.name:
            return 0
        
        # Check location graph
        from_graph = self.location_graph.get(from_location.name, {})
        time = from_graph.get(to_location.name)
        
        if time is not None:
            return time
        
        # Default fallback
        return 30

    def move_agent(
        self, 
        agent: Agent, 
        to_location: Location, 
        timestamp: datetime
    ) -> Tuple[bool, Optional[str]]:
        """
        Move agent to new location.
        
        Returns:
            (success, error_message)
        """
        # Close current location
        current = (
            self.session.query(AgentLocation)
            .filter_by(agent_id=agent.id, until_ts=None)
            .first()
        )
        
        if current:
            current.until_ts = timestamp
        
        # Create new location record
        new_loc = AgentLocation(
            agent_id=agent.id,
            location_id=to_location.id,
            since_ts=timestamp,
        )
        self.session.add(new_loc)
        self.session.commit()
        
        return True, None

    def get_nearby_locations(
        self, 
        current_location: Location, 
        max_travel_minutes: int = 30
    ) -> List[Location]:
        """Get locations reachable within max travel time."""
        nearby = []
        
        graph = self.location_graph.get(current_location.name, {})
        for loc_name, travel_time in graph.items():
            if travel_time <= max_travel_minutes:
                loc = self.get_location_by_name(loc_name)
                if loc:
                    nearby.append(loc)
        
        return nearby

    def get_agents_at_location(self, location: Location) -> List[Agent]:
        """Get all agents currently at a location."""
        agent_locs = (
            self.session.query(AgentLocation)
            .filter_by(location_id=location.id, until_ts=None)
            .all()
        )
        
        agent_ids = [al.agent_id for al in agent_locs]
        if not agent_ids:
            return []
        
        return self.session.query(Agent).filter(Agent.id.in_(agent_ids)).all()
