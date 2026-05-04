import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from core.scheduling.habit_service import HabitService


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock(side_effect=lambda obj: obj)
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []
    return db


def test_create_habit(mock_db):
    svc = HabitService(mock_db)
    habit = svc.create("user-1", {"name": "Exercise", "duration_minutes": 30})
    assert habit.user_id == "user-1"
    assert habit.name == "Exercise"
    mock_db.add.assert_called_once()


def test_get_habit_not_found(mock_db):
    svc = HabitService(mock_db)
    result = svc.get("nonexistent", "user-1")
    assert result is None


def test_complete_habit_increments_streak(mock_db):
    habit = MagicMock()
    habit.streak_count = 5
    habit.longest_streak = 7
    habit.last_completed_at = datetime(2026, 5, 3, tzinfo=timezone.utc)
    mock_db.query.return_value.filter.return_value.first.return_value = habit

    svc = HabitService(mock_db)
    result = svc.complete("habit-1", "user-1")
    assert result.streak_count == 6
    assert result.longest_streak == 7
    mock_db.commit.assert_called()


def test_complete_habit_updates_longest_streak(mock_db):
    habit = MagicMock()
    habit.streak_count = 9
    habit.longest_streak = 9
    habit.last_completed_at = datetime(2026, 5, 3, tzinfo=timezone.utc)
    mock_db.query.return_value.filter.return_value.first.return_value = habit

    svc = HabitService(mock_db)
    result = svc.complete("habit-1", "user-1")
    assert result.streak_count == 10
    assert result.longest_streak == 10


def test_delete_habit(mock_db):
    habit = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = habit
    svc = HabitService(mock_db)
    result = svc.delete("habit-1", "user-1")
    assert result is True
    mock_db.delete.assert_called_once()
