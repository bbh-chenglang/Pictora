import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";

import SkillsView, { type SkillWorkflow } from "./SkillsView.vue";

const workflow: SkillWorkflow = {
  prompt_template: "商品棚拍：{{subject}}",
  provider_type: "gpt",
  model: "gpt-image-1.5",
  quality: "high",
  size: "1024x1024",
  resolution: "",
  image_count: 2,
  reference_requirements: ["object"],
  multi_view: { enabled: false, target: "person", preset_keys: [], custom_views: [] },
};

const skill = {
  id: 4, author_id: 2, author_name: "alice", title: "商品棚拍", description: "电商商品工作流",
  category: "product", status: "published", workflow, has_cover: false, is_favorited: false,
  favorite_count: 2, use_count: 8, moderation_note: null, created_at: "2026-08-16T00:00:00Z",
  updated_at: "2026-08-16T00:00:00Z", published_at: "2026-08-16T00:00:00Z",
};

describe("SkillsView", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("loads a published skill and emits its workflow when applied", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/skills?") && !url.includes("/use")) return Promise.resolve(new Response(JSON.stringify([skill]), { status: 200 }));
      if (url.endsWith("/api/skills/4/use")) {
        expect(init?.method).toBe("POST");
        return Promise.resolve(new Response(JSON.stringify({ skill: { ...skill, use_count: 9 }, workflow }), { status: 200 }));
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const wrapper = mount(SkillsView, { props: { isAdmin: false, username: "alice", currentWorkflow: workflow } });
    await flushPromises();
    expect(wrapper.text()).toContain("商品棚拍");
    await wrapper.get(".skill-card .primary-action").trigger("click");
    await flushPromises();
    expect(wrapper.emitted("apply")?.[0]).toEqual([workflow, "商品棚拍"]);
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith("/api/skills/4/use"))).toBe(true);
  });

  it("creates a draft from the current workflow", async () => {
    let submitted: FormData | null = null;
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/skills?") && !url.includes("/use")) return Promise.resolve(new Response("[]", { status: 200 }));
      if (url.endsWith("/api/skills")) {
        submitted = init?.body as FormData;
        return Promise.resolve(new Response(JSON.stringify({ ...skill, status: "draft" }), { status: 201 }));
      }
      throw new Error(`Unexpected request: ${url}`);
    }));
    const wrapper = mount(SkillsView, { props: { isAdmin: false, username: "alice", currentWorkflow: workflow } });
    await flushPromises();
    await wrapper.get(".skills-heading-actions .primary-action").trigger("click");
    await wrapper.get("input[maxlength='80']").setValue("我的商品技能");
    await wrapper.get("textarea").setValue("一套稳定的商品图流程");
    await wrapper.get(".skill-create-dialog").trigger("submit");
    await flushPromises();
    expect(submitted).not.toBeNull();
    const form = submitted as unknown as FormData;
    expect(form.get("title")).toBe("我的商品技能");
    expect(JSON.parse(String(form.get("workflow_json")))).toEqual(workflow);
  });
});
