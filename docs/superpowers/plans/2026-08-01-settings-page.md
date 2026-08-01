# 独立设置页面 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将工作台账户入口改为“设置”，提供独立 `/settings` 页面管理 API Key、密码和暂不支持的主题选项。

**Architecture:** 继续使用现有单页 Vue 应用，通过 `window.history.pushState` 管理 `/settings` 与工作台视图，不引入新的路由依赖。设置页复用现有 Cookie 会话和 `/api/auth/me`、`/api/settings`、`/api/auth/password`、`/api/auth/logout` 接口，主页面模型选择与自动保存逻辑保持不变。

**Tech Stack:** Vue 3、TypeScript、Vitest、Vue Test Utils、Vite。

---

### Task 1: Add settings route state and navigation

**Files:**
- Modify: `frontend/src/App.vue`
- Test: `frontend/src/App.test.ts`

- [ ] **Step 1: Write failing navigation tests**

Add tests that mock `/api/auth/me` as an authenticated user and assert:

```typescript
it("opens the settings view from the settings button", async () => {
  const wrapper = mount(App);
  await flushPromises();
  await wrapper.get("[data-action='settings']").trigger("click");
  expect(wrapper.find(".settings-page").exists()).toBe(true);
  expect(wrapper.find(".studio-grid").exists()).toBe(false);
  expect(window.location.pathname).toBe("/settings");
});

it("returns from settings to the workspace without logging out", async () => {
  const wrapper = mount(App);
  await flushPromises();
  await wrapper.get("[data-action='settings']").trigger("click");
  await wrapper.get("[data-action='back-to-workspace']").trigger("click");
  expect(wrapper.find(".studio-grid").exists()).toBe(true);
  expect(wrapper.find(".settings-page").exists()).toBe(false);
});
```

Add a test that sets `window.history.replaceState({}, "", "/settings")` before mounting and confirms an authenticated user starts on the settings view.

- [ ] **Step 2: Run the focused tests and verify RED**

Run from `frontend`:

```powershell
npx vitest run src/App.test.ts --pool=threads --maxWorkers=1 --minWorkers=1
```

Expected: failures because the topbar still exposes the old password action and there is no settings view or route state.

- [ ] **Step 3: Implement route state without adding a dependency**

Add `currentView = ref<"workspace" | "settings">(window.location.pathname === "/settings" ? "settings" : "workspace")`, a `navigateToSettings()` function that calls `history.pushState({}, "", "/settings")`, a `navigateToWorkspace()` function that calls `history.pushState({}, "", "/")`, and a `popstate` listener that updates `currentView`.

Replace the topbar password button with:

```vue
<button type="button" class="secondary-action" data-action="settings" @click="navigateToSettings">
  设置
</button>
```

Render the existing workspace inside `v-if="currentView === 'workspace'"`; render the settings page inside `v-else`. Add `data-action="back-to-workspace"` to the return control. Remove any topbar password action that opens a modal.

- [ ] **Step 4: Run the navigation tests and commit**

Run the focused Vitest command again. Expected: navigation tests and all existing authenticated workspace tests pass.

```powershell
git add frontend/src/App.vue frontend/src/App.test.ts
git commit -m "feat: 添加独立设置页导航"
```

### Task 2: Build settings sections and connect existing APIs

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/style.css`
- Test: `frontend/src/App.test.ts`

- [ ] **Step 1: Write failing settings interaction tests**

Add tests that mount at `/settings` as an authenticated user and assert:

```typescript
it("renders API key, password, and disabled theme sections without model selection", async () => {
  const wrapper = mount(App);
  await flushPromises();
  expect(wrapper.get(".settings-page").text()).toContain("接口配置");
  expect(wrapper.get(".settings-page").text()).toContain("修改密码");
  expect(wrapper.get(".settings-page").text()).toContain("主题");
  expect(wrapper.find(".settings-page .model-select").exists()).toBe(false);
  expect(wrapper.find(".theme-option:disabled").exists()).toBe(true);
});

