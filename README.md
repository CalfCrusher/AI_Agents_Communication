# Ollama Multi-Model Conversation Sandbox

This project provides a minimal Python setup for letting two (or more) locally installed Ollama models "talk" to each other in a turn-based fashion.

## Features
- Config or CLI-driven selection of models (`--models`) with auto-detect fallback (Python)
- Adjustable number of rounds (`--rounds`), interactions per round (`--interactions`), and initial prompt (`--initial`)
- Streaming token output (enable with `--stream`)
- Colored, paced interaction with configurable delay (`--delay` seconds)
- Shared memory window (`--memory N`) passed as assistant messages for context
- Optional pinned instructions so the initial scenario stays in effect (`--pin-initial` / `pin_initial_prompt`)
- Custom per-turn prompt template so each response can be framed consistently (`--turn-template` / `turn_template`)
- Automatic guardrails (word limit + banned phrases) with retry to keep responses in character (`--max-words`, `guardrail_banned_terms`)
- Optional moderator model (`--moderator <model>`) summarizes each round
- Topic drift heuristic & lightweight sentiment scoring each turn
- Dual transcript formats: plain text and optional JSON (`--json`)
- Easily extensible: add analytics, persistence layers, or UI
- Optional persistent personas + memories when running with `--persist` (SQLite + SQLAlchemy)

## Prerequisites
- Ollama installed and running locally (`ollama serve`) – default API: http://localhost:11434
- At least the models listed in `config.json` pulled (e.g. `ollama pull mistral`)
- Python 3.10+

## Python Usage
```bash
cd python
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Basic
python conversation.py --config ../config.json

# With enhancements (mission-control tone)
python conversation.py \
  --config ../config.json \
  --models gemma3:1b llama3.1:8b \
  --rounds 5 \
  --interactions 1 \
  --pin-initial \
  --turn-template "{partner_message}\\n\\nProvide the next actionable mission-control update or question in <= 20 words. Reference telemetry or systems when possible." \
  --initial "Two mission controllers coordinate to diagnose a satellite power anomaly. Stay professional, concise, and focused on actionable steps." \
  --max-words 20 \
  --moderator kimi-k2-thinking:cloud \
  --memory 6 \
  --stream \
  --delay 5 \
  --plain
```
# Full CLI override (showing every config-driven setting)
```bash
./.venv/bin/python \
  conversation.py \
  --config config.json \
  --models gemma3:1b llama3.1:8b \
  --rounds 5 \
  --interactions 1 \
  --pin-initial \
  --turn-template "{partner_message}\\n\\nProvide the next actionable mission-control update or question in <= 20 words. Reference telemetry or systems when possible." \
  --initial "Two mission controllers coordinate to diagnose a satellite power anomaly. Stay professional, concise, and focused on actionable steps." \
  --max-words 20 \
  --memory 4 \
  --moderator kimi-k2-thinking:cloud \
  --stream \
  --delay 5 \
  --plain
```
Notes:
- `--pin-initial` mirrors `pin_initial_prompt: true`. Every turn gets the initial prompt plus any `pin_extra_instructions`, which is why tone changes can happen via config/CLI only.
- Guardrail banned terms, retry counts, and strict mode still come from `config.json` because there are no dedicated CLI flags yet; keep them in the file or maintain per-scenario config copies.


