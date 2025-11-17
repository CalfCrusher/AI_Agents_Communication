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

# With enhancements
python conversation.py \
  --config ../config.json \
  --models gemma3:1b tinyllama:1.1b \
  --rounds 4 \
  --interactions 2 \
  --pin-initial \
  --turn-template "Stay in character: {initial_prompt}\nPartner said: {partner_message}\nReply in <=20 words." \
  --initial "Brainstorm coordination tactics for multi-agent swarm." \
  --moderator gemma3:1b \
  --memory 6 \
  --stream \
  --delay 3 \
  --json
```

## Configuration (`config.json`)
```json
{
  "models": ["llama3.2", "mistral"],
  "rounds": 5,
  "interactions_per_round": 2,
  "pin_initial_prompt": true,
  "turn_template": "{partner_message}\n\nStay in the previously described scenario and reply in <=20 words without mentioning instructions.",
  "max_response_words": 20,
  "strict_guardrails": true,
  "guardrail_max_attempts": 3,
  "guardrail_banned_terms": ["instruction", "narrator", "invoice", "accountant", "respond as follows", "please enter"],
  "initial_prompt": "Discuss potential collaboration strategies for building a multi-agent system. Keep responses concise."
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
- `initial_prompt`: seed message given to the first model.

## Extending
Ideas now partially implemented and further options:
- Add persistence to a vector store for long-term memory beyond `--memory`
- Implement a "critic" separate from moderator scoring logical consistency
- Add per-model role instructions (different system messages)
- Integrate a websocket UI for live token display
- Replace simple heuristics with dedicated analysis model calls

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
