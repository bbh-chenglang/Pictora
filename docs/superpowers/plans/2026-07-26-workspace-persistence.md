# GenImage Workspace Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved left-parameter/bottom-composer workspace, persist the custom model and API Key in SQLite, and store generation and analysis history including image BLOBs.

**Architecture:** Use `aiosqlite` repositories for settings and history, initialized by FastAPI lifespan. Keep provider execution in `ImageService`, add a history orchestration service around generation and analysis, and expose summary/detail/image history endpoints. The Vue page uses same-origin `/api` calls, renders settings/history in the left panel, and keeps reference upload above the prompt in a fixed center-bottom composer.

**Tech Stack:** FastAPI, Pydantic, aiosqlite, SQLite BLOBs, pytest/pytest-asyncio, Vue 3, TypeScript, Vite, Vitest, Vue Test Utils, happy-dom, Playwright.

---

## File Map

**Backend files to create**

- `backend/app/database.py`: database path, fixed provider constants, schema bootstrap, and connection helper.
- `backend/app/repositories/settings_repository.py`: read and update the singleton provider settings row.
- `backend/app/repositories/history_repository.py`: create/update/list/read history rows and image BLOBs.
- `backend/app/repositories/__init__.py`: repository package marker.
- `backend/app/schemas/history.py`: history summary/detail/image metadata response models.
- `backend/app/services/history_service.py`: generation/analysis history lifecycle and generated-image materialization.
- `backend/app/api/history.py`: history list, detail, and BLOB response routes.
- `backend/tests/test_database.py`: schema and settings persistence tests.
- `backend/tests/test_history_repository.py`: history repository tests.
- `backend/tests/test_history_service.py`: orchestration and image materialization tests.
- `frontend/src/App.test.ts`: front-end settings/history/layout behavior tests.

**Backend files to modify**

- `backend/requirements.txt`: add `aiosqlite`.
- `backend/app/config.py`: retain environment defaults only for first-run database seeding and fix the custom endpoint defaults.
- `backend/app/dependencies.py`: replace process-memory overrides with repository-backed async dependencies and provider cache keys.
- `backend/app/providers/registry.py`: build the compatible provider from stored settings.
- `backend/app/schemas/settings.py`: accept only model/API Key updates and keep Base URL read-only.
- `backend/app/api/settings.py`: read/write the SQLite settings row.
- `backend/app/api/generate.py`: call the history orchestration service.
- `backend/app/api/analyze.py`: persist reference image and analysis history.
- `backend/app/main.py`: initialize SQLite in lifespan and register history routes.
- `backend/tests/test_api.py`: override new dependencies and test settings/history API contracts.
- `backend/tests/test_provider_registry.py`: test registry construction from stored settings.
- `.gitignore`: ignore `backend/data/*.db` and SQLite sidecar files.

**Frontend files to modify**

- `frontend/package.json` and `frontend/package-lock.json`: add Vitest test tooling.
- `frontend/src/App.vue`: remove visible batch prompts, add history/settings data flow, and reorganize the template.
- `frontend/src/style.css`: implement fixed desktop composer and responsive document-flow layout.
- `frontend/vite.config.ts`: preserve the existing `127.0.0.1:8002` proxy fix and add Vitest configuration.
- `start-dev.ps1`: use the working `127.0.0.1:3000` frontend endpoint consistently.

The existing uncommitted same-origin API change in `frontend/src/App.vue` and IPv4 proxy change in `frontend/vite.config.ts` are prerequisites and must be preserved.

---

### Task 1: SQLite Bootstrap And Persistent Settings

**Files:**
- Create: `backend/app/database.py`
- Create: `backend/app/repositories/__init__.py`
- Create: `backend/app/repositories/settings_repository.py`
- Create: `backend/tests/test_database.py`
- Modify: `backend/requirements.txt`
- Modify: `backend/app/config.py`
- Modify: `.gitignore`

- [ ] **Step 1: Add the failing database and settings repository tests**

```python
# backend/tests/test_database.py
from pathlib import Path

import pytest

from app.database import FIXED_BASE_URL, FIXED_PROVIDER_NAME, initialize_database
from app.repositories.settings_repository import SettingsRepository


@pytest.mark.asyncio
async def test_database_seeds_fixed_provider_settings(tmp_path: Path) -> None:
    database_path = tmp_path / "genimage.db"
    await initialize_database(database_path, default_model="gpt-image-1.5", default_api_key="")
    settings = await SettingsRepository(database_path).get()

    assert settings.provider_name == FIXED_PROVIDER_NAME
    assert settings.base_url == FIXED_BASE_URL
    assert settings.model == "gpt-image-1.5"
    assert settings.api_key == ""


@pytest.mark.asyncio
async def test_settings_update_persists_only_model_and_api_key(tmp_path: Path) -> None:
    database_path = tmp_path / "genimage.db"
    await initialize_database(database_path, default_model="old-model", default_api_key="old-key")
    repository = SettingsRepository(database_path)

    updated = await repository.update(model="new-model", api_key="new-key")
    reloaded = await SettingsRepository(database_path).get()

    assert updated == reloaded
    assert reloaded.model == "new-model"
    assert reloaded.api_key == "new-key"
    assert reloaded.base_url == FIXED_BASE_URL
```