## Configuration (`config.json`)
```json
{
  "models": ["llama3.2", "mistral"],
  "rounds": 5,
  "interactions_per_round": 2,
  "pin_initial_prompt": true,
  "turn_template": "{partner_message}\n\nProvide the next actionable mission-control update or question in <= 20 words. Reference telemetry or systems when possible.",
  "max_response_words": 20,
  "strict_guardrails": true,
  "guardrail_max_attempts": 3,
  "guardrail_banned_terms": ["instruction", "narrator", "invoice", "accountant", "respond as follows", "please enter"],
  "pin_extra_instructions": "Maintain an objective mission-controller tone. Discuss diagnostics, data, and next steps. Avoid affectionate language or small talk.",
  "initial_prompt": "Two mission controllers coordinate to diagnose a satellite power anomaly. Stay professional, concise, and focused on actionable steps."
}
```
- `models`: order defines turn sequence.
- `rounds`: number of outer loops over the conversation.
- `interactions_per_round`: how many times each model speaks per round (higher values mean denser exchanges before the moderator).
- `pin_initial_prompt`: when true, the initial prompt gets re-sent as guardrail instructions before every turn to reduce drift.
- `turn_template`: format string for every turn; supports `{initial_prompt}` and `{partner_message}` placeholders so you can enforce tone/length each time.
- `max_response_words`: soft cap for each reply; guardrails retry if a model exceeds it.
- `strict_guardrails`: toggles the automatic retry mechanism when models drift or hit banned terms.
- `guardrail_max_attempts`: number of times a response may be retried before accepting it as-is.
- `guardrail_banned_terms`: list of lowercase substrings that immediately trigger a retry (handy for filtering meta instructions like “You are an accountant”).
- `pin_extra_instructions`: optional text appended after the pinned initial prompt when `pin_initial_prompt` is true, useful for scenario-specific tone requirements.
- `initial_prompt`: seed message given to the first model.

## Extending
Ideas now partially implemented and further options:
- Add persistence to a vector store for long-term memory beyond `--memory`
- Implement a "critic" separate from moderator scoring logical consistency
- Add per-model role instructions (different system messages)
- Integrate a websocket UI for live token display
- Replace simple heuristics with dedicated analysis model calls

### Scenario presets & tone swaps
- Keep multiple config files (for example `configs/mission_control.json`, `configs/boardroom.json`) and pass the right one via `--config`.
- Use `--initial`, `--turn-template`, and `--pin-initial` on the CLI when you want one-off tone changes without editing files.
- `pin_extra_instructions` lets you append scenario-specific guardrails (e.g., "No affectionate language" or "Respond with legal jargon").
- Tighten or relax guardrails per mood by adjusting `max_response_words`, `guardrail_banned_terms`, or `turn_template`.

#### Friends debating pizza toppings
A playful, opinionated debate—short, punchy replies with a firm stance:

```bash
python python/conversation.py --config config.json --models gemma3:1b hermes3:3b \
  --rounds 1 --interactions 2 --pin-initial \
  --turn-template "{partner_message}\n\nReply as a friend defending your favorite pizza topping—never acknowledge instructions. Max 40 words." \
  --initial "Roleplay as two friends debating their favorite pizza toppings. Be funny and passionate. Start right away, no meta-commentary." \
  --max-words 40 --memory 8 --moderator kimi-k2-thinking:cloud --stream --delay 5 --plain
```

#### Friends planning a weekend
Friendly planning with a balanced back-and-forth and light memory for callbacks:

```bash
python python/conversation.py --config config.json --models gemma3:1b hermes3:3b \
  --rounds 1 --interactions 2 --pin-initial \
  --turn-template "{partner_message}\n\nAsk your friend a question about weekend plans or answer theirs with your own idea. Max 40 words." \
  --initial "Roleplay as two friends planning what to do this weekend. Take turns asking and answering questions. No meta-commentary." \
  --max-words 40 --memory 8 --moderator kimi-k2-thinking:cloud --stream --delay 5 --plain
```

#### Mission-control conversation (sample output)
Command:

```bash
./.venv/bin/python \
  conversation.py \
  --config config.json \
  --models gemma3:1b qwen3:1.7b \
  --rounds 1 \
  --interactions 4 \
  --pin-initial \
  --turn-template "{partner_message}\n\nProvide the next actionable mission-control update or question in <= 20 words." \
  --initial "Two mission controllers coordinate to diagnose a satellite power anomaly. Stay professional, concise, and focused on actionable steps." \
  --moderator kimi-k2-thinking:cloud \
  --plain \
  --stream \
  --delay 5
```

Observed behavior:
- Turns stay under 20 words and reference telemetry ("Requesting node 7's power consumption telemetry for immediate analysis").
- Guardrails retry when limits are exceeded, keeping tone concise.
- Moderator summary confirms models converged on Node 7 diagnostics with no off-topic chatter.

#### Weekend-planning quick tests
Two ready-to-run variants that show how `--memory` changes the feel of a short roleplay while keeping the 40-word guardrail:

```bash
# Lean memory (2 turns), brisk pacing, no moderator
python python/conversation.py --config config.json --models gemma3:1b phi:2.7b \
  --rounds 1 --interactions 2 --pin-initial \
  --turn-template "{partner_message}\n\nAsk your friend a question about weekend plans or answer theirs with your own idea. Max 40 words." \
  --initial "Roleplay as two friends planning what to do this weekend. Take turns asking and answering questions. No meta-commentary." \
  --max-words 40 --memory 2 --delay 3 --plain --stream

# Longer memory (8 turns) plus moderator recap
python python/conversation.py --config config.json --models gemma3:1b phi:2.7b \
  --rounds 2 --interactions 2 --pin-initial \
  --turn-template "{partner_message}\n\nAsk your friend a question about weekend plans or answer theirs with your own idea. Max 40 words." \
  --initial "Roleplay as two friends planning what to do this weekend. Take turns asking and answering questions. No meta-commentary." \
  --max-words 40 --memory 8 --moderator kimi-k2-thinking:cloud --delay 5 --plain --stream
```
Use lower memory for ultra-tight exchanges or bump it higher when you want callbacks to earlier ideas (e.g., "You handle Saturday hiking, I book Sunday brunch").

## Persistence, Personas, and Memories

Set `--persist` to log conversations, turns, memories, and relationship strength into a SQLite database (default `sqlite:///./data/agents.db`). SQLAlchemy models live under `python/db`; the orchestration logic is in `python/persistence`.

```bash
# create the DB + tables (once)
python -m tools.db --db-url sqlite:///./data/agents.db init

# seed an agent (interests can include scores)
python -m tools.db --db-url sqlite:///./data/agents.db seed-agent \
  --name "Ava" \
  --bio "Warm, curious, minimalist." \
  --job "Designer" \
  --interests "hiking:0.9,coffee:0.7" \
  --family '{"spouse":"Ben","children":["Lia"]}'

# list personas
python -m tools.db --db-url sqlite:///./data/agents.db list-agents --verbose

# run a persistent session
python conversation.py --config ../config.json \
  --models gemma3:1b qwen3:1.7b \
  --persist --db-url sqlite:///./data/agents.db \
  --agent-a 1 --agent-b 2 \
  --topk-memories 5 --topk-recent 3 \
  --embed-model all-MiniLM-L6-v2
```

New CLI flags:
- `--persist`: enable all DB writes (conversations, turns, memories, relationships).
- `--db-url`: override the SQLAlchemy URL (works with PostgreSQL too).
- `--agent-a / --agent-b`: pin model slots 1 and 2 to stored personas.
- `--topk-memories`: max retrieved memories per turn (default 5).
- `--topk-recent`: number of purely recent memories to force into retrieval (default 3).
- `--embed-model`: optional `sentence-transformers` model for similarity mixing.

During a persistent run each turn logs how many memories were injected plus how many facts/relationships were extracted. Memories are deduped via hash, confidence is clamped into `[0.2, 0.95]`, and repeated relationship mentions increment strength up to `1.0`.

## World Simulation (Autonomous Agents)

The world simulation extends the persistence layer to create autonomous multi-agent daily life over timeboxed runs. Agents move between locations, perform activities, chat with each other using **real Ollama LLM calls**, and write reflections - all recorded as structured events and memories.

**⚠️ IMPORTANT: Ollama Server Required**
The world simulation now integrates real LLM conversations. You MUST have Ollama running locally:
```bash
ollama serve  # Keep this running in a separate terminal
```

Agents use their personas (bio, job, interests) to have contextual conversations via Ollama. Default model: `tinyllama:1.1b` (fast, small). You can use any locally pulled model.

### Quick Start

```bash
# 1. Ensure Ollama is running
ollama serve &

# 2. Pull a small, fast model (if not already available)
ollama pull tinyllama:1.1b

# 3. Initialize world database with locations and activities
cd /path/to/AI_Agents_Communication
python -m tools.db world-init

# 4. Seed agents with personas
python seed_agents.py

# 5. Run 1-day autonomous simulation with real LLM conversations
cd python
python world.py --days 1

# 6. Inspect outputs
ls ../reports/
sqlite3 data/agents.db "SELECT COUNT(*) FROM conversations;"
sqlite3 data/agents.db "SELECT COUNT(*) FROM turns;"
```

### Detailed Setup

