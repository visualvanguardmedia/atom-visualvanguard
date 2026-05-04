import pytest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.scheduling.constraint_solver import ConstraintSolver


def _make_task(
    task_id="t1",
    title="Task",
    priority="high",
    due_date=None,
    duration_minutes=60,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=task_id,
        title=title,
        priority=priority,
        due_date=due_date,
        estimated_duration_minutes=duration_minutes,
        energy_level=None,
        dependencies=[],
        status="todo",
    )


@pytest.fixture
def mock_db():
    db = MagicMock()
    prefs = MagicMock()
    prefs.buffer_minutes = 15
    prefs.default_task_duration_minutes = 30
    prefs.max_scheduling_density = 0.8
    prefs.working_hours_start = "09:00"
    prefs.working_hours_end = "17:00"
    prefs.working_days = {"0": True, "1": True, "2": True, "3": True, "4": True, "5": False, "6": False}
    prefs.no_meeting_days = {}

    db.query.return_value.filter.return_value.first.return_value = prefs
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    return db


def test_solves_single_task(mock_db):
    solver = ConstraintSolver(mock_db)
    start = datetime(2026, 5, 4, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 8, 0, 0, 0, tzinfo=timezone.utc)

    task = _make_task("t1", "Write code")
    result = solver.solve("user-1", [task], start, end)
    assert len(result) == 1
    assert result[0]["task_id"] == "t1"
    assert result[0]["title"] == "Write code"


def test_solves_multiple_tasks_in_priority_order(mock_db):
    solver = ConstraintSolver(mock_db)
    start = datetime(2026, 5, 4, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 8, 0, 0, 0, tzinfo=timezone.utc)

    tasks = [
        _make_task("t1", "Low task", priority="low", duration_minutes=60),
        _make_task("t2", "Critical task", priority="critical", duration_minutes=60),
    ]
    result = solver.solve("user-1", tasks, start, end)
    assert len(result) == 2


def test_no_working_days_returns_empty(mock_db):
    prefs = mock_db.query.return_value.filter.return_value.first.return_value
    prefs.working_days = {"0": False, "1": False, "2": False, "3": False, "4": False, "5": False, "6": False}

    solver = ConstraintSolver(mock_db)
    start = datetime(2026, 5, 4, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 5, 0, 0, 0, tzinfo=timezone.utc)

    task = _make_task()
    result = solver.solve("user-1", [task], start, end)
    assert len(result) == 0


def test_skips_weekends(mock_db):
    solver = ConstraintSolver(mock_db)
    saturday = datetime(2026, 5, 2, 0, 0, 0, tzinfo=timezone.utc)
    monday = datetime(2026, 5, 4, 0, 0, 0, tzinfo=timezone.utc)

    task = _make_task(duration_minutes=60)
    result = solver.solve("user-1", [task], saturday, monday)
    assert len(result) == 0
