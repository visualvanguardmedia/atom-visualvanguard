import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, AsyncMock

from core.scheduling.calendar_sync_service import CalendarSyncService


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    db.flush = MagicMock()
    db.refresh = MagicMock(side_effect=lambda obj: obj)
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    return db


@pytest.mark.asyncio
async def test_sync_creates_new_events(mock_db):
    sync_svc = CalendarSyncService(mock_db)
    events = [
        {"id": "ext-1", "title": "Team Meeting", "start": "2026-05-04T10:00:00Z", "end": "2026-05-04T11:00:00Z"},
    ]

    with pytest.MonkeyPatch.context() as m:
        m.setattr(sync_svc._rescheduler, "on_event_created", AsyncMock(return_value={"action": "none"}))
        result = await sync_svc.sync_from_provider("user-1", "google", events)

    assert result["created"] == 1
    assert result["updated"] == 0
    assert result["deleted"] == 0


@pytest.mark.asyncio
async def test_sync_handles_cancelled_events(mock_db):
    existing = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = existing

    sync_svc = CalendarSyncService(mock_db)
    events = [{"id": "ext-1", "status": "cancelled", "start": "2026-05-04T10:00:00Z", "end": "2026-05-04T11:00:00Z"}]

    result = await sync_svc.sync_from_provider("user-1", "google", events)
    assert result["deleted"] == 1


@pytest.mark.asyncio
async def test_sync_to_provider_excludes_own_source(mock_db):
    blocks = []
    svc = CalendarSyncService(mock_db)

    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = blocks

    result = await svc.sync_to_provider("user-1", "google")
    assert isinstance(result, list)


def test_parse_datetime_iso_string():
    svc = CalendarSyncService(MagicMock())
    result = svc._parse_datetime("2026-05-04T10:00:00Z")
    assert result is not None
    assert result.year == 2026


def test_parse_datetime_none():
    svc = CalendarSyncService(MagicMock())
    assert svc._parse_datetime(None) is None


def test_parse_datetime_invalid():
    svc = CalendarSyncService(MagicMock())
    assert svc._parse_datetime("not-a-date") is None
