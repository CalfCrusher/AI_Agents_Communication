from __future__ import annotations

import json
import re
from array import array
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha1
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from rich.console import Console
from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session

from db.models import (
    Agent,
    Conversation,
    Embedding,
    Interest,
    Memory,
    Relationship,
    Turn,
)

RELATIONSHIP_KEYWORDS = {
    "wife": "spouse",
    "husband": "spouse",
    "spouse": "spouse",
    "partner": "partner",
    "son": "child",
    "daughter": "child",
    "mom": "parent",
    "mother": "parent",
    "dad": "parent",
    "father": "parent",
    "brother": "sibling",
    "sister": "sibling",
    "friend": "friend",
    "coworker": "coworker",
    "boss": "boss",
    "manager": "manager",
}

PREFERENCE_PATTERN = re.compile(r"\bI (?:really )?(like|love|enjoy|adore)\s+(?P<object>[^.!?]+)", re.IGNORECASE)
DISLIKE_PATTERN = re.compile(r"\bI (?:really )?(?:dislike|hate|can't stand)\s+(?P<object>[^.!?]+)", re.IGNORECASE)
EVENT_PATTERN = re.compile(
    r"\bI (?:just\s+)?(?:went to|visited|traveled to|attended)\s+(?P<object>[^.!?]+)", re.IGNORECASE
)
JOB_PATTERN = re.compile(
    r"\bI (?:work as|work at|am (?:an?|the))\s+(?P<object>[^.!?]+)", re.IGNORECASE
)
RELATIONSHIP_PATTERN = re.compile(
    r"\bmy\s+(?P<relation>wife|husband|spouse|partner|son|daughter|mom|mother|dad|father|brother|sister|friend|coworker|boss|manager)(?:\s+named)?\s+(?P<name>[A-Z][a-zA-Z]+)?",
    re.IGNORECASE,
)
MAX_FACTS_PER_TURN = 6


def _clean_fragment(value: str) -> str:
    fragment = value.strip().strip(",.;:!?")
    return fragment[:240]


@dataclass
class Fact:
    kind: str
    text: str
    confidence: float
    metadata: Optional[Dict] = None


def extract_facts(turn_text: str) -> List[Fact]:
    """Very small heuristic extractor that returns normalized facts and preferences."""

    results: List[Fact] = []

    for pattern, kind, conf, prefix in (
        (PREFERENCE_PATTERN, "preference", 0.8, "Enjoys"),
        (DISLIKE_PATTERN, "preference", 0.75, "Dislikes"),
        (EVENT_PATTERN, "event", 0.7, "Recently"),
        (JOB_PATTERN, "fact", 0.65, "Role"),
    ):
        for match in pattern.finditer(turn_text):
            obj = _clean_fragment(match.group("object"))
            if not obj:
                continue
            text = f"{prefix} {obj}" if prefix != "Role" else f"{prefix}: {obj}"
            results.append(Fact(kind=kind, text=text, confidence=conf))
            if len(results) >= MAX_FACTS_PER_TURN:
                return results

    for rel_match in RELATIONSHIP_PATTERN.finditer(turn_text):
        relation = rel_match.group("relation")
        name = rel_match.group("name")
        relation_type = RELATIONSHIP_KEYWORDS.get(relation.lower(), relation.lower())
        target_name = _clean_fragment(name) if name else None
        if not relation_type:
            continue
        if target_name:
            text = f"Mentions {relation_type}: {target_name}"
        else:
            text = f"Talks about their {relation_type}"
        metadata = {
            "relationship_type": relation_type,
            "target_name": target_name,
        }
        results.append(Fact(kind="relationship", text=text, confidence=0.7, metadata=metadata))
        if len(results) >= MAX_FACTS_PER_TURN:
            break

    return results


