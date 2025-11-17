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
  --models gemma3:1b qwen3:1.7b \
  --rounds 1 \
  --interactions 4 \
  --pin-initial \
  --turn-template "{partner_message}\n\nProvide the next actionable mission-control update or question in <= 20 words." \
  --initial "Two mission controllers coordinate to diagnose a satellite power anomaly. Stay professional, concise, and focused on actionable steps." \
  --moderator kimi-k2-thinking:cloud \
  --memory 6 \
  --stream \
  --delay 5 \
  --plain
```

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

#### Mission-control conversation (sample output)
Command:

```bash
/Users/christopher/Documents/VSCode_Projects/AI_Agents_Communication/.venv/bin/python \
  python/conversation.py \
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
