# 用户管理与个人数据隔离 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 GenImage 增加用户名密码账户、服务端持久化 Cookie 会话，并将 API Key、设置和历史记录按用户隔离。

**Architecture:** 使用 bcrypt 存储密码哈希，使用随机会话令牌的哈希值保存服务端会话；认证依赖从 `HttpOnly` Cookie 解析当前用户。SQLite 使用一次性 schema 版本迁移删除旧全局表并创建用户归属字段，所有业务 repository/API 通过当前用户 ID 做后端隔离。

**Tech Stack:** FastAPI、Pydantic、aiosqlite、SQLite、bcrypt、Vue 3、TypeScript、Vitest、Vue Test Utils、happy-dom。

---

### Task 1: Authentication primitives and database schema

**Files:**
- Create: `backend/app/auth.py`
- Create: `backend/app/repositories/user_repository.py`
- Create: `backend/app/schemas/auth.py`
- Modify: `backend/requirements.txt`
- Modify: `backend/app/database.py`
- Test: `backend/tests/test_auth.py`
- Test: `backend/tests/test_database.py`

- [ ] **Step 1: Add the bcrypt dependency**

Add `bcrypt` to `backend/requirements.txt`. Do not use reversible encryption for passwords and do not store the submitted password in repository objects or response models.

- [ ] **Step 2: Write failing password and repository tests**

Add tests that exercise real bcrypt and SQLite code:

```python
@pytest.mark.asyncio
async def test_password_hash_is_not_reversible_or_equal_to_plaintext():
    hashed = hash_password("secret6")
    assert hashed != "secret6"
    assert verify_password("secret6", hashed)
    assert not verify_password("wrong6", hashed)


@pytest.mark.asyncio
async def test_user_repository_creates_unique_user_and_stores_settings(tmp_path):
    database_path = tmp_path / "users.db"
    await initialize_database(database_path)
    repository = UserRepository(database_path)

    user = await repository.create("alice", hash_password("secret6"))
    await repository.update_settings(user.id, model="gpt-image-1.5", api_key="key-a")

    loaded = await repository.get_by_username("alice")
    assert loaded is not None
    assert loaded.id == user.id
    assert loaded.password_hash != "secret6"
    assert (await repository.get_settings(user.id)).api_key == "key-a"
    with pytest.raises(UserAlreadyExistsError):
        await repository.create("alice", hash_password("another6"))
```

Add a database test that initializes a legacy database containing `settings`, `history`, and `history_images`, sets `PRAGMA user_version = 1`, runs initialization, and asserts those tables are absent while `users`, `user_sessions`, `history`, and `history_images` have the new schema. Add a second initialization assertion proving the version-2 database is not cleared again.

- [ ] **Step 3: Run the focused tests and verify RED**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_auth.py backend/tests/test_database.py -v
```

Expected: collection or assertion failures because the auth module, repository, and new schema do not exist yet.

- [ ] **Step 4: Implement the schema migration and user repository**

In `database.py`, introduce `SCHEMA_VERSION = 2` and a versioned initializer. For databases with `user_version < 2`, drop legacy `history_images`, `history`, and `settings` in that order, then create:

```sql
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    api_key TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT 'gpt-image-1.5',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS user_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('generate', 'analyze')),
    status TEXT NOT NULL CHECK (status IN ('pending', 'completed', 'failed')),
    prompt TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    detail TEXT NOT NULL,
    image_count INTEGER NOT NULL DEFAULT 1,
    size TEXT,
    analysis_text TEXT,
    elapsed_ms INTEGER,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_history_user_created_at ON history(user_id, created_at DESC, id DESC);
