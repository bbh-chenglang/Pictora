"""Lifespan jobs must never inspect or mutate the developer's persistent data volume."""
import pytest


@pytest.fixture(autouse=True)
def isolated_lifespan(tmp_path, monkeypatch):
    from app import main
    from app.database import initialize_database
    from app.config import Settings
    from app.repositories.history_repository import HistoryRepository
    from app.video.repository import VideoRepository
    from app.video.service import VideoService
    from app.dependencies import get_r2_image_storage
    from app.repositories.r2_image_repository import R2ImageRepository
    from app.services.r2_image_storage import R2ImageStorage
    path = tmp_path / 'lifespan.db'
    async def initialize(**kwargs):
        await initialize_database(path, **kwargs)
    service = VideoService(VideoRepository(path), Settings(_env_file=None))
    storage = R2ImageStorage(R2ImageRepository(path), Settings(_env_file=None, r2_enabled=False))
    monkeypatch.setattr(main, "get_r2_image_storage", lambda: storage)
    main.app.dependency_overrides[get_r2_image_storage] = lambda: storage
    monkeypatch.setattr(main, 'initialize_database', initialize)
    monkeypatch.setattr(main, 'get_history_repository', lambda: HistoryRepository(path))
    monkeypatch.setattr(main, 'get_video_service', lambda: service)
    yield
    main.app.dependency_overrides.pop(get_r2_image_storage, None)
