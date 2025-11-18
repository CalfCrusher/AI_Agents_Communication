"""
Conversation runner for world simulation.

Provides a simplified interface to run Ollama-based conversations
between agents in the autonomous world simulation.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Optional

import ollama

# Ensure python directory is in path
PYTHON_DIR = Path(__file__).resolve().parents[1]
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from db.models import Agent, Conversation, Turn


class WorldConversationRunner:
    """Runs LLM conversations between agents in the world simulation."""

    def __init__(self, session, default_model: str = "tinyllama:1.1b"):
        """
        Initialize conversation runner.
        
        Args:
            session: Database session
            default_model: Default Ollama model to use
        """
        self.session = session
        self.default_model = default_model

    def run_duo_chat(
        self,
        agent_a: Agent,
        agent_b: Agent,
        context: str,
        turns: int = 2,
        max_words: int = 50,
    ) -> List[Dict]:
        """
        Run a conversation between two agents.
        
        Args:
            agent_a: First agent
            agent_b: Second agent
            context: Conversation context/prompt
            turns: Number of back-and-forth turns
            max_words: Maximum words per response
        
        Returns:
            List of conversation turns with agent names and responses
        """
        # Create conversation record
        conv = Conversation(
            scenario=f"World chat between {agent_a.name} and {agent_b.name}",
            initial_prompt=context
        )
        self.session.add(conv)
        self.session.flush()

        # Build initial prompt with agent personas
        system_prompt = self._build_agent_prompt(agent_a, context, max_words)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"You are {agent_a.name}. Start a brief conversation about: {context}"}
        ]

        conversation_history = []
        current_agent = agent_a
        other_agent = agent_b

        for turn_idx in range(turns * 2):  # Each "turn" is 2 messages (A->B, B->A)
            try:
                # Get model response
                response = self._call_ollama(self.default_model, messages)
                
                # Log turn to database
                turn_record = Turn(
                    conversation_id=conv.id,
                    round=turn_idx // 2,
                    interaction=0,
                    turn=turn_idx % 2,
                    agent_id=current_agent.id,
                    model=self.default_model,
                    role="assistant",
                    content=response
                )
                self.session.add(turn_record)
                
                # Add to conversation history
                conversation_history.append({
                    "agent": current_agent.name,
                    "content": response,
                    "turn": turn_idx
                })

                # Update messages for next turn
                messages.append({"role": "assistant", "content": response})
                
                # Switch agents
                current_agent, other_agent = other_agent, current_agent
                
                # Update system prompt for new speaker
                system_prompt = self._build_agent_prompt(current_agent, context, max_words)
                messages.append({
                    "role": "user",
                    "content": f"You are {current_agent.name}. Respond to what {other_agent.name} just said."
                })

            except Exception as e:
                print(f"Error in conversation turn {turn_idx}: {e}")
                conversation_history.append({
                    "agent": current_agent.name,
                    "content": f"[Error: {str(e)}]",
                    "turn": turn_idx
                })

        self.session.commit()
        return conversation_history

    def _build_agent_prompt(self, agent: Agent, context: str, max_words: int) -> str:
        """Build system prompt for an agent."""
        prompt_parts = [
            f"You are {agent.name}.",
        ]
        
        if agent.job:
            prompt_parts.append(f"Job: {agent.job}.")
        
        if agent.bio:
            prompt_parts.append(f"Bio: {agent.bio}.")
        
        # Add interests
        if agent.interests:
            interests = ", ".join([i.tag for i in agent.interests[:3]])
            prompt_parts.append(f"Interests: {interests}.")
        
        prompt_parts.extend([
            f"Keep responses under {max_words} words.",
            "Be natural and conversational.",
            "Stay in character.",
        ])
        
        return " ".join(prompt_parts)

    def _call_ollama(self, model: str, messages: List[Dict]) -> str:
        """Call Ollama API."""
        try:
            response = ollama.chat(model=model, messages=messages)
            return response["message"]["content"].strip()
        except Exception as e:
            return f"<error: {e}>"

    def run_group_chat(
        self,
        agents: List[Agent],
        context: str,
        turns_per_agent: int = 1,
        max_words: int = 30,
    ) -> List[Dict]:
        """
        Run a group conversation.
        
        Args:
            agents: List of agents participating
            context: Conversation context
            turns_per_agent: How many times each agent speaks
            max_words: Max words per response
        
        Returns:
            List of conversation turns
        """
        if len(agents) < 2:
            return []

        # Create conversation record
        conv = Conversation(
            scenario=f"Group chat: {', '.join(a.name for a in agents)}",
            initial_prompt=context
        )
        self.session.add(conv)
        self.session.flush()

        conversation_history = []
        messages = [
            {"role": "system", "content": f"Group discussion about: {context}"},
        ]

        for round_idx in range(turns_per_agent):
            for agent_idx, agent in enumerate(agents):
                system_prompt = self._build_agent_prompt(agent, context, max_words)
                messages[0] = {"role": "system", "content": system_prompt}
                
                try:
                    response = self._call_ollama(self.default_model, messages)
                    
                    # Log turn
                    turn_record = Turn(
                        conversation_id=conv.id,
                        round=round_idx,
                        interaction=0,
                        turn=agent_idx,
                        agent_id=agent.id,
                        model=self.default_model,
                        role="assistant",
                        content=response
                    )
                    self.session.add(turn_record)
                    
                    conversation_history.append({
                        "agent": agent.name,
                        "content": response,
                        "round": round_idx,
                        "turn": agent_idx
                    })
                    
                    # Add to context for next agent
                    messages.append({"role": "assistant", "content": f"{agent.name}: {response}"})
                    
                except Exception as e:
                    print(f"Error in group chat for {agent.name}: {e}")

        self.session.commit()
        return conversation_history
