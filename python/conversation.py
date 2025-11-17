import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict
import yaml
import ollama
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.markdown import Markdown


"""
Enhanced multi-model conversation orchestrator with features:
 - CLI overrides for models, rounds, initial prompt
 - Optional auto model detection if models omitted
 - Streaming token-by-token output (Python only) (--stream)
 - Colored output per model + moderator summaries
 - Delay between turns to simulate pacing (--delay seconds)
 - Shared memory of last N utterances passed as chat history (--memory N)
 - Moderator model that summarizes each round (--moderator MODEL)
 - JSON transcript in addition to text (--json)
 - Topic drift heuristic vs initial prompt
 - Basic sentiment heuristic (counts positive/negative words)
"""


console = Console()

TRANSCRIPT_DIR = Path(__file__).resolve().parent.parent / "transcripts"
TRANSCRIPT_DIR.mkdir(exist_ok=True)

POSITIVE_WORDS = {"great", "good", "beneficial", "positive", "robust", "efficient"}
NEGATIVE_WORDS = {"bad", "poor", "problem", "negative", "conflict", "risk"}

MODEL_COLORS = [
    "cyan",
    "magenta",
    "yellow",
    "green",
    "blue",
    "red",
]



def load_config(path: str):
    with open(path, "r", encoding="utf-8") as f:
        if path.endswith((".yaml", ".yml")):
            return yaml.safe_load(f)
        return json.load(f)


def auto_models_if_needed(models: List[str]) -> List[str]:
    if models:
        return models
    try:
        listed = ollama.list().get("models", [])
        # Take first two by default
        return [m["name"] for m in listed[:2]]
    except Exception:
        return []


def sentiment_score(text: str) -> Dict[str, int]:
    tokens = {t.strip('.,:;!?').lower() for t in text.split()}
    pos = len(tokens & POSITIVE_WORDS)
    neg = len(tokens & NEGATIVE_WORDS)
    return {"positive": pos, "negative": neg}


def topic_similarity(base: str, current: str) -> float:
    b = {t.lower() for t in base.split() if len(t) > 3}
    c = {t.lower() for t in current.split() if len(t) > 3}
    if not b or not c:
        return 1.0
    inter = len(b & c)
    union = len(b | c)
    return inter / union if union else 1.0


def stream_chat(model: str, messages: List[Dict[str, str]], live: Live) -> str:
    final = []
    try:
        for part in ollama.chat(model=model, messages=messages, stream=True):
            chunk = part.get("message", {}).get("content", "")
            if chunk:
                final.append(chunk)
                live.update(Markdown("".join(final), style="bright_white"), refresh=True)
        return "".join(final).strip()
    except KeyboardInterrupt:
        console.print("[bold red]\n[Stream interrupted][/bold red]")
        return "".join(final).strip()
    except Exception as e:
        return f"<error streaming {model}: {e}>"


def call_model(model: str, messages: List[Dict[str, str]], stream: bool, live: Live = None) -> str:
    if stream and live:
        return stream_chat(model, messages, live)
    try:
        # Spinner is a renderable, so drive it via console.status to avoid context errors
        with console.status("Model is thinking...", spinner="dots"):
            response = ollama.chat(model=model, messages=messages)
        return response["message"]["content"].strip()
    except Exception as e:
        return f"<error calling {model}: {e}>"



def moderator_summary(model: str, round_idx: int, round_entries: List[Dict], initial_prompt: str) -> str:
    prompt = (
        "You are a moderator. Provide a concise neutral summary of the LAST ROUND only, "
        "including any emerging agreements, disagreements, and topic drift relative to the initial prompt: \nInitial Prompt: "
        f"{initial_prompt}\nRound {round_idx} messages:\n" +
        "\n".join(f"Model {e['model']} said: {e['response']}" for e in round_entries)
    )
    msgs = [{"role": "user", "content": prompt}]
    return call_model(model, msgs, stream=False)


def sanitize(text: str, enable: bool) -> str:
    if not enable:
        return text
    lines = []
    for line in text.splitlines():
        line = line.replace("**", "")
        if line.strip().startswith("* "):
            line = line.replace("* ", "- ", 1)
        if line.strip().startswith("*") and not line.strip().startswith("*-"):
            # remove stray leading asterisks
            line = line.lstrip("*").lstrip()
        lines.append(line)
    return "\n".join(lines)


def make_box(title: str, content: str, color: str) -> str:
    width = 100
    wrapped_lines = []
    for raw_line in content.splitlines() or [""]:
        line = raw_line if raw_line else ""
        while len(line) > width - 4:
            wrapped_lines.append(line[: width - 4])
            line = line[width - 4 :]
        wrapped_lines.append(line)
    top = f"┌─ {title} "
    if len(top) < width:
        top = top + "─" * (width - len(top))
    body = [f"│ {l}" + (" " * (width - 2 - len(l))) for l in wrapped_lines]
    bottom = "└" + "─" * (width - 1)
    return color + "\n" + top + "\n" + "\n".join(body) + "\n" + bottom + Style.RESET_ALL


