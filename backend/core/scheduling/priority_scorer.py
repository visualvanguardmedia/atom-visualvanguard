from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.models_scheduling import ScheduledTask, TaskPriority


class PriorityScorer:
    WEIGHT_DEADLINE = 0.40
    WEIGHT_IMPORTANCE = 0.20
    WEIGHT_EFFORT = 0.15
    WEIGHT_DEPENDENCIES = 0.15
    WEIGHT_ENERGY = 0.10

    PRIORITY_MULTIPLIERS = {
        TaskPriority.CRITICAL: 1.0,
        TaskPriority.HIGH: 0.8,
        TaskPriority.MEDIUM: 0.5,
        TaskPriority.LOW: 0.3,
    }

    def score(self, task: ScheduledTask, now: Optional[datetime] = None) -> float:
        now = now or datetime.now(timezone.utc)
        return (
            self._deadline_score(task, now) * self.WEIGHT_DEADLINE
            + self._importance_score(task) * self.WEIGHT_IMPORTANCE
            + self._effort_score(task) * self.WEIGHT_EFFORT
            + self._dependency_score(task) * self.WEIGHT_DEPENDENCIES
            + self._energy_score(task) * self.WEIGHT_ENERGY
        )

    def score_many(
        self, tasks: List[ScheduledTask], now: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        now = now or datetime.now(timezone.utc)
        scored = []
        for task in tasks:
            s = self.score(task, now)
            scored.append({"task": task, "score": s})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored

    def _deadline_score(self, task: ScheduledTask, now: datetime) -> float:
        if not task.due_date:
            return 0.3
        hours_until = (task.due_date - now).total_seconds() / 3600
        if hours_until < 0:
            return 1.0
        if hours_until < 4:
            return 0.95
        if hours_until < 24:
            return 0.85
        if hours_until < 72:
            return 0.65
        if hours_until < 168:
            return 0.45
        return 0.25

    def _importance_score(self, task: ScheduledTask) -> float:
        return self.PRIORITY_MULTIPLIERS.get(task.priority, 0.5)

    def _effort_score(self, task: ScheduledTask) -> float:
        dur = task.estimated_duration_minutes or 30
        if dur <= 15:
            return 0.9
        if dur <= 30:
            return 0.75
        if dur <= 60:
            return 0.5
        if dur <= 120:
            return 0.35
        return 0.2

    def _dependency_score(self, task: ScheduledTask) -> float:
        deps = task.dependencies or []
        if not deps:
            return 0.5
        return min(1.0, len(deps) * 0.3)

    def _energy_score(self, task: ScheduledTask) -> float:
        energy_map = {"high": 0.3, "medium": 0.6, "low": 0.9}
        return energy_map.get(task.energy_level, 0.5)
