#!/usr/bin/env python3
"""Seed agents for world simulation."""

import sys
from pathlib import Path

# Add python directory to path
PYTHON_DIR = Path(__file__).parent / "python"
sys.path.insert(0, str(PYTHON_DIR))

from db.session import get_session
from db.models import Agent, Interest

def seed_agents():
    """Create initial agents for simulation."""
    session = get_session(db_url="sqlite:///data/agents.db")
    
    # Check if agents already exist
    existing = session.query(Agent).count()
    if existing > 0:
        print(f"Database already has {existing} agents. Skipping seed.")
        return
    
    agents_data = [
        {
            "name": "Alice",
            "bio": "Software engineer focused on backend systems",
            "job": "Senior Backend Engineer",
            "preferred_model": "llama3.1:8b",
            "interests": ["Python", "distributed systems", "rock climbing"]
        },
        {
            "name": "Bob",
            "bio": "Product designer who loves user research",
            "job": "UX Designer",
            "preferred_model": "deepseek-r1:8b",
            "interests": ["design thinking", "coffee", "photography"]
        },
        {
            "name": "Carol",
            "bio": "Data scientist passionate about ML",
            "job": "ML Engineer",
            "preferred_model": "hermes3:3b",
            "interests": ["machine learning", "running", "cooking"]
        },
        {
            "name": "Dave",
            "bio": "Frontend developer who crafts beautiful UIs",
            "job": "Frontend Engineer",
            "preferred_model": "gemma3:1b",
            "interests": ["React", "CSS animations", "gaming"]
        },
    ]
    
    for agent_data in agents_data:
        interests_tags = agent_data.pop("interests")
        agent = Agent(**agent_data)
        
        # Add interests as Interest objects
        for tag in interests_tags:
            interest = Interest(tag=tag, agent=agent)
            agent.interests.append(interest)
        
        session.add(agent)
        print(f"Created agent: {agent.name}")
    
    session.commit()
    print(f"\n✅ Seeded {len(agents_data)} agents")

if __name__ == "__main__":
    seed_agents()
