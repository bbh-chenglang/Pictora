# 提示词库“五百飘雪”主题统一 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将提示词选择、管理、编辑和删除确认统一为浅色雪景主题，不改变任何提示词操作。

**Architecture:** 新建提示词模块 CSS 令牌文件。四个组件导入该文件并替换暗色硬编码，保留 Vue 模板结构、API 调用和响应式布局；只有管理页根节点增加稳定主题挂钩供测试。

**Tech Stack:** Vue 3、TypeScript、Vitest、Vue Test Utils、CSS Custom Properties。

---

### Task 1: 主题令牌与回归测试

**Files:**
- Create: `frontend/src/styles/prompt-snowfall-theme.css`
- Modify: `frontend/src/components/PromptPickerPopover.spec.ts`
- Modify: `frontend/src/components/PromptsView.spec.ts`

- [ ] **Step 1: 编写失败的令牌断言**

在两个 spec 导入 `readFileSync`，然后新增以下测试：

```ts
it("uses snowfall tokens instead of legacy dark palette", () => {
  const source = readFileSync(new URL("./PromptPickerPopover.vue", import.meta.url), "utf8");
  expect(source).toContain("var(--prompt-snow-surface)");
  expect(source).not.toContain("background:#1b1d22");
});
```

```ts
it("uses snowfall tokens for page, borders, and text", () => {
  const source = readFileSync(new URL("./PromptsView.vue", import.meta.url), "utf8");
  expect(source).toContain("var(--prompt-snow-page)");
  expect(source).toContain("var(--prompt-snow-border)");
  expect(source).toContain("var(--prompt-snow-text)");
});
```

- [ ] **Step 2: 确认断言失败**

Run: `npm test -- --run src/components/PromptPickerPopover.spec.ts src/components/PromptsView.spec.ts`

Expected: FAIL because components have no `--prompt-snow-*` references.

- [ ] **Step 3: 创建最小令牌表**

```css
:root {
  --prompt-snow-page: rgba(244, 249, 253, .72);
  --prompt-snow-surface: rgba(255, 255, 255, .9);
  --prompt-snow-surface-muted: rgba(239, 247, 253, .88);
  --prompt-snow-border: rgba(129, 176, 211, .45);
  --prompt-snow-border-strong: rgba(85, 146, 194, .66);
  --prompt-snow-text: #17324d;
  --prompt-snow-text-muted: #60778d;
  --prompt-snow-accent: #1b5f9c;
  --prompt-snow-overlay: rgba(37, 70, 100, .34);
  --prompt-snow-danger: #b94a4a;
  --prompt-snow-shadow: 0 18px 46px rgba(38, 82, 120, .2);
}
```

- [ ] **Step 4: 为相关组件导入令牌**

在 `PromptPickerPopover.vue`、`PromptsView.vue`、`PromptEditorDialog.vue`、`ConfirmDialog.vue` 的 scoped style 首行加入：

```css
@import "../styles/prompt-snowfall-theme.css";
```

- [ ] **Step 5: 验证通过并提交**

Run: `npm test -- --run src/components/PromptPickerPopover.spec.ts src/components/PromptsView.spec.ts`

Expected: PASS.

Commit: `git add frontend/src/styles/prompt-snowfall-theme.css frontend/src/components/*.spec.ts frontend/src/components/*.vue && git commit -m "feat: 添加提示词库雪景主题令牌"`

### Task 2: 选择与编辑弹窗

**Files:**
- Modify: `frontend/src/components/PromptPickerPopover.vue:105-114`
- Modify: `frontend/src/components/PromptEditorDialog.vue:54-62`
- Create: `frontend/src/components/PromptEditorDialog.spec.ts`

- [ ] **Step 1: 编写失败的编辑弹窗主题测试**

```ts
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("PromptEditorDialog theme", () => {
  it("uses snowfall tokens for layer, panel, and fields", () => {
    const source = readFileSync(new URL("./PromptEditorDialog.vue", import.meta.url), "utf8");
    expect(source).toContain("var(--prompt-snow-overlay)");
    expect(source).toContain("var(--prompt-snow-surface)");
    expect(source).toContain("var(--prompt-snow-surface-muted)");
  });
});
```

在 picker spec 增加断言，要求 `--prompt-snow-overlay`、`--prompt-snow-surface`、`--prompt-snow-accent` 存在。

- [ ] **Step 2: 确认失败**

Run: `npm test -- --run src/components/PromptPickerPopover.spec.ts src/components/PromptEditorDialog.spec.ts`

Expected: FAIL because these dialogs still use dark layer, panel and input colors.

- [ ] **Step 3: 替换弹窗颜色**

