# 项目历史记录管理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `v1` 分支为每个用户增加项目管理，使生成/分析历史按项目归属、展示和删除，并用左侧项目列表替代旧历史抽屉。

**Architecture:** 在现有 SQLite + FastAPI + Vue 单页结构上增加 `projects` 持久化层；数据库初始化采用可重复执行的版本迁移，将旧历史回填到每个用户的“第一个项目”。项目接口返回项目及历史摘要，历史写入由服务层校验用户和项目归属，前端在 `App.vue` 中维护当前项目和工作区，项目侧栏负责展示和操作，确认/输入对话框负责危险操作和重命名。

**Tech Stack:** Python 3.12, SQLite, FastAPI, Pydantic, pytest, Vue 3, TypeScript, Vite。

---

### Task 1: 建立数据库迁移与项目模型

**Files:**
- Modify: `backend/app/database.py`
- Create: `backend/app/repositories/project_repository.py`
- Create: `backend/app/schemas/project.py`
- Test: `backend/tests/test_database.py`
- Test: `backend/tests/test_project_repository.py`

- [ ] **Step 1: 写迁移失败测试**

在 `backend/tests/test_database.py` 增加临时 SQLite 初始化测试：从旧版包含 `users`、无 `projects`、且 `history.project_id` 缺失的 schema 启动，断言会创建 `projects`、为每个用户创建唯一“第一个项目”、回填旧历史并令迁移可重复执行。断言新建用户初始化时也有项目。

在 `backend/tests/test_project_repository.py` 增加以下行为测试：项目按用户隔离；创建项目名称去除首尾空白且拒绝空名/超过 80 字符；同一用户不能重复名称；按 `updated_at DESC, id DESC` 返回项目和最多/全部历史摘要；重命名更新 `updated_at`；删除项目在事务中删除其历史和图片，并且最后一个项目先创建“第一个项目”。

- [ ] **Step 2: 运行测试确认失败**

运行：`backend\.venv\Scripts\python.exe -m pytest backend/tests/test_database.py backend/tests/test_project_repository.py -q`

预期：失败，原因是 `projects` 表、`project_id` 列和项目 repository 尚不存在，而不是测试收集错误。

- [ ] **Step 3: 实现最小迁移和 repository**

在 `database.py` 中保留旧 schema 数据，按事务执行版本迁移：创建 `projects`，为每个 `users.id` 插入“第一个项目”，将旧历史写入对应项目，再将 `history` 重建为 `project_id INTEGER NOT NULL` 并创建 `(project_id, created_at DESC, id DESC)` 索引；迁移完成才提升 schema version。所有外键删除依赖显式 SQL 顺序或 SQLite `ON DELETE CASCADE`，不能清空历史表。

在 `project_repository.py` 提供清晰的用户限定方法，接口至少包括：

```python
list_with_history(user_id: int) -> list[ProjectSummary]
get_owned(project_id: int, user_id: int) -> Project
create(user_id: int, name: str) -> Project
rename(project_id: int, user_id: int, name: str) -> Project
delete(project_id: int, user_id: int) -> ProjectDeleteResult
delete_history(project_id: int, user_id: int, history_ids: list[int]) -> int
```

`delete` 和 `delete_history` 必须使用同一个数据库事务，所有条件同时包含 `user_id` 与目标 ID；无归属记录返回已有业务层可识别的 not-found/forbidden 错误。项目 schema 定义 `Project`, `HistorySummary`, `ProjectSummary` 及创建/重命名/批量删除请求。

- [ ] **Step 4: 运行迁移和 repository 测试**

运行同一 pytest 命令，预期全部通过；再运行 `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_history_repository.py -q`，确认历史已有测试未被破坏。

- [ ] **Step 5: 提交独立后端基础变更**

```powershell
git add backend/app/database.py backend/app/repositories/project_repository.py backend/app/schemas/project.py backend/tests/test_database.py backend/tests/test_project_repository.py
git commit -m "feat(项目): 增加项目数据模型和迁移"
```

