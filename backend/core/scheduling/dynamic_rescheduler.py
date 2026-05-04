import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from core.models_scheduling import ScheduledTask, TaskStatus, TimeBlock
from core.scheduling.ai_scheduling_engine import AISchedulingEngine
from core.scheduling.time_block_service import TimeBlockService

logger = logging.getLogger(__name__)


class DynamicRescheduler:
    def __init__(self, db: Session):
        self.db = db
        self._engine = AISchedulingEngine(db)
        self._block_svc = TimeBlockService(db)

    async def on_event_created(self, user_id: str, event: TimeBlock) -> Dict[str, Any]:
        conflicts = self._block_svc.check_conflicts(
            user_id, event.start_time, event.end_time, exclude_id=event.id
        )
        if not conflicts:
            return {"action": "none", "conflicts": 0}

        affected_tasks = self._find_affected_tasks(user_id, event.start_time, event.end_time)
        if not affected_tasks:
            return {"action": "none", "conflicts": len(conflicts), "affected_tasks": 0}

        result = await self._engine.reschedule_around_conflict(
            user_id, event.start_time, event.end_time
        )
        return {
            "action": "rescheduled",
            "conflicts": len(conflicts),
            "affected_tasks": len(affected_tasks),
            "rescheduled": result.get("rescheduled", []),
        }

    async def on_event_cancelled(self, user_id: str, event: TimeBlock) -> Dict[str, Any]:
        freed_start = event.start_time
        freed_end = event.end_time

        high_priority_unscheduled = (
            self.db.query(ScheduledTask)
            .filter(
                ScheduledTask.user_id == user_id,
                ScheduledTask.status == TaskStatus.TODO,
                ScheduledTask.scheduled_start.is_(None),
            )
            .order_by(ScheduledTask.priority.desc(), ScheduledTask.due_date.nulls_last())
            .limit(3)
            .all()
        )

        if not high_priority_unscheduled:
            return {"action": "none", "message": "No unscheduled tasks to fill the gap"}

        return {
            "action": "gap_available",
            "gap_start": freed_start.isoformat(),
            "gap_end": freed_end.isoformat(),
            "candidates": [
                {"task_id": t.id, "title": t.title, "duration_minutes": t.estimated_duration_minutes}
                for t in high_priority_unscheduled
            ],
        }

    async def on_event_updated(
        self, user_id: str, event: TimeBlock, old_start: datetime, old_end: datetime
    ) -> Dict[str, Any]:
        results = {}

        new_conflicts = self._block_svc.check_conflicts(
            user_id, event.start_time, event.end_time, exclude_id=event.id
        )
        if new_conflicts:
            reschedule_result = await self._engine.reschedule_around_conflict(
                user_id, event.start_time, event.end_time
            )
            results["conflict_resolution"] = reschedule_result

        if old_start != event.start_time or old_end != event.end_time:
            gap_result = await self.on_event_cancelled(
                user_id,
                TimeBlock(
                    user_id=user_id,
                    title="virtual_gap",
                    start_time=old_start,
                    end_time=old_end,
                ),
            )
            if gap_result.get("action") == "gap_available":
                results["old_gap"] = gap_result

        return results

    def _find_affected_tasks(
        self, user_id: str, start: datetime, end: datetime
    ) -> List[ScheduledTask]:
        return (
            self.db.query(ScheduledTask)
            .filter(
                ScheduledTask.user_id == user_id,
                ScheduledTask.status.in_([TaskStatus.TODO, TaskStatus.SCHEDULED]),
                ScheduledTask.scheduled_start < end,
                ScheduledTask.scheduled_end > start,
            )
            .all()
        )
