import pytest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from core.scheduling.priority_scorer import PriorityScorer


def _make_task(
    priority="medium",
    due_date=None,
    duration_minutes=30,
    energy_level=None,
    dependencies=None,
) -> SimpleNamespace:
    return SimpleNamespace(
        priority=priority,
        due_date=due_date,
        estimated_duration_minutes=duration_minutes,
        energy_level=energy_level,
        dependencies=dependencies or [],
        title="Test",
    )


def test_overdue_task_scores_highest():
    scorer = PriorityScorer()
    now = datetime.now(timezone.utc)
    overdue = _make_task(due_date=now - timedelta(hours=1))
    future = _make_task(due_date=now + timedelta(days=7))
    assert scorer.score(overdue, now) > scorer.score(future, now)


def test_critical_priority_scores_higher():
    scorer = PriorityScorer()
    critical = _make_task(priority="critical")
    low = _make_task(priority="low")
    assert scorer._importance_score(critical) > scorer._importance_score(low)


def test_short_tasks_score_higher():
    scorer = PriorityScorer()
    short = _make_task(duration_minutes=15)
    long = _make_task(duration_minutes=180)
    assert scorer._effort_score(short) > scorer._effort_score(long)


def test_score_many_sorts_descending():
    scorer = PriorityScorer()
    now = datetime.now(timezone.utc)
    tasks = [
        _make_task(priority="low", due_date=now + timedelta(days=7)),
        _make_task(priority="critical", due_date=now + timedelta(hours=1)),
        _make_task(priority="high", due_date=now + timedelta(days=1)),
    ]
    scored = scorer.score_many(tasks, now)
    assert scored[0]["score"] >= scored[1]["score"] >= scored[2]["score"]
    assert scored[0]["task"].priority == "critical"


def test_no_due_date_scores_low():
    scorer = PriorityScorer()
    no_due = _make_task()
    due = _make_task(due_date=datetime.now(timezone.utc) + timedelta(hours=2))
    assert scorer._deadline_score(due, datetime.now(timezone.utc)) > scorer._deadline_score(no_due, datetime.now(timezone.utc))


def test_dependency_score_increases_with_count():
    scorer = PriorityScorer()
    no_deps = _make_task(dependencies=[])
    many_deps = _make_task(dependencies=["d1", "d2", "d3", "d4"])
    assert scorer._dependency_score(many_deps) > scorer._dependency_score(no_deps)
