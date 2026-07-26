# GenImage Modern Workspace UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 GenImage 改造成冷白灰与蓝色强调的扁平化工作台，并加入可调宽左栏、折叠接口配置、右侧历史抽屉和完整可见的浅色全屏预览。

**Architecture:** 保留现有 Vue 单页和 API 数据流，在 `App.vue` 内增加少量 UI 状态与 Pointer Events 处理；模板重排但不改变生成、分析和持久化接口。`style.css` 使用设计令牌统一视觉，组件测试覆盖状态与结构，Playwright 验证真实尺寸和响应式布局。

**Tech Stack:** Vue 3、TypeScript、Lucide Vue、Vitest、Vue Test Utils、CSS、Playwright CLI

---

### Task 1: 用组件测试锁定新信息结构

**Files:**
- Modify: `frontend/src/App.test.ts`
- Test: `frontend/src/App.test.ts`

- [ ] **Step 1: 替换左栏结构测试**

断言接口配置使用默认关闭的 `details`、Base URL 不显示、外部链接安全属性正确，并验证模型选项：

```typescript
const connection = wrapper.get("details.connection-section");
expect(connection.attributes("open")).toBeUndefined();
expect(connection.text()).toContain("接口配置");
expect(connection.text()).not.toContain("Base URL");

const apiKeyLink = connection.get("a.api-key-link");
expect(apiKeyLink.attributes("href")).toBe("https://sub.beibeihai.xyz/home");
expect(apiKeyLink.attributes("target")).toBe("_blank");
expect(apiKeyLink.attributes("rel")).toBe("noopener noreferrer");

expect(wrapper.findAll(".model-select option").map((option) => option.text())).toEqual([
  "gpt-image-2",
  "gpt-image-1.5",
  "gpt-image-1",
  "gpt-image-1Mini",
]);
expect(wrapper.get(".control-panel").text()).not.toContain("历史记录");
```

- [ ] **Step 2: 添加历史抽屉测试**

```typescript
expect(wrapper.find(".history-drawer").exists()).toBe(false);
await wrapper.get(".history-trigger").trigger("click");
expect(wrapper.get(".history-drawer").attributes("role")).toBe("dialog");
await wrapper.get(".history-drawer-close").trigger("click");
expect(wrapper.find(".history-drawer").exists()).toBe(false);
```

更新历史恢复测试，先打开抽屉再点击记录，并断言恢复后抽屉关闭：

```typescript
await wrapper.get(".history-trigger").trigger("click");
await wrapper.get("[data-history-id='7']").trigger("click");
await flushPromises();
expect(wrapper.find(".history-drawer").exists()).toBe(false);
```

- [ ] **Step 3: 添加左栏拖拽测试**

```typescript
vi.stubGlobal("innerWidth", 1440);
await wrapper.get(".panel-resizer").trigger("pointerdown", { clientX: 320 });
window.dispatchEvent(new PointerEvent("pointermove", { clientX: 450 }));
expect(wrapper.get(".studio-grid").attributes("style")).toContain("450px");
window.dispatchEvent(new PointerEvent("pointermove", { clientX: 900 }));
expect(wrapper.get(".studio-grid").attributes("style")).toContain("480px");
window.dispatchEvent(new PointerEvent("pointerup"));
await wrapper.get(".panel-resizer").trigger("keydown", { key: "ArrowLeft" });
expect(wrapper.get(".studio-grid").attributes("style")).toContain("464px");
```

- [ ] **Step 4: 运行测试并确认失败原因**

Run: `cd frontend && .\\node_modules\\.bin\\vitest.cmd run src/App.test.ts`

Expected: FAIL，失败原因分别为折叠区、模型下拉框、历史抽屉和拖拽手柄尚不存在。

### Task 2: 实现工作台状态与模板

**Files:**
- Modify: `frontend/src/App.vue`
- Test: `frontend/src/App.test.ts`

