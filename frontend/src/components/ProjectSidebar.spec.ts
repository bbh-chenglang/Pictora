import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import ProjectSidebar from "./ProjectSidebar.vue";
import "../style.css";

const history = (count: number) => Array.from({ length: count }, (_, index) => ({
  id: index + 1,
  prompt: `提示词 ${index + 1}`,
  model: "gpt-image-1.5",
  status: "completed",
  created_at: "2026-08-01T00:00:00",
}));

describe("ProjectSidebar", () => {
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
    await wrapper.get(".project-row .icon-action").trigger("click");
    expect(wrapper.find(".project-menu").exists()).toBe(true);
    expect(wrapper.findAll(".project-menu button")).toHaveLength(3);
    expect(wrapper.find(".project-menu").element.parentElement?.classList.contains("project-group")).toBe(true);
    expect(wrapper.find(".project-menu").classes()).toContain("project-menu-overlay");
    expect(wrapper.get('[data-project-action="rename"] svg').exists()).toBe(true);

    await wrapper.find(".project-menu button").trigger("click");
    expect(wrapper.emitted("new-conversation")).toHaveLength(1);
    expect(wrapper.find(".project-menu").exists()).toBe(false);

    await wrapper.get(".project-row .icon-action").trigger("click");
    await wrapper.get(".sidebar-heading").trigger("click");
    expect(wrapper.find(".project-menu").exists()).toBe(false);
    wrapper.unmount();
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
});
