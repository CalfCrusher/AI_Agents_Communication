"""Session helpers for the persistence layer."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

_ENGINE_CACHE: Dict[str, Engine] = {}
_SESSION_FACTORY: Dict[str, sessionmaker] = {}


def _ensure_sqlite_path(db_url: str) -> None:
    if not db_url.startswith("sqlite:///"):
        return
    raw_path = db_url.split("sqlite:///")[1]
    db_path = Path(raw_path)
    if db_path.parent and not db_path.parent.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)


def get_engine(db_url: str) -> Engine:
    _ensure_sqlite_path(db_url)
    if db_url in _ENGINE_CACHE:
        return _ENGINE_CACHE[db_url]
    connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    engine = create_engine(db_url, future=True, echo=False, connect_args=connect_args)
    _ENGINE_CACHE[db_url] = engine
    return engine


def get_session(db_url: Optional[str] = None, engine: Optional[Engine] = None) -> Session:
    if engine is None:
        if not db_url:
            raise ValueError("db_url required when engine not provided")
        engine = get_engine(db_url)
    key = str(id(engine))
    if key not in _SESSION_FACTORY:
        _SESSION_FACTORY[key] = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    return _SESSION_FACTORY[key]()


def init_db(db_url: str) -> Engine:
    engine = get_engine(db_url)
    Base.metadata.create_all(engine)
    return engine
