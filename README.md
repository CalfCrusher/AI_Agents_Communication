# Ollama Multi-Model Conversation Sandbox

This project provides a minimal Python setup for letting two (or more) locally installed Ollama models "talk" to each other in a turn-based fashion.

## Features
- Config or CLI-driven selection of models (`--models`) with auto-detect fallback (Python)
- Adjustable number of rounds (`--rounds`) and initial prompt (`--initial`)
- Streaming token output (enable with `--stream`)
- Colored, paced interaction with configurable delay (`--delay` seconds)
- Shared memory window (`--memory N`) passed as assistant messages for context
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
  "initial_prompt": "Discuss potential collaboration strategies for building a multi-agent system. Keep responses concise."
}
```
- `models`: order defines turn sequence.
- `rounds`: total exchange rounds (each round = each model speaks once).
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
