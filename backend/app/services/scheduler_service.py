"""APScheduler integration.

Managed jobs (configured via `settings` category `scheduler`):
  - pipeline: enabled + interval_hours/cron_expression
  - wallet_snapshot: enabled + interval_minutes
  - settlement_sync: enabled + interval_minutes
  - order_execution_poll: open orders / fills
  - reconcile_stale_drafts: fail stuck drafts and release reserved funds
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.triggers.cron import CronTrigger
    HAS_APSCHEDULER = True
except ImportError:
    HAS_APSCHEDULER = False
    logger.warning("APScheduler not installed — scheduler disabled")


class SchedulerService:
    def __init__(self):
        self._scheduler = None
        self._reconcile_older_than_sec = 60
        if HAS_APSCHEDULER:
            self._scheduler = AsyncIOScheduler()

    async def start(self) -> None:
        if self._scheduler is None:
            return

        # Load and apply scheduler config
        try:
            from app.database import async_session_factory
            from app.services.settings_service import settings_service

            async with async_session_factory() as db:
                sched_cfg = await settings_service.get_by_category(db, "scheduler")
                cfg: dict = {row.key: row.value for row in sched_cfg}
            await self.apply_config(
                enabled=self._as_bool(cfg.get("enabled"), default=False),
                interval_hours=cfg.get("interval_hours"),
                cron_expression=cfg.get("cron_expression"),
                wallet_snapshot_enabled=self._as_bool(cfg.get("wallet_snapshot_enabled"), default=True),
                wallet_snapshot_interval_minutes=cfg.get("wallet_snapshot_interval_minutes"),
                settlement_sync_enabled=self._as_bool(cfg.get("settlement_sync_enabled"), default=True),
                settlement_sync_interval_minutes=cfg.get("settlement_sync_interval_minutes"),
                order_poll_enabled=self._as_bool(cfg.get("order_poll_enabled"), default=True),
                order_poll_interval_seconds=cfg.get("order_poll_interval_seconds"),
                reconcile_stale_drafts_enabled=self._as_bool(cfg.get("reconcile_stale_drafts_enabled"), default=True),
                reconcile_interval_seconds=cfg.get("reconcile_interval_seconds"),
                reconcile_older_than_sec=cfg.get("reconcile_older_than_sec"),
            )
        except Exception as exc:
            logger.warning("Scheduler startup: could not load pipeline config: %s", exc)

        self._scheduler.start()
        logger.info("APScheduler started")

    async def stop(self) -> None:
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def _add_pipeline_job(
        self,
        interval_hours: float | None,
        cron_expression: str | None,
    ) -> None:
        if self._scheduler is None:
            return
        cron_s = (str(cron_expression).strip() if cron_expression else "") or None
        if cron_s:
            trigger = CronTrigger.from_crontab(cron_s)
        elif interval_hours and float(interval_hours) > 0:
            trigger = IntervalTrigger(hours=float(interval_hours))
        else:
            return
        self._scheduler.add_job(
            self._run_pipeline,
            trigger=trigger,
            id="pipeline_main",
            replace_existing=True,
        )
        logger.info("Pipeline job scheduled: interval_hours=%s cron=%s", interval_hours, cron_s)

    def _add_wallet_snapshot_job(self, interval_minutes: float | None) -> None:
        if self._scheduler is None:
            return
        minutes = float(interval_minutes) if interval_minutes and float(interval_minutes) > 0 else 5.0
        self._scheduler.add_job(
            self._run_wallet_snapshot,
            trigger=IntervalTrigger(minutes=minutes),
            id="wallet_snapshot",
            replace_existing=True,
        )
        logger.info("Wallet snapshot job scheduled: every %s minutes", minutes)

    def _add_settlement_sync_job(self, interval_minutes: float | None) -> None:
        if self._scheduler is None:
            return
        minutes = float(interval_minutes) if interval_minutes and float(interval_minutes) > 0 else 30.0
        self._scheduler.add_job(
            self._run_settlement_sync_wrapper,
            trigger=IntervalTrigger(minutes=minutes),
            id="settlement_sync",
            replace_existing=True,
        )
        logger.info("Settlement sync job scheduled: every %s minutes", minutes)

    def _add_order_poll_job(self, interval_seconds: float | None) -> None:
        if self._scheduler is None:
            return
        sec = float(interval_seconds) if interval_seconds and float(interval_seconds) > 0 else 15.0
        self._scheduler.add_job(
            self._run_order_poll,
            trigger=IntervalTrigger(seconds=sec),
            id="order_execution_poll",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        logger.info("Order poll job scheduled: every %s seconds", sec)

    def _add_reconcile_job(self, interval_seconds: float | None) -> None:
        if self._scheduler is None:
            return
        sec = float(interval_seconds) if interval_seconds and float(interval_seconds) > 0 else 60.0
        self._scheduler.add_job(
            self._run_reconcile_stale_drafts,
            trigger=IntervalTrigger(seconds=sec),
            id="reconcile_stale_drafts",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        logger.info("Stale draft reconcile job scheduled: every %s seconds", sec)

    @staticmethod
    def _as_bool(value: object, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            s = value.strip().lower()
            if s in {"true", "1", "yes", "on"}:
                return True
            if s in {"false", "0", "no", "off"}:
                return False
        if value is None:
            return default
        return bool(value)

    def _as_int(self, value: object, default: int) -> int:
        if value is None:
            return default
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default

    async def apply_config(
        self,
        enabled: bool,
        interval_hours: float | None,
        cron_expression: str | None,
        wallet_snapshot_enabled: bool = True,
        wallet_snapshot_interval_minutes: float | None = 5.0,
        settlement_sync_enabled: bool = True,
        settlement_sync_interval_minutes: float | None = 30.0,
        order_poll_enabled: bool = True,
        order_poll_interval_seconds: float | None = 15.0,
        reconcile_stale_drafts_enabled: bool = True,
        reconcile_interval_seconds: float | None = 60.0,
        reconcile_older_than_sec: int | float | None = 60.0,
    ) -> None:
        if self._scheduler is None:
            return
        self._reconcile_older_than_sec = self._as_int(reconcile_older_than_sec, 60)
        try:
            self._scheduler.remove_job("pipeline_main")
        except Exception:
            pass
        try:
            self._scheduler.remove_job("wallet_snapshot")
        except Exception:
            pass
        try:
            self._scheduler.remove_job("settlement_sync")
        except Exception:
            pass
        try:
            self._scheduler.remove_job("order_execution_poll")
        except Exception:
            pass
        try:
            self._scheduler.remove_job("reconcile_stale_drafts")
        except Exception:
            pass
        if enabled:
            self._add_pipeline_job(interval_hours, cron_expression)
        if wallet_snapshot_enabled:
            self._add_wallet_snapshot_job(wallet_snapshot_interval_minutes)
        if settlement_sync_enabled:
            self._add_settlement_sync_job(settlement_sync_interval_minutes)
        if order_poll_enabled:
            self._add_order_poll_job(order_poll_interval_seconds)
        if reconcile_stale_drafts_enabled:
            self._add_reconcile_job(reconcile_interval_seconds)

    async def _run_wallet_snapshot(self) -> None:
        from app.database import async_session_factory
        from app.services.settings_service import settings_service
        from app.services.wallet_service import wallet_service

        try:
            async with async_session_factory() as db:
                cfg = await settings_service.get_all_as_dict(db)
            await wallet_service.save_snapshot(cfg)
        except Exception as exc:
            logger.exception("Wallet snapshot failed: %s", exc)

    async def _run_order_poll(self) -> None:
        from app.services.order_execution_service import order_execution_service

        try:
            r = await order_execution_service.poll_open_orders()
            if r.get("polled", 0):
                logger.debug("order poll: %s", r)
        except Exception as exc:
            logger.exception("Order poll failed: %s", exc)

    async def _run_reconcile_stale_drafts(self) -> None:
        from app.services.order_execution_service import order_execution_service

        try:
            r = await order_execution_service.reconcile_stale_drafts(
                older_than_sec=self._reconcile_older_than_sec
            )
            if r.get("reconciled_failed", 0):
                logger.info("reconcile stale drafts: %s", r)
        except Exception as exc:
            logger.exception("Reconcile stale drafts failed: %s", exc)

    async def _run_settlement_sync_wrapper(self) -> None:
        from app.database import async_session_factory
        from app.services.bet_settlement_service import bet_settlement_service
        from app.services.settings_service import settings_service

        try:
            async with async_session_factory() as db:
                cfg = await settings_service.get_all_as_dict(db)
            await bet_settlement_service.sync_unresolved(config=cfg)
        except Exception as exc:
            logger.exception("Settlement sync failed: %s", exc)

    async def _run_pipeline(self) -> None:
        from app.database import async_session_factory
        from app.services.pipeline_service import pipeline_service
        async with async_session_factory() as db:
            run_id = await pipeline_service.start_run(db, trigger="scheduled")
        if run_id:
            await pipeline_service.execute_full_pipeline(run_id=run_id)

    async def get_status(self) -> dict:
        if self._scheduler is None:
            return {"running": False, "jobs": []}
        jobs = []
        for job in self._scheduler.get_jobs():
            next_run = job.next_run_time
            jobs.append({
                "id": job.id,
                "next_run": next_run.isoformat() if next_run else None,
            })
        return {"running": self._scheduler.running, "jobs": jobs}


scheduler_service = SchedulerService()
