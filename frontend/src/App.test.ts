import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App.vue";

const jsonResponse = (body: unknown) =>
  Promise.resolve(
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

describe("GenImage workspace", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/providers")) {
          return jsonResponse({
            providers: [
              {
                id: "compatible",
                label: "北海AI",
                models: ["gpt-image-1.5"],
              },
            ],
          });
        }
        if (url.endsWith("/api/settings")) {
          return jsonResponse({
            provider_name: "北海AI",
            model: "gpt-image-1.5",
            base_url: "https://sub.beibeihai.xyz/v1",
            api_key_configured: false,
          });
        }
        if (url.endsWith("/api/history")) return jsonResponse([]);
        throw new Error(`Unexpected request: ${url}`);
      }),
    );
  });

  afterEach(() => vi.unstubAllGlobals());

  it("places connection settings above image parameters without showing the provider", async () => {
    const wrapper = mount(App);
    await flushPromises();

    const panel = wrapper.get(".control-panel");
    const connection = wrapper.get(".connection-section").element;
    const imageParameters = wrapper.get(".image-parameter-section").element;

    expect(panel.text()).toContain("API Key");
    expect(panel.text()).not.toContain("提供商");
    expect(
      connection.compareDocumentPosition(imageParameters) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(wrapper.find(".composer-dock .reference-row").exists()).toBe(true);
    expect(wrapper.find(".composer-dock .prompt-row textarea").exists()).toBe(true);
    expect(wrapper.text()).not.toContain("批量提示词");
  });

  it("restores a selected history record into the result canvas", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/api/history/7")) {
        return jsonResponse({
          id: 7,
          kind: "generate",
          status: "completed",
          prompt: "蓝色海面",
          provider: "compatible",
          model: "gpt-image-1.5",
          detail: "high",
          image_count: 1,
          analysis_text: null,
          elapsed_ms: 500,
          error_code: null,
          error_message: null,
          created_at: "2026-07-26T10:00:00",
          completed_at: "2026-07-26T10:00:01",
          images: [
            {
              id: 9,
              role: "generated",
              mime_type: "image/png",
              filename: "result.png",
              position: 0,
              url: "/api/history/7/images/9",
            },
          ],
        });
      }
      if (url.endsWith("/api/history")) {
        return jsonResponse([
          {
            id: 7,
            kind: "generate",
            status: "completed",
            prompt: "蓝色海面",
            provider: "compatible",
            model: "gpt-image-1.5",
            detail: "high",
            image_count: 1,
            elapsed_ms: 500,
            error_code: null,
            error_message: null,
            created_at: "2026-07-26T10:00:00",
          },
        ]);
      }
      if (url.endsWith("/api/providers")) {
        return jsonResponse({
          providers: [
            {
              id: "compatible",
              label: "北海AI",
              models: ["gpt-image-1.5"],
            },
          ],
        });
      }
      return jsonResponse({
        provider_name: "北海AI",
        model: "gpt-image-1.5",
        base_url: "https://sub.beibeihai.xyz/v1",
        api_key_configured: false,
      });
    });

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get("[data-history-id='7']").trigger("click");
    await flushPromises();

    const prompt = wrapper.get<HTMLTextAreaElement>(".prompt-row textarea");
    expect(prompt.element.value).toBe("蓝色海面");
    expect(wrapper.get(".image-grid img").attributes("src")).toBe(
      "/api/history/7/images/9",
    );

    await wrapper.get(".image-grid img").trigger("click");
    expect(wrapper.get("[role='dialog'] img").attributes("src")).toBe(
      "/api/history/7/images/9",
    );

    await wrapper.get(".lightbox-close").trigger("click");
    expect(wrapper.find("[role='dialog']").exists()).toBe(false);
  });

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
          providers: [
            {
              id: "compatible",
              label: "北海AI",
              models: ["gpt-image-1.5"],
            },
          ],
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

    const metadata = wrapper
      .findAll(".image-meta strong")
      .map((node) => node.text());
    expect(metadata).toEqual(["0.50 秒", "14.05 秒"]);
    expect(wrapper.text()).not.toContain("500 ms");
  });
});
