import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import BoundedSemaphore

from app.parser.models import FileParserResult, ParserWorkerPayload, sanitized_failure
from app.parser.ports import FileParserRunnerPort

logger = logging.getLogger(__name__)


class ParserWorkerPool:
    def __init__(self, runner: FileParserRunnerPort, max_workers: int, max_queue_size: int) -> None:
        if max_workers < 1 or max_queue_size < 1:
            raise ValueError("worker and queue sizes must be positive")
        self._runner = runner
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="parser-worker")
        self._capacity = BoundedSemaphore(max_workers + max_queue_size)

    def execute(self, payload: ParserWorkerPayload, timeout_ms: int) -> FileParserResult:
        if timeout_ms < 1:
            raise ValueError("timeout_ms must be positive")
        if not self._capacity.acquire(blocking=False):
            return self._failure(payload.input_id, "PARSER_LIMIT_EXCEEDED")
        try:
            future = self._executor.submit(self._runner.run, payload)
        except Exception:
            self._capacity.release()
            logger.error("Parser worker submission failed", extra={"failure_code": "PARSER_WORKER_FAILED"})
            return self._failure(payload.input_id, "PARSER_WORKER_FAILED")
        future.add_done_callback(lambda _: self._capacity.release())
        try:
            return future.result(timeout=timeout_ms / 1000)
        except TimeoutError:
            future.cancel()
            return self._failure(payload.input_id, "PARSER_TIMEOUT", status="timeout")
        except Exception:
            logger.error("Parser worker failed", extra={"failure_code": "PARSER_WORKER_FAILED"})
            return self._failure(payload.input_id, "PARSER_WORKER_FAILED")

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=True)

    @staticmethod
    def _failure(input_id: str, code: str, status: str = "failed") -> FileParserResult:
        return FileParserResult(
            input_id=input_id,
            parser_status=status,
            failure=sanitized_failure(code),
        )
