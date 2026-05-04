import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from core.models_scheduling import (
    ScheduledTask, ScheduleSnapshot, TaskStatus, TimeBlock,
)
from core.scheduling.constraint_solver import ConstraintSolver
from core.scheduling.preferences_service import PreferencesService
from core.scheduling.priority_scorer import PriorityScorer
from core.scheduling.scheduled_task_service import ScheduledTaskService
from core.scheduling.time_block_service import TimeBlockService

logger = logging.getLogger(__name__)


class AISchedulingEngine:
    def __init__(self, db: Session):
        self.db = db
        self._solver = ConstraintSolver(db)
        self._prefs = PreferencesService(db)
        self._scorer = PriorityScorer()
        self._task_svc = ScheduledTaskService(db)
        self._block_svc = TimeBlockService(db)

    async def auto_schedule(
        self,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        use_ai: bool = True,
    ) -> Dict[str, Any]:
        if not start_date:
            start_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        if not end_date:
            end_date = start_date + timedelta(days=7)

        unscheduled = self._task_svc.get_unscheduled(user_id, limit=50)
        if not unscheduled:
            return {"scheduled": [], "message": "No unscheduled tasks found"}

        assignments = self._solver.solve(
            user_id=user_id,
            tasks=unscheduled,
            start_date=start_date,
            end_date=end_date,
        )

        if use_ai and assignments:
            try:
                assignments = await self._ai_refine(user_id, assignments, start_date, end_date)
            except Exception as e:
                logger.warning(f"AI refinement failed, using deterministic results: {e}")

        persisted = self._persist_assignments(user_id, assignments)

        await self._save_snapshot(user_id, start_date, persisted)

        return {
            "scheduled": persisted,
            "total_tasks": len(unscheduled),
            "scheduled_count": len(persisted),
            "unscheduled_count": len(unscheduled) - len(persisted),
        }

    async def reschedule_around_conflict(
        self,
        user_id: str,
        conflict_start: datetime,
        conflict_end: datetime,
    ) -> Dict[str, Any]:
        affected_tasks = (
            self.db.query(ScheduledTask)
            .filter(
                ScheduledTask.user_id == user_id,
                ScheduledTask.status.in_([TaskStatus.TODO, TaskStatus.SCHEDULED]),
                ScheduledTask.scheduled_start < conflict_end,
                ScheduledTask.scheduled_end > conflict_start,
            )
            .all()
        )

        if not affected_tasks:
            return {"rescheduled": [], "message": "No tasks affected by conflict"}

        for task in affected_tasks:
            task.scheduled_start = None
            task.scheduled_end = None
            task.status = TaskStatus.TODO
        self.db.commit()

        start_date = conflict_start.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + timedelta(days=7)

        assignments = self._solver.solve(
            user_id=user_id,
            tasks=affected_tasks,
            start_date=start_date,
            end_date=end_date,
        )

        persisted = self._persist_assignments(user_id, assignments)

        return {
            "rescheduled": persisted,
            "affected_count": len(affected_tasks),
            "rescheduled_count": len(persisted),
        }

    async def suggest_optimizations(self, user_id: str) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7)

        blocks = self._block_svc.get_events_for_range(user_id, start, end)
        tasks = self._task_svc.get_scheduled_for_range(user_id, start, end)

        suggestions = []

        total_scheduled_hours = sum(
            (t.scheduled_end - t.scheduled_start).total_seconds() / 3600
            for t in tasks
            if t.scheduled_start and t.scheduled_end
        )

        prefs = self._prefs.get_or_create(user_id)
        density = total_scheduled_hours / (int(prefs.working_hours_end.split(":")[0]) - int(prefs.working_hours_start.split(":")[0])) / 5

        if density > prefs.max_scheduling_density:
            suggestions.append({
                "type": "overloaded",
                "message": f"Schedule density is {density:.0%}, exceeding your {prefs.max_scheduling_density:.0%} threshold",
                "action": "Consider deferring low-priority tasks",
            })

        back_to_back = 0
        for i in range(len(blocks) - 1):
            gap = (blocks[i + 1].start_time - blocks[i].end_time).total_seconds() / 60
            if gap < prefs.buffer_minutes:
                back_to_back += 1
        if back_to_back > 2:
            suggestions.append({
                "type": "buffer",
                "message": f"{back_to_back} back-to-back meetings detected",
                "action": "Add buffer time between meetings",
            })

        unscheduled = self._task_svc.get_unscheduled(user_id)
        overdue = [
            t for t in unscheduled
            if t.due_date and t.due_date < now
        ]
        if overdue:
            suggestions.append({
                "type": "overdue",
                "message": f"{len(overdue)} overdue tasks need scheduling",
                "action": "Prioritize and schedule these immediately",
            })

        try:
            ai_suggestions = await self._ai_suggest(user_id, density, len(overdue), back_to_back)
            suggestions.extend(ai_suggestions)
        except Exception as e:
            logger.debug(f"AI suggestion generation skipped: {e}")

        return {"suggestions": suggestions, "density": density, "total_scheduled_hours": total_scheduled_hours}

    async def _ai_refine(
        self,
        user_id: str,
        assignments: List[Dict[str, Any]],
        start_date: datetime,
        end_date: datetime,
    ) -> List[Dict[str, Any]]:
        try:
            from core.llm_service import LLMService
            llm = LLMService(db=self.db)
        except ImportError:
            return assignments

        prompt = json.dumps({
            "assignments": assignments,
            "user_id": user_id,
            "date_range": [start_date.isoformat(), end_date.isoformat()],
        })

        system = (
            "You are a scheduling optimization AI. Review the task assignments and suggest "
            "improvements for energy alignment, focus time protection, and deadline safety. "
            "Return a JSON array of refined assignments with the same structure. "
            "Only include tasks where you want to change the scheduled times."
        )

        try:
            response = await llm.generate(
                prompt=prompt,
                system_instruction=system,
                model="deepseek-chat",
                temperature=0.3,
                max_tokens=2000,
            )
            if response and response.strip():
                refined = json.loads(response)
                if isinstance(refined, list) and len(refined) > 0:
                    refined_map = {r.get("task_id"): r for r in refined if "task_id" in r}
                    for i, a in enumerate(assignments):
                        if a["task_id"] in refined_map:
                            r = refined_map[a["task_id"]]
                            if "scheduled_start" in r:
                                assignments[i]["scheduled_start"] = r["scheduled_start"]
                            if "scheduled_end" in r:
                                assignments[i]["scheduled_end"] = r["scheduled_end"]
            return assignments
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"AI refinement parse error: {e}")
            return assignments

    async def _ai_suggest(
        self,
        user_id: str,
        density: float,
        overdue_count: int,
        back_to_back: int,
    ) -> List[Dict[str, Any]]:
        try:
            from core.llm_service import LLMService
            llm = LLMService(db=self.db)
        except ImportError:
            return []

        prompt = json.dumps({
            "density": density,
            "overdue_count": overdue_count,
            "back_to_back_meetings": back_to_back,
        })

        system = (
            "You are a productivity coach AI. Based on the schedule metrics, "
            "suggest 1-2 actionable optimizations. Return a JSON array of objects "
            'with "type", "message", and "action" fields.'
        )

        try:
            response = await llm.generate(
                prompt=prompt,
                system_instruction=system,
                model="deepseek-chat",
                temperature=0.4,
                max_tokens=500,
            )
            if response and response.strip():
                result = json.loads(response)
                if isinstance(result, list):
                    return result
        except Exception:
            pass
        return []

    def _persist_assignments(
        self, user_id: str, assignments: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        persisted = []
        for a in assignments:
            task = self.db.query(ScheduledTask).filter(
                ScheduledTask.id == a["task_id"],
                ScheduledTask.user_id == user_id,
            ).first()
            if not task:
                continue

            task.scheduled_start = datetime.fromisoformat(a["scheduled_start"])
            task.scheduled_end = datetime.fromisoformat(a["scheduled_end"])
            task.status = TaskStatus.SCHEDULED

            existing_block = (
                self.db.query(TimeBlock)
                .filter(TimeBlock.task_id == task.id)
                .first()
            )
            if existing_block:
                existing_block.start_time = task.scheduled_start
                existing_block.end_time = task.scheduled_end
                existing_block.title = task.title
            else:
                block = TimeBlock(
                    user_id=user_id,
                    title=task.title,
                    description=task.description,
                    block_type="focus",
                    start_time=task.scheduled_start,
                    end_time=task.scheduled_end,
                    source="auto_schedule",
                    task_id=task.id,
                    color=task.color or "#3182CE",
                )
                self.db.add(block)

            persisted.append(a)

        self.db.commit()
        return persisted

    async def _save_snapshot(
        self,
        user_id: str,
        date: datetime,
        assignments: List[Dict[str, Any]],
    ) -> None:
        scored = self._scorer.score_many(
            self._task_svc.get_scheduled_for_range(
                user_id,
                date,
                date + timedelta(days=7),
            )
        )
        optimization_score = sum(s["score"] for s in scored) / max(len(scored), 1)

        snapshot = ScheduleSnapshot(
            user_id=user_id,
            snapshot_date=date,
            schedule_data=assignments,
            optimization_score=optimization_score,
            algorithm_version="v1",
        )
        self.db.add(snapshot)
        self.db.commit()
