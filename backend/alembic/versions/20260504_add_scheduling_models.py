"""Add scheduling models for AI calendar assistant

Revision ID: 20260504_scheduling_models
Revises: 20260425_add_template_component_tables
Create Date: 2026-05-04

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20260504_scheduling_models"
down_revision: Union[str, Sequence[str], None] = "20260425_add_template_component_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scheduling_preferences",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("timezone", sa.String(), nullable=False, server_default="UTC"),
        sa.Column("working_days", sa.JSON(), nullable=False),
        sa.Column("working_hours_start", sa.String(), nullable=False, server_default="09:00"),
        sa.Column("working_hours_end", sa.String(), nullable=False, server_default="17:00"),
        sa.Column("buffer_minutes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("max_scheduling_density", sa.Float(), nullable=False, server_default="0.8"),
        sa.Column("preferred_focus_slots", sa.JSON(), nullable=True),
        sa.Column("no_meeting_days", sa.JSON(), nullable=True),
        sa.Column("lunch_break_start", sa.String(), nullable=True),
        sa.Column("lunch_break_end", sa.String(), nullable=True),
        sa.Column("energy_profile", sa.JSON(), nullable=True),
        sa.Column("default_task_duration_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("auto_schedule_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("deep_work_min_minutes", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_scheduling_preferences_user_id", "scheduling_preferences", ["user_id"], unique=True)

    op.create_table(
        "scheduled_tasks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("priority", sa.String(), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(), nullable=False, server_default="todo"),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("estimated_duration_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("actual_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("scheduled_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("energy_level", sa.String(), nullable=True),
        sa.Column("project", sa.String(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("dependencies", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(), nullable=False, server_default="manual"),
        sa.Column("external_id", sa.String(), nullable=True),
        sa.Column("platform", sa.String(), nullable=False, server_default="local"),
        sa.Column("color", sa.String(), nullable=True, server_default="#3182CE"),
        sa.Column("task_metadata", sa.JSON(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_scheduled_tasks_user_id", "scheduled_tasks", ["user_id"])
    op.create_index("ix_scheduled_tasks_user_status", "scheduled_tasks", ["user_id", "status"])
    op.create_index("ix_scheduled_tasks_user_due_date", "scheduled_tasks", ["user_id", "due_date"])
    op.create_index("ix_scheduled_tasks_user_scheduled_start", "scheduled_tasks", ["user_id", "scheduled_start"])

    op.create_table(
        "habits",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("frequency", sa.String(), nullable=False, server_default="daily"),
        sa.Column("preferred_time", sa.String(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("color", sa.String(), nullable=True, server_default="#38A169"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("streak_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("longest_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_habits_user_id", "habits", ["user_id"])
    op.create_index("ix_habits_user_active", "habits", ["user_id", "is_active"])

    op.create_table(
        "habit_completions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("habit_id", sa.String(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["habit_id"], ["habits.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_habit_completions_habit_id", "habit_completions", ["habit_id"])
    op.create_index("ix_habit_completions_habit_date", "habit_completions", ["habit_id", "completed_at"])

    op.create_table(
        "time_blocks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("block_type", sa.String(), nullable=False, server_default="focus"),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_recurring", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("recurrence_rule", sa.JSON(), nullable=True),
        sa.Column("color", sa.String(), nullable=True, server_default="#3182CE"),
        sa.Column("source", sa.String(), nullable=False, server_default="manual"),
        sa.Column("external_id", sa.String(), nullable=True),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("habit_id", sa.String(), nullable=True),
        sa.Column("block_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["scheduled_tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["habit_id"], ["habits.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_time_blocks_user_id", "time_blocks", ["user_id"])
    op.create_index("ix_time_blocks_user_start", "time_blocks", ["user_id", "start_time"])
    op.create_index("ix_time_blocks_user_type", "time_blocks", ["user_id", "block_type"])

    op.create_table(
        "calendar_sync_states",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("sync_token", sa.String(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("calendar_id", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("sync_errors", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_calendar_sync_user_provider", "calendar_sync_states", ["user_id", "provider"], unique=True)

    op.create_table(
        "schedule_snapshots",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("snapshot_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schedule_data", sa.JSON(), nullable=False),
        sa.Column("optimization_score", sa.Float(), nullable=True),
        sa.Column("algorithm_version", sa.String(), nullable=False, server_default="v1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_schedule_snapshots_user_id", "schedule_snapshots", ["user_id"])


def downgrade() -> None:
    op.drop_table("schedule_snapshots")
    op.drop_table("calendar_sync_states")
    op.drop_table("time_blocks")
    op.drop_table("habit_completions")
    op.drop_table("habits")
    op.drop_table("scheduled_tasks")
    op.drop_table("scheduling_preferences")
