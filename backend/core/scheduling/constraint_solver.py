from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from core.models_scheduling import ScheduledTask, TimeBlock, TaskStatus
from core.scheduling.preferences_service import PreferencesService
from core.scheduling.priority_scorer import PriorityScorer
from sqlalchemy.orm import Session


class ConstraintSolver:
    def __init__(self, db: Session):
        self.db = db
        self._prefs = PreferencesService(db)
        self._scorer = PriorityScorer()

    def solve(
        self,
        user_id: str,
        tasks: List[ScheduledTask],
        start_date: datetime,
        end_date: datetime,
        existing_blocks: Optional[List[TimeBlock]] = None,
    ) -> List[Dict[str, Any]]:
        scored = self._scorer.score_many(tasks)
        sorted_tasks = [item["task"] for item in scored]

        occupied = self._build_occupied_map(user_id, start_date, end_date, existing_blocks)
        prefs = self._prefs.get_or_create(user_id)
        buffer_td = timedelta(minutes=prefs.buffer_minutes)

        assignments = []
        for task in sorted_tasks:
            duration = timedelta(minutes=task.estimated_duration_minutes or prefs.default_task_duration_minutes)
            slot = self._find_slot(
                user_id, task, duration, start_date, end_date,
                occupied, buffer_td, prefs,
            )
            if slot:
                start, end = slot
                assignments.append({
                    "task_id": task.id,
                    "title": task.title,
                    "scheduled_start": start.isoformat(),
                    "scheduled_end": end.isoformat(),
                    "duration_minutes": int(duration.total_seconds() / 60),
                })
                occupied.append((start, end))

        return assignments

    def _build_occupied_map(
        self,
        user_id: str,
        start_date: datetime,
        end_date: datetime,
        existing_blocks: Optional[List[TimeBlock]] = None,
    ) -> List[Tuple[datetime, datetime]]:
        occupied = []
        if existing_blocks:
            for b in existing_blocks:
                if b.start_time and b.end_time:
                    occupied.append((b.start_time, b.end_time))
        else:
            blocks = (
                self.db.query(TimeBlock)
                .filter(
                    TimeBlock.user_id == user_id,
                    TimeBlock.start_time < end_date,
                    TimeBlock.end_time > start_date,
                )
                .all()
            )
            for b in blocks:
                occupied.append((b.start_time, b.end_time))
        occupied.sort(key=lambda x: x[0])
        return occupied

    def _find_slot(
        self,
        user_id: str,
        task: ScheduledTask,
        duration: timedelta,
        start_date: datetime,
        end_date: datetime,
        occupied: List[Tuple[datetime, datetime]],
        buffer_td: timedelta,
        prefs: Any,
    ) -> Optional[Tuple[datetime, datetime]]:
        current_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

        while current_date < end_date:
            if not self._prefs.is_working_day(user_id, current_date):
                current_date += timedelta(days=1)
                continue

            window = self._prefs.get_working_window_for_date(user_id, current_date)
            if not window:
                current_date += timedelta(days=1)
                continue

            day_start, day_end = window

            if task.due_date and day_start > task.due_date:
                return None

            slot = self._find_in_window(day_start, day_end, duration, occupied, buffer_td)
            if slot:
                return slot

            current_date += timedelta(days=1)

        return None

    def _find_in_window(
        self,
        day_start: datetime,
        day_end: datetime,
        duration: timedelta,
        occupied: List[Tuple[datetime, datetime]],
        buffer_td: timedelta,
    ) -> Optional[Tuple[datetime, datetime]]:
        current = day_start

        day_occupied = [
            (s, e) for s, e in occupied
            if s < day_end and e > day_start
        ]
        day_occupied.sort(key=lambda x: x[0])

        for busy_start, busy_end in day_occupied:
            gap = busy_start - buffer_td - current
            if gap >= duration:
                return (current, current + duration)
            current = max(current, busy_end + buffer_td)

        if current + duration <= day_end:
            return (current, current + duration)

        return None
