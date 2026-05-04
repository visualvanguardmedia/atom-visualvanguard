import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from core.scheduling.scheduled_task_service import ScheduledTaskService


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock(side_effect=lambda obj: obj)
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.offset.return_value.all.return_value = []
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
    return db


def test_create_task(mock_db):
    svc = ScheduledTaskService(mock_db)
    task = svc.create("user-1", {"title": "Test Task", "priority": "high"})
    assert task.user_id == "user-1"
    assert task.title == "Test Task"
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()


def test_get_task_not_found(mock_db):
    svc = ScheduledTaskService(mock_db)
    result = svc.get("nonexistent", "user-1")
    assert result is None


def test_list_tasks_returns_all(mock_db):
    mock_db.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [
        MagicMock(title="Task 1"), MagicMock(title="Task 2")
    ]
    svc = ScheduledTaskService(mock_db)
    tasks = svc.list_tasks("user-1")
    assert len(tasks) == 2


def test_delete_task_not_found(mock_db):
    svc = ScheduledTaskService(mock_db)
    result = svc.delete("nonexistent", "user-1")
    assert result is False


def test_delete_task_success(mock_db):
    task = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = task
    svc = ScheduledTaskService(mock_db)
    result = svc.delete("task-1", "user-1")
    assert result is True
    mock_db.delete.assert_called_once_with(task)


def test_complete_task(mock_db):
    task = MagicMock()
    task.status = "todo"
    mock_db.query.return_value.filter.return_value.first.return_value = task
    svc = ScheduledTaskService(mock_db)
    result = svc.complete("task-1", "user-1", actual_minutes=45)
    assert result is task
    mock_db.commit.assert_called()


def test_import_external_creates_new(mock_db):
    mock_db.query.return_value.filter.return_value.first.return_value = None
    svc = ScheduledTaskService(mock_db)
    imported = svc.import_external("user-1", [
        {"title": "Asana Task", "external_id": "ext-1"},
    ], "asana")
    assert len(imported) == 1
    mock_db.commit.assert_called()


def test_import_external_updates_existing(mock_db):
    existing = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = existing
    svc = ScheduledTaskService(mock_db)
    imported = svc.import_external("user-1", [
        {"title": "Updated Task", "external_id": "ext-1"},
    ], "asana")
    assert len(imported) == 1
