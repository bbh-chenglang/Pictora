# Parameter Menu Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a checkmark for selected parameter-menu values and provide six image-size choices with usage descriptions.

**Architecture:** Extend the existing `SIZE_OPTIONS` records with descriptions, then use value comparisons directly in the existing Vue menu loops to apply selected state and render a Lucide check icon. Reuse the current option-selection handlers and generated-request size field.

**Tech Stack:** Vue 3, TypeScript, lucide-vue-next, Vitest, Vue Test Utils, CSS.

---

### Task 1: Define selected menu feedback with tests

**Files:**
- Modify: `frontend/src/App.test.ts`
- Test: `frontend/src/App.test.ts`

- [ ] **Step 1: Write failing selected-option and size-description tests**

Add a test that opens the default size menu and requires six option buttons, usage text, and exactly one selected option with a check icon:

```ts
await wrapper.get("[data-parameter-trigger='size']").trigger("click");
const menu = wrapper.get("[data-parameter-menu='size']");
expect(menu.findAll(".parameter-option")).toHaveLength(6);
expect(menu.text()).toContain("正方形，头像");
expect(menu.text()).toContain("桌面壁纸，风景");
expect(menu.findAll(".parameter-option.is-selected")).toHaveLength(1);
expect(menu.get(".parameter-option.is-selected svg").exists()).toBe(true);
```

- [ ] **Step 2: Run the targeted test and verify RED**

Run from `frontend`:

```powershell
npx vitest run src/App.test.ts --pool=threads --maxWorkers=1 --minWorkers=1
```

Expected: FAIL because the existing size menu has three entries, no descriptions, and no selected-state icon.

### Task 2: Render descriptions and selected checkmarks

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/style.css`
- Test: `frontend/src/App.test.ts`

- [ ] **Step 1: Extend size records and import the icon**

Add `Check` to the Lucide imports. Replace `SIZE_OPTIONS` with six records containing `label`, `value`, and `description`; use `1024x1024`, `1024x1536`, `1152x1536`, `1536x1152`, `864x1536`, and `1536x864` respectively.

- [ ] **Step 2: Render selected state for every menu**

Give each `.parameter-option` a conditional `is-selected` class when its value equals `model`, `size`, `detail`, or `imageCount`. Render `<Check v-if="..." :size="15" />` after each selected option label. Render the size description after its label.

- [ ] **Step 3: Style menu rows and selected feedback**

Make `.parameter-option` a two-column layout for its label/description and the trailing check icon. Give `.parameter-option.is-selected` the existing blue text color and give its SVG a fixed right-side placement. Use a muted smaller font for `.parameter-option-description`.

- [ ] **Step 4: Run the targeted test and verify GREEN**

Run from `frontend`:

```powershell
npx vitest run src/App.test.ts --pool=threads --maxWorkers=1 --minWorkers=1
```

Expected: all tests pass and the selected option is observable for every menu type.

### Task 3: Verify and commit

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/style.css`
- Modify: `frontend/src/App.test.ts`

- [ ] **Step 1: Run production verification**

Run from `frontend`:

```powershell
npx vitest run src/App.test.ts --pool=threads --maxWorkers=1 --minWorkers=1
npm run build
```

Expected: Vitest reports zero failures and Vite exits with code 0.

- [ ] **Step 2: Commit only scoped frontend files and this plan**

Run:

```powershell
git add frontend/src/App.vue frontend/src/style.css frontend/src/App.test.ts docs/superpowers/plans/2026-08-01-parameter-menu-selection.md
git commit -m "feat: 标记参数菜单已选选项"
```

Expected: a new commit on `v1`; existing backend personal-data changes remain unstaged.
