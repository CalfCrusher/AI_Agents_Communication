# Autonomous World Extension Plan

Follow-up instructions for extending the conversation sandbox into a lightweight autonomous world simulation. This builds on `docs/agent_plan.md` and assumes the persistence layer (agents, relationships, conversations, memories) already exists.

## Objectives
- Simulate multi-agent daily life over timeboxed "day" or "week" runs.
- Drive autonomous actions (move locations, perform activities, start chats, write reflections) using existing personas, interests, and relationships.
- Capture every action as structured data (events, schedules, outcomes) and reuse the memory extractor for long-term state.
- Produce daily world-state reports summarizing interactions, new memories, and relationship deltas.

## Non-Goals (v1)
- Real-time or continuous background daemons (runs stay bounded to explicit CLI sessions).
- Complex physics/economy/3D simulation; we model a simple schedule + activity graph.
- Agent-level reinforcement learning or planning beyond prompt-driven heuristics.

## Architecture Overview
1. **World Scheduler (`python/world.py`)**
   - CLI entrypoint orchestrating day ticks (default 60-minute ticks, 12-hour window).
   - Loads agents, locations, and activity catalog; assigns each agent a daily agenda seed.
   - At each tick, selects eligible agents and dispatches actions to the Services layer.
2. **Environment Service (`python/world/environment.py`)**
   - Manages locations (home, office, café, gym, park) and occupancy rules.
   - Implements simple travel cost/timeouts so agents cannot teleport across ticks.
3. **Action Service (`python/world/actions.py`)**
   - Encodes action templates: `move`, `solo_reflection`, `duo_chat`, `group_meeting`, `task_update`.
   - Uses `conversation.ConversationRunner` helper to reuse the existing two-model chat flow for duo/group interactions.
4. **Reporting Service (`python/world/reporting.py`)**
   - Aggregates metrics per tick/day: location visits, activities, memories extracted, relationship deltas.
   - Writes Markdown + JSON summaries into `reports/world_<timestamp>.md`.
5. **Persistence Hooks**
   - Reuse the `PersistenceManager` for auto memory extraction + relationship adjustments.
   - Add `world_events` and `agent_schedules` tables to capture non-conversation actions.

## Schema Additions (via SQLAlchemy models)
- `locations`: id, name, kind (home/cafe/office), capacity, open_hours_json.
- `activities`: id, name, category (work/social/wellness), default_duration_min, prompt_template.
- `agent_locations`: id, agent_id, location_id, since_ts, until_ts.
- `agent_schedules`: id, agent_id, day_label, slot_hour, planned_activity_id, partner_agent_id (nullable).
- `world_events`: id, agent_id, tick_index, activity_id, location_id, metadata_json, created_at.
- `daily_reports`: id, day_label, summary_text, metrics_json, created_at.

> Migration strategy: extend `python/db/models.py` and update `tools/db.py world-init` command to seed canonical locations + activities.

## CLI & Config Additions
- New command: `python -m tools.db world-init --db-url ...` to seed `locations` + `activities`.
- New runner: `python python/world.py --days 1 --agents 4 --tick-minutes 60 --start-hour 8 --end-hour 20 --persist --db-url ...`.
- Optional flags:
  - `--scripted-events path.json` to load scenario-specific schedule overrides.
  - `--max-concurrent-chats N` to bound simultaneous LLM calls.
  - `--report-format markdown|json|both`.
  - `--dry-run` to simulate without hitting models (log planned actions only).

## Milestones
### M1 — World Bootstrap
- Extend models with new tables and seed helpers in `tools/db.py`.
- Implement `world_config.yaml` describing default hours, action weights, and location graph.
- Add fixtures for at least 5 locations + 6 activities.

### M2 — Scheduler Core
- Create `world.py` with:
  - CLI parsing (days, tick minutes, slots per day, agent subset selection).
  - Loop that advances ticks, selects agents based on availability + schedules.
  - Hooks for logging events and persisting to `world_events`.

### M3 — Action Implementations
- Implement `MoveAction`, `SoloReflectionAction`, `DuoChatAction`, `GroupStandupAction` classes.
- Each action updates state, optionally calls the existing conversation orchestration, and writes events/memories.
- Add guardrails (max actions per agent/day, cool-down between duo chats).

### M4 — Reporting & Metrics
- Summaries per day: number of activities per category, top relationships strengthened, new memories by kind.
- Optional `--report-channel slack://...` stub for future integrations (log-only).
- CLI flag `--summary-only` to skip transcripts but keep metrics.

### M5 — Testing + Examples
- Provide sample scenario `scenarios/weekend_getaway.yaml`.
- Add scripted test `tests/test_world_scheduler.py` covering:
  - Tick progression and schedule generation.
  - Event logging when `--dry-run` is set (no LLM calls).
- Document reproducible runbook in README.

## Runbook (Example)
```bash
# 1. Initialize base DB + world assets
python -m tools.db --db-url sqlite:///./data/agents.db init
python -m tools.db --db-url sqlite:///./data/agents.db seed-agent --name "Ava" --bio "Designer" --interests "coffee:0.8" --family '{"spouse":"Ben"}'
python -m tools.db --db-url sqlite:///./data/agents.db seed-agent --name "Ben" --bio "Developer" --interests "cycling:0.9"
python -m tools.db --db-url sqlite:///./data/agents.db world-init

# 2. Simulate a single 12-hour day for three agents
python python/world.py --days 1 --agents 3 --tick-minutes 60 \
  --start-hour 8 --end-hour 20 --persist --db-url sqlite:///./data/agents.db \
  --max-concurrent-chats 1 --report-format both

# 3. Inspect outputs
ls reports/
sqlite3 data/agents.db 'SELECT count(*) FROM world_events;'
```

## Testing Strategy
- Unit tests for scheduler math (tick increments, availability windows).
- Integration smoke test with `--dry-run` to ensure deterministic event logs.
- Manual end-to-end run (as above) verifying memories + world events grow and report files are created.

## Risks & Mitigations
- **LLM cost/execution time:** enforce tick-level concurrency caps, default to short day spans.
- **Token bloat:** continue to cap context cards and compress transcripts when `--summary-only` is set.
- **State drift:** periodic persistence checkpoints; abort run if DB errors occur.

This plan should give the next coding agent everything needed to evolve the project from pairwise conversations into a manageable autonomous simulation without exploding scope.
