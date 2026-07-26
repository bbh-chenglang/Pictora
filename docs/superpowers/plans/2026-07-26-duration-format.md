# GenImage 计时格式 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将前端所有生成耗时统一显示为固定两位小数的秒数。

**Architecture:** 保留后端毫秒字段和现有组件结构，只修改 `App.vue` 的共享 `formatDuration` 展示函数。通过组件级生成流程测试验证不足一秒和超过一秒的实际页面输出。

**Tech Stack:** Vue 3、TypeScript、Vitest、Vue Test Utils

---

### Task 1: 锁定统一秒格式

**Files:**
- Modify: `frontend/src/App.test.ts`
- Modify: `frontend/src/App.vue:197`

- [ ] **Step 1: 写入失败的组件测试**

在 `frontend/src/App.test.ts` 中添加生成响应测试，返回两个耗时值并断言页面格式：

```typescript
it("formats every generation duration as seconds with two decimals", async () => {
  const fetchMock = vi.mocked(fetch);
  fetchMock.mockImplementation((input) => {
    const url = String(input);
    if (url.endsWith("/api/generate")) {
      return jsonResponse({
        images: [
          { url: "/short.png", generation_time_ms: 500 },
          { url: "/long.png", generation_time_ms: 14050 },
        ],
      });
    }
    if (url.endsWith("/api/providers")) {
      return jsonResponse({
        providers: [{ id: "compatible", label: "北海AI", models: ["gpt-image-1.5"] }],
      });
    }
    if (url.endsWith("/api/settings")) {
      return jsonResponse({
        provider_name: "北海AI",
        model: "gpt-image-1.5",
        base_url: "https://sub.beibeihai.xyz/v1",
        api_key_configured: true,
      });
    }
    if (url.endsWith("/api/history")) return jsonResponse([]);
    throw new Error(`Unexpected request: ${url}`);
  });

  const wrapper = mount(App);
  await flushPromises();
  await wrapper.get(".prompt-row textarea").setValue("测试提示词");
  await wrapper.get(".primary-action").trigger("click");
  await flushPromises();

  const metadata = wrapper.findAll(".image-meta strong").map((node) => node.text());
  expect(metadata).toEqual(["0.50 秒", "14.05 秒"]);
  expect(wrapper.text()).not.toContain("500 ms");
});
```

- [ ] **Step 2: 运行单测并确认按预期失败**

Run: `cd frontend && .\\node_modules\\.bin\\vitest.cmd run src/App.test.ts`

Expected: FAIL，实际首项仍为 `500 ms`，而期望为 `0.50 秒`。

- [ ] **Step 3: 写入最小实现**

将 `frontend/src/App.vue` 中的 `formatDuration` 改为：

```typescript
function formatDuration(milliseconds?: number | null) {
  if (milliseconds == null) return "计时不可用";
  return `${(milliseconds / 1000).toFixed(2)} 秒`;
}
```

- [ ] **Step 4: 运行前端测试并确认通过**

Run: `cd frontend && .\\node_modules\\.bin\\vitest.cmd run`

Expected: 1 个测试文件通过，3 项测试通过。

- [ ] **Step 5: 运行生产构建**

Run: `cd frontend && npm run build`

Expected: Vite 构建成功并以退出码 `0` 结束。

- [ ] **Step 6: 提交实现**

```powershell
git add -- frontend/src/App.test.ts frontend/src/App.vue docs/superpowers/plans/2026-07-26-duration-format.md
git commit -m "fix: 统一计时秒数格式"
```
