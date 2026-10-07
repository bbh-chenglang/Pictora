from pathlib import Path

import aiosqlite
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
async def test_empty_project_name_can_be_filled_from_prompt(tmp_path: Path) -> None:
    database_path = tmp_path / "projects.db"
    await initialize_database(database_path)
    user = await UserRepository(database_path).create("alice", hash_password("secret6"))
    repository = ProjectRepository(database_path)
    project = (await repository.list_with_history(user.id))[0]

    async with aiosqlite.connect(database_path) as connection:
        await connection.execute("UPDATE projects SET name = '   ' WHERE id = ?", (project.id,))
        await connection.commit()

    renamed = await repository.rename_if_empty(project.id, user.id, "蓝色海面与晨光")

    assert renamed is True
    assert (await repository.get_owned(project.id, user.id)).name == "蓝色海面与晨光"


@pytest.mark.asyncio
async def test_default_project_name_can_be_filled_from_prompt(tmp_path: Path) -> None:
    database_path = tmp_path / "projects.db"
    await initialize_database(database_path)
    user = await UserRepository(database_path).create("alice", hash_password("secret6"))
    repository = ProjectRepository(database_path)
    project = (await repository.list_with_history(user.id))[0]

    renamed = await repository.rename_if_empty(project.id, user.id, "蓝色海面与晨光")

    assert renamed is True
    saved = await repository.get_owned(project.id, user.id)
    assert saved is not None
    assert saved.name == "蓝色海面与晨光"


@pytest.mark.asyncio
async def test_project_history_includes_generation_metadata(tmp_path: Path) -> None:
    database_path = tmp_path / "projects.db"
    await initialize_database(database_path)
    user = await UserRepository(database_path).create("alice", hash_password("secret6"))
    projects = ProjectRepository(database_path)
    project = (await projects.list_with_history(user.id))[0]
    history = HistoryRepository(database_path)
    await history.create(
        user_id=user.id,
        project_id=project.id,
        kind="generate",
        prompt="宽屏海报",
        provider="compatible",
        model="gpt-image-2",
        detail="high",
        image_count=2,
        size="16:9",
        resolution="4K",
    )

    item = (await projects.list_with_history(user.id))[0].history[0]

    assert item.model == "gpt-image-2"
    assert item.size == "16:9"
    assert item.resolution == "4K"
    assert item.image_count == 2


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


@pytest.mark.asyncio
async def test_project_names_and_deletion_are_scoped_by_media_type(tmp_path: Path) -> None:
    db = tmp_path / "typed-projects.db"
    await initialize_database(db)
    user = await UserRepository(db).create("alice", hash_password("secret6"))
    repository = ProjectRepository(db)
    image = (await repository.list_with_history(user.id, "image"))[0]
    video = await repository.create(user.id, image.name, "video")
    assert image.id != video.id
    assert video.media_type == "video"
    await repository.rename(video.id, user.id, "视频项目")
    result = await repository.delete(video.id, user.id)
    assert (await repository.get_owned(image.id, user.id)).model_dump() == image.model_dump(exclude={"history", "history_count", "video_history", "video_history_count"})
    replacement = await repository.get_owned(result.selected_project_id, user.id)
    assert replacement.media_type == "video"
    assert [p.id for p in await repository.list_with_history(user.id, "image")] == [image.id]
    await repository.ensure_video_project(user.id)
    await repository.ensure_video_project(user.id)
    assert len(await repository.list_with_history(user.id, "video")) == 1


@pytest.mark.asyncio
async def test_legacy_mixed_projects_are_split_losslessly_and_idempotently(tmp_path: Path) -> None:
    from app.database import _initialize_legacy_database, SCHEMA_VERSION
    from app.video.database import migrate_video
    db = tmp_path / "legacy-mixed.db"
    await _initialize_legacy_database(db)
    async with aiosqlite.connect(db) as connection:
        await migrate_video(connection)
        await connection.execute("INSERT INTO users(username,password_hash) VALUES('alice','hash')")
        image_project = (await (await connection.execute("SELECT id FROM projects")).fetchone())[0]
        await connection.execute("INSERT INTO projects(user_id,name) VALUES(1,'纯视频')")
        video_project = (await (await connection.execute("SELECT id FROM projects WHERE name='纯视频'")).fetchone())[0]
        await connection.execute("INSERT INTO history(user_id,project_id,kind,status,prompt,provider,model,detail) VALUES(1,?,'generate','completed','image','gpt','gpt-image-1','auto')", (image_project,))
        for project_id in (image_project, video_project):
            await connection.execute("""
                INSERT INTO video_tasks(user_id,project_id,request_id,request_json,payload_json,model,prompt,duration,resolution,ratio,status,upstream_task_id)
                VALUES(1,?,?,'{}','{}','sd-2.0-J2','movie',5,'720p','16:9','running',?)
            """, (project_id, str(project_id), "remote-" + str(project_id)))
        await connection.execute("INSERT INTO video_results(task_id,position,object_key,filename,stored) VALUES(1,0,'keep-me','movie.mp4',1)")
        await connection.execute("PRAGMA user_version=18")
        await connection.commit()
    await initialize_database(db)
    repository = ProjectRepository(db)
    projects = await repository.list_with_history(1)
    image = next(p for p in projects if p.id == image_project)
    video_only = next(p for p in projects if p.id == video_project)
    split = next(p for p in projects if p.name == image.name and p.media_type == "video")
    assert image.media_type == "image" and image.history_count == 1 and image.video_history_count == 0
    assert video_only.media_type == "video" and video_only.video_history_count == 1
    assert split.video_history_count == 1 and split.history_count == 0
    async with aiosqlite.connect(db) as connection:
        assert await (await connection.execute("PRAGMA foreign_key_check")).fetchall() == []
        assert await (await connection.execute("SELECT object_key FROM video_results")).fetchall() == [("keep-me",)]
        assert await (await connection.execute("SELECT * FROM video_storage_cleanup")).fetchall() == []
        assert (await (await connection.execute("PRAGMA user_version")).fetchone())[0] == SCHEMA_VERSION
        with pytest.raises(aiosqlite.IntegrityError, match="video_project_tracking"):
            await connection.execute("DELETE FROM projects WHERE id=?", (split.id,))
    await initialize_database(db)
    assert await repository.list_with_history(1) == projects


