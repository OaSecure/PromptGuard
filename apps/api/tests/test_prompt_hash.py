import pytest

from app.core.prompt_hash import compute_prompt_hash


@pytest.mark.parametrize(
    "prompt",
    [
        "hello prompt",
        "한국어 프롬프트와 emoji-like text",
        "line one\nline two\twith symbols !@#$%^&*()",
        "x" * 4096,
    ],
)
def test_prompt_hash_is_deterministic_for_same_workspace_and_prompt(prompt: str) -> None:
    first = compute_prompt_hash(
        workspace_id="workspace-alpha",
        prompt=prompt,
        secret="test-secret",
        key_id="test-key",
    )
    second = compute_prompt_hash(
        workspace_id="workspace-alpha",
        prompt=prompt,
        secret="test-secret",
        key_id="test-key",
    )

    assert first == second
    assert first.value == f"{first.key_id}:{first.digest}"
    assert first.key_id == "test-key"
    assert len(first.digest) == 64
    assert all(character in "0123456789abcdef" for character in first.digest)


def test_prompt_hash_changes_by_workspace_id() -> None:
    prompt = "same prompt"

    alpha = compute_prompt_hash(
        workspace_id="workspace-alpha",
        prompt=prompt,
        secret="test-secret",
        key_id="test-key",
    )
    beta = compute_prompt_hash(
        workspace_id="workspace-beta",
        prompt=prompt,
        secret="test-secret",
        key_id="test-key",
    )

    assert alpha.digest != beta.digest


def test_prompt_hash_changes_by_secret() -> None:
    first = compute_prompt_hash(
        workspace_id="workspace-alpha",
        prompt="same prompt",
        secret="test-secret-one",
        key_id="test-key",
    )
    second = compute_prompt_hash(
        workspace_id="workspace-alpha",
        prompt="same prompt",
        secret="test-secret-two",
        key_id="test-key",
    )

    assert first.digest != second.digest


def test_prompt_hash_output_is_raw_free() -> None:
    raw_prompt = "sensitive prompt value"
    raw_workspace_id = "workspace-sensitive"
    raw_secret = "secret-that-must-not-leak"

    prompt_hash = compute_prompt_hash(
        workspace_id=raw_workspace_id,
        prompt=raw_prompt,
        secret=raw_secret,
        key_id="safe-key",
    )

    assert raw_prompt not in prompt_hash.value
    assert raw_workspace_id not in prompt_hash.value
    assert raw_secret not in prompt_hash.value
    assert prompt_hash.value == f"safe-key:{prompt_hash.digest}"


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"workspace_id": " ", "prompt": "prompt", "secret": "secret", "key_id": "key"}, "workspace_id"),
        ({"workspace_id": "workspace", "prompt": " ", "secret": "secret", "key_id": "key"}, "prompt"),
        ({"workspace_id": "workspace", "prompt": "prompt", "secret": " ", "key_id": "key"}, "secret"),
        ({"workspace_id": "workspace", "prompt": "prompt", "secret": "secret", "key_id": " "}, "key id"),
        ({"workspace_id": "workspace", "prompt": "prompt", "secret": "secret", "key_id": "bad:key"}, "key id"),
    ],
)
def test_prompt_hash_rejects_invalid_inputs(kwargs: dict[str, str], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        compute_prompt_hash(**kwargs)
