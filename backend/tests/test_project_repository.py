from pathlib import Path

import pytest

from app.auth import hash_password
from app.database import initialize_database
from app.repositories.history_repository import HistoryRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository


@pytest.mark.asyncio
async def test_user_starts_with_default_project_and_projects_are_isolated(tmp_path: Path) -> None:
    database_path = tmp_path / "projects.db"
    await initialize_database(database_path)
    users = UserRepository(database_path)
    first = await users.create("alice", hash_password("secret6"))
    second = await users.create("bob", hash_password("secret6"))
    repository = ProjectRepository(database_path)

    first_projects = await repository.list_with_history(first.id)
    second_projects = await repository.list_with_history(second.id)

    assert [project.name for project in first_projects] == ["第一个项目"]
    assert [project.name for project in second_projects] == ["第一个项目"]
    assert await repository.get_owned(first_projects[0].id, second.id) is None


@pytest.mark.asyncio
async def test_deleting_last_project_replaces_it_and_cascades_history_images(tmp_path: Path) -> None:
    database_path = tmp_path / "projects.db"
    await initialize_database(database_path)
    user = await UserRepository(database_path).create("alice", hash_password("secret6"))
    projects = ProjectRepository(database_path)
    default_project = (await projects.list_with_history(user.id))[0]
    history = HistoryRepository(database_path)
    history_id = await history.create(
        user_id=user.id,
        project_id=default_project.id,
        kind="generate",
        prompt="test",
        provider="compatible",
        model="gpt-image-1.5",
        detail="auto",
        image_count=1,
    )
    await history.add_image(
        user_id=user.id,
        history_id=history_id,
        role="generated",
        mime_type="image/png",
        filename="test.png",
        position=0,
        data=b"png",
    )

    result = await projects.delete(default_project.id, user.id)
    remaining = await projects.list_with_history(user.id)

    assert result.deleted_history_count == 1
    assert len(remaining) == 1
    assert remaining[0].name == "第一个项目"
    assert await history.get(user.id, history_id) is None


@pytest.mark.asyncio
async def test_batch_delete_only_removes_selected_history_in_project(tmp_path: Path) -> None:
    database_path = tmp_path / "projects.db"
    await initialize_database(database_path)
    user = await UserRepository(database_path).create("alice", hash_password("secret6"))
    projects = ProjectRepository(database_path)
    project = (await projects.list_with_history(user.id))[0]
    history = HistoryRepository(database_path)
    ids = []
    for prompt in ("one", "two"):
        ids.append(await history.create(
            user_id=user.id,
            project_id=project.id,
            kind="generate",
            prompt=prompt,
            provider="compatible",
            model="gpt-image-1.5",
            detail="auto",
            image_count=1,
        ))

    assert await projects.delete_history(project.id, user.id, [ids[0]]) == 1
    assert await history.get(user.id, ids[0]) is None
    assert (await history.get(user.id, ids[1])) is not None
