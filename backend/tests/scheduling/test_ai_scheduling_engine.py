import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, AsyncMock, patch
from types import SimpleNamespace

from core.scheduling.ai_scheduling_engine import AISchedulingEngine


@pytest.fixture
def mock_prefs():
    prefs = SimpleNamespace(
        buffer_minutes=15,
        default_task_duration_minutes=30,
        max_scheduling_density=0.8,
        working_hours_start="09:00",
        working_hours_end="17:00",
        working_days={"0": True, "1": True, "2": True, "3": True, "4": True, "5": False, "6": False},
        no_meeting_days={},
    )
    return prefs


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock(side_effect=lambda obj: obj)
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
    db.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []
    return db


@pytest.mark.asyncio
async def test_auto_schedule_no_unscheduled(mock_db):
    engine = AISchedulingEngine(mock_db)
    result = await engine.auto_schedule("user-1", use_ai=False)
    assert result["scheduled"] == []
    assert "No unscheduled tasks found" in result["message"]


@pytest.mark.asyncio
async def test_suggest_optimizations_empty_schedule(mock_db, mock_prefs):
    engine = AISchedulingEngine(mock_db)

    with patch.object(engine._prefs, "get_or_create", return_value=mock_prefs):
        with patch.object(engine._block_svc, "get_events_for_range", return_value=[]):
            with patch.object(engine._task_svc, "get_scheduled_for_range", return_value=[]):
                with patch.object(engine._task_svc, "get_unscheduled", return_value=[]):
                    result = await engine.suggest_optimizations("user-1")

    assert "suggestions" in result
    assert "density" in result