def run_conversation(args):
    config = load_config(args.config)
    models = auto_models_if_needed(args.models or config.get("models", []))
    rounds = args.rounds or int(config.get("rounds", 5))
    initial_prompt = args.initial or config.get("initial_prompt", "Hello")
    moderator_model = args.moderator
    memory = args.memory
    stream = args.stream
    delay = args.delay

    if len(models) < 2:
        raise ValueError("Need at least two models (provide via --models or config)")

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    text_file = TRANSCRIPT_DIR / f"conversation_{timestamp}.txt"
    json_file = TRANSCRIPT_DIR / f"conversation_{timestamp}.json"

    history: List[Dict] = []
    current_prompt = initial_prompt
    base_topic = initial_prompt

    console.print(f"[bold white]Models: {', '.join(models)} | Rounds: {rounds} | Start: {timestamp}[/bold white]")
    console.print(f"[bold white]Initial Prompt -> {models[0]}:[/bold white] [bright_cyan]{initial_prompt}[/bright_cyan]")
    console.rule()

    with text_file.open("w", encoding="utf-8") as tf:
        tf.write(f"Models: {', '.join(models)} | Rounds: {rounds} | Start: {timestamp}\n")
        tf.write(f"Initial Prompt -> {models[0]}: {initial_prompt}\n{'='*70}\n")

        for r in range(1, rounds + 1):
            round_entries: List[Dict] = []
            for idx, model in enumerate(models):
                color = MODEL_COLORS[idx % len(MODEL_COLORS)]
                mem_slice = history[-memory:] if memory > 0 else []
                messages = (
                    [{"role": "system", "content": "You are an agent collaborating concisely."}]
                    + [{"role": "assistant", "content": e["response"]} for e in mem_slice]
                    + [{"role": "user", "content": current_prompt}]
                )

                panel_title = f"Round {r} • Turn {idx+1} • Model [bold]{model}[/bold]"
                
                response_content = Text("Thinking...")
                live = Live(Panel(response_content, title=panel_title, border_style=color), console=console, refresh_per_second=10)
                
                with live:
                    response = call_model(model, messages, stream, live)

                sim = topic_similarity(base_topic, response)
                senti = sentiment_score(response)
                
                final_panel = Panel(
                    Markdown(response, style="bright_white"),
                    title=panel_title,
                    subtitle=f"Sentiment: [green]+{senti['positive']}[/green] [red]-{senti['negative']}[/red] | Similarity: {sim:.2f}",
                    border_style=color
                )
                console.print(final_panel)

                entry = {
                    "round": r,
                    "turn": idx + 1,
                    "model": model,
                    "prompt": current_prompt,
                    "response": response,
                    "topic_similarity": sim,
                    "sentiment": senti,
                }
                history.append(entry)
                round_entries.append(entry)

                tf.write(
                    f"[Round {r} | Turn {idx+1} | Model: {model}]\n"
                    f"Prompt:\n{current_prompt}\n"
                    f"Response:\n{response}\n"
                    f"TopicSimilarity: {sim:.2f} Sentiment: +{senti['positive']} -{senti['negative']}\n"
                    f"{'-'*50}\n"
                )

                if sim < 0.25:
                    console.print(f"[bold red]⚠️ Topic Drift Alert: similarity {sim:.2f}[/bold red]")

                current_prompt = response
                time.sleep(delay)

            if moderator_model:
                summary = moderator_summary(moderator_model, r, round_entries, initial_prompt)
                mod_panel = Panel(
                    Markdown(summary),
                    title=f"🕵️ Moderator Summary • Round {r} • Model [bold]{moderator_model}[/bold]",
                    border_style="white"
                )
                console.print(mod_panel)
                tf.write(f"[Moderator Round {r}]\n{summary}\n{'='*50}\n")
                history.append({
                    "round": r,
                    "turn": None,
                    "model": moderator_model,
                    "prompt": "round summary",
                    "response": summary,
                })
                time.sleep(delay)

        tf.write(f"Conversation complete. Transcript saved to {text_file}\n")
        console.print(f"[bold green]\n✅ Conversation complete. Transcript saved to {text_file}[/bold green]")

    if args.json:
        with json_file.open("w", encoding="utf-8") as jf:
            json.dump({
                "timestamp": timestamp,
                "models": models,
                "moderator": moderator_model,
                "rounds": rounds,
                "initial_prompt": initial_prompt,
                "history": history,
            }, jf, indent=2)
        console.print(f"[bold green]📄 JSON transcript written: {json_file}[/bold green]")



def build_parser():
    p = argparse.ArgumentParser(description="Run an enhanced multi-model Ollama conversation.")
    p.add_argument("--config", default="../config.json", help="Path to config.json or .yaml")
    p.add_argument("--models", nargs="*", help="Override models (space separated)")
    p.add_argument("--rounds", type=int, help="Override number of rounds")
    p.add_argument("--initial", help="Override initial prompt")
    p.add_argument("--moderator", help="Moderator model name (optional)")
    p.add_argument("--memory", type=int, default=4, help="Number of previous responses to include as context")
    p.add_argument("--stream", action="store_true", help="Enable streaming output (auto disabled if boxed)")
    p.add_argument("--delay", type=float, default=10.0, help="Delay in seconds between turns (default 10)")
    p.add_argument("--json", action="store_true", help="Write JSON transcript")
    p.add_argument("--no-box", action="store_true", help="Disable boxed display")
    p.add_argument("--plain", action="store_true", help="Sanitize markdown (remove asterisks/bold)")
    return p


if __name__ == "__main__":
    parser = build_parser()
    run_conversation(parser.parse_args())