it("saves only the API key from settings", async () => {
  const wrapper = mount(App);
  await flushPromises();
  await wrapper.get("[data-field='api-key']").setValue("new-private-key");
  await wrapper.get("[data-action='save-api-key']").trigger("click");
  await flushPromises();
  const request = vi.mocked(fetch).mock.calls.find(([input, init]) => String(input).endsWith("/api/settings") && init?.method === "PUT");
  expect(JSON.parse(String(request?.[1]?.body))).toEqual({ model: "gpt-image-1.5", api_key: "new-private-key" });
  expect(wrapper.text()).not.toContain("new-private-key");
});

it("submits password change and returns to login after success", async () => {
  const wrapper = mount(App);
  await flushPromises();
  await wrapper.get("[data-field='old-password']").setValue("secret6");
  await wrapper.get("[data-field='new-password']").setValue("changed6");
  await wrapper.get("[data-field='new-password-confirmation']").setValue("changed6");
  await wrapper.get("[data-action='change-password']").trigger("click");
  await flushPromises();
  expect(wrapper.find(".auth-page").exists()).toBe(true);
});
```

- [ ] **Step 2: Run the tests and verify RED**

Run the same focused Vitest command. Expected: failures because the settings sections and controls are not present.

- [ ] **Step 3: Implement the settings page**

Add a `.settings-page` with:

- Header: back button, current username, logout button.
- API section: password-type API Key input with `data-field="api-key"`, configured status, save button with `data-action="save-api-key"`. Submit `{ model: model.value, api_key: enteredKey || "" }` to `/api/settings`; never render the raw value after saving.
- Password section: three password inputs with the three `data-field` attributes and a `data-action="change-password"` submit control. Require a six-character new password and matching confirmation, then call `/api/auth/password` with `old_password`, `new_password`, and `new_password_confirmation`. On success clear local credentials and show login.
- Theme section: disabled radio controls labeled 亮色 and 暗色 with a visible 暂不支持 label. Do not add theme state or persistence.

Use the existing `apiKeyConfigured` state and settings response. Do not render the model selector in `.settings-page`; leave `.model-select` in the workspace. Add compact responsive styles with the existing hard-edge border and spacing system.

- [ ] **Step 4: Run tests and build**

Run:

```powershell
npx vitest run src/App.test.ts --pool=threads --maxWorkers=1 --minWorkers=1
npm run build
```

Expected: all frontend tests pass and Vite builds successfully.

- [ ] **Step 5: Commit settings behavior**

```powershell
git add frontend/src/App.vue frontend/src/App.test.ts frontend/src/style.css
git commit -m "feat: 添加独立设置页面功能"
```

### Task 3: Unauthorized routing and browser verification

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/App.test.ts`

- [ ] **Step 1: Write failing unauthorized test**

Mock `/api/auth/me` with `401`, start at `/settings`, mount the app, and assert the app shows `.auth-page` and changes the path to `/` or the login state. Mock a protected settings request with `401` and assert the same redirect behavior.

- [ ] **Step 2: Implement centralized unauthorized handling**

When `/api/auth/me` is not successful, set the auth view to login and use `history.replaceState({}, "", "/")`. Apply the same transition when settings API calls return `401`. Keep logout and password-change redirects on the login view.

- [ ] **Step 3: Run final checks**

```powershell
npx vitest run --pool=threads --maxWorkers=1 --minWorkers=1
npm run build
```

Start the existing development services and verify manually:

- Workbench topbar shows 设置 instead of 修改密码.
- Settings opens at `/settings` and hides the workspace.
- API configuration contains no model selector and does not echo the full API Key.
- Password change requires old password and matching new passwords.
- Theme controls are visibly disabled.
- Back returns to the workspace, logout returns to login, and unauthenticated `/settings` redirects to login.

## Self-review

- All confirmed requirements are covered: independent settings page, API Key-only interface configuration, password change, disabled theme options, model selector remaining on the workspace, session preservation on back navigation, and unauthorized redirects.
- No database or backend changes are required.
- No TODO/TBD placeholders remain.
