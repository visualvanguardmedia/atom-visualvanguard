from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.auth import get_current_user
from core.database import get_db
from core.scheduling.habit_service import HabitService

router = APIRouter(prefix="/api/v1/scheduling/habits", tags=["habits"])


class CreateHabitRequest(BaseModel):
    name: str
    description: Optional[str] = None
    frequency: str = "daily"
    preferred_time: Optional[str] = None
    duration_minutes: int = 30
    color: Optional[str] = "#38A169"


class UpdateHabitRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    frequency: Optional[str] = None
    preferred_time: Optional[str] = None
    duration_minutes: Optional[int] = None
    color: Optional[str] = None
    is_active: Optional[bool] = None


class CompleteHabitRequest(BaseModel):
    notes: Optional[str] = None


@router.get("/")
async def list_habits(
    active_only: bool = True,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = HabitService(db)
    habits = svc.list_habits(current_user.id, active_only=active_only, limit=limit, offset=offset)
    return {"success": True, "habits": habits, "count": len(habits)}


@router.post("/")
async def create_habit(
    data: CreateHabitRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = HabitService(db)
    habit = svc.create(current_user.id, data.dict())
    return {"success": True, "habit": habit}


@router.get("/{habit_id}")
async def get_habit(
    habit_id: str,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = HabitService(db)
    habit = svc.get(habit_id, current_user.id)
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")
    return {"success": True, "habit": habit}


@router.put("/{habit_id}")
async def update_habit(
    habit_id: str,
    updates: UpdateHabitRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = HabitService(db)
    habit = svc.update(habit_id, current_user.id, updates.dict(exclude_unset=True))
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")
    return {"success": True, "habit": habit}


@router.delete("/{habit_id}")
async def delete_habit(
    habit_id: str,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = HabitService(db)
    if not svc.delete(habit_id, current_user.id):
        raise HTTPException(status_code=404, detail="Habit not found")
    return {"success": True, "id": habit_id}


@router.post("/{habit_id}/complete")
async def complete_habit(
    habit_id: str,
    body: CompleteHabitRequest = None,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = HabitService(db)
    notes = body.notes if body else None
    habit = svc.complete(habit_id, current_user.id, notes)
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")
    return {"success": True, "habit": habit, "streak": habit.streak_count}


@router.get("/{habit_id}/completions")
async def get_completions(
    habit_id: str,
    days: int = Query(30, ge=1, le=365),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = HabitService(db)
    completions = svc.get_completions(habit_id, current_user.id, days=days)
    return {"success": True, "completions": completions, "count": len(completions)}
