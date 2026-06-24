import subprocess
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from threading import BoundedSemaphore, Lock
from typing import Callable


@dataclass(frozen=True)
class ResidentWorkerSnapshot:
    process_running: bool
    warm: bool
    in_flight_or_queued: int
    requests_total: int
    succeeded_total: int
    timeout_total: int
    failed_total: int
    restart_total: int
    last_failure_code: str | None = None


class ResidentWorkerProcess:
    """Own a long-lived worker subprocess and exchange one JSON line per job."""

    def __init__(
        self,
        command: list[str],
        *,
        env_factory: Callable[[], dict[str, str]],
        timeout_seconds: float,
        max_pending_requests: int = 32,
    ) -> None:
        self._command = command
        self._env_factory = env_factory
        self._timeout_seconds = timeout_seconds
        self._lock = Lock()
        self._stats_lock = Lock()
        self._slots = BoundedSemaphore(max(1, max_pending_requests))
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="resident-worker-rpc")
        self._process: subprocess.Popen[str] | None = None
        self._in_flight_or_queued = 0
        self._requests_total = 0
        self._succeeded_total = 0
        self._timeout_total = 0
        self._failed_total = 0
        self._restart_total = 0
        self._last_failure_code: str | None = None

    def request(self, payload: str) -> str | None:
        if not self._slots.acquire(blocking=False):
            self._record_failed("WORKER_QUEUE_FULL")
            return None
        self._record_submitted()
        try:
            future = self._executor.submit(self._request_locked, payload)
            result = future.result(timeout=self._timeout_seconds)
            if result is None:
                self._record_failed("WORKER_NO_RESPONSE")
            else:
                self._record_succeeded()
            return result
        except TimeoutError:
            self._record_timeout()
            self.restart()
            return None
        except Exception:
            self._record_failed("WORKER_REQUEST_FAILED")
            self.restart()
            return None
        finally:
            self._record_finished()
            self._slots.release()

    def restart(self) -> None:
        with self._lock:
            self._stop_locked()

    def close(self) -> None:
        with self._lock:
            self._stop_locked()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def snapshot(self) -> ResidentWorkerSnapshot:
        with self._stats_lock:
            return ResidentWorkerSnapshot(
                process_running=self._process is not None and self._process.poll() is None,
                warm=self._succeeded_total > 0,
                in_flight_or_queued=self._in_flight_or_queued,
                requests_total=self._requests_total,
                succeeded_total=self._succeeded_total,
                timeout_total=self._timeout_total,
                failed_total=self._failed_total,
                restart_total=self._restart_total,
                last_failure_code=self._last_failure_code,
            )

    def _request_locked(self, payload: str) -> str | None:
        with self._lock:
            process = self._ensure_started_locked()
            if process.stdin is None or process.stdout is None:
                self._stop_locked()
                return None
            try:
                process.stdin.write(payload.rstrip("\n") + "\n")
                process.stdin.flush()
                line = process.stdout.readline()
            except Exception:
                self._stop_locked()
                return None
            if not line:
                self._stop_locked()
                return None
            return line

    def _ensure_started_locked(self) -> subprocess.Popen[str]:
        if self._process is not None and self._process.poll() is None:
            return self._process
        self._process = subprocess.Popen(
            self._command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            env=self._env_factory(),
        )
        return self._process

    def _stop_locked(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        with self._stats_lock:
            self._restart_total += 1
        try:
            if process.stdin is not None:
                process.stdin.close()
        except Exception:
            pass
        try:
            process.terminate()
            process.wait(timeout=1)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def _record_submitted(self) -> None:
        with self._stats_lock:
            self._in_flight_or_queued += 1
            self._requests_total += 1

    def _record_finished(self) -> None:
        with self._stats_lock:
            self._in_flight_or_queued = max(0, self._in_flight_or_queued - 1)

    def _record_succeeded(self) -> None:
        with self._stats_lock:
            self._succeeded_total += 1
            self._last_failure_code = None

    def _record_timeout(self) -> None:
        with self._stats_lock:
            self._timeout_total += 1
            self._last_failure_code = "WORKER_TIMEOUT"

    def _record_failed(self, code: str) -> None:
        with self._stats_lock:
            self._failed_total += 1
            self._last_failure_code = code
