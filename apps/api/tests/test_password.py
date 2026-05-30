from app.core.password import hash_password, verify_password


def test_verify_password_accepts_matching_password() -> None:
    password_hash = hash_password("correct horse battery staple")

    assert verify_password("correct horse battery staple", password_hash)


def test_verify_password_rejects_different_password() -> None:
    password_hash = hash_password("correct horse battery staple")

    assert not verify_password("wrong password", password_hash)


def test_password_hash_does_not_contain_plain_password() -> None:
    plain_password = "plain-password-that-must-not-be-stored"

    password_hash = hash_password(plain_password)

    assert plain_password not in password_hash


def test_same_password_gets_different_hashes() -> None:
    plain_password = "same password"

    first_hash = hash_password(plain_password)
    second_hash = hash_password(plain_password)

    assert first_hash != second_hash


def test_different_hashes_still_verify_same_password() -> None:
    plain_password = "same password"
    first_hash = hash_password(plain_password)
    second_hash = hash_password(plain_password)

    assert verify_password(plain_password, first_hash)
    assert verify_password(plain_password, second_hash)
