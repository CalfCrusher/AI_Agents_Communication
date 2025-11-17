# Agent Implementation Plan: Persistent Personas, Relationships, and Memory

This plan instructs an AI coding agent to implement persistent personas, relationships, and conversational memory for the existing multi-model conversation sandbox.

## Objectives
- Persist agent personas (name, bio, job, family), interests, and inter-agent relationships.
- Store all conversations/turns; extract structured facts as memories with confidence and provenance.
- Retrieve the most relevant memories pre-turn (recency + similarity) and inject a concise context card.
- Keep the current CLI experience; add minimal, explicit flags to enable/shape persistence.

## Non-Goals (for now)
- UI beyond CLI.
- Long-term RAG beyond local DB (we’ll keep door open to Postgres later).
- Complex conflict-resolution; we’ll use simple dedupe + confidence updates.

## Tech Choices
- DB: SQLite (default) with SQLAlchemy ORM. Leave easy path to Postgres.
- Optional migrations: Alembic (only if needed; otherwise a small bootstrap script).
- Embeddings: start with text-only retrieval by recency; add optional vector similarity (e.g., `all-MiniLM` via `sentence-transformers`) later.

## Schema (Minimal v1)
- `agents`: id, name, bio, job, family_json, traits_json, created_at, updated_at
- `interests`: id, agent_id → agents.id, tag, score (0–1), created_at
- `relationships`: id, from_agent_id, to_agent_id, type (friend/spouse/coworker), strength (0–1), since_date, updated_at
- `conversations`: id, scenario, initial_prompt, started_at
- `turns`: id, conversation_id → conversations.id, round, interaction, turn, agent_id (nullable), model, role, content, created_at
- `memories`: id, agent_id → agents.id, kind (preference/event/fact/relationship), text, confidence (0–1), source_turn_id → turns.id, created_at
- `embeddings` (optional v2): id, doc_type (memory/turn), doc_id, model, dim, vector (BLOB)

Note: family/traits JSON keeps v1 schema simple while allowing nested detail.

## CLI Additions
- `--persist`: enable DB writes (turns, memories, relationships).
- `--agent-a <id>` and `--agent-b <id>`: map model order to persistent agents.
- `--topk-memories <int>` and `--topk-recent <int>`: retrieval tuning (default 5/3).
- `--embed-model <name>`: optional embeddings model name (if enabled later).
- `--db-url <url>`: default `sqlite:///./data/agents.db`.

## Integration Points in `python/conversation.py`
1. Startup
   - Parse new CLI flags.
   - Initialize DB session (lazy-create tables if not present).
   - Load Agent A/B personas; construct compact persona cards.

2. Pre-turn context assembly
   - If `--persist` is set: retrieve top-k memories (by recency and, if available, similarity).
   - Build a succinct Context Card for the current speaker:
     - Persona snippet (name, job, 1–2 interests, 1–2 key relationships) within ~50–80 tokens.
     - Relevant memories: <= N items, bullet summaries.
   - Prepend as system content for that model’s turn (after base system prompt and pinned initial prompt).

3. Post-turn extraction
   - Run a lightweight extractor (LLM or rule-based) to produce normalized JSON facts:
     - preferences/interests, events (“went to…”), relationships mentions (“my wife…”, “my son…”), jobs, likes/dislikes.
   - Dedupe by simple hash of normalized text; upsert with confidence adjustments.
   - Persist to `memories`; optionally update `relationships` strength (+small increments on consistent mentions).

4. Logging
   - Print: #memories retrieved, #facts extracted, #upserts performed.
   - Guardrail: cap injected context tokens (e.g., ~300 tokens) with a priority order: persona > relationships > top memories.

## Phased Milestones
- M1: DB bootstrap + models + seed script; wire `--agent-a/b` persona pinning.
- M2: Save conversations/turns when `--persist` is on; implement basic post-turn extraction to `memories` (preferences/events).
- M3: Retrieval pre-turn (recency first); compose context card and inject.
- M4: Add relationships detection + strength updates; optional embeddings retrieval.
- M5: Docs, examples, and minimal metrics (counts, drift, repetition).