### Task 2: 增加项目 API 并改造历史归属

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/dependencies.py`
- Modify: `backend/app/api/history.py`
- Modify: `backend/app/api/generate.py`
- Modify: `backend/app/api/analyze.py`
- Modify: `backend/app/services/history_service.py`
- Modify: `backend/app/repositories/history_repository.py`
- Modify: `backend/app/schemas/generate.py`
- Modify: `backend/app/schemas/analyze.py`
- Test: `backend/tests/test_projects_api.py`
- Test: `backend/tests/test_api.py`
- Test: `backend/tests/test_history_service.py`

- [ ] **Step 1: 写 API/service 失败测试**

在 `backend/tests/test_projects_api.py` 覆盖认证用户的 GET/POST/PATCH/DELETE 项目、批量删除当前项目历史、非法项目 ID、跨用户访问和最后项目删除；断言删除项目后历史图片也不存在。

在现有 API/service 测试中先断言生成和分析请求必须有 `project_id`，且服务写入的 `history.project_id` 等于请求项目；缺少项目、项目属于其他用户或项目不存在时返回明确 4xx。保留旧 `/api/history` 的兼容行为，但列表只能返回当前用户数据，详情也必须检查历史所属项目。

- [ ] **Step 2: 运行目标测试确认失败**

运行：`backend\.venv\Scripts\python.exe -m pytest backend/tests/test_projects_api.py backend/tests/test_api.py backend/tests/test_history_service.py -q`

预期：失败于项目路由不存在、请求 schema 缺少 `project_id` 或历史服务没有项目校验。

- [ ] **Step 3: 实现项目路由和项目归属校验**

在 `api/projects.py` 中新增：

```python
GET    /api/projects
POST   /api/projects
PATCH  /api/projects/{project_id}
DELETE /api/projects/{project_id}
DELETE /api/projects/{project_id}/history
```

所有路由使用现有会话用户依赖；创建/重命名复用 schema 长度校验；删除项目返回切换后的项目 ID、删除数量和项目摘要。批量删除只接受去重后的有限 ID 列表，并只删除当前项目、当前用户的记录。

扩展生成/分析 schema 的 `project_id: int`，在 API 中把它传入 `HistoryService.generate/analyze`。服务先通过 project repository 校验归属，再调用 history repository 写入；读取详情时同样校验用户和项目。更新 repository 的查询、插入、删除参数，使所有历史操作以 `user_id` 和 `project_id` 为边界。

- [ ] **Step 4: 运行后端全量测试**

运行：`backend\.venv\Scripts\python.exe -m pytest backend/tests -q`

预期：通过；若旧测试构造请求未提供项目 ID，测试 fixture 应创建默认项目并在请求中带上该 ID，而不是降低生产校验。

- [ ] **Step 5: 提交 API 变更**

```powershell
git add backend/app/main.py backend/app/dependencies.py backend/app/api/projects.py backend/app/api/history.py backend/app/api/generate.py backend/app/api/analyze.py backend/app/services/history_service.py backend/app/repositories/history_repository.py backend/app/schemas/generate.py backend/app/schemas/analyze.py backend/tests/test_projects_api.py backend/tests/test_api.py backend/tests/test_history_service.py
git commit -m "feat(项目): 增加项目 API 和历史归属校验"
```

### Task 3: 以 TDD 建立前端项目状态与侧栏

**Files:**
- Create: `frontend/src/components/ProjectSidebar.vue`
- Create: `frontend/src/components/ConfirmDialog.vue`
- Create: `frontend/src/components/ProjectDialog.vue`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/style.css` (若现有全局样式文件为其他名称，以实际入口为准)
- Test: `frontend/src/components/ProjectSidebar.spec.ts`
- Test: `frontend/src/App.spec.ts`

- [ ] **Step 1: 写前端失败测试**

使用项目现有测试框架；若当前未安装测试框架，先在 `frontend/package.json` 增加 Vitest、Vue Test Utils 和 jsdom。测试组件行为：默认渲染“第一个项目”；新建项目后选中它；项目重命名和删除事件带出项目 ID；历史超过 5 条默认只显示最近 5 条，点击展开显示全部；勾选历史后出现批量删除；当前项目切换会发出选择事件；新建对话清空工作区但保留项目 ID。

- [ ] **Step 2: 运行测试确认失败**

运行：`npm --prefix frontend test -- --run`

预期：失败于组件文件/状态不存在，先修正测试配置错误直到得到功能缺失的失败。

