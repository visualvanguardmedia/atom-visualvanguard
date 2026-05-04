from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

from core.models_scheduling import ScheduledTask, TaskPriority, TaskStatus


class ScheduledTaskService:
    def __init__(self, db: Session):
        self.db = db

    def create(self, user_id: str, data: Dict[str, Any]) -> ScheduledTask:
        task = ScheduledTask(user_id=user_id, **data)
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def get(self, task_id: str, user_id: str) -> Optional[ScheduledTask]:
        return (
            self.db.query(ScheduledTask)
            .filter(ScheduledTask.id == task_id, ScheduledTask.user_id == user_id)
            .first()
        )

    def list_tasks(
        self,
        user_id: str,
        status: Optional[str] = None,
        project: Optional[str] = None,
        source: Optional[str] = None,
        due_before: Optional[datetime] = None,
        due_after: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ScheduledTask]:
        q = self.db.query(ScheduledTask).filter(ScheduledTask.user_id == user_id)
        if status:
            q = q.filter(ScheduledTask.status == status)
        if project:
            q = q.filter(ScheduledTask.project == project)
        if source:
            q = q.filter(ScheduledTask.source == source)
        if due_before:
            q = q.filter(ScheduledTask.due_date <= due_before)
        if due_after:
            q = q.filter(ScheduledTask.due_date >= due_after)
        return q.order_by(ScheduledTask.due_date.nulls_last()).offset(offset).limit(limit).all()

    def update(self, task_id: str, user_id: str, updates: Dict[str, Any]) -> Optional[ScheduledTask]:
        task = self.get(task_id, user_id)
        if not task:
            return None
        for key, value in updates.items():
            if hasattr(task, key):
                setattr(task, key, value)
        self.db.commit()
        self.db.refresh(task)
        return task

    def delete(self, task_id: str, user_id: str) -> bool:
        task = self.get(task_id, user_id)
        if not task:
            return False
        self.db.delete(task)
        self.db.commit()
        return True

    def complete(self, task_id: str, user_id: str, actual_minutes: Optional[int] = None) -> Optional[ScheduledTask]:
        task = self.get(task_id, user_id)
        if not task:
            return None
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now(timezone.utc)
        if actual_minutes is not None:
            task.actual_duration_minutes = actual_minutes
        self.db.commit()
        self.db.refresh(task)
        return task

    def get_scheduled_for_range(
        self, user_id: str, start: datetime, end: datetime
    ) -> List[ScheduledTask]:
        return (
            self.db.query(ScheduledTask)
            .filter(
                ScheduledTask.user_id == user_id,
                ScheduledTask.scheduled_start >= start,
                ScheduledTask.scheduled_start < end,
                ScheduledTask.status.in_([TaskStatus.TODO, TaskStatus.SCHEDULED, TaskStatus.IN_PROGRESS]),
            )
            .order_by(ScheduledTask.scheduled_start)
            .all()
        )

    def get_unscheduled(self, user_id: str, limit: int = 50) -> List[ScheduledTask]:
        return (
            self.db.query(ScheduledTask)
            .filter(
                ScheduledTask.user_id == user_id,
                ScheduledTask.status == TaskStatus.TODO,
                ScheduledTask.scheduled_start.is_(None),
            )
            .order_by(ScheduledTask.due_date.nulls_last())
            .limit(limit)
            .all()
        )

    def import_external(
        self, user_id: str, tasks_data: List[Dict[str, Any]], platform: str
    ) -> List[ScheduledTask]:
        imported = []
        for td in tasks_data:
            existing = None
            external_id = td.get("external_id")
            if external_id:
                existing = (
                    self.db.query(ScheduledTask)
                    .filter(
                        ScheduledTask.user_id == user_id,
                        ScheduledTask.external_id == external_id,
                        ScheduledTask.platform == platform,
                    )
                    .first()
                )
            if existing:
                for key, value in td.items():
                    if hasattr(existing, key) and key != "id":
                        setattr(existing, key, value)
                imported.append(existing)
            else:
                task = ScheduledTask(
                    user_id=user_id,
                    platform=platform,
                    source="import",
                    **{k: v for k, v in td.items() if k != "id"},
                )
                self.db.add(task)
                imported.append(task)
        self.db.commit()
        for t in imported:
            self.db.refresh(t)
        return imported