class PersistenceManager:
    """Coordinates persona loading, turn storage, memory extraction, and retrieval."""

    def __init__(
        self,
        session: Session,
        console: Optional[Console] = None,
        *,
        embed_model_name: Optional[str] = None,
        topk_memories: int = 5,
        topk_recent: int = 3,
        token_cap: int = 300,
    ) -> None:
        self.session = session
        self.console = console
        self.embed_model_name = embed_model_name
        self._embedder = None
        self.topk_memories = max(1, topk_memories)
        self.topk_recent = max(1, topk_recent)
        self.token_cap = max(80, token_cap)
        self.conversation: Optional[Conversation] = None
        self.binding_index: Dict[int, Agent] = {}
        self.name_to_agent: Dict[str, Agent] = {}
        self._persona_cache: Dict[int, str] = {}

    # --- Conversation + agents -------------------------------------------------
    def create_conversation(self, scenario: str, initial_prompt: str) -> Conversation:
        conversation = Conversation(scenario=scenario, initial_prompt=initial_prompt)
        self.session.add(conversation)
        self.session.commit()
        self.conversation = conversation
        return conversation

    def register_binding(self, slot_idx: int, agent: Agent) -> None:
        self.binding_index[slot_idx] = agent
        self.name_to_agent[agent.name.lower()] = agent
        self._persona_cache.pop(agent.id, None)

    def load_agent(self, agent_id: Optional[int]) -> Optional[Agent]:
        if not agent_id:
            return None
        try:
            stmt = select(Agent).where(Agent.id == agent_id)
            return self.session.execute(stmt).scalar_one()
        except NoResultFound:
            return None

    # --- Turns / memories ------------------------------------------------------
    def record_turn(
        self,
        *,
        round_idx: int,
        interaction_idx: int,
        turn_idx: int,
        model: str,
        role: str,
        content: str,
        agent: Optional[Agent] = None,
    ) -> Turn:
        if not self.conversation:
            raise RuntimeError("Conversation must be created before recording turns")
        turn = Turn(
            conversation_id=self.conversation.id,
            round=round_idx,
            interaction=interaction_idx,
            turn=turn_idx,
            model=model,
            role=role,
            content=content,
            agent_id=agent.id if agent else None,
        )
        self.session.add(turn)
        self.session.commit()
        return turn

    def process_memories(
        self,
        *,
        agent: Agent,
        turn: Turn,
    ) -> Dict[str, int]:
        facts = extract_facts(turn.content)
        upserts = 0
        relationship_updates = 0
        for fact in facts:
            stored = self._upsert_memory(agent, turn, fact)
            if stored:
                upserts += 1
                if fact.kind == "relationship" and fact.metadata:
                    relationship_updates += self._update_relationship(agent, fact.metadata)
        self.session.commit()
        return {
            "facts": len(facts),
            "upserts": upserts,
            "relationships": relationship_updates,
        }

    def _update_relationship(self, agent: Agent, metadata: Dict) -> int:
        target_name = metadata.get("target_name")
        rel_type = metadata.get("relationship_type")
        if not rel_type or not target_name:
            return 0
        target_agent = self.name_to_agent.get(target_name.lower())
        if not target_agent:
            return 0
        stmt = select(Relationship).where(
            Relationship.from_agent_id == agent.id,
            Relationship.to_agent_id == target_agent.id,
        )
        rel = self.session.execute(stmt).scalar_one_or_none()
        if rel is None:
            rel = Relationship(
                from_agent_id=agent.id,
                to_agent_id=target_agent.id,
                type=rel_type,
                strength=0.4,
                since_date=datetime.utcnow().date(),
            )
            self.session.add(rel)
        else:
            rel.strength = min(1.0, rel.strength + 0.05)
            rel.type = rel_type or rel.type
            rel.updated_at = datetime.utcnow()
        return 1

    def _upsert_memory(self, agent: Agent, turn: Turn, fact: Fact) -> bool:
        normalized = " ".join(fact.text.lower().split())
        digest = sha1(f"{agent.id}:{fact.kind}:{normalized}".encode("utf-8")).hexdigest()
        stmt = select(Memory).where(Memory.normalized_hash == digest)
        memory = self.session.execute(stmt).scalar_one_or_none()
        payload = {
            "agent_id": agent.id,
            "kind": fact.kind,
            "text": fact.text,
            "confidence": min(0.95, max(0.2, fact.confidence)),
            "source_turn_id": turn.id,
            "normalized_hash": digest,
            "metadata_json": json.dumps(fact.metadata) if fact.metadata else None,
        }
        created = False
        if memory is None:
            memory = Memory(**payload)
            self.session.add(memory)
            created = True
        else:
            if fact.confidence > memory.confidence:
                memory.confidence = min(0.95, max(memory.confidence, fact.confidence))
            memory.text = fact.text
            memory.source_turn_id = turn.id
            memory.metadata_json = payload["metadata_json"]
        self.session.flush()
        if created:
            self._persist_embedding("memory", memory.id, memory.text)
        return created

    # --- Retrieval -------------------------------------------------------------
    def build_context_card(self, agent: Agent, query_text: str) -> Tuple[Optional[str], Dict[str, int]]:
        persona_lines = self._persona_lines(agent)
        relationship_lines = self._relationship_lines(agent)
        memories, memory_stats = self._retrieve_memories(agent.id, query_text)

        if not persona_lines and not memories:
            return None, {"memories": 0, "recent": 0}

        sections: List[str] = [f"Context Card — {agent.name}"]
        if persona_lines:
            sections.append("Persona: " + " ".join(persona_lines))
        if relationship_lines:
            sections.append("Relationships:\n" + "\n".join(f"- {line}" for line in relationship_lines))
        if memories:
            sections.append(
                "Memories:\n" + "\n".join(
                    f"- [{mem.kind}] {mem.text}" for mem in memories
                )
            )
        limited = self._clip_sections(sections)
        return limited, memory_stats

    def _persona_lines(self, agent: Agent) -> List[str]:
        if agent.id in self._persona_cache:
            cached = self._persona_cache[agent.id]
            return [cached] if cached else []
        parts: List[str] = []
        if agent.bio:
            parts.append(agent.bio.strip())
        if agent.job:
            parts.append(f"Job: {agent.job.strip()}")
        interests = (
            self.session.query(Interest)
            .filter(Interest.agent_id == agent.id)
            .order_by(Interest.score.desc())
            .limit(2)
            .all()
        )
        if interests:
            interest_text = ", ".join(i.tag for i in interests)
            parts.append(f"Interests: {interest_text}")
        persona = " | ".join(parts).strip()
        self._persona_cache[agent.id] = persona
        return [persona] if persona else []

    def _relationship_lines(self, agent: Agent) -> List[str]:
        relationships = (
            self.session.query(Relationship)
            .filter(Relationship.from_agent_id == agent.id)
            .order_by(Relationship.strength.desc())
            .limit(2)
            .all()
        )
        lines = []
        for rel in relationships:
            target = rel.to_agent.name if rel.to_agent else "unknown"
            lines.append(f"{rel.type} with {target} ({rel.strength:.2f})")
        return lines

    def _retrieve_memories(self, agent_id: int, query_text: str) -> Tuple[List[Memory], Dict[str, int]]:
        recents = (
            self.session.query(Memory)
            .filter(Memory.agent_id == agent_id)
            .order_by(Memory.created_at.desc())
            .limit(self.topk_recent)
            .all()
        )
        sim_ranked: List[Tuple[float, Memory]] = []
        embedder = self._get_embedder()
        if embedder and query_text:
            sim_ranked = self._similar_memories(agent_id, query_text)
        ordered: List[Memory] = []
        seen = set()
        for _, memory in sim_ranked:
            if memory.id in seen:
                continue
            ordered.append(memory)
            seen.add(memory.id)
            if len(ordered) >= self.topk_memories:
                break
        for memory in recents:
            if memory.id in seen:
                continue
            ordered.append(memory)
            seen.add(memory.id)
            if len(ordered) >= self.topk_memories:
                break
        stats = {
            "memories": len(ordered),
            "recent": len(recents),
            "similar": len(sim_ranked),
        }
        return ordered, stats

    def _clip_sections(self, sections: Sequence[str]) -> str:
        words = 0
        limited_lines: List[str] = []
        for block in sections:
            for line in block.splitlines():
                line_words = len(line.split()) or 1
                if words + line_words > self.token_cap:
                    limited_lines.append("...")
                    return "\n".join(limited_lines)
                limited_lines.append(line)
                words += line_words
        return "\n".join(limited_lines)

    def _get_embedder(self):
        if not self.embed_model_name:
            return None
        if self._embedder is not None:
            return self._embedder
        try:
            from sentence_transformers import SentenceTransformer

            self._embedder = SentenceTransformer(self.embed_model_name)
        except Exception as exc:  # pragma: no cover - optional dependency
            if self.console:
                self.console.print(f"[yellow]Embedding model load failed: {exc}[/yellow]")
            self._embedder = None
        return self._embedder

    def _persist_embedding(self, doc_type: str, doc_id: int, text: str) -> None:
        embedder = self._get_embedder()
        if not embedder:
            return
        vector = embedder.encode([text], convert_to_numpy=True)[0]
        arr = array("f", vector.tolist())
        embedding = Embedding(
            doc_type=doc_type,
            doc_id=doc_id,
            model=self.embed_model_name,
            dim=len(vector),
            vector=arr.tobytes(),
        )
        self.session.add(embedding)

    def _similar_memories(self, agent_id: int, query_text: str) -> List[Tuple[float, Memory]]:
        embedder = self._get_embedder()
        if not embedder:
            return []
        query_vec = embedder.encode([query_text], convert_to_numpy=True)[0]
        embeddings = (
            self.session.query(Embedding, Memory)
            .join(Memory, Embedding.doc_id == Memory.id)
            .filter(
                Embedding.doc_type == "memory",
                Memory.agent_id == agent_id,
                Embedding.model == self.embed_model_name,
            )
            .all()
        )
        scored: List[Tuple[float, Memory]] = []
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            return []
        for embedding, memory in embeddings:
            vec = np.frombuffer(embedding.vector, dtype=np.float32)
            if vec.size != embedding.dim:
                continue
            denom = np.linalg.norm(vec) * query_norm
            if denom == 0:
                continue
            score = float(np.dot(vec, query_vec) / denom)
            scored.append((score, memory))
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[: self.topk_memories]
