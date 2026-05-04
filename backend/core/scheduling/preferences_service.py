from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from core.models_scheduling import SchedulingPreferences


class PreferencesService:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create(self, user_id: str) -> SchedulingPreferences:
        prefs = (
            self.db.query(SchedulingPreferences)
            .filter(SchedulingPreferences.user_id == user_id)
            .first()
        )
        if prefs:
            return prefs
        prefs = SchedulingPreferences(
            user_id=user_id,
            working_days={"0": True, "1": True, "2": True, "3": True, "4": True, "5": False, "6": False},
        )
        self.db.add(prefs)
        self.db.commit()
        self.db.refresh(prefs)
        return prefs

    def update(self, user_id: str, updates: Dict[str, Any]) -> SchedulingPreferences:
        prefs = self.get_or_create(user_id)
        allowed = {
            "timezone", "working_days", "working_hours_start", "working_hours_end",
            "buffer_minutes", "max_scheduling_density", "preferred_focus_slots",
            "no_meeting_days", "lunch_break_start", "lunch_break_end", "energy_profile",
            "default_task_duration_minutes", "auto_schedule_enabled", "deep_work_min_minutes",
        }
        for key, value in updates.items():
            if key in allowed:
                setattr(prefs, key, value)
        self.db.commit()
        self.db.refresh(prefs)
        return prefs

    def get_working_hours(self, user_id: str) -> tuple[time, time]:
        prefs = self.get_or_create(user_id)
        start_parts = prefs.working_hours_start.split(":")
        end_parts = prefs.working_hours_end.split(":")
        return (
            time(int(start_parts[0]), int(start_parts[1])),
            time(int(end_parts[0]), int(end_parts[1])),
        )

    def is_working_day(self, user_id: str, dt: datetime) -> bool:
        prefs = self.get_or_create(user_id)
        day_key = str(dt.weekday())
        return prefs.working_days.get(day_key, False)

    def is_no_meeting_day(self, user_id: str, dt: datetime) -> bool:
        prefs = self.get_or_create(user_id)
        if not prefs.no_meeting_days:
            return False
        day_key = str(dt.weekday())
        return prefs.no_meeting_days.get(day_key, False)

    def get_working_window_for_date(self, user_id: str, dt: datetime) -> Optional[tuple[datetime, datetime]]:
        if not self.is_working_day(user_id, dt):
            return None
        start_time, end_time = self.get_working_hours(user_id)
        tz_name = self._get_timezone(user_id)
        start = dt.replace(hour=start_time.hour, minute=start_time.minute, second=0, microsecond=0)
        end = dt.replace(hour=end_time.hour, minute=end_time.minute, second=0, microsecond=0)
        return (start, end)

    def _get_timezone(self, user_id: str) -> str:
        prefs = (
            self.db.query(SchedulingPreferences)
            .filter(SchedulingPreferences.user_id == user_id)
            .first()
        )
        return prefs.timezone if prefs else "UTC"
