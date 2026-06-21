from app.domain.types.common import SizeBucket

ONE_MIB = 1_048_576
TEN_MIB = 10_485_760


def persistence_size_bucket(size_bytes: int) -> SizeBucket:
    """Project runtime byte size to the canonical coarse persistence bucket."""
    if size_bytes < 0:
        raise ValueError("size_bytes must be non-negative")
    if size_bytes == 0:
        return "empty"
    if size_bytes <= ONE_MIB:
        return "small"
    if size_bytes <= TEN_MIB:
        return "medium"
    return "large"
