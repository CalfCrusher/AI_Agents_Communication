"""
Reporting Service - Aggregates and formats world simulation metrics.

Provides:
- Daily summary report generation
- Metrics aggregation (activities, locations, memories, relationships)
- Multiple output formats (Markdown, JSON)
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from sqlalchemy import func
from sqlalchemy.orm import Session

from db.models import (
    Agent, WorldEvent, Memory, Relationship, 
    AgentLocation, Activity, Location, DailyReport
)


class ReportingService:
    """Generates reports and metrics for world simulation."""

    def __init__(self, session: Session, reports_dir: Path):
        self.session = session
        self.reports_dir = reports_dir
        self.reports_dir.mkdir(exist_ok=True)

    def generate_daily_report(
        self, 
        day_label: str, 
        format_type: str = "markdown"
    ) -> Path:
        """
        Generate daily summary report.
        
        Args:
            day_label: Day identifier (e.g., "2025-11-18")
            format_type: "markdown", "json", or "both"
        
        Returns:
            Path to generated report file
        """
        metrics = self._collect_metrics(day_label)
        summary = self._generate_summary(day_label, metrics)
        
        # Save to database
        self._save_report_to_db(day_label, summary, metrics)
        
        # Generate files
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if format_type in ("markdown", "both"):
            md_path = self.reports_dir / f"world_{day_label}_{timestamp}.md"
            self._write_markdown_report(md_path, day_label, summary, metrics)
        
        if format_type in ("json", "both"):
            json_path = self.reports_dir / f"world_{day_label}_{timestamp}.json"
            self._write_json_report(json_path, day_label, summary, metrics)
        
        return self.reports_dir / f"world_{day_label}_{timestamp}.md"

    def _collect_metrics(self, day_label: str) -> Dict:
        """Collect all metrics for a given day."""
        # Event counts by agent
        events = (
            self.session.query(WorldEvent)
            .join(Agent)
            .all()
        )
        
        # Filter events for this day
        day_events = []
        for event in events:
            try:
                metadata = json.loads(event.metadata_json) if event.metadata_json else {}
                if metadata.get("day_label") == day_label:
                    day_events.append(event)
            except json.JSONDecodeError:
                continue
        
        # Activity breakdown
        activities_counter = Counter()
        locations_counter = Counter()
        agent_actions = defaultdict(list)
        
        for event in day_events:
            metadata = json.loads(event.metadata_json) if event.metadata_json else {}
            action = metadata.get("action", "unknown")
            activities_counter[action] += 1
            
            if event.location_id:
                location = self.session.query(Location).get(event.location_id)
                if location:
                    locations_counter[location.name] += 1
            
            agent = self.session.query(Agent).get(event.agent_id)
            if agent:
                agent_actions[agent.name].append(action)
        
        # Memory counts
        memory_count = self.session.query(Memory).count()
        
        # Relationship updates
        relationships = self.session.query(Relationship).all()
        strong_relationships = [r for r in relationships if r.strength > 0.5]
        
        return {
            "total_events": len(day_events),
            "activities": dict(activities_counter),
            "locations": dict(locations_counter),
            "agent_actions": dict(agent_actions),
            "memory_count": memory_count,
            "relationship_count": len(relationships),
            "strong_relationship_count": len(strong_relationships),
            "agents_active": len(agent_actions),
        }

    def _generate_summary(self, day_label: str, metrics: Dict) -> str:
        """Generate human-readable summary text."""
        lines = [
            f"Day {day_label} Summary:",
            f"- Total events: {metrics['total_events']}",
            f"- Active agents: {metrics['agents_active']}",
            f"- Memories recorded: {metrics['memory_count']}",
            f"- Relationships: {metrics['relationship_count']} ({metrics['strong_relationship_count']} strong)",
        ]
        
        if metrics['activities']:
            lines.append("\nTop activities:")
            for activity, count in sorted(
                metrics['activities'].items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:5]:
                lines.append(f"  - {activity}: {count}")
        
        if metrics['locations']:
            lines.append("\nMost visited locations:")
            for location, count in sorted(
                metrics['locations'].items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:5]:
                lines.append(f"  - {location}: {count}")
        
        return "\n".join(lines)

    def _save_report_to_db(self, day_label: str, summary: str, metrics: Dict):
        """Save report to database."""
        existing = self.session.query(DailyReport).filter_by(day_label=day_label).first()
        
        if existing:
            existing.summary_text = summary
            existing.metrics_json = json.dumps(metrics)
        else:
            report = DailyReport(
                day_label=day_label,
                summary_text=summary,
                metrics_json=json.dumps(metrics)
            )
            self.session.add(report)
        
        self.session.commit()

    def _write_markdown_report(
        self, 
        path: Path, 
        day_label: str, 
        summary: str, 
        metrics: Dict
    ):
        """Write Markdown report file."""
        content = [
            f"# World Simulation Report - {day_label}",
            "",
            "## Summary",
            "",
            summary,
            "",
            "## Agent Activity Breakdown",
            "",
        ]
        
        for agent_name, actions in metrics['agent_actions'].items():
            content.append(f"### {agent_name}")
            action_counts = Counter(actions)
            for action, count in action_counts.most_common():
                content.append(f"- {action}: {count}")
            content.append("")
        
        content.extend([
            "## Metrics",
            "",
            f"- Total Events: {metrics['total_events']}",
            f"- Active Agents: {metrics['agents_active']}",
            f"- Memory Count: {metrics['memory_count']}",
            f"- Relationships: {metrics['relationship_count']}",
            "",
            "---",
            f"*Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
        ])
        
        path.write_text("\n".join(content), encoding="utf-8")

    def _write_json_report(
        self, 
        path: Path, 
        day_label: str, 
        summary: str, 
        metrics: Dict
    ):
        """Write JSON report file."""
        report_data = {
            "day_label": day_label,
            "summary": summary,
            "metrics": metrics,
            "generated_at": datetime.now().isoformat(),
        }
        
        path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")

    def print_tick_summary(self, tick_idx: int, hour: int, events: List[Dict]):
        """Print brief tick summary to console."""
        if not events:
            return
        
        action_counts = Counter(e.get("action") for e in events)
        print(f"  Summary: {dict(action_counts)}")