@pytest.mark.asyncio
async def test_image_generation_cannot_use_video_projects(tmp_path: Path) -> None:
    import httpx
    from app.services.history_service import HistoryService
    from app.repositories.project_repository import ProjectNotFoundError
    db = tmp_path / "generation-scope.db"
    await initialize_database(db)
    user = await UserRepository(db).create("alice", hash_password("secret6"))
    projects = ProjectRepository(db)
    image = (await projects.list_with_history(user.id, "image"))[0]
    video = await projects.create(user.id, "视频", "video")
    async with httpx.AsyncClient() as client:
        service = HistoryService(HistoryRepository(db), client, project_repository=projects)
        with pytest.raises(ProjectNotFoundError):
            await service._resolve_project(video.id, user.id)
        assert await service._resolve_project(None, user.id) == image.id


@pytest.mark.asyncio
async def test_project_migration_preserves_existing_orphans(tmp_path: Path) -> None:
    from app.database import _initialize_legacy_database, SCHEMA_VERSION

    db = tmp_path / "legacy-orphans.db"
    await _initialize_legacy_database(db)
    async with aiosqlite.connect(db) as connection:
        await connection.execute("INSERT INTO users(username,password_hash) VALUES('alice','hash')")
        await connection.execute("""
            INSERT INTO history_images(history_id,role,mime_type,data)
            VALUES(9999,'generated','image/png',X'0102')
        """)
        await connection.execute("""
            INSERT INTO generation_batches(history_id,api_key_config_id,prompt,provider,model,detail,image_count)
            VALUES(9999,8888,'legacy','gpt','gpt-image-1','auto',1)
        """)
        await connection.commit()
        before = await (await connection.execute("PRAGMA foreign_key_check")).fetchall()
        assert len(before) == 3

    await initialize_database(db)
    await initialize_database(db)
    async with aiosqlite.connect(db) as connection:
        assert await (await connection.execute("PRAGMA foreign_key_check")).fetchall() == before
        assert await (await connection.execute("SELECT data FROM history_images")).fetchall() == [(b"\x01\x02",)]
        assert await (await connection.execute("SELECT history_id,api_key_config_id FROM generation_batches")).fetchall() == [(9999, 8888)]
        assert (await (await connection.execute("PRAGMA user_version")).fetchone())[0] == SCHEMA_VERSION


@pytest.mark.asyncio
@pytest.mark.parametrize("replace_existing", [False, True])
async def test_project_migration_rejects_new_foreign_key_violations_and_rolls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, replace_existing: bool
) -> None:
    from app.database import _initialize_legacy_database
    from app import project_migration

    db = tmp_path / "new-orphans.db"
    await _initialize_legacy_database(db)
    async with aiosqlite.connect(db) as connection:
        await connection.execute("INSERT INTO users(username,password_hash) VALUES('alice','hash')")
        await connection.execute("""
            INSERT INTO history_images(history_id,role,mime_type,data)
            VALUES(9999,'generated','image/png',X'01')
        """)
        await connection.commit()
        before = await (await connection.execute("PRAGMA foreign_key_check")).fetchall()

    original = project_migration.migrate_project_types

    async def broken_migration(connection: aiosqlite.Connection) -> None:
        await original(connection)
        if replace_existing:
            # An equal total count must not hide a different broken relationship.
            await connection.execute("DELETE FROM history_images")
        await connection.execute("INSERT INTO projects(user_id,name) VALUES(9999,'invalid')")

    monkeypatch.setattr(project_migration, "migrate_project_types", broken_migration)
    with pytest.raises(RuntimeError, match="introduced invalid foreign keys"):
        await initialize_database(db)
    async with aiosqlite.connect(db) as connection:
        assert await (await connection.execute("PRAGMA foreign_key_check")).fetchall() == before
        assert "media_type" not in {row[1] for row in await (await connection.execute("PRAGMA table_info(projects)")).fetchall()}
        assert await (await connection.execute("SELECT COUNT(*) FROM projects WHERE user_id=9999")).fetchone() == (0,)
