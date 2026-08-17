import { flushPromises, mount } from "@vue/test-utils";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";

import PromptPickerPopover from "./PromptPickerPopover.vue";

const entries = [
  {
    id: 1, user_id: 1, name: "商品模板", prompt: "商品棚拍，柔和光线", category: "电商",
    created_at: "2026-08-16T00:00:00Z", updated_at: "2026-08-16T00:00:00Z",
  },
  {
    id: 2, user_id: 1, name: "随手记录", prompt: "一段未分类内容", category: "",
    created_at: "2026-08-16T00:00:00Z", updated_at: "2026-08-16T00:00:00Z",
  },
];

describe("PromptPickerPopover", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("loads, filters, and emits a selected prompt", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify(entries), { status: 200 }))));
    const wrapper = mount(PromptPickerPopover, { props: { open: true, currentPrompt: "" } });
    await flushPromises();
    expect(wrapper.text()).toContain("商品模板");
    await wrapper.get("select").setValue("电商");
    expect(wrapper.findAll(".prompt-picker-entry")).toHaveLength(1);
    await wrapper.get(".prompt-picker-entry .primary-action").trigger("click");
    expect(wrapper.emitted("select")?.[0]?.[0]).toMatchObject({ id: 1, prompt: "商品棚拍，柔和光线" });
  });

  it("emits management navigation and supports search", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify(entries), { status: 200 }))));
    const wrapper = mount(PromptPickerPopover, { props: { open: true, currentPrompt: "已有内容" } });
    await flushPromises();
    await wrapper.get("input[type='search']").setValue("随手");
    expect(wrapper.findAll(".prompt-picker-entry")).toHaveLength(1);
    expect(wrapper.text()).toContain("选择后将替换当前提示词");
    await wrapper.get(".prompt-picker-footer .secondary-action").trigger("click");
    expect(wrapper.emitted("manage")).toHaveLength(1);
  });

  it("uses snowfall tokens instead of the legacy dark palette", () => {
    const source = readFileSync(resolve(process.cwd(), "src/components/PromptPickerPopover.vue"), "utf8");
    expect(source).toContain("var(--prompt-snow-surface)");
    expect(source).toContain("var(--prompt-snow-overlay)");
    expect(source).toContain("var(--prompt-snow-accent)");
    expect(source).not.toContain("background:#1b1d22");
  });
});
