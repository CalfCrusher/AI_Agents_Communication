"""SQLAlchemy models for agent personas, conversations, and memories."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    and_,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False, unique=True)
    bio = Column(Text)
    job = Column(String(120))
    family_json = Column(Text)
    traits_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    interests = relationship("Interest", back_populates="agent", cascade="all, delete-orphan")
    memories = relationship("Memory", back_populates="agent", cascade="all, delete-orphan")


class Interest(Base):
    __tablename__ = "interests"
    __table_args__ = (UniqueConstraint("agent_id", "tag", name="uq_interest_agent_tag"),)

    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    tag = Column(String(120), nullable=False)
    score = Column(Float, default=0.5)
    created_at = Column(DateTime, default=datetime.utcnow)

    agent = relationship("Agent", back_populates="interests")


class Relationship(Base):
    __tablename__ = "relationships"
    __table_args__ = (
        UniqueConstraint("from_agent_id", "to_agent_id", name="uq_relationship_pair"),
    )

    id = Column(Integer, primary_key=True)
    from_agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    to_agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"))
    type = Column(String(64))
    strength = Column(Float, default=0.0)
    since_date = Column(Date)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    from_agent = relationship("Agent", foreign_keys=[from_agent_id])
    to_agent = relationship("Agent", foreign_keys=[to_agent_id])


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True)
    scenario = Column(Text)
    initial_prompt = Column(Text)
    started_at = Column(DateTime, default=datetime.utcnow)

    turns = relationship("Turn", back_populates="conversation", cascade="all, delete-orphan")


class Turn(Base):
    __tablename__ = "turns"

    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    round = Column(Integer, nullable=False)
    interaction = Column(Integer, nullable=False)
    turn = Column(Integer, nullable=False)
    agent_id = Column(Integer, ForeignKey("agents.id"))
    model = Column(String(120), nullable=False)
    role = Column(String(32), nullable=False, default="assistant")
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="turns")
    agent = relationship("Agent")
    source_memory = relationship("Memory", back_populates="source_turn", uselist=False)


class Memory(Base):
    __tablename__ = "memories"
    __table_args__ = (UniqueConstraint("normalized_hash", name="uq_memory_hash"),)

    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(64), nullable=False)
    text = Column(Text, nullable=False)
    confidence = Column(Float, default=0.5)
    source_turn_id = Column(Integer, ForeignKey("turns.id", ondelete="SET NULL"))
    normalized_hash = Column(String(64), nullable=False)
    metadata_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    agent = relationship("Agent", back_populates="memories")
    source_turn = relationship("Turn", back_populates="source_memory")

class Embedding(Base):
    __tablename__ = "embeddings"
    __table_args__ = (
        UniqueConstraint("doc_type", "doc_id", "model", name="uq_embedding_doc"),
    )

    id = Column(Integer, primary_key=True)
    doc_type = Column(String(32), nullable=False)
    doc_id = Column(Integer, nullable=False)
    model = Column(String(120), nullable=False)
    dim = Column(Integer, nullable=False)
    vector = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Location(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False, unique=True)
    kind = Column(String(64), nullable=False)  # home/cafe/office/gym/park
    capacity = Column(Integer, default=10)
    open_hours_json = Column(Text)  # JSON with open hours config
    created_at = Column(DateTime, default=datetime.utcnow)

    agent_locations = relationship("AgentLocation", back_populates="location", cascade="all, delete-orphan")
    world_events = relationship("WorldEvent", back_populates="location")


class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False, unique=True)
    category = Column(String(64), nullable=False)  # work/social/wellness
    default_duration_min = Column(Integer, default=60)
    prompt_template = Column(Text)  # Template for generating activity prompts
    created_at = Column(DateTime, default=datetime.utcnow)

    agent_schedules = relationship("AgentSchedule", back_populates="activity")
    world_events = relationship("WorldEvent", back_populates="activity")


class AgentLocation(Base):
    __tablename__ = "agent_locations"

    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id", ondelete="CASCADE"), nullable=False)
    since_ts = Column(DateTime, nullable=False, default=datetime.utcnow)
    until_ts = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    agent = relationship("Agent")
    location = relationship("Location", back_populates="agent_locations")


class AgentSchedule(Base):
    __tablename__ = "agent_schedules"

    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    day_label = Column(String(64), nullable=False)  # e.g., "2025-11-18"
    slot_hour = Column(Integer, nullable=False)  # 0-23
    planned_activity_id = Column(Integer, ForeignKey("activities.id", ondelete="SET NULL"))
    partner_agent_id = Column(Integer, ForeignKey("agents.id", ondelete="SET NULL"))
    created_at = Column(DateTime, default=datetime.utcnow)

    agent = relationship("Agent", foreign_keys=[agent_id])
    activity = relationship("Activity", back_populates="agent_schedules")
    partner = relationship("Agent", foreign_keys=[partner_agent_id])


class WorldEvent(Base):
    __tablename__ = "world_events"

    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    tick_index = Column(Integer, nullable=False)
    activity_id = Column(Integer, ForeignKey("activities.id", ondelete="SET NULL"))
    location_id = Column(Integer, ForeignKey("locations.id", ondelete="SET NULL"))
    metadata_json = Column(Text)  # JSON with event details
    created_at = Column(DateTime, default=datetime.utcnow)

    agent = relationship("Agent")
    activity = relationship("Activity", back_populates="world_events")
    location = relationship("Location", back_populates="world_events")


class DailyReport(Base):
    __tablename__ = "daily_reports"

    id = Column(Integer, primary_key=True)
    day_label = Column(String(64), nullable=False, unique=True)
    summary_text = Column(Text)
    metrics_json = Column(Text)  # JSON with aggregated metrics
    created_at = Column(DateTime, default=datetime.utcnow)

