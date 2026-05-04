import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from core.scheduling.time_block_service import TimeBlockService


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock(side_effect=lambda obj: obj)
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []
    return db


def test_create_block(mock_db):
    svc = TimeBlockService(mock_db)
    block = svc.create("user-1", {
        "title": "Focus Time",
        "block_type": "focus",
        "start_time": datetime(2026, 5, 4, 9, tzinfo=timezone.utc),
        "end_time": datetime(2026, 5, 4, 10, tzinfo=timezone.utc),
    })
    assert block.user_id == "user-1"
    assert block.title == "Focus Time"
    mock_db.add.assert_called_once()


def test_check_conflicts_no_overlap(mock_db):
    mock_db.query.return_value.filter.return_value.all.return_value = []
    svc = TimeBlockService(mock_db)
    conflicts = svc.check_conflicts(
        "user-1",
        datetime(2026, 5, 4, 9, tzinfo=timezone.utc),
        datetime(2026, 5, 4, 10, tzinfo=timezone.utc),
    )
    assert len(conflicts) == 0


def test_check_conflicts_with_overlap(mock_db):
    existing = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = [existing]
    svc = TimeBlockService(mock_db)
    conflicts = svc.check_conflicts(
        "user-1",
        datetime(2026, 5, 4, 9, tzinfo=timezone.utc),
        datetime(2026, 5, 4, 10, tzinfo=timezone.utc),
    )
    assert len(conflicts) == 1


def test_check_conflicts_excludes_self(mock_db):
    mock_db.query.return_value.filter.return_value.all.return_value = []
    svc = TimeBlockService(mock_db)
    conflicts = svc.check_conflicts(
        "user-1",
        datetime(2026, 5, 4, 9, tzinfo=timezone.utc),
        datetime(2026, 5, 4, 10, tzinfo=timezone.utc),
        exclude_id="block-1",
    )
    assert len(conflicts) == 0


def test_to_calendar_event_dict():
    block = MagicMock()
    block.id = "b1"
    block.title = "Meeting"
    block.description = "Team sync"
    block.start_time = datetime(2026, 5, 4, 9, tzinfo=timezone.utc)
    block.end_time = datetime(2026, 5, 4, 10, tzinfo=timezone.utc)
    block.source = "google"
    block.color = "#4285F4"
    block.block_type.value = "meeting"
    block.task_id = None
    block.habit_id = None
    block.metadata = {}

    svc = TimeBlockService(MagicMock())
    result = svc.to_calendar_event_dict(block)
    assert result["id"] == "b1"
    assert result["title"] == "Meeting"
    assert result["platform"] == "google"
    assert result["color"] == "#4285F4"
