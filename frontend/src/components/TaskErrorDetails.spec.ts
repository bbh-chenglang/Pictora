import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import TaskErrorDetails from "./TaskErrorDetails.vue";
import { validationMessage } from "../errorDetails";

afterEach(() => vi.unstubAllGlobals());
describe("task diagnostics", () => {
  it("shows complete upstream diagnostics and copies useful identifiers", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const reason = "像素数必须介于 407696 和 8295044 之间。".repeat(60);
    const wrapper = mount(TaskErrorDetails, { props: {
      taskId: 12, model: "test-model", errorCode: "provider_request",
      details: { stage: "generation", http_status: 422, upstream_message: reason, parameter: "size", upstream_request_id: "req-42", reason_provided: true, suggestion: "检查尺寸" },
    } });
    expect(wrapper.get("summary").text()).toBe("查看失败详情");
    expect(wrapper.text()).toContain(reason);
    expect(wrapper.text()).toContain("上游生成");
    await wrapper.get("button").trigger("click");
    await flushPromises();
    expect(writeText.mock.calls[0][0]).toContain("上游请求 ID：req-42");
    expect(wrapper.text()).toContain("已复制");
    wrapper.unmount();
  });
  it("uses the selected slot's cause instead of another image's error", () => {
    const wrapper = mount(TaskErrorDetails, { props: { position: 1, errorCode: "partial_generation", details: {
      stage: "generation", upstream_message: "first image reason",
      failures: [{ position: 1, error_code: "bad_size", error_message: "第二张尺寸超限" }],
    } } });
    expect(wrapper.text()).toContain("第二张尺寸超限");
    expect(wrapper.text()).not.toContain("first image reason");
    expect(wrapper.text()).toContain("第 2 张");
    wrapper.unmount();
  });
  it("explicitly identifies missing upstream reasons and supports old records", () => {
    const wrapper = mount(TaskErrorDetails, { props: { message: "旧任务错误", details: { reason_provided: false } } });
    expect(wrapper.text()).toContain("未记录");
    expect(wrapper.text()).toContain("旧任务错误");
    expect(wrapper.text()).toContain("上游未提供具体失败原因");
    wrapper.unmount();
  });
  it("preserves validation field paths", () => {
    expect(validationMessage({ detail: [{ loc: ["body", "materials", 0, "url"], msg: "Invalid URL" }] }))
      .toBe("materials.0.url：Invalid URL");
  });
});