```

Keep the existing history columns and image constraints, adding `user_id` to `history`. Set `PRAGMA user_version = 2` only after the schema and indexes are committed. The initializer must no longer seed a global settings row or read default API Key values.

`UserRepository` must provide `create`, `get_by_id`, `get_by_username`, `update_settings`, `get_settings`, `update_password`, `create_session`, `get_session_user`, `delete_session`, and `delete_sessions_for_user`. Translate SQLite unique violations into `UserAlreadyExistsError`.

- [ ] **Step 5: Implement password and token helpers**

In `auth.py`, define `SESSION_COOKIE = "genimage_session"` and `SESSION_MAX_AGE = 30 * 24 * 60 * 60`. Implement `hash_password(password: str) -> str` with bcrypt, `verify_password(password: str, password_hash: str) -> bool` with bcrypt verification, `new_session_token() -> str` with `secrets.token_urlsafe(32)`, and `hash_session_token(token: str) -> str` with SHA-256. Store an ISO UTC expiry exactly 30 days after session creation.

- [ ] **Step 6: Run the focused tests and verify GREEN**

Run the same pytest command. Expected: all auth primitive, repository, migration, and idempotence tests pass.

- [ ] **Step 7: Commit the authentication primitives**

```powershell
git add backend/requirements.txt backend/app/auth.py backend/app/database.py backend/app/repositories/user_repository.py backend/app/schemas/auth.py backend/tests/test_auth.py backend/tests/test_database.py
git commit -m "feat: 添加用户认证基础设施"
```

### Task 2: Session dependency and authentication HTTP API

**Files:**
- Modify: `backend/app/dependencies.py`
- Create: `backend/app/api/auth.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: Write failing auth endpoint tests**

Add API tests using `TestClient` and a temporary database override. Cover registration with `password` and `password_confirmation`, automatic authenticated access to `GET /api/auth/me`, duplicate username, password mismatch, login with a wrong password, logout invalidation, and password change invalidating the old client session. Assert response bodies never contain `password_hash`, raw passwords, or API Keys.

Use concrete expectations such as:

```python
response = client.post("/api/auth/register", json={
    "username": "alice", "password": "secret6", "password_confirmation": "secret6"
})
assert response.status_code == 201
assert response.cookies.get("genimage_session")
assert client.get("/api/auth/me").json() == {
    "username": "alice", "api_key_configured": False
}
```

- [ ] **Step 2: Run the auth tests and verify RED**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_api.py -k auth -v
```

Expected: failures because the auth router and current-user dependency are not registered.

- [ ] **Step 3: Add schemas and current-user dependency**

Define strict request models in `schemas/auth.py`: registration username/password/confirmation, login username/password, and password-change old/new/confirmation. Validate non-empty username, minimum six-character passwords, and matching confirmation fields. Define a safe `CurrentUser` response with only `id`, `username`, and configuration state.

Add `get_current_user` in `dependencies.py`: read the Cookie, hash it, reject missing/unknown/expired sessions with `401` and the existing `{"error": {"code": "authentication_required", "message": "请先登录"}}` format, and return the loaded user. Add a user repository dependency and clear it in `clear_dependency_caches` if cached.

- [ ] **Step 4: Implement auth routes and Cookie behavior**

Implement register, login, logout, me, and password-change routes. Registration and login must call `set_cookie(key=SESSION_COOKIE, value=raw_token, max_age=SESSION_MAX_AGE, httponly=True, samesite="lax", secure=production_flag, path="/")`. Logout must call `delete_cookie` with the same key/path. Registration creates the session before returning `201`, so the client is authenticated immediately. Password change verifies the old password, updates the bcrypt hash, deletes all user sessions, and returns success without reusing the old session.

- [ ] **Step 5: Register the router and run GREEN**

Register `auth_router` in `main.py`, keep `/health` public, and run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_api.py -k auth -v
```

Expected: all auth endpoint tests pass.

- [ ] **Step 6: Commit the auth HTTP layer**

```powershell
git add backend/app/dependencies.py backend/app/api/auth.py backend/app/main.py backend/app/schemas/auth.py backend/tests/test_api.py
git commit -m "feat: 添加 Cookie 会话认证接口"
```

### Task 3: Per-user settings and history repositories

**Files:**
- Modify: `backend/app/repositories/settings_repository.py`
- Modify: `backend/app/repositories/history_repository.py`
- Modify: `backend/app/services/history_service.py`
- Modify: `backend/app/dependencies.py`
- Test: `backend/tests/test_history_repository.py`
- Test: `backend/tests/test_history_service.py`
- Test: `backend/tests/test_database.py`

- [ ] **Step 1: Write failing ownership tests**

