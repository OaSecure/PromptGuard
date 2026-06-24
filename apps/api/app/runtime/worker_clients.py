from functools import lru_cache
from pathlib import Path

from app.runtime.paddle_worker_client import PaddleWorkerClient, PaddleWorkerClientConfig
from app.runtime.paddle_worker_payload import PaddleWorkerPayloadStore
from app.runtime.torch_worker_client import TorchWorkerClient, TorchWorkerClientConfig
from app.runtime.torch_worker_payload import TorchWorkerPayloadStore


@lru_cache(maxsize=8)
def cached_torch_worker_client(
    python_path: str,
    script_path: str,
    payload_dir: str,
    timeout_ms: int,
    max_queue_size: int,
) -> TorchWorkerClient:
    return TorchWorkerClient(
        TorchWorkerClientConfig(
            python_path=Path(python_path),
            script_path=Path(script_path),
            timeout_ms=timeout_ms,
            max_queue_size=max_queue_size,
        ),
        payload_store=TorchWorkerPayloadStore(Path(payload_dir)),
    )


@lru_cache(maxsize=8)
def cached_paddle_worker_client(
    python_path: str,
    script_path: str,
    payload_dir: str,
    timeout_ms: int,
    max_queue_size: int,
) -> PaddleWorkerClient:
    return PaddleWorkerClient(
        PaddleWorkerClientConfig(
            python_path=Path(python_path),
            script_path=Path(script_path),
            timeout_ms=timeout_ms,
            max_queue_size=max_queue_size,
        ),
        payload_store=PaddleWorkerPayloadStore(Path(payload_dir)),
    )
