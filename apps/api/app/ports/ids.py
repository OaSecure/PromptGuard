from typing import Protocol


class IdGeneratorPort(Protocol):
    def new_id(self, prefix: str) -> str: ...
