import hashlib
import hmac
import json
import re
from dataclasses import dataclass

from app.core.config import get_settings

_KEY_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,80}$")


@dataclass(frozen=True)
class PromptHash:
    key_id: str
    digest: str

    @property
    def value(self) -> str:
        return f"{self.key_id}:{self.digest}"


def compute_prompt_hash(
    *,
    workspace_id: str,
    prompt: str,
    secret: str | None = None,
    key_id: str | None = None,
) -> PromptHash:
    workspace_id = workspace_id.strip()
    if not workspace_id:
        raise ValueError("workspace_id must not be blank")
    if not prompt.strip():
        raise ValueError("prompt must not be blank")

    settings = get_settings()
    hash_secret = secret if secret is not None else settings.prompt_hash_secret
    hash_key_id = key_id if key_id is not None else settings.prompt_hash_key_id

    if not hash_secret.strip():
        raise ValueError("prompt hash secret must not be blank")
    hash_key_id = hash_key_id.strip()
    if not hash_key_id:
        raise ValueError("prompt hash key id must not be blank")
    if not _KEY_ID_PATTERN.fullmatch(hash_key_id):
        raise ValueError("prompt hash key id must contain only letters, numbers, '.', '_', or '-'")

    payload = json.dumps(
        {"prompt": prompt, "workspace_id": workspace_id},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hmac.new(hash_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return PromptHash(key_id=hash_key_id, digest=digest)
