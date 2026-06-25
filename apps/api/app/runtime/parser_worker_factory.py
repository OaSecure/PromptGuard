from app.infrastructure.ocr.paddle_runtime import PaddleOcrRuntimeConfig, compose_paddle_ocr_engine
from app.infrastructure.pdf.pdfium_renderer import (
    InMemoryRenderedImageStore,
    PdfiumRenderer,
    RuntimePdfSourcePort,
)
from app.infrastructure.temp_storage import EncryptedTemporaryFileStorage
from app.infrastructure.temp_storage.parser_adapter import (
    TemporaryStorageContentSource,
    TemporaryStorageParserRepository,
)
from app.parser.adapters.code_text import CodeTextParserAdapter
from app.parser.adapters.image_ocr import ImageOcrAdapter
from app.parser.adapters.native_text import NativeTextAdapter
from app.parser.adapters.pdf_foundation import PdfParserFoundationAdapter
from app.parser.adapters.pdf_native_ocr import PdfNativeOcrAdapter
from app.parser.executor import ParserPlanExecutor
from app.parser.models import ParserAdapterCapability
from app.parser.planning import ParserPlanResolver
from app.parser.registry import InMemoryParserAdapterRegistry, ParserAdapterRegistration
from app.parser.runner import FileParserRunner
from app.parser.temp_file_resolver import TemporaryFileResolver
from app.ports.clock import ClockPort
from app.runtime.ml_inference_queue import MlInferenceQueue
from app.runtime.paddle_worker_client import PaddleOcrSubprocessRuntime
from app.runtime.parser_worker import ParserWorkerPool
from app.runtime.worker_clients import cached_paddle_worker_client


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
    paddle_worker_python_path: str = "/opt/venvs/paddle/bin/python",
    paddle_worker_script_path: str = "/app/scripts/paddle_ocr_worker.py",
    paddle_worker_payload_dir: str = "/tmp/promptguard-paddle-payloads",
    paddle_inference_queue: MlInferenceQueue | None = None,
) -> ParserWorkerPool:
    clock = clock or SystemClock()
    content_source = TemporaryStorageContentSource(storage, clock)
    rendered_images = InMemoryRenderedImageStore()

    def pdf_renderer_factory(source: RuntimePdfSourcePort) -> PdfiumRenderer:
        return PdfiumRenderer(source, rendered_images)

    def image_resolver(handle: str):
        return rendered_images.resolve_for_ocr(handle) if handle.startswith("rendered-image-") else handle
    paddle_runtime = PaddleOcrSubprocessRuntime(
        cached_paddle_worker_client(
            paddle_worker_python_path,
            paddle_worker_script_path,
            paddle_worker_payload_dir,
            60_000,
            max_queue_size,
        ),
        image_resolver=image_resolver,
        inference_queue=paddle_inference_queue,
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
            capability=ParserAdapterCapability(capability_id="pdf-native-v1", step_kinds=("pdf_native_text_extract",)),
            adapter=PdfParserFoundationAdapter(content_source),
        ),
        ParserAdapterRegistration(
            capability=ParserAdapterCapability(capability_id="pdf-native-ocr-v1", step_kinds=("pdf_native_ocr",)),
            adapter=PdfNativeOcrAdapter(
                content_source,
                paddle_engine,
                renderer_factory=pdf_renderer_factory,
            ),
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
