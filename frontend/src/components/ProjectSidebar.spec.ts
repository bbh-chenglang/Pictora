import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import ProjectSidebar from "./ProjectSidebar.vue";

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
    await wrapper.get(".danger-text").trigger("click");
    expect(wrapper.emitted("delete-history")?.[0]).toEqual([
      expect.objectContaining({ id: 1 }),
      [1],
    ]);
  });
});
