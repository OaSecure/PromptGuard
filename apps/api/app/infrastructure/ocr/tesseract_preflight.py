from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import Protocol

from app.domain.types.parser import OcrOptions

from .failures import TesseractFailureReason


class TesseractArtifactVerifierPort(Protocol):
    def path_exists(self, path: str) -> bool: ...

    def checksum_matches(self, path: str, expected_sha256: str) -> bool: ...


@dataclass(frozen=True)
class TesseractPreflightConfig:
    binary_path: str
    binary_sha256: str
    tessdata_directory: str
    traineddata_sha256: dict[str, str]
    language_allowlist: frozenset[str]
    production_package_pin_verified: bool
    native_dependency_pins_verified: bool
    platform: str
    platform_binary_verified: bool
    max_timeout_ms: int
    max_input_bytes: int
    max_output_bytes: int
    page_segmentation_mode: int = 6
    allowed_page_segmentation_modes: frozenset[int] = frozenset({3, 6})


def validate_preflight(
    config: TesseractPreflightConfig,
    options: OcrOptions,
    verifier: TesseractArtifactVerifierPort,
) -> TesseractFailureReason | None:
    policy_failure = _validate_policy(config, options)
    if policy_failure is not None:
        return policy_failure
    return _validate_artifacts(config, options.languages, verifier)


def _validate_policy(
    config: TesseractPreflightConfig,
    options: OcrOptions,
) -> TesseractFailureReason | None:
    checks = (
        _validate_paths(config),
        _validate_platform(config),
        _validate_pins(config),
        _validate_bounds(config, options),
        _validate_languages(config, options.languages),
        _validate_page_segmentation_mode(config),
    )
    return next((failure for failure in checks if failure is not None), None)


def _validate_paths(config: TesseractPreflightConfig) -> TesseractFailureReason | None:
    if not _is_explicit_absolute_path(config.binary_path) or not _is_explicit_absolute_path(config.tessdata_directory):
        return TesseractFailureReason.INVALID_PATH
    return None


def _validate_platform(config: TesseractPreflightConfig) -> TesseractFailureReason | None:
    if config.platform.lower() == "windows" and not config.platform_binary_verified:
        return TesseractFailureReason.UNVERIFIED_WINDOWS_BINARY
    return None


def _validate_pins(config: TesseractPreflightConfig) -> TesseractFailureReason | None:
    if not config.production_package_pin_verified or not config.native_dependency_pins_verified:
        return TesseractFailureReason.NATIVE_PIN_MISMATCH
    return None


def _validate_bounds(
    config: TesseractPreflightConfig,
    options: OcrOptions,
) -> TesseractFailureReason | None:
    if min(config.max_timeout_ms, config.max_input_bytes, config.max_output_bytes) <= 0:
        return TesseractFailureReason.INVALID_PATH
    if options.timeout_ms > config.max_timeout_ms:
        return TesseractFailureReason.TIMEOUT
    return None


def _validate_languages(
    config: TesseractPreflightConfig,
    languages: list[str],
) -> TesseractFailureReason | None:
    if not languages or any(language not in config.language_allowlist for language in languages):
        return TesseractFailureReason.UNSUPPORTED_LANGUAGE
    return None


def _validate_page_segmentation_mode(
    config: TesseractPreflightConfig,
) -> TesseractFailureReason | None:
    if (
        not config.allowed_page_segmentation_modes
        or config.page_segmentation_mode not in config.allowed_page_segmentation_modes
    ):
        return TesseractFailureReason.INVALID_CONFIG
    return None


def _validate_artifacts(
    config: TesseractPreflightConfig,
    languages: list[str],
    verifier: TesseractArtifactVerifierPort,
) -> TesseractFailureReason | None:
    if not verifier.path_exists(config.binary_path):
        return TesseractFailureReason.BINARY_MISSING
    if not verifier.checksum_matches(config.binary_path, config.binary_sha256):
        return TesseractFailureReason.CHECKSUM_MISMATCH
    for language in languages:
        expected_sha256 = config.traineddata_sha256.get(language)
        if not expected_sha256:
            return TesseractFailureReason.TRAINEDDATA_MISSING
        traineddata_path = _join_path(config.tessdata_directory, f"{language}.traineddata")
        if not verifier.path_exists(traineddata_path):
            return TesseractFailureReason.TRAINEDDATA_MISSING
        if not verifier.checksum_matches(traineddata_path, expected_sha256):
            return TesseractFailureReason.CHECKSUM_MISMATCH
    return None


def _is_explicit_absolute_path(value: str) -> bool:
    return bool(value) and (PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute())


def _join_path(directory: str, filename: str) -> str:
    path_type = PureWindowsPath if PureWindowsPath(directory).is_absolute() else PurePosixPath
    return str(path_type(directory) / filename)