- [ ] **Step 3: 实现侧栏和对话框组件**

`ProjectSidebar` 接收 `projects`, `selectedProjectId`, `loading`，发出 `select-project`, `create-project`, `rename-project`, `delete-project`, `delete-history` 和 `toggle-expanded`；每个项目下展示历史摘要，使用 `history.length > 5` 控制折叠，默认 false。所有删除动作先由 `ConfirmDialog` 确认，确认文案包含项目名或历史条数；`ProjectDialog` 负责新建/重命名并提交非空、80 字符以内名称。

- [ ] **Step 4: 接入 App.vue 的项目状态**

增加 `projects`, `selectedProjectId`, `projectLoading`, `projectError`, 对话框状态和 `loadProjects/selectProject/createProject/renameProject/deleteProject/deleteHistory/startNewConversation`。初次加载项目接口后选中返回的当前/首个项目；生成和分析请求 JSON 增加 `project_id`；项目切换清空生成结果、分析内容、参考图、提示词和当前历史详情。移除 `historyOpen/openHistory/closeHistory`、顶部 `.history-trigger` 和 `.history-drawer`，保留当前项目下的侧栏历史入口。

- [ ] **Step 5: 运行前端测试和构建**

运行：`npm --prefix frontend test -- --run` 和 `npm --prefix frontend run build`，预期测试通过且 Vite 构建无 TypeScript/Vue 模板错误。

- [ ] **Step 6: 提交前端项目工作区**

```powershell
git add frontend/src/App.vue frontend/src/components frontend/src/style.css frontend/package.json frontend/package-lock.json frontend/*config* frontend/*setup*
git commit -m "feat(项目): 用项目侧栏管理历史记录"
```

### Task 4: 删除确认、交互回归与完整校验

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/components/ProjectSidebar.vue`
- Modify: `backend/tests/test_projects_api.py`
- Modify: `frontend/src/components/ProjectSidebar.spec.ts`
- Test: `backend/tests/test_personal_data.py`

- [ ] **Step 1: 增加危险操作回归测试**

断言取消遮罩、Escape 和取消按钮都不会调用删除 API；确认项目删除后自动选中剩余项目；确认最后项目删除后使用新建的“第一个项目”；批量删除空选择时不显示操作；正在请求时禁用重复提交。后端增加跨用户项目/历史 ID 的删除回归，确保响应为业务错误且数据库行未变化。

- [ ] **Step 2: 实现交互边界和错误恢复**

所有删除按钮使用危险样式并在请求期间禁用；删除成功后只刷新项目列表并保留有效选择，删除失败保留原列表和选择并显示中文错误；详情加载失败不清空侧栏；项目切换和新建对话不删除历史。对历史摘要使用稳定 key 和固定缩略图尺寸，避免展开/勾选导致布局跳动。

- [ ] **Step 3: 运行完整验证**

运行：

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests -q
npm --prefix frontend test -- --run
npm --prefix frontend run build
git diff --check
```

预期：后端和前端测试全部通过、构建成功、`git diff --check` 无输出。手动启动开发服务，验证左侧项目创建/切换/展开、单条/批量历史删除、项目删除和新建对话。

- [ ] **Step 4: 仅提交本功能文件到 v1**

先执行 `git status --short`，逐项确认不暂存既有用户管理改动；只将本计划产生或明确改造的文件加入暂存区，然后提交：

```powershell
git add <本功能文件列表>
git commit -m "feat(项目): 完成项目历史记录管理"
git branch --show-current
```

预期当前分支为 `v1`，所有提交只发生在 v1 worktree，不执行 `git push`。

---

## 自检结果

- 规格覆盖：项目创建/选择/重命名/删除、默认项目、按项目历史、5 条折叠、单条/批量删除、级联图片删除、二次确认、最后项目兜底、新建对话、移除旧历史入口均由 Task 1-4 覆盖。
- 数据边界：项目、历史和图片删除均要求当前用户归属并在事务中执行；旧历史迁移不清空数据。
- 测试覆盖：迁移、repository、API/service、前端组件、确认取消、跨用户隔离、构建和差异格式均有明确命令。
- 类型一致性：后端统一使用 `project_id`；前端统一使用 `selectedProjectId`，生成/分析请求都从该状态取值。
