from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.auth import get_current_user
from core.database import get_db
from core.scheduling.ai_scheduling_engine import AISchedulingEngine
from core.scheduling.calendar_sync_service import CalendarSyncService
from core.scheduling.time_block_service import TimeBlockService

router = APIRouter(prefix="/api/v1/scheduling", tags=["scheduling"])


class AutoScheduleRequest(BaseModel):
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    use_ai: bool = True


class RescheduleRequest(BaseModel):
    conflict_start: datetime
    conflict_end: datetime


class SyncRequest(BaseModel):
    provider: str
    events: list = []
    sync_token: Optional[str] = None


@router.get("/schedule")
async def get_schedule(
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    block_svc = TimeBlockService(db)
    blocks = block_svc.list_blocks(current_user.id, start=start, end=end)
    events = [block_svc.to_calendar_event_dict(b) for b in blocks]
    return {"success": True, "events": events, "count": len(events)}


@router.post("/auto-schedule")
async def auto_schedule(
    request: AutoScheduleRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    engine = AISchedulingEngine(db)
    result = await engine.auto_schedule(
        current_user.id,
        start_date=request.start_date,
        end_date=request.end_date,
        use_ai=request.use_ai,
    )
    return {"success": True, **result}


@router.post("/reschedule")
async def reschedule(
    request: RescheduleRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    engine = AISchedulingEngine(db)
    result = await engine.reschedule_around_conflict(
        current_user.id, request.conflict_start, request.conflict_end,
    )
    return {"success": True, **result}


@router.get("/suggestions")
async def get_suggestions(
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    engine = AISchedulingEngine(db)
    result = await engine.suggest_optimizations(current_user.id)
    return {"success": True, **result}


@router.post("/sync")
async def sync_calendar(
    request: SyncRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sync_svc = CalendarSyncService(db)
    result = await sync_svc.sync_from_provider(
        current_user.id,
        request.provider,
        request.events,
        sync_token=request.sync_token,
    )
    return {"success": True, **result}
