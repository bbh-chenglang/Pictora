import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import ProjectSidebar from "./ProjectSidebar.vue";
import "../style.css";

const history = (count: number) => Array.from({ length: count }, (_, index) => ({
  id: index + 1,
  kind: "generate" as const,
  prompt: `提示词 ${index + 1}`,
  provider: "compatible",
  model: "gpt-image-1.5",
  status: "completed" as const,
  detail: "auto",
  image_count: 2,
  size: "16:9",
  resolution: "4K",
  created_at: "2026-08-01T00:00:00",
}));

describe("ProjectSidebar", () => {
  it("shows model, aspect ratio, resolution, and count for every history item", () => {
    const wrapper = mount(ProjectSidebar, {
      props: { projects: [{ id: 1, name: "第一个项目", history: history(1), history_count: 1 }], selectedProjectId: 1 },
    });

    expect(wrapper.get(".history-provider-model").text()).toBe("OpenAI · gpt-image-1.5");
    expect(wrapper.get(".history-generation-meta").text()).toBe("尺寸 16:9 · 2张");
  });

  it("defaults to five history items and expands the rest", async () => {
    const wrapper = mount(ProjectSidebar, {
      props: { projects: [{ id: 1, name: "第一个项目", history: history(6), history_count: 6 }], selectedProjectId: 1 },
    });
    expect(wrapper.findAll(".history-row")).toHaveLength(5);
    await wrapper.get(".text-action").trigger("click");
    expect(wrapper.findAll(".history-row")).toHaveLength(6);
  });

  it("emits selected history ids for batch deletion", async () => {
    const wrapper = mount(ProjectSidebar, {
      props: { projects: [{ id: 1, name: "第一个项目", history: history(1), history_count: 1 }], selectedProjectId: 1 },
    });
    await wrapper.get("input[type=checkbox]").setValue(true);
    expect(wrapper.get("input[type=checkbox]").classes()).toContain("history-checkbox");
    await wrapper.get(".danger-text").trigger("click");
    expect(wrapper.emitted("delete-history")?.[0]).toEqual([
      expect.objectContaining({ id: 1 }),
      [1],
    ]);
  });

  it("clears deleted history selections when project data refreshes", async () => {
    const wrapper = mount(ProjectSidebar, {
      props: { projects: [{ id: 1, name: "第一个项目", history: history(1), history_count: 1 }], selectedProjectId: 1 },
    });

    await wrapper.get("input[type=checkbox]").setValue(true);
    expect(wrapper.find(".danger-text").exists()).toBe(true);

    await wrapper.setProps({ projects: [{ id: 1, name: "第一个项目", history: [], history_count: 0 }] });
    expect(wrapper.find(".danger-text").exists()).toBe(false);
  });

  it("opens project actions, starts a conversation, and closes on outside click", async () => {
    const wrapper = mount(ProjectSidebar, {
      props: { projects: [{ id: 1, name: "project", history: history(1), history_count: 1 }], selectedProjectId: 1 },
      attachTo: document.body,
    });

    expect(wrapper.find(".new-conversation").exists()).toBe(false);
    await wrapper.get("[data-project-menu-trigger]").trigger("click");
    expect(wrapper.find(".project-menu").exists()).toBe(true);
    expect(wrapper.findAll(".project-menu button")).toHaveLength(3);
    expect(wrapper.find(".project-menu").element.parentElement?.classList.contains("project-group")).toBe(true);
    expect(wrapper.find(".project-menu").classes()).toContain("project-menu-overlay");
    expect(wrapper.find('[data-project-action="rename"] svg').exists()).toBe(true);

    await wrapper.find(".project-menu button").trigger("click");
    expect(wrapper.emitted("new-conversation")?.[0]).toEqual([1]);
    expect(wrapper.find(".project-menu").exists()).toBe(false);

    await wrapper.get("[data-project-menu-trigger]").trigger("click");
    await wrapper.get(".sidebar-heading").trigger("click");
    expect(wrapper.find(".project-menu").exists()).toBe(false);
    wrapper.unmount();
  });

  it("shows Grok native aspect ratio and resolution", () => {
    const grokHistory = [{ ...history(1)[0], provider: "grok", model: "grok-imagine-image", size: "20:9", resolution: "2K" }];
    const wrapper = mount(ProjectSidebar, {
      props: { projects: [{ id: 1, name: "Grok 项目", history: grokHistory, history_count: 1 }], selectedProjectId: 1 },
    });

    expect(wrapper.get(".history-generation-meta").text()).toBe("比例 20:9 · 分辨率 2K · 2张");
  });

  it("shows a new-conversation button beside every project", async () => {
    const projects = [
      { id: 1, name: "项目一", history: history(1), history_count: 1 },
      { id: 2, name: "项目二", history: [], history_count: 0 },
    ];
    const wrapper = mount(ProjectSidebar, { props: { projects, selectedProjectId: 1 } });

    const buttons = wrapper.findAll(".project-new-conversation");
    expect(buttons).toHaveLength(2);
    expect(buttons[1].attributes("aria-label")).toBe("在“项目二”中新建对话");
    await buttons[1].trigger("click");

    expect(wrapper.emitted("new-conversation")?.[0]).toEqual([2]);
  });

  it("expands and collapses each project independently", async () => {
    const projects = [
      { id: 1, name: "项目一", history: history(1), history_count: 1 },
      { id: 2, name: "项目二", history: history(1), history_count: 1 },
    ];
    const wrapper = mount(ProjectSidebar, { props: { projects, selectedProjectId: 1 } });

    expect(wrapper.find('[data-project-id="1"] .project-history').exists()).toBe(true);
    expect(wrapper.find('[data-project-id="2"] .project-history').exists()).toBe(false);

    await wrapper.get('[data-project-id="2"] .project-toggle').trigger("click");
    expect(wrapper.find('[data-project-id="1"] .project-history').exists()).toBe(true);
    expect(wrapper.find('[data-project-id="2"] .project-history').exists()).toBe(true);

    await wrapper.get('[data-project-id="1"] .project-toggle').trigger("click");
    expect(wrapper.find('[data-project-id="1"] .project-history').exists()).toBe(false);
    expect(wrapper.find('[data-project-id="2"] .project-history').exists()).toBe(true);
  });

  it("selects projects, history, and running generations", async () => {
    const wrapper = mount(ProjectSidebar, {
      props: {
        projects: [{ id: 1, name: "项目一", history: history(1), history_count: 1 }],
        selectedProjectId: 1,
        runningGenerations: [{ id: 9, projectId: 1, prompt: "生成中", model: "gpt-image-1.5", size: "1:1", resolution: "1K", elapsedMs: 1200 }],
      },
    });

    await wrapper.get(".project-select").trigger("click");
    expect(wrapper.emitted("select-project")?.[0]).toEqual([1]);

    await wrapper.get(".history-select").trigger("click");
    await wrapper.get(".running-generation").trigger("click");
    expect(wrapper.emitted("open-history")?.[0]).toEqual([1]);
    expect(wrapper.emitted("open-generation")?.[0]).toEqual([9]);
  });
});
