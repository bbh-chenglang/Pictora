# Remove Settings Version Update Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Remove the version-update module and its frontend-only implementation from the settings page while preserving the backend version endpoint and build configuration.

**Architecture:** Keep the change inside `frontend/src/App.vue` and its existing integration test file. The settings page will continue to render profile, API configuration, community, and theme sections; only version-update markup and its dedicated state/handlers will be removed. The backend `/api/version` route and build-time version variables are untouched.

**Tech Stack:** Vue 3, TypeScript, Vue Test Utils, Vitest, Vite.

---

### Task 1: Replace obsolete settings/version tests with the removal contract

**Files:**
- Modify: `frontend/src/App.test.ts:273-343`
- Modify: `frontend/src/App.test.ts:364-432`

- [x] **Step 1: Write the failing test**

Replace the existing settings-page assertions so the settings test explicitly asserts that the removed section is absent and that navigation makes no version request:

```ts
  it("opens settings without the version update module", async () => {
    const fetchMock = vi.mocked(fetch);
    const wrapper = mount(App);
    await flushPromises();

    await wrapper.get("[data-action='settings']").trigger("click");

    expect(window.location.pathname).toBe("/settings");
    expect(wrapper.find(".settings-page").exists()).toBe(true);
    expect(wrapper.text()).not.toContain("版本更新");
    expect(wrapper.find("[data-action='version-update']").exists()).toBe(false);
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/api/version?"))).toBe(false);
  });
```

Update the community/theme test expected headings to contain only `界面主题`, and remove the three tests that click `[data-action='version-update']` because that control is intentionally gone.

- [x] **Step 2: Run the focused test to verify it fails**

Run:

```powershell
npm test -- --run src/App.test.ts -t "opens settings without the version update module|labels the community number"
```

Expected: the new removal test fails because the current settings page still renders `版本更新` and the existing markup still contains `[data-action='version-update']`; the focused suite may also fail on the old expected heading until it is updated.

### Task 2: Remove frontend version-update implementation and markup

**Files:**
- Modify: `frontend/src/App.vue:471-472, 985, 990-1073, settings template version section`
- Modify: `frontend/src/style.css:2901, 3014-3080`

- [x] **Step 1: Remove only dedicated state and handlers**

Delete `updateStatus`, `serverVersion`, `CLIENT_VERSION`, `versionActionLabel`, `versionStatusMessage`, `checkForUpdate`, `applyUpdate`, and `handleVersionAction` from `frontend/src/App.vue`. Keep `API_BASE`, `apiFetch`, the backend API, and unrelated version/build configuration intact.

- [x] **Step 2: Remove the settings-page version section**

Delete the settings template block containing the `版本更新` heading, `[data-action='version-update']`, `.version-status`, `.version-meta`, and any version update explanatory text. Keep the surrounding `.settings-preferences` container and the `界面主题` section so the remaining layout stays valid.

Also delete the now-unused `.settings-update`, `.version-update-copy`, `.version-update-heading`, `.version-meta`, `.version-status`, and `.version-update-action` rules from `frontend/src/style.css`.

- [x] **Step 3: Run the focused test to verify it passes**

Run:

```powershell
npm test -- --run src/App.test.ts -t "opens settings without the version update module|labels the community number"
```

Expected: PASS, with no `/api/version?` request when opening settings.

### Task 3: Verify regression surface and preserved backend behavior

**Files:**
- No backend files modified.

- [x] **Step 1: Run the complete frontend test suite**

Run `npm test -- --run` from `frontend`.

Expected: all tests pass, including the updated settings tests; no test references `[data-action='version-update']` or the removed version status selectors.

- [x] **Step 2: Run type checking**

Run `npm run typecheck` from `frontend`.

Expected: `vue-tsc --noEmit` exits successfully with no unused-symbol or template errors.

- [x] **Step 3: Run the production build**

Run `npm run build` from `frontend`.

Expected: Vite produces the production bundle successfully.

- [x] **Step 4: Confirm backend version endpoint and build configuration are unchanged**

Run:

```powershell
git diff -- backend/app/main.py frontend/vite.config.ts frontend/package.json
rg -n "api/version|APP_VERSION|VITE_APP_VERSION" backend frontend
```

Expected: no diff in the backend endpoint or build configuration, and the existing `/api/version`, `APP_VERSION`, and `VITE_APP_VERSION` references remain available.

- [x] **Step 5: Commit the implementation**

Run:

```powershell
git add frontend/src/App.vue frontend/src/App.test.ts
git commit -m "feat: 移除设置页版本更新模块"
```
