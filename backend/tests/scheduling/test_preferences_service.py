import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from core.scheduling.preferences_service import PreferencesService


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.add = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock(side_effect=lambda obj: obj)
    return db


def test_get_or_create_creates_defaults(mock_db):
    svc = PreferencesService(mock_db)
    prefs = svc.get_or_create("user-1")
    assert prefs is not None
    assert prefs.user_id == "user-1"
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()


def test_get_or_create_returns_existing(mock_db):
    existing = MagicMock()
    existing.user_id = "user-1"
    mock_db.query.return_value.filter.return_value.first.return_value = existing

    svc = PreferencesService(mock_db)
    prefs = svc.get_or_create("user-1")
    assert prefs.user_id == "user-1"
    mock_db.add.assert_not_called()


def test_update_changes_allowed_fields(mock_db):
    existing = MagicMock()
    existing.user_id = "user-1"
    mock_db.query.return_value.filter.return_value.first.return_value = existing

    svc = PreferencesService(mock_db)
    updated = svc.update("user-1", {"timezone": "America/New_York", "buffer_minutes": 30})
    assert updated is existing
    mock_db.commit.assert_called()


def test_update_ignores_disallowed_fields(mock_db):
    existing = MagicMock()
    existing.user_id = "user-1"
    mock_db.query.return_value.filter.return_value.first.return_value = existing

    svc = PreferencesService(mock_db)
    updated = svc.update("user-1", {"id": "hacked", "timezone": "UTC"})
    assert updated is existing


def test_is_working_day_default_weekday(mock_db):
    prefs = MagicMock()
    prefs.working_days = {"0": True, "1": True, "2": True, "3": True, "4": True, "5": False, "6": False}
    mock_db.query.return_value.filter.return_value.first.return_value = prefs

    svc = PreferencesService(mock_db)
    monday = datetime(2026, 5, 4, tzinfo=timezone.utc)
    assert svc.is_working_day("user-1", monday) is True

    saturday = datetime(2026, 5, 9, tzinfo=timezone.utc)
    assert svc.is_working_day("user-1", saturday) is False


def test_is_no_meeting_day(mock_db):
    prefs = MagicMock()
    prefs.no_meeting_days = {"0": True}
    mock_db.query.return_value.filter.return_value.first.return_value = prefs

    svc = PreferencesService(mock_db)
    monday = datetime(2026, 5, 4, tzinfo=timezone.utc)
    assert svc.is_no_meeting_day("user-1", monday) is True

    tuesday = datetime(2026, 5, 5, tzinfo=timezone.utc)
    assert svc.is_no_meeting_day("user-1", tuesday) is False
