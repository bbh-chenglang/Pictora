from pathlib import Path

import pytest

from app.auth import hash_password, verify_password
from app.database import initialize_database
from app.repositories.user_repository import UserAlreadyExistsError, UserRepository


def test_password_hash_verifies_without_storing_plaintext() -> None:
    password_hash = hash_password("secret6")

    assert password_hash != "secret6"
    assert verify_password("secret6", password_hash)
    assert not verify_password("wrong6", password_hash)


@pytest.mark.asyncio
async def test_user_repository_creates_unique_user_and_personal_settings(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "users.db"
    await initialize_database(database_path)
    repository = UserRepository(database_path)

    user = await repository.create("alice", hash_password("secret6"))
    await repository.update_settings(user.id, model="gpt-image-1.5", api_key="key-a")

    loaded = await repository.get_by_username("alice")
    settings = await repository.get_settings(user.id)

    assert loaded is not None
    assert loaded.id == user.id
    assert loaded.password_hash != "secret6"
    assert settings.model == "gpt-image-1.5"
    assert settings.api_key == "key-a"

    with pytest.raises(UserAlreadyExistsError):
        await repository.create("alice", hash_password("another6"))