## Tasks (Checklists)

### M1 — DB + Personas
- [ ] Add `python/db/models.py`: SQLAlchemy models for schema above.
- [ ] Add `python/db/session.py`: `get_session(db_url)` helper + `init_db()`.
- [ ] Script `tools/db.py` (click or argparse): `init`, `seed-agent`, `list-agents`.
- [ ] New flags in `conversation.py`: `--persist`, `--agent-a`, `--agent-b`, `--db-url`.
- [ ] Persona pinning: load A/B by id and inject compact persona snippet per model turn.

### M2 — Persist Conversations + Memories
- [ ] Create a `conversations` row on start; `turns` rows per turn (with model, role, content).
- [ ] Add basic extractor function:
  - Input: turn text; Output: JSON { kind, text, confidence } list.
  - Simple patterns: “I like …”, “my wife…”, “my job…”, “I work as…”, “my son…”, “I went to…”.
- [ ] Upsert memories by (agent_id, normalized_text_hash) with confidence clamp [0.2, 0.95].

### M3 — Retrieval + Context Card
- [ ] Retrieval query: top N by recency; (optional) if `embeddings` present, mix top similarity.
- [ ] Context Card composer: persona (1–2 lines), relationship bullets (<=2), memories (<=5 short bullets).
- [ ] Inject as a short system message just before the user payload for that model.

### M4 — Relationships + Embeddings
- [ ] Extend extractor to detect relationship mentions and update `relationships` (type, strength +0.05 capped at 1.0).
- [ ] Optional: add embeddings table and offline build for memories; similarity search by cosine.

### M5 — Docs + Metrics
- [ ] README updates with setup, flags, and example runs.
- [ ] Counters: printed summary each round: retrieved X, added Y, updated Z.

## Extractor Prompts (LLM)
- Summarizer → Facts JSON:
  - System: “Extract verifiable, concise facts/preferences/relationships from the user message. Output JSON list with fields: kind, text, confidence (0-1). Do not include meta-instructions.”
  - User: `<TURN_TEXT>`
- Keep under 100 tokens; if empty, return `[]`.

## Acceptance Criteria
- Running with `--persist` creates a DB and writes a conversation with turns.
- Given two agents with seeded personas, pre-turn messages include a context card drawn from their persona and memories.
- After a run, new memories appear in DB; duplicates are deduped; relationships increment strength upon repeated mentions.
- Retrieval is bounded (token cap) and deterministic given the same DB state.

## Runbook (Examples)
```bash
# Init DB
python -m tools.db init --db-url sqlite:///./data/agents.db

# Seed two agents
python -m tools.db seed-agent --name "Ava" --job "Designer" --interests "hiking,coffee" --bio "Warm, curious, minimalist." \
  --family '{"spouse":"Ben","children":["Lia"]}'
python -m tools.db seed-agent --name "Ben" --job "Developer" --interests "cycling,salsa" --bio "Calm, methodical, loves gadgets."

# Run with persistence
python python/conversation.py --config config.json --models gemma3:1b qwen3:1.7b \
  --persist --db-url sqlite:///./data/agents.db --agent-a 1 --agent-b 2 \
  --topk-memories 5 --topk-recent 3 --memory 4 \
  --initial "Two friends catching up about their day." \
  --turn-template "{partner_message}\n\nAnswer and ask a short follow-up. Max 40 words." \
  --max-words 40 --stream --delay 3 --plain
```

## Risks and Mitigations
- Token bloat from long memory cards → enforce hard cap and priority order.
- Noisy extractions → require minimum confidence, stabilize via dedupe and throttled updates.
- Identity confusion between agents → always pin persona per model turn.

---

If any ambiguity arises, implement the smallest working slice (M1 → M2), verify with one run, then iterate.