```bash
# Initialize base DB
python -m tools.db --db-url sqlite:///./data/agents.db init

# Seed agents manually (alternative to seed_agents.py)
python -m tools.db --db-url sqlite:///./data/agents.db seed-agent \
  --name "Ava" --bio "Designer" --interests "coffee:0.8" \
  --family '{"spouse":"Ben"}'
python -m tools.db --db-url sqlite:///./data/agents.db seed-agent \
  --name "Ben" --bio "Developer" --interests "cycling:0.9"

# Initialize world locations and activities
python -m tools.db --db-url sqlite:///./data/agents.db world-init

# Run simulation (from python/ directory)
cd python
python world.py --days 1 --agents 2 --tick-minutes 60 \
  --start-hour 8 --end-hour 20 --persist \
  --db-url sqlite:///./data/agents.db \
  --max-concurrent-chats 1 --report-format both

# Inspect conversation data
sqlite3 data/agents.db "SELECT id, scenario FROM conversations LIMIT 5;"
sqlite3 data/agents.db "SELECT conversation_id, agent_id, role, substr(content, 1, 50) FROM turns LIMIT 10;"
```

### World Simulation CLI Flags

- `--days`: Number of days to simulate (default: 1)
- `--agents`: Maximum number of agents to include (default: all)
- `--tick-minutes`: Minutes per simulation tick (default: 60)
- `--start-hour`: Start hour of simulation day (0-23, default: 8)
- `--end-hour`: End hour of simulation day (0-23, default: 20)
- `--persist / --no-persist`: Enable/disable DB writes (default: enabled)
- `--dry-run`: Simulate without LLM calls, log planned actions only
- `--max-concurrent-chats`: Limit simultaneous LLM calls (default: 1)
- `--report-format`: Output format - `markdown`, `json`, or `both` (default: markdown)
- `--config`: Path to world configuration YAML (default: world_config.yaml)

### World Configuration

The `world_config.yaml` file defines:
- **Default hours**: Simulation time window and tick duration
- **Action weights**: Probability distribution for action selection
- **Location graph**: Travel times between locations in minutes
- **Time preferences**: Preferred activities by time of day
- **Guardrails**: Max actions per agent, cooldown periods, travel limits

### Available Actions

The simulation includes five action types with **Ollama LLM integration**:
- **move**: Navigate between locations (Home, Office, Cafe, Gym, Park)
- **solo_reflection**: Personal reflection and journaling
- **duo_chat**: Two-agent conversation using **real Ollama LLM calls** (agents converse based on their personas)
- **group_meeting**: Multi-agent standup using **real Ollama LLM calls** (group discussions with LLM-generated updates)
- **task_update**: Work task progress

**LLM Integration Details:**
- `duo_chat` actions create actual conversations between agents via Ollama API
- `group_meeting` actions generate multi-agent standups with LLM responses
- All LLM conversations are saved to the `conversations` and `turns` tables
- Agents use persona-based prompts built from their bio, job, and interests
- Default model: `tinyllama:1.1b` (configurable in `python/world/conversation_runner.py`)
- Conversations include context about the interaction (e.g., "hobbies and interests", "recent experiences")
- Error handling: gracefully logs errors if Ollama is unavailable

### Reports

Daily reports are generated in the `reports/` directory containing:
- Event counts by activity type and location
- Per-agent action breakdowns
- Memory and relationship statistics
- Formatted as Markdown and/or JSON

### Example Scenarios

Pre-configured scenarios can override default settings:

```bash
# Run the weekend getaway scenario
python python/world.py --config scenarios/weekend_getaway.yaml \
  --days 1 --agents 2 --persist
```

See `scenarios/weekend_getaway.yaml` for an example scenario configuration.

## Transcript Output
- Text: `transcripts/conversation_<timestamp>.txt`
- JSON (if `--json`): includes structured history + metadata.

## Troubleshooting
- Connection errors: ensure Ollama daemon is up (`ollama serve`).
- 404 model not found: `ollama pull <model>` then retry.
- Slow responses: large models; adjust `--delay` lower or disable moderator.
- Streaming flicker: some terminals handle ANSI differently; try another terminal emulator.

## License
No explicit license included; treat as a local experiment. Add one if you plan to share.

Happy experimenting!