Change repository test setup to create two users named `alice` and `bob`. Assert settings written for Alice are not returned for Bob. Create one history for each user and assert `list(alice_id)` contains only Alice's row, `get(alice_id, bob_history_id)` returns `None`, and `get_image(alice_id, bob_history_id, bob_image_id)` returns `None`. Call `HistoryService.generate(request, image_service, user_id=alice_id)` and assert the newly created row stores Alice's ID.

- [ ] **Step 2: Run repository/service tests and verify RED**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_history_repository.py backend/tests/test_history_service.py -v
```

Expected: failures because current methods do not accept or filter by `user_id`.

- [ ] **Step 3: Make settings repository user-scoped**

Replace the global `settings` repository with user-backed settings methods. `get(user_id)` and `update(user_id, model, api_key)` must read and write `users.model` and `users.api_key`, returning the existing safe provider settings shape with fixed provider name/base URL. Preserve the rule that `api_key=None` leaves the existing key unchanged; use an explicit empty string to clear it.

- [ ] **Step 4: Make history repository methods user-scoped**

Add `user_id` to `create`. Add `user_id` to `list`, `get`, and `get_image` SQL predicates. For detail/image access, require both the requested history ID and current user ID in the same query path. Keep BLOB bytes out of summary/detail responses and preserve existing image URLs.

- [ ] **Step 5: Pass ownership through HistoryService**

Add a required `user_id` parameter to `generate` and `analyze`; pass it to every create/add-image/complete/fail repository operation. Update dependency factories to construct user-aware settings, history, and provider services.

- [ ] **Step 6: Run GREEN and commit**

Run the focused repository/service tests, then the full backend suite:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_history_repository.py backend/tests/test_history_service.py backend/tests/test_database.py -v
backend\.venv\Scripts\python.exe -m pytest backend/tests -v
```

Expected: all pass after updating existing fixtures to create an authenticated user and passing that user ID explicitly.

```powershell
git add backend/app/repositories/settings_repository.py backend/app/repositories/history_repository.py backend/app/services/history_service.py backend/app/dependencies.py backend/tests/test_history_repository.py backend/tests/test_history_service.py backend/tests/test_database.py
git commit -m "feat: 按用户隔离设置与历史记录"
```

### Task 4: Protect and update business APIs

**Files:**
- Modify: `backend/app/api/settings.py`
- Modify: `backend/app/api/history.py`
- Modify: `backend/app/api/generate.py`
- Modify: `backend/app/api/analyze.py`
- Modify: `backend/app/api/providers.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_api.py`

- [ ] **Step 1: Write failing authorization tests**

Add tests proving every protected endpoint returns `401` without a session, that authenticated user A can update/read only A settings, and that user A receives `404` for user B history details and images. Add generation and analysis tests asserting the fake history service receives the authenticated user ID. Keep `/health` public.

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_api.py -k "settings or history or generate or analyze or providers" -v
```

Expected: unauthenticated calls currently succeed or use the old global repository.

- [ ] **Step 3: Add `get_current_user` to every protected route**

Require the current user in providers, settings, generate, analyze, and history routes. Pass `current_user.id` to repository/service calls. Settings responses must continue to expose only `api_key_configured`; never return `api_key`.

- [ ] **Step 4: Remove global settings defaults from startup and provider resolution**

Update `main.py` lifespan to initialize only the versioned database schema. Update `get_provider_registry` to load the current user settings and build the compatible provider with that user’s key/model. Do not cache a registry across users; cache only static dependencies or key by user ID and settings values. Ensure providers with no configured key still return a safe empty provider list.

- [ ] **Step 5: Run GREEN and commit**

Run the focused authorization tests and full backend suite. Expected: all pass, with old tests updated to establish a session before protected calls.

```powershell
git add backend/app/api/settings.py backend/app/api/history.py backend/app/api/generate.py backend/app/api/analyze.py backend/app/api/providers.py backend/app/main.py backend/tests/test_api.py
git commit -m "feat: 保护业务接口并绑定当前用户"
```

### Task 5: Frontend authentication and account settings

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/App.test.ts`
- Modify: `frontend/src/style.css`

- [ ] **Step 1: Write failing Vue tests**

