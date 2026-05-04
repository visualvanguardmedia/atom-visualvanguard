from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.auth import get_current_user
from core.database import get_db
from core.scheduling.scheduled_task_service import ScheduledTaskService

router = APIRouter(prefix="/api/v1/scheduling/tasks", tags=["scheduled_tasks"])


class CreateScheduledTaskRequest(BaseModel):
    title: str
    description: Optional[str] = None
    priority: str = "medium"
    due_date: Optional[datetime] = None
    estimated_duration_minutes: int = 30
    energy_level: Optional[str] = None
    project: Optional[str] = None
    tags: Optional[List[str]] = None
    dependencies: Optional[List[str]] = None
    platform: str = "local"
    color: Optional[str] = "#3182CE"
    external_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class UpdateScheduledTaskRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[datetime] = None
    estimated_duration_minutes: Optional[int] = None
    energy_level: Optional[str] = None
    project: Optional[str] = None
    tags: Optional[List[str]] = None
    dependencies: Optional[List[str]] = None
    actual_duration_minutes: Optional[int] = None
    color: Optional[str] = None


class CompleteTaskRequest(BaseModel):
    actual_duration_minutes: Optional[int] = None


@router.get("/")
async def list_tasks(
    status: Optional[str] = None,
    project: Optional[str] = None,
    source: Optional[str] = None,
    due_before: Optional[datetime] = None,
    due_after: Optional[datetime] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = ScheduledTaskService(db)
    tasks = svc.list_tasks(
        current_user.id, status=status, project=project, source=source,
        due_before=due_before, due_after=due_after, limit=limit, offset=offset,
    )
    return {"success": True, "tasks": tasks, "count": len(tasks)}


@router.post("/")
async def create_task(
    data: CreateScheduledTaskRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = ScheduledTaskService(db)
    task = svc.create(current_user.id, data.dict())
    return {"success": True, "task": task}


@router.get("/{task_id}")
async def get_task(
    task_id: str,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = ScheduledTaskService(db)
    task = svc.get(task_id, current_user.id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "task": task}


@router.put("/{task_id}")
async def update_task(
    task_id: str,
    updates: UpdateScheduledTaskRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = ScheduledTaskService(db)
    task = svc.update(task_id, current_user.id, updates.dict(exclude_unset=True))
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "task": task}


@router.delete("/{task_id}")
async def delete_task(
    task_id: str,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = ScheduledTaskService(db)
    if not svc.delete(task_id, current_user.id):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "id": task_id}


@router.post("/{task_id}/complete")
async def complete_task(
    task_id: str,
    body: CompleteTaskRequest = None,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = ScheduledTaskService(db)
    actual = body.actual_duration_minutes if body else None
    task = svc.complete(task_id, current_user.id, actual)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "task": task}


@router.post("/import")
async def import_tasks(
    tasks: List[Dict[str, Any]],
    platform: str = Query("asana"),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = ScheduledTaskService(db)
    imported = svc.import_external(current_user.id, tasks, platform)
    return {"success": True, "imported": imported, "count": len(imported)}