- [ ] **Step 1: 增加模型、抽屉和左栏状态**

```typescript
const MODEL_OPTIONS = [
  "gpt-image-2",
  "gpt-image-1.5",
  "gpt-image-1",
  "gpt-image-1Mini",
] as const;
const DEFAULT_MODEL = MODEL_OPTIONS[0];
const PANEL_MIN_WIDTH = 280;
const PANEL_MAX_WIDTH = 480;

const historyOpen = ref(false);
const sidebarWidth = ref(320);
const resizingSidebar = ref(false);
```

加载设置时仅允许下拉框中的值，否则在前端回退但不写数据库：

```typescript
model.value = (MODEL_OPTIONS as readonly string[]).includes(data.model)
  ? data.model
  : DEFAULT_MODEL;
```

- [ ] **Step 2: 增加抽屉与拖拽处理函数**

```typescript
function closeHistory() {
  historyOpen.value = false;
}

function updateSidebarWidth(clientX: number) {
  const viewportMax = Math.max(PANEL_MIN_WIDTH, window.innerWidth - 560);
  sidebarWidth.value = Math.min(PANEL_MAX_WIDTH, viewportMax, Math.max(PANEL_MIN_WIDTH, clientX));
}

function handleSidebarPointerMove(event: PointerEvent) {
  if (resizingSidebar.value) updateSidebarWidth(event.clientX);
}

function stopSidebarResize() {
  resizingSidebar.value = false;
  window.removeEventListener("pointermove", handleSidebarPointerMove);
  window.removeEventListener("pointerup", stopSidebarResize);
}

function startSidebarResize(event: PointerEvent) {
  if (window.matchMedia("(max-width: 860px)").matches) return;
  resizingSidebar.value = true;
  updateSidebarWidth(event.clientX);
  window.addEventListener("pointermove", handleSidebarPointerMove);
  window.addEventListener("pointerup", stopSidebarResize);
}

function handleSidebarKeydown(event: KeyboardEvent) {
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
  event.preventDefault();
  updateSidebarWidth(sidebarWidth.value + (event.key === "ArrowLeft" ? -16 : 16));
}
```

全局 `Esc` 先关闭图片预览，否则关闭历史抽屉。组件卸载时移除拖拽监听。

- [ ] **Step 3: 重排模板**

将 `.studio-grid` 绑定 CSS 变量：

```vue
<div class="studio-grid" :style="{ '--sidebar-width': `${sidebarWidth}px` }">
```

左栏使用默认折叠的接口配置和模型下拉框：

```vue
<details class="connection-section">
  <summary><span>接口配置</span><small>{{ apiKeyConfigured ? "已配置" : "未配置" }}</small></summary>
  <div class="connection-body">
    <label>API Key<input v-model="apiKey" type="password" autocomplete="off" /></label>
    <a class="api-key-link" href="https://sub.beibeihai.xyz/home" target="_blank" rel="noopener noreferrer"><ExternalLink :size="16" />获取 API Key</a>
  </div>
</details>
<label>模型名称<select v-model="model" class="model-select"><option v-for="option in MODEL_OPTIONS" :key="option" :value="option">{{ option }}</option></select></label>
```

在左栏和画布间添加分隔条：

```vue
<div class="panel-resizer" role="separator" aria-label="调整参数栏宽度" aria-orientation="vertical" :aria-valuenow="sidebarWidth" :aria-valuemin="PANEL_MIN_WIDTH" :aria-valuemax="PANEL_MAX_WIDTH" tabindex="0" @pointerdown="startSidebarResize" @keydown="handleSidebarKeydown"></div>
```

顶栏加入 `.history-trigger`，页面末尾加入 `.drawer-layer` 与 `.history-drawer`；历史记录点击时调用现有 `openHistory` 后关闭抽屉。

- [ ] **Step 4: 运行组件测试并修正到通过**