Add fetch fixtures for `/api/auth/me`, `/api/auth/register`, `/api/auth/login`, `/api/auth/logout`, and `/api/auth/password`. Add five concrete tests named `shows registration fields and enters the workspace after successful registration`, `shows login when auth/me returns 401 and enters the workspace after login`, `logs out and returns to the login view`, `submits old password and matching new password confirmation`, and `does not render a stored API key value`. Assert the exact request bodies for registration and password change, the visible transition to the workspace/login view, and the absence of the raw fixture API Key from rendered text. The tests must assert request bodies and visible UI behavior, not just mocked function call counts.

- [ ] **Step 2: Run Vitest and verify RED**

Run:

```powershell
cd frontend
npm test -- --run src/App.test.ts
```

Expected: failures because the app currently mounts the workspace without an auth view or account controls.

- [ ] **Step 3: Add auth state and credential forms**

In `App.vue`, add an auth state (`checking`, `authenticated`, `login`, `register`) and call `/api/auth/me` on mount with `credentials: "include"`. Render login/register forms before the workspace. Validate non-empty username, six-character minimum passwords, and matching confirmations before sending requests. On successful registration or login, set the authenticated user and load providers, settings, and history.

- [ ] **Step 4: Add account controls and API calls**

Add username display, logout action, password-change form, and API Key settings. Every `fetch` must use `credentials: "include"`. Handle `401` centrally by returning to login. Keep API Key input blank and use only `api_key_configured` in rendered state; blank submission clears it.

- [ ] **Step 5: Run GREEN and commit**

Run `npm test -- --run src/App.test.ts` and then `npm run build`. Expected: all frontend tests pass and the production build succeeds.

```powershell
git add frontend/src/App.vue frontend/src/App.test.ts frontend/src/style.css
git commit -m "feat: 添加前端登录注册与账户设置"
```

### Task 6: End-to-end verification and cleanup

**Files:**
- Modify: `frontend/vite.config.ts` only if the verified dev proxy or test configuration needs adjustment.
- Modify: `README.md` to document account registration, 30-day sessions, and the destructive legacy-data migration.
- Test: `backend/tests/test_api.py`
- Test: `frontend/src/App.test.ts`

- [ ] **Step 1: Run all automated checks**

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests -v
cd frontend
npm test -- --run
npm run build
```

Expected: all backend and frontend tests pass and the frontend build completes without warnings that indicate a broken import or template.

- [ ] **Step 2: Start the local services**

Run the existing development script and verify `http://127.0.0.1:5173/` plus `http://127.0.0.1:8002/health`. Use a fresh database or explicitly confirm the version-1-to-version-2 migration before browser testing.

- [ ] **Step 3: Verify the user journeys in a real browser**

Register user A and confirm the app opens directly to the workspace. Save A’s API Key, generate a record, log out, register user B, and confirm B sees neither A’s key state nor A’s history. Confirm A cannot read B’s history by changing the URL ID. Test login, logout, password change, and re-login with the new password.

- [ ] **Step 4: Review the security surface**

Inspect browser-visible responses and SQLite rows to confirm passwords are bcrypt hashes, session tokens are hashed, full API Keys are absent from JSON responses, and old global tables/data are gone after the one-time migration. Confirm Cookie flags include `HttpOnly`, `SameSite=Lax`, 30-day `Max-Age`, and production `Secure`.

- [ ] **Step 5: Commit documentation or focused fixes only**

If verification exposes a defect, add its failing regression test first, make the smallest fix, rerun all checks, and commit the affected files. Otherwise commit only the README update:

```powershell
git add README.md
git commit -m "docs: 补充用户账户使用说明"
```

## Self-review

- Spec coverage: authentication, automatic registration login, 30-day sessions, password hashing and confirmation, plaintext API Key storage without response exposure, legacy data deletion, per-user settings/history/image authorization, frontend login/register/account flows, `401` handling, and automated/browser verification each have explicit tasks.
- Placeholder scan: no TODO, TBD, or unspecified implementation steps remain.
- Type consistency: all user-scoped repository methods use `user_id`; all protected routes use `get_current_user`; `HistoryService` receives the same user ID passed from the route.
- Migration safety: legacy tables are removed only while upgrading databases below version 2; version-2 databases are not cleared on later starts.
