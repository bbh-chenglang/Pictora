# Prompt Parameter Toolbar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move image generation parameters into an upward-opening toolbar below the prompt and place the light-blue image analysis action above image generation.

**Architecture:** Keep the UI state in `App.vue`, adding one ref to identify the open menu and shared handlers to update the existing generation refs. Replace the desktop two-column workspace with one workspace panel and anchor the popup menus with CSS inside the composer.

**Tech Stack:** Vue 3 Composition API, TypeScript, Vitest, Vue Test Utils, CSS.

---

### Task 1: Define the desktop toolbar behavior with failing tests

**Files:**
- Modify: `frontend/src/App.test.ts`
- Test: `frontend/src/App.test.ts`

- [ ] **Step 1: Write failing layout and menu tests**

Replace the side-panel assertions with tests that require the new controls:

```ts
expect(wrapper.find(".control-panel").exists()).toBe(false);
expect(wrapper.find(".panel-resizer").exists()).toBe(false);
expect(wrapper.findAll("[data-parameter-trigger]")).toHaveLength(4);

await wrapper.get("[data-parameter-trigger='model']").trigger("click");
expect(wrapper.find("[data-parameter-menu='model']").exists()).toBe(true);
await wrapper.get("[data-parameter-trigger='size']").trigger("click");
expect(wrapper.find("[data-parameter-menu='model']").exists()).toBe(false);
expect(wrapper.find("[data-parameter-menu='size']").exists()).toBe(true);
```

- [ ] **Step 2: Write a failing action-stack test**

Require choosing a model option to save settings and the analysis button to precede generation:

```ts
await wrapper.get("[data-parameter-trigger='model']").trigger("click");
await wrapper.get("[data-parameter-option='gpt-image-2']").trigger("click");
await flushPromises();
expect(JSON.parse(String(settingsUpdate?.[1]?.body))).toEqual({
  model: "gpt-image-2",
  api_key: null,
});
expect(wrapper.get(".composer-actions").findAll("button")[0].classes()).toContain("analyze-action");
```

- [ ] **Step 3: Verify RED**

Run `npx vitest run src/App.test.ts --pool=threads --maxWorkers=1 --minWorkers=1` from `frontend`.

Expected: FAIL because the side panel still exists and parameter triggers are absent.

### Task 2: Implement menu state and toolbar markup

**Files:**
- Modify: `frontend/src/App.vue`
- Test: `frontend/src/App.test.ts`

- [ ] **Step 1: Add the shared menu state and handlers**

Add this state alongside the existing refs:

```ts
type ParameterMenu = "model" | "size" | "detail" | "count";
const openParameterMenu = ref<ParameterMenu | null>(null);

function toggleParameterMenu(menu: ParameterMenu) {
  openParameterMenu.value = openParameterMenu.value === menu ? null : menu;
}

function closeParameterMenu() {
  openParameterMenu.value = null;
}
```

Add selection handlers. The model handler sets `model.value`, invokes `applyRuntimeSettings()`, and closes. Size, detail, and count handlers set their corresponding existing refs and close.

- [ ] **Step 2: Replace the side panel with menus below the prompt**

Remove `<aside class="control-panel">` and the `.panel-resizer`. Below the prompt, render four `data-parameter-trigger` buttons. Each conditionally renders an upward option list identified by `data-parameter-menu`; option buttons use the model, size, detail, and count values already defined by the component.

- [ ] **Step 3: Add close behavior**

Register a document pointer-down handler that closes the menu only when the event target is outside `.parameter-toolbar`, and a keydown handler that calls `closeParameterMenu()` for `Escape`. Register in `onMounted` and remove in `onUnmounted`.

- [ ] **Step 4: Create the vertical action stack**

Move the existing analysis button out of `.reference-row` and into `.composer-actions` next to the prompt. Keep `:disabled="!canAnalyze"` and `@click="analyzeImage"`, add `analyze-action`, and place the existing generation button directly after it.

- [ ] **Step 5: Verify GREEN**

Run `npx vitest run src/App.test.ts --pool=threads --maxWorkers=1 --minWorkers=1` from `frontend`.

Expected: all tests pass.

### Task 3: Implement desktop Native UI styling

**Files:**
- Modify: `frontend/src/style.css`
- Test: `frontend/src/App.test.ts`

- [ ] **Step 1: Remove side-panel layout styles**

Convert `.studio-grid` to a single-column full-height container. Remove rules for `.control-panel`, `.panel-resizer`, `.image-parameter-section`, and `.parameter-grid`; retain the result-and-composer vertical structure in `.workspace-panel`.

- [ ] **Step 2: Add toolbar and action styles**

Add `.parameter-toolbar` with a horizontal flex layout and `position: relative`. Add `.parameter-menu` positioned above its trigger using `bottom: calc(100% + 8px)`, a 1px neutral border, 8px radius, white background, and restrained shadow. Add `.parameter-trigger` and `.parameter-option` with the existing neutral and blue design tokens.

Style `.composer-actions` as a fixed-width vertical grid. Style `.analyze-action` with a light-blue background, blue text, and a light-blue border. Leave `.primary-action` as the generation action style. Do not add mobile breakpoints.

- [ ] **Step 3: Verify full frontend behavior**

Run these commands from `frontend`:

```powershell
npx vitest run src/App.test.ts --pool=threads --maxWorkers=1 --minWorkers=1
npm run build
```

Expected: Vitest reports no failures and Vite exits with code 0.

### Task 4: Verify and commit the feature

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/style.css`
- Modify: `frontend/src/App.test.ts`

- [ ] **Step 1: Check the scoped diff**

Run `git diff --check` and inspect `git diff -- frontend/src/App.vue frontend/src/style.css frontend/src/App.test.ts`.

Expected: no whitespace errors and no unrelated files staged.

- [ ] **Step 2: Commit the feature**

Run:

```powershell
git add frontend/src/App.vue frontend/src/style.css frontend/src/App.test.ts
git commit -m "feat: 添加提示词参数工具栏"
```

Expected: a new commit on `v1`; existing uncommitted backend personal-data changes remain unstaged.