Run: `cd frontend && .\\node_modules\\.bin\\vitest.cmd run src/App.test.ts`

Expected: 组件测试全部通过。

### Task 3: 替换为现代扁平视觉

**Files:**
- Modify: `frontend/src/style.css`

- [ ] **Step 1: 建立冷白灰与蓝色设计令牌**

```css
:root {
  font-family: Inter, "Segoe UI", ui-sans-serif, system-ui, sans-serif;
  color: #111827;
  background: #f7f7f8;
  --bg: #f7f7f8;
  --surface: #ffffff;
  --surface-subtle: #f8fafc;
  --text: #111827;
  --muted: #64748b;
  --line: #e2e8f0;
  --line-strong: #cbd5e1;
  --blue: #002fa7;
  --blue-hover: #00237d;
  --blue-soft: #eef3ff;
  --danger: #dc2626;
}
```

- [ ] **Step 2: 更新工作台布局与控件**

```css
.studio-grid {
  grid-template-columns: var(--sidebar-width, 320px) 6px minmax(0, 1fr);
}

.panel-resizer {
  position: relative;
  cursor: col-resize;
  touch-action: none;
  background: var(--bg);
}

.panel-resizer::after {
  content: "";
  position: absolute;
  inset: 0 2px;
  background: transparent;
}

.panel-resizer:hover::after,
.panel-resizer:focus-visible::after {
  background: var(--blue);
}
```

将顶部栏、左栏、输入框、图片卡片和底部创作区统一为白色表面、`1px` 浅灰边界、`6–8px` 圆角和蓝色主按钮，移除黄色、粗黑边和硬阴影。

- [ ] **Step 3: 实现历史抽屉与浅色全屏预览**

```css
.drawer-layer,
.image-lightbox {
  position: fixed;
  inset: 0;
  z-index: 100;
  background: rgba(241, 245, 249, .82);
}

.history-drawer {
  width: min(400px, 100vw);
  height: 100dvh;
  margin-left: auto;
  background: var(--surface);
  border-left: 1px solid var(--line);
  box-shadow: -16px 0 40px rgba(15, 23, 42, .12);
}

.image-lightbox > img {
  max-width: calc(100vw - 32px);
  max-height: calc(100dvh - 32px);
  object-fit: contain;
}
```

移动端在 `860px` 以下隐藏 `.panel-resizer`，将 `.studio-grid` 改为单列，并保证抽屉、创作区和全屏图片不产生横向滚动。

- [ ] **Step 4: 运行生产构建**

Run: `cd frontend && npm run build`

Expected: Vite 构建成功，退出码为 `0`。

### Task 4: 真实浏览器验证与提交

**Files:**
- Verify: `frontend/src/App.vue`
- Verify: `frontend/src/style.css`
- Verify: `frontend/src/App.test.ts`

- [ ] **Step 1: 桌面端验证**

在 `1440x1000` 视口验证：接口配置默认折叠、模型选项正确、左栏拖拽边界为 `280–480px`、历史抽屉覆盖画布且可关闭。

- [ ] **Step 2: 全屏预览验证**

打开真实历史图片，测量图片 `top/left >= 0`、`right <= innerWidth`、`bottom <= innerHeight`，并确认预览层背景不是黑色。

- [ ] **Step 3: 移动端验证**

在 `390x844` 视口验证 `scrollWidth === clientWidth`、拖拽手柄隐藏、历史抽屉不溢出、页面内容顺序正确。

- [ ] **Step 4: 最终验证并提交**

Run: `cd frontend && .\\node_modules\\.bin\\vitest.cmd run`

Run: `cd frontend && npm run build`

Run: `git diff --check`

Expected: 测试、构建和差异检查全部通过。

```powershell
git add -- frontend/src/App.vue frontend/src/App.test.ts frontend/src/style.css docs/superpowers/plans/2026-07-26-modern-workspace-ui.md
git commit -m "feat: 重构现代化图像工作台"
```
