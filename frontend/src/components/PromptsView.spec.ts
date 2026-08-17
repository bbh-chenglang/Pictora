import { flushPromises, mount } from "@vue/test-utils";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";

import PromptsView from "./PromptsView.vue";

const entry = {
  id: 7,
  user_id: 1,
  name: "电影感人像",
  prompt: "电影感人像，柔和侧光，浅景深",
  category: "portrait",
  created_at: "2026-08-16T00:00:00Z",
  updated_at: "2026-08-16T00:00:00Z",
};

describe("PromptsView", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("loads entries and emits the selected prompt", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      if (String(input).startsWith("/api/prompts")) return Promise.resolve(new Response(JSON.stringify([entry]), { status: 200 }));
      throw new Error(`Unexpected request: ${String(input)}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mount(PromptsView);
    await flushPromises();
    expect(wrapper.text()).toContain("电影感人像");
    await wrapper.get(".prompt-entry .primary-action").trigger("click");
    expect(wrapper.emitted("apply")?.[0]).toEqual([entry.prompt, entry.name]);
  });

  it("creates and edits a prompt entry", async () => {
    let saved: Record<string, string> | null = null;
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.startsWith("/api/prompts") && !init?.method) return Promise.resolve(new Response("[]", { status: 200 }));
      if (url === "/api/prompts" && init?.method === "POST") {
        saved = JSON.parse(String(init.body));
        return Promise.resolve(new Response(JSON.stringify({ ...entry, ...saved }), { status: 201 }));
      }
      if (url === "/api/prompts/7" && init?.method === "PATCH") return Promise.resolve(new Response(JSON.stringify(entry), { status: 200 }));
      throw new Error(`Unexpected request: ${url}`);
    }));
    const wrapper = mount(PromptsView);
    await flushPromises();
    await wrapper.get(".prompts-heading-actions .primary-action").trigger("click");
    await wrapper.get("input[maxlength='80']").setValue("我的提示词");
    await wrapper.get("textarea").setValue("新的提示词内容");
    await wrapper.get(".prompt-editor-dialog").trigger("submit");
    await flushPromises();
    expect(saved).toEqual({ name: "我的提示词", prompt: "新的提示词内容", category: "" });
  });

  it("uses snowfall tokens for page, borders, and text", () => {
    const source = readFileSync(resolve(process.cwd(), "src/components/PromptsView.vue"), "utf8");
    expect(source).toContain("var(--prompt-snow-page)");
    expect(source).toContain("var(--prompt-snow-border)");
    expect(source).toContain("var(--prompt-snow-text)");
  });

  it("marks management content as a snowfall surface", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify([entry]), { status: 200 }))));
    const wrapper = mount(PromptsView);
    await flushPromises();
    expect(wrapper.get(".prompts-page").attributes("data-theme")).toBe("snowfall");
    expect(wrapper.get(".prompt-entry").classes()).toContain("prompt-snow-surface");
  });
});
