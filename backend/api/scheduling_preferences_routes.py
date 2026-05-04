from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Any, Dict

from core.auth import get_current_user
from core.database import get_db
from core.scheduling.preferences_service import PreferencesService

router = APIRouter(prefix="/api/v1/scheduling/preferences", tags=["scheduling_preferences"])


@router.get("/")
async def get_preferences(
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = PreferencesService(db)
    prefs = svc.get_or_create(current_user.id)
    return {"success": True, "preferences": prefs}


@router.put("/")
async def update_preferences(
    updates: Dict[str, Any],
    current_user: Any = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = PreferencesService(db)
    prefs = svc.update(current_user.id, updates)
    return {"success": True, "preferences": prefs}
