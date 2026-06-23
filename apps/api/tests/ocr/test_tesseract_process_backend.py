import subprocess
from copy import deepcopy

from app.infrastructure.ocr.process_backend import SubprocessOcrProcessBackend
from app.infrastructure.ocr.process_port import ProcessBoundaryRequest, ProcessLifecycleState


class FakeProcess:
    def __init__(
        self,
        *,
        stdout: bytes = b"safe tsv",
        stderr: bytes = b"PRIVATE_STDERR",
        returncode: int = 0,
        timeout: bool = False,
    ) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.timeout = timeout
        self.killed = False
        self.inputs: list[bytes] = []

    def communicate(self, input=None, timeout=None):
        if input is not None:
            self.inputs.append(input)
        if self.timeout and not self.killed:
            raise subprocess.TimeoutExpired("PRIVATE_COMMAND", timeout)
        return self.stdout, self.stderr

    def kill(self) -> None:
        self.killed = True


class FakeFactory:
    def __init__(self, process: FakeProcess | None = None, error: Exception | None = None) -> None:
        self.process = process or FakeProcess()
        self.error = error
        self.calls: list[tuple[tuple[str, ...], dict]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append((tuple(argv), kwargs))
        if self.error is not None:
            raise self.error
        return self.process


def _request(**updates: object) -> ProcessBoundaryRequest:
    values = {
        "image_handle": "/PRIVATE_TEMP_PATH/input.png",
        "argv": ("/verified/tesseract", "stdin", "stdout", "--psm", "6", "tsv"),
        "environment": (("LANG", "C.UTF-8"),),
        "timeout_ms": 500,
        "max_input_bytes": 100,
        "max_output_bytes": 100,
    }
    values.update(updates)
    return ProcessBoundaryRequest(**values)  # type: ignore[arg-type]


def test_backend_uses_argv_without_shell_and_returns_only_stdout():
    process = FakeProcess()
    factory = FakeFactory(process)
    backend = SubprocessOcrProcessBackend(
        process_factory=factory,
        input_reader=lambda _: b"image-bytes",
    )

    request = _request()
    original = deepcopy(request)
    result = backend.execute(request)

    assert result.state is ProcessLifecycleState.EXITED
    assert result.exit_code == 0
    assert result.stdout == "safe tsv"
    assert result.stderr == ""
    assert result.input_bytes == len(b"image-bytes")
    assert process.inputs == [b"image-bytes"]
    assert factory.calls[0][0] == request.argv
    assert factory.calls[0][1]["shell"] is False
    assert factory.calls[0][1]["env"] == {"LANG": "C.UTF-8"}
    assert request == original


def test_backend_fails_closed_before_spawn_when_input_exceeds_limit():
    factory = FakeFactory()
    result = SubprocessOcrProcessBackend(
        process_factory=factory,
        input_reader=lambda _: b"x" * 101,
    ).execute(_request())

    assert result.state is ProcessLifecycleState.SPAWN_FAILED
    assert result.stdout == ""
    assert result.stderr == ""
    assert factory.calls == []


def test_backend_timeout_kills_process_and_discards_all_output():
    process = FakeProcess(stdout=b"PRIVATE_STDOUT", timeout=True)
    result = SubprocessOcrProcessBackend(
        process_factory=FakeFactory(process),
        input_reader=lambda _: b"image",
    ).execute(_request())

    assert result.state is ProcessLifecycleState.TIMED_OUT
    assert result.stdout == ""
    assert result.stderr == ""
    assert process.killed is True


def test_backend_sanitizes_spawn_decode_and_output_limit_failures():
    cases = (
        SubprocessOcrProcessBackend(
            process_factory=FakeFactory(error=RuntimeError("PRIVATE_RAW_EXCEPTION")),
            input_reader=lambda _: b"image",
        ),
        SubprocessOcrProcessBackend(
            process_factory=FakeFactory(FakeProcess(stdout=b"\xff")),
            input_reader=lambda _: b"image",
        ),
        SubprocessOcrProcessBackend(
            process_factory=FakeFactory(FakeProcess(stdout=b"x" * 101)),
            input_reader=lambda _: b"image",
        ),
    )
    for backend in cases:
        result = backend.execute(_request())
        assert result.state is ProcessLifecycleState.SPAWN_FAILED
        assert result.stdout == ""
        assert result.stderr == ""
        assert "PRIVATE" not in repr(result)
