from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import Analysis
from app.models.bet import Bet
from app.models.decision import Decision
from app.models.pipeline_run import PipelineRun
from app.database import async_session_factory


class PipelineService:
    async def start_run(
        self,
        db: AsyncSession,
        trigger: str = "manual",
        top_n: int | None = None,
    ) -> uuid.UUID | None:
        """Create a PipelineRun row. Returns None if another run is already active."""
        # Run locking: reject if a run is already pending or running
        active = await db.scalar(
            select(func.count()).select_from(PipelineRun).where(
                PipelineRun.status.in_(["pending", "running"])
            )
        )
        if active and active > 0:
            return None

        run = PipelineRun(
            id=uuid.uuid4(),
            status="pending",
            trigger=trigger,
            current_stage="pending",
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run.id

    async def execute_full_pipeline(self, run_id: uuid.UUID) -> None:
        """Run the full LangGraph pipeline for a given run_id."""
        async with async_session_factory() as db:
            from app.services.settings_service import settings_service
            config_dict = await settings_service.get_all_as_dict(db)
            prompts_dict = await settings_service.get_all_prompts_as_dict(db)

            result = await db.execute(select(PipelineRun).where(PipelineRun.id == run_id))
            run = result.scalar_one_or_none()
            if run is None:
                return
            if run.status == "cancelled":
                if run.finished_at is None:
                    run.finished_at = datetime.now(timezone.utc)
                await db.commit()
                return
            run.status = "running"
            run.current_stage = "screener"
            run.config_snapshot = config_dict
            await db.commit()

        top_n = int(config_dict.get("ranker", {}).get("top_n", 3))
        initial_state = {
            "pipeline_run_id": str(run_id),
            "config": config_dict,
            "prompts": prompts_dict,
            "top_n": top_n,
            "screened_markets": [],
            "ranked_markets": [],
            "analyses": [],
            "errors": [],
        }

        from app.graph.builder import get_pipeline_graph
        from app.graph.pipeline_persistence import PipelineCancelled

        error_msg = None
        try:
            await get_pipeline_graph().ainvoke(initial_state)
        except PipelineCancelled:
            pass
        except Exception as exc:
            error_msg = str(exc)

        async with async_session_factory() as db:
            result = await db.execute(select(PipelineRun).where(PipelineRun.id == run_id))
            run = result.scalar_one_or_none()
            if run:
                n_analyses = await db.scalar(
                    select(func.count()).select_from(Analysis).where(Analysis.pipeline_run_id == run_id)
                )
                n_decisions = await db.scalar(
                    select(func.count()).select_from(Decision).where(Decision.pipeline_run_id == run_id)
                )
                n_bets = await db.scalar(
                    select(func.count()).select_from(Bet).where(Bet.pipeline_run_id == run_id)
                )
                run.markets_analyzed = int(n_analyses or 0)
                run.decisions_count = int(n_decisions or 0)
                run.bets_placed = int(n_bets or 0)

                if run.status == "cancelled":
                    run.finished_at = datetime.now(timezone.utc)
                    run.current_stage = "cancelled"
                elif error_msg:
                    run.status = "failed"
                    run.current_stage = "failed"
                    run.finished_at = datetime.now(timezone.utc)
                    run.error_message = error_msg
                else:
                    run.status = "completed"
                    run.current_stage = "completed"
                    run.finished_at = datetime.now(timezone.utc)
                    run.error_message = None

                await db.commit()


pipeline_service = PipelineService()
