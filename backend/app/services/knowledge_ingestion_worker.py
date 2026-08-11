from __future__ import annotations

import asyncio
import logging

from backend.app.db.ai_execution_repository import AiExecutionRecordRepository
from backend.app.services.knowledge_ingestion_service import (
    KnowledgeIngestionFailure,
    KnowledgeIngestionService,
)


logger = logging.getLogger(__name__)


class KnowledgeIngestionWorker:
    def __init__(
        self,
        repository: AiExecutionRecordRepository,
        service: KnowledgeIngestionService,
        *,
        poll_interval_seconds: float,
        lease_seconds: int,
    ) -> None:
        self.repository = repository
        self.service = service
        self.poll_interval_seconds = poll_interval_seconds
        self.lease_seconds = lease_seconds
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._stop.clear()
            self._task = asyncio.create_task(self.run(), name="knowledge-ingestion-worker")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def run(self) -> None:
        while not self._stop.is_set():
            record = self.repository.claim_next(
                operation_type="DOCUMENT_INDEX",
                lease_seconds=self.lease_seconds,
            )
            if record is None:
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval_seconds)
                except asyncio.TimeoutError:
                    continue
                continue
            await self._execute(record)

    async def _execute(self, record: dict) -> None:
        operation_id = record["operation_id"]
        lease_token = record["lease_token"]
        payload = record.get("request")
        if not payload:
            self.repository.fail_leased(
                operation_id,
                lease_token,
                self._error("EXECUTION_PAYLOAD_MISSING", "persisted ingestion payload is missing", False),
            )
            return
        try:
            result = await self._execute_with_heartbeat(
                operation_id,
                lease_token,
                payload,
            )
            if result is None:
                return
            self.repository.complete_leased(operation_id, lease_token, result)
        except KnowledgeIngestionFailure as exc:
            self.repository.fail_leased(
                operation_id,
                lease_token,
                self._error(exc.code, exc.message, exc.retryable),
                status="TIMED_OUT" if exc.timed_out else "FAILED",
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("document ingestion failed", extra={"operation_id": operation_id})
            self.repository.fail_leased(
                operation_id,
                lease_token,
                self._error("INGESTION_INTERNAL_ERROR", "document ingestion failed", True),
            )

    async def _execute_with_heartbeat(
        self,
        operation_id: str,
        lease_token: str,
        payload: dict,
    ) -> dict | None:
        execution = asyncio.create_task(asyncio.to_thread(self.service.execute, payload))
        heartbeat_interval = max(1.0, self.lease_seconds / 3)
        while not execution.done():
            done, _pending = await asyncio.wait({execution}, timeout=heartbeat_interval)
            if done:
                break
            renewed = self.repository.renew_lease(
                operation_id,
                lease_token,
                lease_seconds=self.lease_seconds,
                progress=50,
            )
            if not renewed:
                logger.warning("document ingestion lease was lost", extra={"operation_id": operation_id})
                return None
        return await execution

    @staticmethod
    def _error(code: str, message: str, retryable: bool) -> dict:
        return {"code": code, "message": message, "retryable": retryable, "details": {}}