层使用 `--prompt-snow-overlay`，面板和列表使用 `--prompt-snow-surface`，输入和筛选控件使用 `--prompt-snow-surface-muted`，分隔线使用 `--prompt-snow-border`，标题使用 `--prompt-snow-text`，辅助文字使用 `--prompt-snow-text-muted`，分类强调使用 `--prompt-snow-accent`，弹窗阴影使用 `--prompt-snow-shadow`。不改模板类名、watcher 或 submit 函数。

- [ ] **Step 4: 验证并提交**

Run: `npm test -- --run src/components/PromptPickerPopover.spec.ts src/components/PromptEditorDialog.spec.ts`

Expected: PASS.

Commit: `git add frontend/src/components/PromptPickerPopover.vue frontend/src/components/PromptPickerPopover.spec.ts frontend/src/components/PromptEditorDialog.vue frontend/src/components/PromptEditorDialog.spec.ts && git commit -m "feat: 统一提示词弹窗雪景主题"`

### Task 3: 管理页与删除确认

**Files:**
- Modify: `frontend/src/components/PromptsView.vue:86-101`
- Modify: `frontend/src/components/ConfirmDialog.vue:1-17`
- Modify: `frontend/src/components/PromptsView.spec.ts`
- Create: `frontend/src/components/ConfirmDialog.spec.ts`

- [ ] **Step 1: 添加失败的稳定主题挂钩测试**

把管理页根元素改为：

```vue
<section class="prompts-page" data-theme="snowfall">
```

把条目改为：

```vue
<article v-for="entry in visibleEntries" :key="entry.id" class="prompt-entry prompt-snow-surface">
```

先在 `PromptsView.spec.ts` 断言根节点 `data-theme` 为 `snowfall`，条目有 `prompt-snow-surface` 类，运行并确认失败。

新建 `ConfirmDialog.spec.ts`，使用 `readFileSync` 断言含 `--prompt-snow-overlay`、`--prompt-snow-surface`、`--prompt-snow-danger`，运行并确认失败。

- [ ] **Step 2: 迁移管理页样式**

页面使用 `--prompt-snow-page`，卡片使用 `--prompt-snow-surface`，搜索/分类控件使用 `--prompt-snow-surface-muted`，边线使用 `--prompt-snow-border`，标题使用 `--prompt-snow-text`，说明、日期、空状态和正文使用 `--prompt-snow-text-muted`，分类使用 `--prompt-snow-accent`，卡片加 `--prompt-snow-shadow`。保留现有布局和 760px 响应式规则。

- [ ] **Step 3: 添加确认弹窗浅色样式**

```css
.confirm-layer { position:fixed; inset:0; z-index:1000; display:grid; place-items:center; padding:22px; background:var(--prompt-snow-overlay); }
.confirm-dialog { width:min(420px,100%); padding:24px; border:1px solid var(--prompt-snow-border-strong); background:var(--prompt-snow-surface); color:var(--prompt-snow-text); box-shadow:var(--prompt-snow-shadow); }
.confirm-dialog p { color:var(--prompt-snow-text-muted); line-height:1.55; }
.confirm-actions .danger-action { background:var(--prompt-snow-danger); color:#fff; }
```

- [ ] **Step 4: 验证并提交**

Run: `npm test -- --run src/components/PromptsView.spec.ts src/components/ConfirmDialog.spec.ts`

Expected: PASS.

Commit: `git add frontend/src/components/PromptsView.vue frontend/src/components/PromptsView.spec.ts frontend/src/components/ConfirmDialog.vue frontend/src/components/ConfirmDialog.spec.ts && git commit -m "feat: 统一提示词管理雪景主题"`

### Task 4: 全量验证

**Files:** Verify only the files above.

- [ ] **Step 1: 执行全部前端质量检查**

Run: `npm test -- --run; npm run typecheck; npm run build`

Expected: all commands exit 0.

- [ ] **Step 2: 浏览器检查核心状态**

Run: `npm run dev -- --host 127.0.0.1`

在桌面及 390px 宽度检查选择提示词、管理页加载/筛选/空态、创建/编辑、删除确认。确认无暗色表面、文本与冰蓝边框可读、无重叠和横向溢出。

- [ ] **Step 3: 提交验证后的改动**

Commit: `git add frontend/src/styles/prompt-snowfall-theme.css frontend/src/components/PromptPickerPopover.vue frontend/src/components/PromptPickerPopover.spec.ts frontend/src/components/PromptEditorDialog.vue frontend/src/components/PromptEditorDialog.spec.ts frontend/src/components/PromptsView.vue frontend/src/components/PromptsView.spec.ts frontend/src/components/ConfirmDialog.vue frontend/src/components/ConfirmDialog.spec.ts && git commit -m "test: 验证提示词库雪景主题"`
