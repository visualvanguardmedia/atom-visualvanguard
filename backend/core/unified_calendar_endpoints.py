from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import uuid
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.auth import get_current_user
from core.database import get_db
from core.schedule_optimizer import ResolutionSlot, schedule_optimizer
from core.scheduling.time_block_service import TimeBlockService
from core.scheduling.dynamic_rescheduler import DynamicRescheduler

router = APIRouter(prefix="/api/v1/calendar", tags=["unified_calendar"])


class Attendee(BaseModel):
    id: str
    name: str
    email: str
    role: str = "required"

class CalendarEvent(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    start: datetime
    end: datetime
    location: Optional[str] = None
    attendees: Optional[List[Attendee]] = []
    status: str = "confirmed"
    platform: str = "local"
    color: Optional[str] = "#3182CE"
    metadata: Optional[Dict[str, Any]] = {}

class CreateEventRequest(BaseModel):
    title: str
    description: Optional[str] = None
    start: datetime
    end: datetime
    location: Optional[str] = None
    status: str = "confirmed"
    platform: str = "local"
    color: Optional[str] = "#3182CE"
    metadata: Optional[Dict[str, Any]] = {}

class UpdateEventRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    location: Optional[str] = None
    status: Optional[str] = None
    platform: Optional[str] = None
    color: Optional[str] = None

class ConflictCheckRequest(BaseModel):
    start: datetime
    end: datetime
    exclude_event_id: Optional[str] = None

class ConflictingEvent(BaseModel):
    id: str
    title: str
    start: datetime
    end: datetime
    platform: str

class ConflictResponse(BaseModel):
    has_conflicts: bool
    conflicts: List[ConflictingEvent] = []
    conflict_count: int = 0
    message: str


@router.get("/events", response_model=Dict[str, Any])
async def get_events(
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = TimeBlockService(db)
    blocks = svc.list_blocks(current_user.id, start=start, end=end)
    events = [svc.to_calendar_event_dict(b) for b in blocks]
    return {"success": True, "events": events}


@router.post("/events", response_model=Dict[str, Any])
async def create_event(
    event_data: CreateEventRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = TimeBlockService(db)
    rescheduler = DynamicRescheduler(db)
    block = svc.create(current_user.id, {
        "title": event_data.title,
        "description": event_data.description,
        "block_type": "meeting",
        "start_time": event_data.start,
        "end_time": event_data.end,
        "source": event_data.platform,
        "color": event_data.color,
        "metadata": {
            "location": event_data.location,
            "status": event_data.status,
            "attendees": [a.dict() for a in (event_data.metadata or {}).get("attendees", [])],
        },
    })
    await rescheduler.on_event_created(current_user.id, block)
    event = svc.to_calendar_event_dict(block)
    return {"success": True, "event": event}


@router.put("/events/{event_id}", response_model=Dict[str, Any])
async def update_event(
    event_id: str,
    updates: UpdateEventRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = TimeBlockService(db)
    rescheduler = DynamicRescheduler(db)

    block = svc.get(event_id, current_user.id)
    if not block:
        raise HTTPException(status_code=404, detail="Event not found")

    old_start = block.start_time
    old_end = block.end_time

    update_data = updates.dict(exclude_unset=True)
    field_map = {"start": "start_time", "end": "end_time"}
    mapped = {}
    for k, v in update_data.items():
        mapped[field_map.get(k, k)] = v
    if "description" in mapped and block.block_metadata:
        meta = (block.block_metadata or {}).copy()
        meta["location"] = mapped.pop("description", None)
        mapped["metadata"] = meta

    block = svc.update(event_id, current_user.id, mapped)
    if not block:
        raise HTTPException(status_code=404, detail="Event not found")

    if updates.start or updates.end:
        await rescheduler.on_event_updated(current_user.id, block, old_start, old_end)

    event = svc.to_calendar_event_dict(block)
    return {"success": True, "event": event}


@router.delete("/events/{event_id}", response_model=Dict[str, Any])
async def delete_event(
    event_id: str,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = TimeBlockService(db)
    rescheduler = DynamicRescheduler(db)

    block = svc.get(event_id, current_user.id)
    if not block:
        raise HTTPException(status_code=404, detail="Event not found")

    await rescheduler.on_event_cancelled(current_user.id, block)
    svc.delete(event_id, current_user.id)
    return {"success": True, "id": event_id}


@router.post("/check-conflicts", response_model=ConflictResponse)
async def check_conflicts(
    request: ConflictCheckRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = TimeBlockService(db)
    conflicts = svc.check_conflicts(
        current_user.id, request.start, request.end,
        exclude_id=request.exclude_event_id,
    )

    conflict_events = [
        ConflictingEvent(
            id=c.id, title=c.title,
            start=c.start_time, end=c.end_time,
            platform=c.source or "local",
        )
        for c in conflicts
    ]

    has_conflicts = len(conflict_events) > 0
    if has_conflicts:
        titles = [c.title for c in conflict_events]
        message = f"Warning: Scheduling conflict detected with {len(conflict_events)} event(s): {', '.join(titles)}"
    else:
        message = "No conflicts found - time slot is available"

    return ConflictResponse(
        has_conflicts=has_conflicts,
        conflicts=conflict_events,
        conflict_count=len(conflict_events),
        message=message,
    )


@router.get("/optimize", response_model=List[Dict[str, Any]])
async def get_schedule_optimization(
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = TimeBlockService(db)
    now = datetime.now()
    blocks = svc.list_blocks(current_user.id, start=now, end=now + timedelta(days=7))

    events_as_dict = [svc.to_calendar_event_dict(b) for b in blocks]
    for e in events_as_dict:
        e["start"] = datetime.fromisoformat(e["start"]) if e.get("start") else now
        e["end"] = datetime.fromisoformat(e["end"]) if e.get("end") else now

    conflicts = await schedule_optimizer.detect_all_conflicts(events_as_dict)

    resolutions = []
    for conflict in conflicts:
        e1 = conflict["event1"]
        e2 = conflict["event2"]
        p1 = conflict["priority1"]
        p2 = conflict["priority2"]

        event_to_move = e2 if p2 <= p1 else e1
        conflict_with = e1 if p2 <= p1 else e2

        slots = await schedule_optimizer.find_resolution_slots(event_to_move, events_as_dict)

        if slots:
            resolutions.append({
                "type": "conflict",
                "event_to_move": event_to_move["title"],
                "event_id": event_to_move["id"],
                "event_priority": min(p1, p2),
                "conflict_with": conflict_with["title"],
                "suggested_slots": [s.dict() for s in slots],
                "reason": f"Rescheduling lower priority event '{event_to_move['title']}' ({min(p1, p2)} pts) to respect higher priority '{conflict_with['title']}' ({max(p1, p2)} pts).",
            })

    return resolutions
