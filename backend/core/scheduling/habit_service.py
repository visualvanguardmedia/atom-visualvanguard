from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from core.models_scheduling import Habit, HabitCompletion


class HabitService:
    def __init__(self, db: Session):
        self.db = db

    def create(self, user_id: str, data: Dict[str, Any]) -> Habit:
        habit = Habit(user_id=user_id, **data)
        self.db.add(habit)
        self.db.commit()
        self.db.refresh(habit)
        return habit

    def get(self, habit_id: str, user_id: str) -> Optional[Habit]:
        return (
            self.db.query(Habit)
            .filter(Habit.id == habit_id, Habit.user_id == user_id)
            .first()
        )

    def list_habits(
        self, user_id: str, active_only: bool = True, limit: int = 100, offset: int = 0
    ) -> List[Habit]:
        q = self.db.query(Habit).filter(Habit.user_id == user_id)
        if active_only:
            q = q.filter(Habit.is_active == True)
        return q.order_by(Habit.created_at.desc()).offset(offset).limit(limit).all()

    def update(self, habit_id: str, user_id: str, updates: Dict[str, Any]) -> Optional[Habit]:
        habit = self.get(habit_id, user_id)
        if not habit:
            return None
        for key, value in updates.items():
            if hasattr(habit, key):
                setattr(habit, key, value)
        self.db.commit()
        self.db.refresh(habit)
        return habit

    def delete(self, habit_id: str, user_id: str) -> bool:
        habit = self.get(habit_id, user_id)
        if not habit:
            return False
        self.db.delete(habit)
        self.db.commit()
        return True

    def complete(self, habit_id: str, user_id: str, notes: Optional[str] = None) -> Optional[Habit]:
        habit = self.get(habit_id, user_id)
        if not habit:
            return None

        completion = HabitCompletion(habit_id=habit_id, notes=notes)
        self.db.add(completion)

        now = datetime.now(timezone.utc)
        habit.last_completed_at = now

        if habit.last_completed_at:
            prev = habit.last_completed_at
            if prev and (now - prev).days <= 1:
                habit.streak_count += 1
            else:
                habit.streak_count = 1
        else:
            habit.streak_count = 1

        if habit.streak_count > habit.longest_streak:
            habit.longest_streak = habit.streak_count

        self.db.commit()
        self.db.refresh(habit)
        return habit

    def get_completions(
        self, habit_id: str, user_id: str, days: int = 30
    ) -> List[HabitCompletion]:
        habit = self.get(habit_id, user_id)
        if not habit:
            return []
        since = datetime.now(timezone.utc) - timedelta(days=days)
        return (
            self.db.query(HabitCompletion)
            .filter(HabitCompletion.habit_id == habit_id, HabitCompletion.completed_at >= since)
            .order_by(HabitCompletion.completed_at.desc())
            .all()
        )

    def get_active_for_date(self, user_id: str, dt: datetime) -> List[Habit]:
        habits = self.list_habits(user_id, active_only=True)
        result = []
        for habit in habits:
            if self._should_occur_on_date(habit, dt):
                result.append(habit)
        return result

    def _should_occur_on_date(self, habit: Habit, dt: datetime) -> bool:
        from core.models_scheduling import RecurrenceFrequency
        if habit.frequency == RecurrenceFrequency.DAILY:
            return True
        if habit.frequency == RecurrenceFrequency.WEEKLY:
            created = habit.created_at
            if created:
                return dt.weekday() == created.weekday()
            return True
        if habit.frequency == RecurrenceFrequency.MONTHLY:
            created = habit.created_at
            if created:
                return dt.day == created.day
            return True
        return True
