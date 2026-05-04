import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from core.models_scheduling import BlockType, CalendarSyncState, SyncProvider, TimeBlock
from core.scheduling.dynamic_rescheduler import DynamicRescheduler
from core.scheduling.time_block_service import TimeBlockService

logger = logging.getLogger(__name__)


class CalendarSyncService:
    def __init__(self, db: Session):
        self.db = db
        self._block_svc = TimeBlockService(db)
        self._rescheduler = DynamicRescheduler(db)

    def get_sync_state(self, user_id: str, provider: str) -> Optional[CalendarSyncState]:
        return (
            self.db.query(CalendarSyncState)
            .filter(
                CalendarSyncState.user_id == user_id,
                CalendarSyncState.provider == provider,
            )
            .first()
        )

    async def sync_from_provider(
        self,
        user_id: str,
        provider: str,
        events: List[Dict[str, Any]],
        sync_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        sync_state = self.get_sync_state(user_id, provider)

        if not sync_state:
            sync_state = CalendarSyncState(
                user_id=user_id,
                provider=provider,
                sync_token=sync_token,
                is_active=True,
            )
            self.db.add(sync_state)
            self.db.flush()

        created, updated, deleted = 0, 0, 0

        for event_data in events:
            external_id = event_data.get("id")
            if not external_id:
                continue

            existing = (
                self.db.query(TimeBlock)
                .filter(
                    TimeBlock.user_id == user_id,
                    TimeBlock.external_id == external_id,
                    TimeBlock.source == provider,
                )
                .first()
            )

            start = self._parse_datetime(event_data.get("start"))
            end = self._parse_datetime(event_data.get("end"))

            if not start or not end:
                continue

            if event_data.get("status") == "cancelled":
                if existing:
                    self.db.delete(existing)
                    deleted += 1
                continue

            if existing:
                old_start = existing.start_time
                old_end = existing.end_time
                existing.title = event_data.get("title", existing.title)
                existing.description = event_data.get("description", existing.description)
                existing.start_time = start
                existing.end_time = end
                existing.block_type = BlockType.EXTERNAL_CALENDAR
                updated += 1
                self.db.flush()
                await self._rescheduler.on_event_updated(user_id, existing, old_start, old_end)
            else:
                block = TimeBlock(
                    user_id=user_id,
                    title=event_data.get("title", "External Event"),
                    description=event_data.get("description"),
                    block_type=BlockType.EXTERNAL_CALENDAR,
                    start_time=start,
                    end_time=end,
                    source=provider,
                    external_id=external_id,
                    color=event_data.get("color"),
                    metadata=event_data.get("metadata", {}),
                )
                self.db.add(block)
                created += 1
                self.db.flush()
                await self._rescheduler.on_event_created(user_id, block)

        sync_state.sync_token = sync_token or sync_state.sync_token
        sync_state.last_synced_at = datetime.now(timezone.utc)
        sync_state.sync_errors = None
        self.db.commit()

        return {"created": created, "updated": updated, "deleted": deleted}

    async def sync_to_provider(
        self,
        user_id: str,
        provider: str,
        since: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        blocks = self._block_svc.list_blocks(
            user_id,
            start=since,
            block_type=BlockType.FOCUS.value,
        )

        events = []
        for block in blocks:
            if block.source == provider:
                continue
            events.append({
                "title": block.title,
                "description": block.description or "",
                "start": block.start_time.isoformat(),
                "end": block.end_time.isoformat(),
                "source": "atom_scheduler",
                "metadata": {
                    "task_id": block.task_id,
                    "block_type": block.block_type.value if block.block_type else None,
                },
            })

        return events

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                return None
        return None