- [ ] **Step 2: Run the test and verify the missing modules fail**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_database.py -v`

Expected: collection fails because `app.database` and `app.repositories.settings_repository` do not exist.

- [ ] **Step 3: Add aiosqlite and the database schema**

Add `aiosqlite==0.21.0` to `backend/requirements.txt`, then implement:

```python
# backend/app/database.py
from pathlib import Path

import aiosqlite

DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "genimage.db"
FIXED_PROVIDER_NAME = "北海AI"
FIXED_BASE_URL = "https://sub.beibeihai.xyz/v1"

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    provider_name TEXT NOT NULL,
    base_url TEXT NOT NULL,
    model TEXT NOT NULL,
    api_key TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK (kind IN ('generate', 'analyze')),
    status TEXT NOT NULL CHECK (status IN ('pending', 'completed', 'failed')),
    prompt TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    detail TEXT NOT NULL,
    image_count INTEGER NOT NULL DEFAULT 1,
    analysis_text TEXT,
    elapsed_ms INTEGER,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS history_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    history_id INTEGER NOT NULL REFERENCES history(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('reference', 'generated')),
    mime_type TEXT NOT NULL,
    filename TEXT,
    position INTEGER NOT NULL DEFAULT 0,
    data BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_created_at ON history(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_images_history_id ON history_images(history_id, position);
"""


async def initialize_database(
    path: Path = DATABASE_PATH,
    default_model: str = "gpt-image-1.5",
    default_api_key: str = "",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(path) as connection:
        await connection.executescript(SCHEMA)
        await connection.execute(
            """INSERT OR IGNORE INTO settings
               (id, provider_name, base_url, model, api_key)
               VALUES (1, ?, ?, ?, ?)""",
            (FIXED_PROVIDER_NAME, FIXED_BASE_URL, default_model, default_api_key),
        )
        await connection.commit()
```

Implement the focused repository:

```python
# backend/app/repositories/settings_repository.py
from dataclasses import dataclass
from pathlib import Path

import aiosqlite

from app.database import DATABASE_PATH


@dataclass(frozen=True)
class StoredProviderSettings:
    provider_name: str
    base_url: str
    model: str
    api_key: str


class SettingsRepository:
    def __init__(self, database_path: Path = DATABASE_PATH) -> None:
        self.database_path = database_path

    async def get(self) -> StoredProviderSettings:
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            cursor = await connection.execute(
                "SELECT provider_name, base_url, model, api_key FROM settings WHERE id = 1"
            )
            row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("Provider settings are not initialized")
        return StoredProviderSettings(**dict(row))

    async def update(self, model: str, api_key: str | None) -> StoredProviderSettings:
        async with aiosqlite.connect(self.database_path) as connection:
            if api_key is None:
                await connection.execute(
                    "UPDATE settings SET model = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                    (model,),
                )
            else:
                await connection.execute(
                    "UPDATE settings SET model = ?, api_key = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                    (model, api_key),
                )
            await connection.commit()
        return await self.get()
```

Set `Settings.custom_base_url` to the fixed URL, `custom_provider_name` to `北海AI`, and `custom_model` to `gpt-image-1.5` for first-run seeding. Add these ignore rules:

```gitignore
backend/data/*.db
backend/data/*.db-shm
backend/data/*.db-wal
```

- [ ] **Step 4: Install dependencies and run the tests**

Run: `uv pip install --python backend\.venv\Scripts\python.exe --link-mode=copy -r backend\requirements-dev.txt`

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_database.py -v`

Expected: both tests pass.

- [ ] **Step 5: Commit the database foundation**

```powershell
git add .gitignore backend/requirements.txt backend/app/config.py backend/app/database.py backend/app/repositories backend/tests/test_database.py
git commit -m "feat: 添加 SQLite 配置存储"
```

---

### Task 2: Database-Backed Settings And Provider Dependencies

**Files:**
- Modify: `backend/app/dependencies.py`
- Modify: `backend/app/providers/registry.py`
- Modify: `backend/app/schemas/settings.py`
- Modify: `backend/app/api/settings.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_api.py`
- Modify: `backend/tests/test_provider_registry.py`

- [ ] **Step 1: Write failing settings API and provider tests**

Add tests asserting that `PUT /api/settings` rejects `base_url` and `provider_name`, retains the key when `api_key` is omitted, and never returns the key:

```python
@pytest.fixture
def settings_repository(tmp_path: Path) -> SettingsRepository:
    database_path = tmp_path / "settings-api.db"
    asyncio.run(
        initialize_database(
            database_path,
            default_model="gpt-image-1.5",
            default_api_key="",
        )
    )
    return SettingsRepository(database_path)


def test_settings_api_updates_only_model_and_optional_key(settings_repository) -> None:
    app.dependency_overrides[get_settings_repository] = lambda: settings_repository
    with TestClient(app) as client:
        response = client.put(
            "/api/settings",
            json={"model": "custom-image-model", "api_key": "private-key"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "provider_name": "北海AI",
        "model": "custom-image-model",
        "base_url": "https://sub.beibeihai.xyz/v1",
        "provider_id": "compatible",
        "api_key_configured": True,
    }
    assert "private-key" not in response.text


def test_settings_api_rejects_mutating_fixed_fields(settings_repository) -> None:
    app.dependency_overrides[get_settings_repository] = lambda: settings_repository
    with TestClient(app) as client:
        response = client.put(
            "/api/settings",
            json={
                "model": "custom-image-model",
                "provider_name": "other",
                "base_url": "https://other.example/v1",
            },
        )

    assert response.status_code == 422
```

Update the registry test to construct from `StoredProviderSettings` and assert only `compatible` is exposed.

- [ ] **Step 2: Run focused tests and verify the old contract fails**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_api.py backend/tests/test_provider_registry.py -v`

Expected: settings payload tests fail because the current request still requires provider name and Base URL and dependencies are synchronous/in-memory.

- [ ] **Step 3: Implement async repository-backed dependencies**

Replace runtime overrides with these dependency boundaries:

```python
# backend/app/dependencies.py
from functools import lru_cache

from fastapi import Depends
from pydantic import SecretStr

from app.database import DATABASE_PATH
from app.providers.registry import ProviderRegistry
from app.repositories.settings_repository import SettingsRepository, StoredProviderSettings
from app.services.image_service import ImageService


@lru_cache
def get_settings_repository() -> SettingsRepository:
    return SettingsRepository(DATABASE_PATH)


@lru_cache
def _registry_for(api_key: str, model: str) -> ProviderRegistry:
    return ProviderRegistry.from_stored_settings(
        StoredProviderSettings(
            provider_name="北海AI",
            base_url="https://sub.beibeihai.xyz/v1",
            model=model,
            api_key=api_key,
        )
    )


async def get_provider_registry(
    repository: SettingsRepository = Depends(get_settings_repository),
) -> ProviderRegistry:
    settings = await repository.get()
    return _registry_for(settings.api_key, settings.model)


async def get_image_service(
    registry: ProviderRegistry = Depends(get_provider_registry),
) -> ImageService:
    return ImageService(registry)


def clear_dependency_caches() -> None:
    _registry_for.cache_clear()
    get_settings_repository.cache_clear()
```

Add `ProviderRegistry.from_stored_settings(settings)` using `SecretStr(settings.api_key)` and the fixed compatible provider fields. Keep `from_settings` for existing OpenAI provider unit tests until all callers are migrated.

Change the settings request model to:

```python
class RuntimeProviderSettings(BaseModel):
    model: str = Field(min_length=1, max_length=120)
    api_key: str | None = Field(default=None, min_length=1, max_length=500)
```

Update the API route to await `repository.get()` and `repository.update()`, then call `clear_dependency_caches()` after a successful update.

Initialize the database in FastAPI lifespan using the current `.env` model/API Key only for the first insert:

```python
@asynccontextmanager
async def lifespan(_: FastAPI):
    defaults = Settings()
    await initialize_database(
        default_model=defaults.custom_model,
        default_api_key=defaults.custom_api_key.get_secret_value(),
    )
    yield


app = FastAPI(title="GenImage API", lifespan=lifespan)
```

- [ ] **Step 4: Run settings, registry, and API tests**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_database.py backend/tests/test_provider_registry.py backend/tests/test_api.py -v`

Expected: tests pass; no response body contains the configured API Key.

- [ ] **Step 5: Commit database-backed settings**

```powershell
git add backend/app/dependencies.py backend/app/providers/registry.py backend/app/schemas/settings.py backend/app/api/settings.py backend/app/main.py backend/tests/test_api.py backend/tests/test_provider_registry.py
git commit -m "feat: 使用数据库加载模型配置"
```

---

### Task 3: History Repository And Response Schemas

**Files:**
- Create: `backend/app/repositories/history_repository.py`
- Create: `backend/app/schemas/history.py`
- Create: `backend/tests/test_history_repository.py`

- [ ] **Step 1: Write failing repository lifecycle tests**

```python
@pytest.mark.asyncio
async def test_history_repository_tracks_task_and_blob_images(tmp_path: Path) -> None:
    database_path = tmp_path / "genimage.db"
    await initialize_database(database_path)
    repository = HistoryRepository(database_path)

    history_id = await repository.create(
        kind="generate",
        prompt="画一个苹果",
        provider="compatible",
        model="custom-model",
        detail="high",
        image_count=1,
    )
    await repository.add_image(
        history_id=history_id,
        role="generated",
        mime_type="image/png",
        filename="generated-1.png",
        position=0,
        data=b"png-bytes",
    )
    await repository.complete(history_id, elapsed_ms=1250)

    summaries = await repository.list(limit=20)
    detail = await repository.get(history_id)
    image = await repository.get_image(history_id, detail.images[0].id)

    assert summaries[0].status == "completed"
    assert summaries[0].prompt == "画一个苹果"
    assert detail.images[0].role == "generated"
    assert detail.images[0].url == f"/api/history/{history_id}/images/{detail.images[0].id}"
    assert image.data == b"png-bytes"


@pytest.mark.asyncio
async def test_history_repository_records_failures_without_secrets(tmp_path: Path) -> None:
    database_path = tmp_path / "genimage.db"
    await initialize_database(database_path)
    repository = HistoryRepository(database_path)
    history_id = await repository.create(
        kind="analyze", prompt="描述图片", provider="compatible",
        model="custom-model", detail="auto", image_count=1,
    )

    await repository.fail(history_id, error_code="provider_auth", error_message="服务商鉴权失败")
    detail = await repository.get(history_id)

    assert detail.status == "failed"
    assert detail.error_code == "provider_auth"
    assert "key" not in (detail.error_message or "").lower()
```

- [ ] **Step 2: Run tests and verify the repository is missing**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_history_repository.py -v`

Expected: collection fails because history repository and schemas do not exist.

- [ ] **Step 3: Implement typed history schemas and SQL methods**

Define `HistoryImageMeta`, `HistorySummary`, `HistoryDetail`, and internal `StoredHistoryImage` models. Use `Literal` types for kind/status/role. `HistoryRepository` must implement:

```python
async def create(self, *, kind, prompt, provider, model, detail, image_count) -> int
async def add_image(self, *, history_id, role, mime_type, filename, position, data) -> int
async def complete(self, history_id: int, *, elapsed_ms: int | None = None, analysis_text: str | None = None) -> None
async def fail(self, history_id: int, *, error_code: str, error_message: str) -> None
async def list(self, *, limit: int = 50) -> list[HistorySummary]
async def get(self, history_id: int) -> HistoryDetail | None
async def get_image(self, history_id: int, image_id: int) -> StoredHistoryImage | None
```

Use parameterized SQL only. `list()` selects no BLOB columns. `get()` loads image metadata but never image bytes. Construct each image URL as `/api/history/{history_id}/images/{image_id}`.

- [ ] **Step 4: Run repository tests**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_history_repository.py -v`

Expected: both tests pass.

- [ ] **Step 5: Commit the history repository**

```powershell
git add backend/app/repositories/history_repository.py backend/app/schemas/history.py backend/tests/test_history_repository.py
git commit -m "feat: 添加生成历史数据库仓库"
```

---

### Task 4: Persist Generation And Analysis Lifecycles

**Files:**
- Create: `backend/app/services/history_service.py`
- Create: `backend/tests/test_history_service.py`
- Modify: `backend/app/dependencies.py`
- Modify: `backend/app/api/generate.py`
- Modify: `backend/app/api/analyze.py`
- Modify: `backend/tests/test_api.py`

- [ ] **Step 1: Write failing history service tests**

Cover Base64, remote URL, analysis reference image, and provider failure:

```python
@pytest_asyncio.fixture
async def history_repository(tmp_path: Path) -> HistoryRepository:
    database_path = tmp_path / "history-service.db"
    await initialize_database(database_path)
    return HistoryRepository(database_path)


class FakeImageService:
    def __init__(self, generate_response: GenerateResponse | None = None) -> None:
        self.generate_response = generate_response or GenerateResponse(
            provider="compatible",
            model="custom-model",
            images=[],
        )

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        return self.generate_response

    async def analyze(self, provider, model, prompt, detail, image_bytes, content_type):
        return AnalyzeResponse(provider=provider, model=model, text="分析结果")


class FakeHttpResponse:
    status_code = 200
    content = b"downloaded-image"
    headers = {"Content-Type": "image/png"}

    def raise_for_status(self) -> None:
        return None


class FakeHttpClient:
    async def get(self, url: str) -> FakeHttpResponse:
        return FakeHttpResponse()


class FailingImageService(FakeImageService):
    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        raise self.error


@pytest.mark.asyncio
async def test_generation_history_decodes_base64_into_blob(history_repository) -> None:
    image_service = FakeImageService(
        generate_response=GenerateResponse(
            provider="compatible",
            model="custom-model",
            images=[ImageResult(base64_data="cG5nLWJ5dGVz")],
        )
    )
    service = HistoryService(history_repository, http_client=FakeHttpClient())

    response = await service.generate(
        GenerateRequest(provider="compatible", model="custom-model", prompt="苹果"),
        image_service,
    )
    detail = (await history_repository.list(limit=1))[0]
    stored = await history_repository.get(detail.id)
    blob = await history_repository.get_image(stored.id, stored.images[0].id)

    assert response.images[0].base64_data == "cG5nLWJ5dGVz"
    assert blob.data == b"png-bytes"
    assert blob.mime_type == "image/png"


@pytest.mark.asyncio
async def test_analysis_history_stores_reference_and_text(history_repository) -> None:
    service = HistoryService(history_repository, http_client=FakeHttpClient())
    result = await service.analyze(
        image_service=FakeImageService(), provider="compatible", model="vision-model",
        prompt="描述", detail="auto", image_bytes=b"jpeg", content_type="image/jpeg",
        filename="reference.jpg",
    )

    detail = await history_repository.get((await history_repository.list(limit=1))[0].id)
    assert result.text == "分析结果"
    assert detail.analysis_text == "分析结果"
    assert detail.images[0].role == "reference"


@pytest.mark.asyncio
async def test_provider_failure_marks_history_failed(history_repository) -> None:
    service = HistoryService(history_repository, http_client=FakeHttpClient())
    with pytest.raises(ProviderAuthError):
        await service.generate(
            GenerateRequest(
                provider="compatible",
                model="custom-model",
                prompt="苹果",
            ),
            FailingImageService(ProviderAuthError()),
        )

    detail = await history_repository.get((await history_repository.list(limit=1))[0].id)
    assert detail.status == "failed"
    assert detail.error_code == "provider_auth"
```

- [ ] **Step 2: Run tests and verify the service is missing**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_history_service.py -v`

Expected: collection fails because `HistoryService` does not exist.

- [ ] **Step 3: Implement the history orchestration service**

`HistoryService.generate()` creates a pending row, awaits `ImageService.generate()`, materializes every result, writes BLOBs, and completes the row. Base64 is decoded with `base64.b64decode(..., validate=True)`. URL images are downloaded through an injected `httpx.AsyncClient`, require a 2xx response, and use the response `Content-Type` without parameters.

`HistoryService.analyze()` creates a pending row, writes the uploaded reference BLOB before calling the provider, saves analysis text, and completes the row.

Both methods use this failure mapping before re-raising:

```python
except ProviderError as exc:
    await self.repository.fail(
        history_id, error_code=exc.code, error_message=exc.message
    )
    raise
except Exception:
    await self.repository.fail(
        history_id,
        error_code="internal_error",
        error_message="任务处理失败",
    )
    raise
```

Add cached `get_history_repository()` and dependency-injected `get_history_service()` factories. Update generate/analyze routes to inject `HistoryService`; pass `image.filename` into `analyze()`.

- [ ] **Step 4: Run service and API tests**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_history_service.py backend/tests/test_api.py -v`

Expected: history service tests pass and existing API behavior remains unchanged.

- [ ] **Step 5: Commit lifecycle persistence**

```powershell
git add backend/app/services/history_service.py backend/app/dependencies.py backend/app/api/generate.py backend/app/api/analyze.py backend/tests/test_history_service.py backend/tests/test_api.py
git commit -m "feat: 持久化生成与分析任务"
```

---

### Task 5: History HTTP API

**Files:**
- Create: `backend/app/api/history.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_api.py`

- [ ] **Step 1: Write failing history endpoint tests**

```python
@pytest.fixture
def empty_history_repository(tmp_path: Path) -> HistoryRepository:
    database_path = tmp_path / "empty-history.db"
    asyncio.run(initialize_database(database_path))
    return HistoryRepository(database_path)


@pytest.fixture
def history_repository_with_record(tmp_path: Path) -> HistoryRepository:
    database_path = tmp_path / "history-api.db"
    asyncio.run(initialize_database(database_path))
    repository = HistoryRepository(database_path)
    history_id = asyncio.run(repository.create(
        kind="generate",
        prompt="画一个苹果",
        provider="compatible",
        model="custom-model",
        detail="high",
        image_count=1,
    ))
    asyncio.run(repository.add_image(
        history_id=history_id,
        role="generated",
        mime_type="image/png",
        filename="result.png",
        position=0,
        data=b"png-bytes",
    ))
    asyncio.run(repository.complete(history_id, elapsed_ms=500))
    return repository


def test_history_list_excludes_blob_data(history_repository_with_record) -> None:
    app.dependency_overrides[get_history_repository] = lambda: history_repository_with_record
    with TestClient(app) as client:
        response = client.get("/api/history")

    assert response.status_code == 200
    assert response.json()[0]["prompt"] == "画一个苹果"
    assert "data" not in response.text
    assert "base64" not in response.text


def test_history_detail_and_image_routes(history_repository_with_record) -> None:
    app.dependency_overrides[get_history_repository] = lambda: history_repository_with_record
    with TestClient(app) as client:
        detail = client.get("/api/history/1")
        image = client.get("/api/history/1/images/1")

    assert detail.status_code == 200
    assert detail.json()["images"][0]["url"] == "/api/history/1/images/1"
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert image.content == b"png-bytes"


def test_missing_history_resources_return_404(empty_history_repository) -> None:
    app.dependency_overrides[get_history_repository] = lambda: empty_history_repository
    with TestClient(app) as client:
        assert client.get("/api/history/999").status_code == 404
        assert client.get("/api/history/999/images/999").status_code == 404
```

- [ ] **Step 2: Run tests and verify routes return 404**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_api.py -k history -v`

Expected: tests fail because `/api/history` is not registered.

- [ ] **Step 3: Add summary, detail, and image routes**

```python
router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("", response_model=list[HistorySummary])
async def list_history(repository=Depends(get_history_repository)):
    return await repository.list(limit=50)


@router.get("/{history_id}", response_model=HistoryDetail)
async def read_history(history_id: int, repository=Depends(get_history_repository)):
    record = await repository.get(history_id)
    if record is None:
        raise HTTPException(404, {"error": {"code": "history_not_found", "message": "历史记录不存在"}})
    return record


@router.get("/{history_id}/images/{image_id}")
async def read_history_image(history_id: int, image_id: int, repository=Depends(get_history_repository)):
    image = await repository.get_image(history_id, image_id)
    if image is None:
        raise HTTPException(404, {"error": {"code": "history_image_not_found", "message": "历史图片不存在"}})
    return Response(content=image.data, media_type=image.mime_type)
```

Register the router in `main.py`.

- [ ] **Step 4: Run the full backend suite**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests -v`

Expected: all backend tests pass.

- [ ] **Step 5: Commit history endpoints**

```powershell
git add backend/app/api/history.py backend/app/main.py backend/tests/test_api.py
git commit -m "feat: 提供历史记录查询接口"
```

---

### Task 6: Frontend Settings, History, And Layout Behavior

**Files:**
- Create: `frontend/src/App.test.ts`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `frontend/vite.config.ts`
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Add frontend test tooling**

Run: `npm install --save-dev vitest@3.0.5 @vue/test-utils@2.4.6 happy-dom@16.7.2`

Add `"test": "vitest"` to `scripts` and configure `test: { environment: "happy-dom" }` in `vite.config.ts`. Preserve the proxy target `http://127.0.0.1:8002`.

- [ ] **Step 2: Write failing workspace tests**

```typescript
// frontend/src/App.test.ts
import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App.vue";

const jsonResponse = (body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  }));

describe("GenImage workspace", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/providers")) return jsonResponse({ providers: [{ id: "compatible", label: "北海AI", models: ["gpt-image-1.5"] }] });
      if (url.endsWith("/api/settings")) return jsonResponse({ provider_name: "北海AI", model: "gpt-image-1.5", base_url: "https://sub.beibeihai.xyz/v1", api_key_configured: false });
      if (url.endsWith("/api/history")) return jsonResponse([]);
      throw new Error(`Unexpected request: ${url}`);
    }));
  });

  afterEach(() => vi.unstubAllGlobals());

  it("places parameters on the left and reference upload above the bottom prompt", async () => {
    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.find(".control-panel").text()).toContain("API Key");
    expect(wrapper.find(".composer-dock .reference-row").exists()).toBe(true);
    expect(wrapper.find(".composer-dock .prompt-row textarea").exists()).toBe(true);
    expect(wrapper.text()).not.toContain("批量提示词");
  });

  it("renders history summaries and restores a selected record", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/api/history/7")) return jsonResponse({ id: 7, kind: "generate", status: "completed", prompt: "蓝色海面", provider: "compatible", model: "gpt-image-1.5", detail: "high", image_count: 1, analysis_text: null, elapsed_ms: 500, error_code: null, error_message: null, created_at: "2026-07-26T10:00:00", completed_at: "2026-07-26T10:00:01", images: [{ id: 9, role: "generated", mime_type: "image/png", filename: "result.png", position: 0, url: "/api/history/7/images/9" }] });
      if (url.endsWith("/api/history")) return jsonResponse([{ id: 7, kind: "generate", status: "completed", prompt: "蓝色海面", provider: "compatible", model: "gpt-image-1.5", detail: "high", image_count: 1, elapsed_ms: 500, error_code: null, error_message: null, created_at: "2026-07-26T10:00:00" }]);
      if (url.endsWith("/api/providers")) return jsonResponse({ providers: [{ id: "compatible", label: "北海AI", models: ["gpt-image-1.5"] }] });
      return jsonResponse({ provider_name: "北海AI", model: "gpt-image-1.5", base_url: "https://sub.beibeihai.xyz/v1", api_key_configured: false });
    });

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get("[data-history-id='7']").trigger("click");
    await flushPromises();

    expect(wrapper.get(".prompt-row textarea").element.value).toBe("蓝色海面");
    expect(wrapper.find(".image-grid img").attributes("src")).toBe("/api/history/7/images/9");
  });
});
```

- [ ] **Step 3: Run tests and verify the new layout contract fails**

Run: `npm test -- --run`

Expected: tests fail because `.composer-dock`, history loading, and API Key settings UI do not exist.

- [ ] **Step 4: Implement settings and history state**

In `App.vue`, keep `API_BASE = import.meta.env.VITE_API_BASE ?? ""`, remove `providerName` editing, retain `model` and `apiKey`, and add:

```typescript
type HistorySummary = { id: number; kind: "generate" | "analyze"; status: "pending" | "completed" | "failed"; prompt: string; model: string; created_at: string; error_message?: string | null };
type HistoryDetail = HistorySummary & { analysis_text?: string | null; images: Array<{ id: number; role: "reference" | "generated"; url: string }> };

const baseUrl = ref("https://sub.beibeihai.xyz/v1");
const apiKeyConfigured = ref(false);
const history = ref<HistorySummary[]>([]);
const historyError = ref("");

async function loadHistory() {
  try {
    const response = await fetch(`${API_BASE}/api/history`);
    const data = await response.json();
    if (!response.ok) throw new Error(readableError(data, "无法加载历史记录"));
    history.value = data;
    historyError.value = "";
  } catch (exception) {
    historyError.value = exception instanceof Error ? exception.message : "无法加载历史记录";
  }
}

async function openHistory(historyId: number) {
  const response = await fetch(`${API_BASE}/api/history/${historyId}`);
  const data: HistoryDetail = await response.json();
  if (!response.ok) throw new Error(readableError(data, "无法加载历史详情"));
  prompt.value = data.prompt;
  model.value = data.model;
  analysis.value = data.analysis_text ?? "";
  generated.value = data.images
    .filter((image) => image.role === "generated")
    .map((image) => ({ url: `${API_BASE}${image.url}` }));
}
```

Initialize with `Promise.all([loadProviders(), loadRuntimeSettings(), loadHistory()])`. After generation or analysis completes, call `await loadHistory()`.

Change settings PUT body to `{ model: model.value.trim(), api_key: apiKey.value.trim() || null }`; display Base URL in a read-only input and API Key status without exposing the stored value.

- [ ] **Step 5: Reorganize the template**

Move the existing fixed provider, model, API Key, read-only Base URL, detail, count, and settings-save controls into `.control-panel`. Move the existing result heading, analysis note, image grid, and empty state unchanged into `.result-panel`. Add this concrete history section at the end of the left panel:

```vue
<section class="history-section">
  <div class="history-heading">
    <span>历史记录</span>
    <small>{{ history.length }}</small>
  </div>
  <button
    v-for="item in history"
    :key="item.id"
    type="button"
    class="history-item"
    :data-history-id="item.id"
    @click="openHistory(item.id)"
  >
    <span>{{ item.prompt }}</span>
    <small>{{ item.model }}</small>
  </button>
  <p v-if="historyError" class="history-error">{{ historyError }}</p>
</section>
```

Make `.workspace-panel` the second direct child of `.studio-grid`, with `.result-panel` first and this exact composer second:

```vue
<section class="composer-dock">
  <div class="reference-row">
    <div class="upload-zone" @dragover.prevent @drop.prevent="setFile(($event as DragEvent).dataTransfer?.files[0])">
      <input id="image-input" type="file" accept="image/png,image/jpeg,image/webp,image/gif" @change="setFile(($event.target as HTMLInputElement).files?.[0])" />
      <label for="image-input">
        <Upload :size="18" />
        <span>{{ imageFile ? imageFile.name : "添加参考图片" }}</span>
        <small>支持 PNG、JPG、WEBP 或 GIF</small>
      </label>
    </div>
    <div v-if="previewUrl" class="file-chip">
      <img :src="previewUrl" alt="参考图片预览" />
      <span>{{ imageFile?.name }}</span>
      <button type="button" aria-label="移除参考图片" @click="clearFile"><X :size="15" /></button>
    </div>
    <button type="button" class="secondary-action" :disabled="!canAnalyze" @click="analyzeImage">
      <LoaderCircle v-if="busy === 'analyze'" class="spin" :size="17" />
      <ImagePlus v-else :size="17" />
      分析图片
    </button>
  </div>
  <div class="prompt-row">
    <label>提示词<textarea v-model="prompt" placeholder="描述一个场景、一种质感，或一个不可能存在的物体..."></textarea></label>
    <button type="button" class="primary-action" :class="{ 'cancel-action': busy === 'generate' }" :disabled="busy === 'analyze'" @click="handleGenerateClick">
      <X v-if="busy === 'generate'" :size="17" />
      <LoaderCircle v-else-if="busy === 'analyze'" class="spin" :size="17" />
      <Sparkles v-else :size="17" />
      {{ busy === "generate" ? "取消生成" : "生成图片" }}
    </button>
  </div>
  <p v-if="error" class="error-message">{{ error }}</p>
</section>
```

Do not render a batch prompt label or textarea. Keep `batchPrompts` and the existing `prompts` request field unchanged for backend compatibility.

- [ ] **Step 6: Run frontend tests**

Run: `npm test -- --run`

Expected: both workspace tests pass.

- [ ] **Step 7: Commit frontend behavior**

```powershell
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/src/App.vue frontend/src/App.test.ts
git commit -m "feat: 添加工作台配置与历史交互"
```

---

### Task 7: Fixed Composer Styling And Development Startup

**Files:**
- Modify: `frontend/src/style.css`
- Modify: `start-dev.ps1`

- [ ] **Step 1: Capture the current failing layout evidence**

Start the services and capture desktop/mobile screenshots before the CSS change. Verify that the current page has prompt/reference controls inside the left panel and no center-bottom dock. Save screenshots under `.playwright-cli/` only; do not commit them.

- [ ] **Step 2: Implement the desktop layout**

Use the existing palette and hard-edge visual system. Add stable geometry:

```css
.studio-grid{grid-template-columns:minmax(300px,340px) minmax(0,1fr);height:calc(100vh - 78px);overflow:hidden}
.control-panel{height:100%;overflow-y:auto}
.workspace-panel{position:relative;min-width:0;height:100%;display:grid;grid-template-rows:minmax(0,1fr) auto;background:#fffdf8}
.result-panel{min-height:0;overflow-y:auto;padding-bottom:32px}
.composer-dock{position:relative;z-index:4;border-top:2px solid #191817;background:#fffdf8;padding:12px clamp(16px,2.5vw,36px) 16px}
.reference-row{display:flex;align-items:center;gap:10px;min-height:48px}
.reference-row .upload-zone{flex:1;margin:0}
.prompt-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:end}
.prompt-row label{margin:0}
.prompt-row textarea{height:92px;min-height:92px;max-height:180px}
.prompt-row .primary-action{min-width:132px;min-height:48px;border:2px solid #191817}
.history-section{margin-top:24px;border-top:2px solid #191817;padding-top:14px}
.history-item{width:100%;display:grid;gap:4px;text-align:left;border:0;border-bottom:1px solid rgba(25,24,23,.28);background:transparent;padding:10px 2px;cursor:pointer}
.history-item span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:800}
.history-item small{color:#625d54}
```

Ensure the result panel's last image remains fully visible above the composer; do not use negative margins or viewport-scaled font sizes.

- [ ] **Step 3: Implement responsive document flow**

```css
@media(max-width:800px){
  .studio-grid{height:auto;min-height:calc(100vh - 68px);grid-template-columns:1fr;overflow:visible}
  .control-panel{height:auto;overflow:visible;border-right:0;border-bottom:2px solid #191817}
  .workspace-panel{height:auto;display:flex;flex-direction:column}
  .result-panel{overflow:visible;order:1}
  .composer-dock{position:static;order:2}
  .reference-row{align-items:stretch;flex-direction:column}
  .prompt-row{grid-template-columns:1fr}
  .prompt-row .primary-action{width:100%}
}
```

Remove the old mobile sticky `.action-row` rule because actions now live in the composer.

- [ ] **Step 4: Align the startup script with the verified ports**

Set `$frontendPort = 3000`, start Vite with `--host 127.0.0.1`, and wait on `http://127.0.0.1:$frontendPort/`. Preserve backend port `8002` and process cleanup behavior.

- [ ] **Step 5: Build and run automated tests**

Run: `npm test -- --run`

Run: `npm run build`

Expected: Vitest passes and Vite produces `dist/` without errors.

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests -v`

Expected: all backend tests pass.

- [ ] **Step 6: Commit layout and startup changes**

```powershell
git add frontend/src/style.css start-dev.ps1
git commit -m "style: 调整工作台与底部创作区布局"
```

---

### Task 8: Browser And Persistence Verification

**Files:**
- No production files unless verification reveals a defect; any defect requires a new failing test before a fix.

- [ ] **Step 1: Start both services with the project script**

Run: `powershell -ExecutionPolicy Bypass -File .\start-dev.ps1`

Expected endpoints:

- Frontend: `http://127.0.0.1:3000/`
- Backend health: `http://127.0.0.1:8002/health`

- [ ] **Step 2: Verify the desktop workspace at 1440x1000**

Check that the left panel contains parameters and history, the center result panel scrolls independently, reference upload appears immediately above the prompt, and the composer remains visible without covering the last result. Confirm there is no visible “批量提示词”.

- [ ] **Step 3: Verify the mobile workspace at 390x844**

Check that controls flow in this order: parameters, results, reference upload, prompt. Confirm there is no horizontal overflow, no overlapping controls, and button text fits.

- [ ] **Step 4: Verify settings persistence and fixed fields**

Use the UI to save an API Key and custom model, restart the backend, and confirm the model and configured state remain. Send a manual PUT containing `base_url` or `provider_name` and confirm HTTP 422. Confirm no API response or browser-visible state contains the API Key.

- [ ] **Step 5: Verify generation and analysis history**

Generate one image and analyze one uploaded image. Confirm both appear in history after refresh and after backend restart. Open each history item and verify generated images and analysis text restore correctly from SQLite. Inspect `GET /api/history` and confirm it contains no Base64 or BLOB data.

- [ ] **Step 6: Run final verification**

Run: `backend\.venv\Scripts\python.exe -m pytest backend/tests -v`

Run: `npm test -- --run`

Run: `npm run build`

Expected: all commands succeed with no test failures or build errors.

- [ ] **Step 7: Commit any verification-only test adjustments**

If no defect was found, do not create an empty commit. If a defect was found, add its regression test and focused fix, rerun Step 6, then commit only those files with a Chinese message describing the corrected behavior.
