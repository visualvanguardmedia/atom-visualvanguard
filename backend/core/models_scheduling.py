import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, DateTime, Float, Integer, Boolean, Text, ForeignKey, Index, Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from core.database import Base
from core.models import JSONColumn


class TaskPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskStatus(str, enum.Enum):
    TODO = "todo"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class RecurrenceFrequency(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class BlockType(str, enum.Enum):
    MEETING = "meeting"
    FOCUS = "focus"
    BREAK = "break"
    COMMUTING = "commuting"
    EXERCISE = "exercise"
    PERSONAL = "personal"
    HABIT = "habit"
    EXTERNAL_CALENDAR = "external_calendar"


class SyncProvider(str, enum.Enum):
    GOOGLE = "google"
    OUTLOOK = "outlook"


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SchedulingPreferences(Base):
    __tablename__ = "scheduling_preferences"
    __table_args__ = {"extend_existing": True}

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    timezone = Column(String, nullable=False, default="UTC")
    working_days = Column(JSONColumn, nullable=False, default=dict)
    working_hours_start = Column(String, nullable=False, default="09:00")
    working_hours_end = Column(String, nullable=False, default="17:00")
    buffer_minutes = Column(Integer, nullable=False, default=15)
    max_scheduling_density = Column(Float, nullable=False, default=0.8)
    preferred_focus_slots = Column(JSONColumn, nullable=True)
    no_meeting_days = Column(JSONColumn, nullable=True)
    lunch_break_start = Column(String, nullable=True)
    lunch_break_end = Column(String, nullable=True)
    energy_profile = Column(JSONColumn, nullable=True)
    default_task_duration_minutes = Column(Integer, nullable=False, default=30)
    auto_schedule_enabled = Column(Boolean, nullable=False, default=True)
    deep_work_min_minutes = Column(Integer, nullable=False, default=90)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="scheduling_preferences")


class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"
    __table_args__ = (
        Index("ix_scheduled_tasks_user_status", "user_id", "status"),
        Index("ix_scheduled_tasks_user_due_date", "user_id", "due_date"),
        Index("ix_scheduled_tasks_user_scheduled_start", "user_id", "scheduled_start"),
        {"extend_existing": True},
    )

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(SQLEnum(TaskPriority), nullable=False, default=TaskPriority.MEDIUM)
    status = Column(SQLEnum(TaskStatus), nullable=False, default=TaskStatus.TODO)
    due_date = Column(DateTime(timezone=True), nullable=True)
    estimated_duration_minutes = Column(Integer, nullable=False, default=30)
    actual_duration_minutes = Column(Integer, nullable=True)
    scheduled_start = Column(DateTime(timezone=True), nullable=True)
    scheduled_end = Column(DateTime(timezone=True), nullable=True)
    energy_level = Column(String, nullable=True)
    project = Column(String, nullable=True)
    tags = Column(JSONColumn, nullable=True)
    dependencies = Column(JSONColumn, nullable=True)
    source = Column(String, nullable=False, default="manual")
    external_id = Column(String, nullable=True)
    platform = Column(String, nullable=False, default="local")
    color = Column(String, nullable=True, default="#3182CE")
    task_metadata = Column(JSONColumn, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="scheduled_tasks")


class Habit(Base):
    __tablename__ = "habits"
    __table_args__ = (
        Index("ix_habits_user_active", "user_id", "is_active"),
        {"extend_existing": True},
    )

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    frequency = Column(SQLEnum(RecurrenceFrequency), nullable=False, default=RecurrenceFrequency.DAILY)
    preferred_time = Column(String, nullable=True)
    duration_minutes = Column(Integer, nullable=False, default=30)
    color = Column(String, nullable=True, default="#38A169")
    is_active = Column(Boolean, nullable=False, default=True)
    streak_count = Column(Integer, nullable=False, default=0)
    longest_streak = Column(Integer, nullable=False, default=0)
    last_completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="habits")
    completions = relationship("HabitCompletion", back_populates="habit", cascade="all, delete-orphan",
                               order_by="desc(HabitCompletion.completed_at)")


class HabitCompletion(Base):
    __tablename__ = "habit_completions"
    __table_args__ = (
        Index("ix_habit_completions_habit_date", "habit_id", "completed_at"),
        {"extend_existing": True},
    )

    id = Column(String, primary_key=True, default=_uuid)
    habit_id = Column(String, ForeignKey("habits.id", ondelete="CASCADE"), nullable=False, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    notes = Column(Text, nullable=True)

    habit = relationship("Habit", back_populates="completions")


class TimeBlock(Base):
    __tablename__ = "time_blocks"
    __table_args__ = (
        Index("ix_time_blocks_user_start", "user_id", "start_time"),
        Index("ix_time_blocks_user_type", "user_id", "block_type"),
        {"extend_existing": True},
    )

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    block_type = Column(SQLEnum(BlockType), nullable=False, default=BlockType.FOCUS)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    is_recurring = Column(Boolean, nullable=False, default=False)
    recurrence_rule = Column(JSONColumn, nullable=True)
    color = Column(String, nullable=True, default="#3182CE")
    source = Column(String, nullable=False, default="manual")
    external_id = Column(String, nullable=True)
    task_id = Column(String, ForeignKey("scheduled_tasks.id", ondelete="SET NULL"), nullable=True)
    habit_id = Column(String, ForeignKey("habits.id", ondelete="SET NULL"), nullable=True)
    block_metadata = Column(JSONColumn, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="time_blocks")
    task = relationship("ScheduledTask", backref="time_blocks")
    habit_ref = relationship("Habit", backref="time_blocks")


class CalendarSyncState(Base):
    __tablename__ = "calendar_sync_states"
    __table_args__ = (
        Index("ix_calendar_sync_user_provider", "user_id", "provider", unique=True),
        {"extend_existing": True},
    )

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(SQLEnum(SyncProvider), nullable=False)
    sync_token = Column(String, nullable=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    calendar_id = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    sync_errors = Column(JSONColumn, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="calendar_sync_states")


class ScheduleSnapshot(Base):
    __tablename__ = "schedule_snapshots"
    __table_args__ = {"extend_existing": True}

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot_date = Column(DateTime(timezone=True), nullable=False)
    schedule_data = Column(JSONColumn, nullable=False)
    optimization_score = Column(Float, nullable=True)
    algorithm_version = Column(String, nullable=False, default="v1")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="schedule_snapshots")
