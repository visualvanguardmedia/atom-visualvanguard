import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, AsyncMock

from core.scheduling.dynamic_rescheduler import DynamicRescheduler


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
    return db


@pytest.mark.asyncio
async def test_on_event_created_no_conflicts(mock_db):
    rescheduler = DynamicRescheduler(mock_db)
    event = MagicMock()
    event.id = "e1"
    event.start_time = datetime(2026, 5, 4, 9, tzinfo=timezone.utc)
    event.end_time = datetime(2026, 5, 4, 10, tzinfo=timezone.utc)

    with pytest.MonkeyPatch.context() as m:
        m.setattr(rescheduler._block_svc, "check_conflicts", lambda *a, **kw: [])
        result = await rescheduler.on_event_created("user-1", event)
    assert result["action"] == "none"
    assert result["conflicts"] == 0


@pytest.mark.asyncio
async def test_on_event_cancelled_no_candidates(mock_db):
    rescheduler = DynamicRescheduler(mock_db)
    event = MagicMock()
    event.start_time = datetime(2026, 5, 4, 9, tzinfo=timezone.utc)
    event.end_time = datetime(2026, 5, 4, 10, tzinfo=timezone.utc)

    mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
    result = await rescheduler.on_event_cancelled("user-1", event)
    assert result["action"] == "none"
