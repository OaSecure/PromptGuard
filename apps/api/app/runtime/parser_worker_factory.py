from app.infrastructure.ocr.paddle_real_adapter import PaddleOcrLazyRuntimeConfig, PaddleOcrLazyRuntimeSkeleton
from app.infrastructure.ocr.paddle_runtime import PaddleOcrRuntimeConfig, compose_paddle_ocr_engine
from app.infrastructure.temp_storage import EncryptedTemporaryFileStorage
from app.infrastructure.temp_storage.parser_adapter import (
    TemporaryStorageContentSource,
    TemporaryStorageParserRepository,
)
from app.parser.adapters.code_text import CodeTextParserAdapter
from app.parser.adapters.image_ocr import ImageOcrAdapter
from app.parser.adapters.native_text import NativeTextAdapter
from app.parser.executor import ParserPlanExecutor
from app.parser.models import ParserAdapterCapability
from app.parser.planning import ParserPlanResolver
from app.parser.registry import InMemoryParserAdapterRegistry, ParserAdapterRegistration
from app.parser.runner import FileParserRunner
from app.parser.temp_file_resolver import TemporaryFileResolver
from app.ports.clock import ClockPort
from app.runtime.parser_worker import ParserWorkerPool


class SystemClock(ClockPort):
    def now(self):
        from datetime import UTC, datetime

        return datetime.now(UTC)


def build_parser_worker_pool(
    storage: EncryptedTemporaryFileStorage,
    *,
    max_workers: int,
    max_queue_size: int,
    clock: ClockPort | None = None,
) -> ParserWorkerPool:
    clock = clock or SystemClock()
    content_source = TemporaryStorageContentSource(storage, clock)
    paddle_runtime = PaddleOcrLazyRuntimeSkeleton(
        PaddleOcrLazyRuntimeConfig(enabled=True),
        image_resolver=lambda handle: handle,
    )
    paddle_engine = compose_paddle_ocr_engine(
        PaddleOcrRuntimeConfig(enabled=True),
        runtime=paddle_runtime,
    )
    registrations = (
        ParserAdapterRegistration(
            capability=ParserAdapterCapability(capability_id="native-text-v1", step_kinds=("native_text_extract",)),
            adapter=NativeTextAdapter(content_source),
        ),
        ParserAdapterRegistration(
            capability=ParserAdapterCapability(capability_id="code-text-v1", step_kinds=("code_parse",)),
            adapter=CodeTextParserAdapter(content_source),
        ),
        ParserAdapterRegistration(
            capability=ParserAdapterCapability(capability_id="image-ocr-v1", step_kinds=("image_ocr", "ocr_fallback")),
            adapter=ImageOcrAdapter(content_source, paddle_engine),
        ),
    )
    runner = FileParserRunner(
        temporary_file_resolver=TemporaryFileResolver(TemporaryStorageParserRepository(storage), clock),
        plan_resolver=ParserPlanResolver(capabilities=tuple(registration.capability for registration in registrations)),
        plan_executor=ParserPlanExecutor(InMemoryParserAdapterRegistry(registrations)),
    )
    return ParserWorkerPool(runner=runner, max_workers=max_workers, max_queue_size=max_queue_size)
