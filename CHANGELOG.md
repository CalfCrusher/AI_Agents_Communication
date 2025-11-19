# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added - 2025-11-19

#### Visualization
- **Isometric Viewer**: Added a web-based isometric viewer for the agent world (`visualizer/index.html`) using Phaser.js
- **Visualization Server**: Added `python/server.py` (FastAPI) to serve real-time agent state from the database

### Added - 2025-11-18

#### Ollama LLM Integration for Autonomous Agents
- **WorldConversationRunner** (`python/world/conversation_runner.py`): New class to bridge world simulation and Ollama API
  - `run_duo_chat()`: Executes 2-agent conversations with configurable turns and word limits
  - `run_group_chat()`: Executes multi-agent group conversations
  - `_build_agent_prompt()`: Constructs persona-based system prompts from agent bio, job, and interests
  - `_call_ollama()`: Wrapper for ollama.chat() API calls with error handling
- **seed_agents.py**: Utility script to populate database with test agents (Alice, Bob, Carol)
- **Real LLM Conversations**: DuoChatAction and GroupStandupAction now use actual Ollama LLM calls instead of logging fake metadata
- **Conversation Persistence**: All LLM conversations and turns are saved to database tables
- **Default Model**: Changed to `tinyllama:1.1b` (fast, small, widely available)

#### World Simulation Testing
- Comprehensive testing documentation in `TESTING_SUMMARY.md`
- 1-day simulation test: 4 conversations, 16 LLM-generated turns successfully saved
- Database verification: conversations and turns tables properly populated
- Performance validated: ~10 seconds per 2-turn conversation

### Changed - 2025-11-18
- **DuoChatAction.execute()**: Updated to call `conv_runner.run_duo_chat()` with real Ollama API
- **GroupStandupAction.execute()**: Updated to call `conv_runner.run_group_chat()` with real Ollama API
- **BaseAction.__init__()**: Added `self.conv_runner = WorldConversationRunner(session)`
- **actions.py imports**: Added `from world.conversation_runner import WorldConversationRunner`
- **Console output**: Added emoji progress indicators (🗣️ chatting..., ✅ N messages exchanged, 👥 group standup)
- **TESTING_SUMMARY.md**: Updated with Ollama LLM integration test results and performance metrics

### Fixed - 2025-11-18
- **Bug #1**: Fixed `PROJECT_ROOT` calculation in `world.py` (changed `parents[2]` to `parents[1]`)
- **Bug #2**: Added missing `day_label` to action metadata for proper report filtering
- **Bug #3 (CRITICAL)**: Agents were not actually using Ollama - only logging fake actions. Now integrated with real LLM API calls.

## [0.2.0] - 2025-11-18

### Added
- World scheduler (`python/world.py`) for autonomous agent simulation
- 5 action types: MoveAction, SoloReflectionAction, DuoChatAction, GroupStandupAction, TaskUpdateAction
- Environment service (`python/world/environment.py`) for location management
- Reporting service (`python/world/reporting.py`) for daily simulation reports
- `world-init` command in `tools/db.py` to seed locations and activities
- `world_config.yaml` configuration file for simulation parameters
- Unit tests (`tests/test_world_scheduler.py`) for world simulation components
- Extended database models: Location, Activity, WorldEvent, Memory tables
- Daily report generation (Markdown and JSON formats)

### Changed
- Database models extended with world simulation entities
- SQLAlchemy session management updated for world simulation

## [0.1.0] - Initial Release

### Added
- Ollama multi-model conversation system
- Turn-based conversation with configurable rounds and interactions
- Streaming token output support
- Colored, paced interaction with configurable delay
- Shared memory window for context
- Pinned instructions support
- Custom per-turn prompt templates
- Automatic guardrails (word limit + banned phrases)
- Optional moderator model for round summaries
- Topic drift heuristic and sentiment scoring
- Dual transcript formats (plain text and JSON)
- SQLite persistence with SQLAlchemy models
- Agent, Interest, Relationship, Conversation, Turn, Memory models
- CLI tools for database initialization and agent seeding
- Embedding-based memory retrieval with sentence-transformers
- Configuration-driven setup via `config.json`

### Core Features
- `conversation.py`: Main conversation orchestrator
- `db/models.py`: SQLAlchemy models for persistence
- `db/session.py`: Database session management
- `persistence/manager.py`: Memory and relationship management
- `tools/db.py`: CLI utilities for database operations
- Comprehensive README with usage examples
- Multiple scenario presets (mission control, friends debating, weekend planning)
