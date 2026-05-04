from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_
from sqlalchemy.orm import Session

from core.models_scheduling import BlockType, TimeBlock
from core.scheduling.preferences_service import PreferencesService


class TimeBlockService:
    def __init__(self, db: Session):
        self.db = db
        self._prefs = PreferencesService(db)

    def create(self, user_id: str, data: Dict[str, Any]) -> TimeBlock:
        block = TimeBlock(user_id=user_id, **data)
        self.db.add(block)
        self.db.commit()
        self.db.refresh(block)
        return block

    def get(self, block_id: str, user_id: str) -> Optional[TimeBlock]:
        return (
            self.db.query(TimeBlock)
            .filter(TimeBlock.id == block_id, TimeBlock.user_id == user_id)
            .first()
        )

    def list_blocks(
        self,
        user_id: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        block_type: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> List[TimeBlock]:
        q = self.db.query(TimeBlock).filter(TimeBlock.user_id == user_id)
        if start:
            q = q.filter(TimeBlock.end_time > start)
        if end:
            q = q.filter(TimeBlock.start_time < end)
        if block_type:
            q = q.filter(TimeBlock.block_type == block_type)
        return q.order_by(TimeBlock.start_time).offset(offset).limit(limit).all()

    def update(self, block_id: str, user_id: str, updates: Dict[str, Any]) -> Optional[TimeBlock]:
        block = self.get(block_id, user_id)
        if not block:
            return None
        for key, value in updates.items():
            if hasattr(block, key):
                setattr(block, key, value)
        self.db.commit()
        self.db.refresh(block)
        return block

    def delete(self, block_id: str, user_id: str) -> bool:
        block = self.get(block_id, user_id)
        if not block:
            return False
        self.db.delete(block)
        self.db.commit()
        return True

    def get_events_for_range(
        self, user_id: str, start: datetime, end: datetime
    ) -> List[TimeBlock]:
        return (
            self.db.query(TimeBlock)
            .filter(
                TimeBlock.user_id == user_id,
                TimeBlock.start_time < end,
                TimeBlock.end_time > start,
            )
            .order_by(TimeBlock.start_time)
            .all()
        )

    def find_free_slots(
        self,
        user_id: str,
        date: datetime,
        duration_minutes: int = 30,
        min_slot_minutes: int = 15,
    ) -> List[Tuple[datetime, datetime]]:
        window = self._prefs.get_working_window_for_date(user_id, date)
        if not window:
            return []

        day_start, day_end = window
        blocks = self.get_events_for_range(user_id, day_start, day_end)
        prefs = self._prefs.get_or_create(user_id)
        buffer_td = timedelta(minutes=prefs.buffer_minutes)

        busy_intervals = [(b.start_time, b.end_time) for b in blocks]
        busy_intervals.sort(key=lambda x: x[0])

        free_slots = []
        current = day_start

        for busy_start, busy_end in busy_intervals:
            gap_end = busy_start - buffer_td
            if gap_end > current:
                gap_minutes = (gap_end - current).total_seconds() / 60
                if gap_minutes >= min_slot_minutes:
                    free_slots.append((current, gap_end))
            current = max(current, busy_end + buffer_td)

        if current < day_end:
            gap_minutes = (day_end - current).total_seconds() / 60
            if gap_minutes >= min_slot_minutes:
                free_slots.append((current, day_end))

        if duration_minutes > min_slot_minutes:
            free_slots = [
                (s, e) for s, e in free_slots
                if (e - s).total_seconds() / 60 >= duration_minutes
            ]

        return free_slots

    def check_conflicts(
        self,
        user_id: str,
        start: datetime,
        end: datetime,
        exclude_id: Optional[str] = None,
    ) -> List[TimeBlock]:
        q = self.db.query(TimeBlock).filter(
            TimeBlock.user_id == user_id,
            TimeBlock.start_time < end,
            TimeBlock.end_time > start,
        )
        if exclude_id:
            q = q.filter(TimeBlock.id != exclude_id)
        return q.all()

    def to_calendar_event_dict(self, block: TimeBlock) -> Dict[str, Any]:
        return {
            "id": block.id,
            "title": block.title,
            "description": block.description,
            "start": block.start_time.isoformat() if block.start_time else None,
            "end": block.end_time.isoformat() if block.end_time else None,
            "location": None,
            "status": "confirmed",
            "platform": block.source or "local",
            "color": block.color or "#3182CE",
            "block_type": block.block_type.value if block.block_type else None,
            "task_id": block.task_id,
            "habit_id": block.habit_id,
            "metadata": block.block_metadata or {},
        }
