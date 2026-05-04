import asyncio
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional
import uuid
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.auth import get_current_user
from core.database import get_db
from core.scheduling.scheduled_task_service import ScheduledTaskService

backend_root = Path(__file__).parent.parent.resolve()
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

logger = logging.getLogger(__name__)

try:
    from integrations.asana_service import asana_service
    ASANA_AVAILABLE = True
    logger.info("Asana service loaded successfully")
except ImportError as e:
    ASANA_AVAILABLE = False
    asana_service = None
    logger.warning(f"Asana service not available: {e}")

router = APIRouter(prefix="/api/v1/tasks", tags=["unified_tasks"])
project_router = APIRouter(prefix="/api/v1/projects", tags=["unified_projects"])

ASANA_ACCESS_TOKEN = "2/1211551477617044/1211959900544452:04904fb3621a011e810dc1c21ef41890"
ASANA_WORKSPACE_GID = "1211551477617056"
ASANA_DEFAULT_PROJECT_GID = "1211551443885526"


class Task(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    dueDate: datetime
    priority: str
    status: str
    project: Optional[str] = None
    tags: Optional[List[str]] = []
    assignee: Optional[str] = None
    estimatedHours: Optional[float] = 0
    actualHours: Optional[float] = 0
    dependencies: Optional[List[str]] = []
    platform: str = "local"
    color: Optional[str] = "#3182CE"
    createdAt: datetime
    updatedAt: datetime
    metadata: Optional[Dict[str, Any]] = {}

class CreateTaskRequest(BaseModel):
    title: str
    description: Optional[str] = None
    dueDate: datetime
    priority: str = "medium"
    status: str = "todo"
    project: Optional[str] = None
    tags: Optional[List[str]] = []
    assignee: Optional[str] = None
    estimatedHours: Optional[float] = 0
    platform: str = "local"
    color: Optional[str] = "#3182CE"

class UpdateTaskRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    dueDate: Optional[datetime] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    project: Optional[str] = None
    tags: Optional[List[str]] = None
    assignee: Optional[str] = None
    estimatedHours: Optional[float] = None
    actualHours: Optional[float] = None
    platform: Optional[str] = None
    color: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class Project(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    color: str = "#3182CE"
    progress: float = 0
    task_count: int = 0

class CreateProjectRequest(BaseModel):
    name: str
    description: Optional[str] = None
    color: str = "#3182CE"

class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None


MOCK_PROJECTS: List[Project] = [
    Project(id="project-1", name="Web Application", description="Main web application development", color="#3182CE", progress=33, task_count=2),
    Project(id="project-2", name="Documentation", description="Project documentation and guides", color="#38A169", progress=0, task_count=0),
]


def _db_task_to_response(task_model) -> Task:
    return Task(
        id=task_model.id,
        title=task_model.title,
        description=task_model.description,
        dueDate=task_model.due_date or datetime.now(timezone.utc),
        priority=task_model.priority.value if hasattr(task_model.priority, "value") else (task_model.priority or "medium"),
        status=task_model.status.value if hasattr(task_model.status, "value") else (task_model.status or "todo"),
        project=task_model.project,
        tags=task_model.tags or [],
        assignee=None,
        estimatedHours=(task_model.estimated_duration_minutes or 0) / 60,
        actualHours=(task_model.actual_duration_minutes or 0) / 60 if task_model.actual_duration_minutes else 0,
        dependencies=task_model.dependencies or [],
        platform=task_model.platform,
        color=task_model.color or "#3182CE",
        createdAt=task_model.created_at or datetime.now(timezone.utc),
        updatedAt=task_model.updated_at or datetime.now(timezone.utc),
        metadata=task_model.task_metadata or {},
    )


@router.get("/")
async def get_tasks(
    platform: str = Query("all"),
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = ScheduledTaskService(db)
    db_tasks = svc.list_tasks(current_user.id, limit=200)
    local_tasks = [_db_task_to_response(t) for t in db_tasks]

    if ASANA_AVAILABLE and platform in ["asana", "all"]:
        try:
            result = await asyncio.to_thread(
                asana_service._make_request,
                "GET",
                f"/projects/{ASANA_DEFAULT_PROJECT_GID}/tasks?opt_fields=name,notes,completed,due_on,assignee,tags,created_at,modified_at",
                ASANA_ACCESS_TOKEN,
            )
            if result and result.get("data"):
                asana_tasks = []
                for at in result.get("data", []):
                    status = "completed" if at.get("completed") else "in-progress"
                    due_date = datetime.now()
                    if at.get("due_on"):
                        try:
                            due_date = datetime.fromisoformat(at["due_on"] + "T00:00:00")
                        except (ValueError, TypeError):
                            pass
                    created_at = datetime.now()
                    if at.get("created_at"):
                        try:
                            created_str = at["created_at"].replace("Z", "+00:00")
                            created_at = datetime.fromisoformat(created_str)
                        except (ValueError, TypeError):
                            pass
                    asana_tasks.append(Task(
                        id=at.get("gid"), title=at.get("name"),
                        description=at.get("notes", ""), dueDate=due_date,
                        priority="medium", status=status,
                        project=ASANA_DEFAULT_PROJECT_GID,
                        tags=[tag.get("name") for tag in at.get("tags", [])],
                        estimatedHours=0, actualHours=0, dependencies=[],
                        platform="asana", color="#3182CE",
                        createdAt=created_at, updatedAt=created_at,
                    ))
                all_tasks = asana_tasks + local_tasks if platform == "all" else asana_tasks
                return {"success": True, "tasks": all_tasks, "source": "asana+db"}
        except Exception as e:
            logger.error(f"Error fetching Asana tasks: {e}")

    return {"success": True, "tasks": local_tasks, "source": "db"}


@router.post("/", response_model=Dict[str, Any])
async def create_task(
    task_data: CreateTaskRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    logger.info(f"CREATE_TASK called - Platform: {task_data.platform}")

    if task_data.platform == "asana" and ASANA_AVAILABLE:
        try:
            due_date_str = task_data.dueDate.strftime("%Y-%m-%d") if isinstance(task_data.dueDate, datetime) else task_data.dueDate.split("T")[0]
            asana_task_data = {
                "name": task_data.title,
                "description": task_data.description or "",
                "due_on": due_date_str,
                "projects": [ASANA_DEFAULT_PROJECT_GID],
                "workspace": ASANA_WORKSPACE_GID,
            }
            result = await asana_service.create_task(ASANA_ACCESS_TOKEN, asana_task_data)
            if result.get("ok"):
                at = result.get("task")
                created_at = datetime.now()
                if at.get("created_at"):
                    try:
                        created_str = at["created_at"].replace("Z", "+00:00")
                        created_at = datetime.fromisoformat(created_str)
                    except (ValueError, TypeError):
                        pass
                svc = ScheduledTaskService(db)
                db_task = svc.create(current_user.id, {
                    "title": at.get("name"),
                    "description": at.get("notes", ""),
                    "due_date": datetime.fromisoformat(at.get("due_on") + "T00:00:00") if at.get("due_on") else None,
                    "priority": task_data.priority,
                    "platform": "asana",
                    "external_id": at.get("gid"),
                    "source": "import",
                    "estimated_duration_minutes": int((task_data.estimatedHours or 0) * 60),
                    "color": task_data.color,
                })
                created_task = _db_task_to_response(db_task)
                logger.info(f"Created Asana task: {created_task.id}")
                return {"success": True, "task": created_task, "platform": "asana"}
        except Exception as e:
            logger.error(f"Error creating Asana task: {e}")

    svc = ScheduledTaskService(db)
    db_task = svc.create(current_user.id, {
        "title": task_data.title,
        "description": task_data.description,
        "due_date": task_data.dueDate,
        "priority": task_data.priority,
        "platform": task_data.platform,
        "project": task_data.project,
        "tags": task_data.tags,
        "estimated_duration_minutes": int((task_data.estimatedHours or 0) * 60),
        "color": task_data.color,
    })

    if task_data.project:
        for p in MOCK_PROJECTS:
            if p.id == task_data.project:
                p.task_count += 1
                break

    try:
        from core.behavior_analyzer import get_behavior_analyzer
        analyzer = get_behavior_analyzer()
        analyzer.log_user_action(
            user_id=current_user.id,
            action_type="task_created",
            metadata={"task_id": db_task.id, "platform": db_task.platform},
        )
    except Exception:
        pass

    created_task = _db_task_to_response(db_task)
    return {"success": True, "task": created_task, "platform": "local"}


@router.put("/{task_id}", response_model=Dict[str, Any])
async def update_task(
    task_id: str,
    updates: UpdateTaskRequest,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = ScheduledTaskService(db)
    update_data = updates.dict(exclude_unset=True)
    mapped = {}
    field_map = {"dueDate": "due_date", "estimatedHours": "estimated_duration_minutes", "actualHours": "actual_duration_minutes"}
    for k, v in update_data.items():
        mapped_key = field_map.get(k, k)
        if mapped_key == "estimated_duration_minutes" and v is not None:
            v = int(v * 60)
        if mapped_key == "actual_duration_minutes" and v is not None:
            v = int(v * 60)
        mapped[mapped_key] = v

    db_task = svc.update(task_id, current_user.id, mapped)
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")

    try:
        if db_task.task_metadata and "workflow_id" in (db_task.task_metadata or {}):
            from core.workflow_analytics_engine import get_analytics_engine
            analytics = get_analytics_engine()
            analytics.track_manual_override(
                workflow_id=db_task.task_metadata.get("workflow_id"),
                execution_id=db_task.task_metadata.get("execution_id", "manual"),
                resource_id=task_id,
                action="task_updated",
                user_id=current_user.id,
                metadata={"updates": update_data},
            )
    except Exception:
        pass

    return {"success": True, "task": _db_task_to_response(db_task)}


@router.delete("/{task_id}", response_model=Dict[str, Any])
async def delete_task(
    task_id: str,
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = ScheduledTaskService(db)
    db_task = svc.get(task_id, current_user.id)
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")

    try:
        if db_task.task_metadata and "workflow_id" in (db_task.task_metadata or {}):
            from core.workflow_analytics_engine import get_analytics_engine
            analytics = get_analytics_engine()
            analytics.track_manual_override(
                workflow_id=db_task.task_metadata.get("workflow_id"),
                execution_id=db_task.task_metadata.get("execution_id", "manual"),
                resource_id=task_id,
                action="task_deleted",
            )
    except Exception:
        pass

    project_id = db_task.project
    svc.delete(task_id, current_user.id)

    if project_id:
        for p in MOCK_PROJECTS:
            if p.id == project_id:
                p.task_count = max(0, p.task_count - 1)
                break

    return {"success": True, "id": task_id}


@project_router.get("/", response_model=Dict[str, Any])
async def get_projects(
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = ScheduledTaskService(db)
    for p in MOCK_PROJECTS:
        tasks = svc.list_tasks(current_user.id, project=p.id, limit=1000)
        p.task_count = len(tasks)
        if p.task_count > 0:
            from core.models_scheduling import TaskStatus
            completed = len([t for t in tasks if t.status == TaskStatus.COMPLETED])
            p.progress = int((completed / p.task_count) * 100)
        else:
            p.progress = 0
    return {"success": True, "projects": MOCK_PROJECTS}


@project_router.post("/", response_model=Dict[str, Any])
async def create_project(project_data: CreateProjectRequest):
    new_project = Project(
        id=str(uuid.uuid4()),
        **project_data.dict(),
        progress=0,
        task_count=0,
    )
    MOCK_PROJECTS.append(new_project)
    return {"success": True, "project": new_project}


@project_router.put("/{project_id}", response_model=Dict[str, Any])
async def update_project(project_id: str, updates: UpdateProjectRequest):
    for i, project in enumerate(MOCK_PROJECTS):
        if project.id == project_id:
            update_data = updates.dict(exclude_unset=True)
            updated_project = project.copy(update=update_data)
            MOCK_PROJECTS[i] = updated_project
            return {"success": True, "project": updated_project}
    raise HTTPException(status_code=404, detail="Project not found")
