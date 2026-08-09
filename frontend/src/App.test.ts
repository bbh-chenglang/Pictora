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
        if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: false });
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

  afterEach(() => {
    vi.unstubAllGlobals();
    window.history.replaceState({}, "", "/");
  });

  it("opens a dedicated settings page without the workspace model selector", async () => {
    const wrapper = mount(App);
    await flushPromises();

    await wrapper.get("[data-action='settings']").trigger("click");

    expect(window.location.pathname).toBe("/settings");
    expect(wrapper.find(".settings-page").exists()).toBe(true);
    expect(wrapper.find(".settings-page .model-select").exists()).toBe(false);
    expect(wrapper.find(".theme-option").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("暂不支持");
  });

  it("labels the community number as a QQ group number", async () => {
    const wrapper = mount(App);
    await flushPromises();

    await wrapper.get("[data-action='settings']").trigger("click");

    const communityLabels = wrapper.get(".settings-community").findAll("dt").map((label) => label.text());
    expect(communityLabels).toContain("QQ群号");
    expect(communityLabels).not.toContain("群号");
  });

  it("saves an API key from settings when editing finishes and returns to login after changing password", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: false });
      if (url.endsWith("/api/providers")) return jsonResponse({ providers: [] });
      if (url.endsWith("/api/settings") && init?.method === "PUT") return jsonResponse({ model: "gpt-image-1.5", api_key_configured: true });
      if (url.endsWith("/api/settings")) return jsonResponse({ model: "gpt-image-1.5", api_key_configured: false });
      if (url.endsWith("/api/history")) return jsonResponse([]);
      if (url.endsWith("/api/auth/password")) return Promise.resolve(new Response(null, { status: 204 }));
      throw new Error(`Unexpected request: ${url}`);
    });
    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get("[data-action='settings']").trigger("click");
    await wrapper.get("[data-field='api-key']").setValue("new-private-key");
    await wrapper.get("[data-field='api-key']").trigger("blur");
    await flushPromises();
    const settingsUpdate = fetchMock.mock.calls.find(
      ([input, init]) =>
        String(input).endsWith("/api/settings") && init?.method === "PUT",
    );
    expect(settingsUpdate).toBeDefined();
    expect(JSON.parse(String(settingsUpdate?.[1]?.body))).toEqual({
      model: "gpt-image-1.5",
      api_key: "new-private-key",
    });
    expect(wrapper.text()).not.toContain("new-private-key");

    await wrapper.get("[data-field='old-password']").setValue("secret6");
    await wrapper.get("[data-field='new-password']").setValue("changed6");
    await wrapper.get("[data-field='new-password-confirmation']").setValue("changed6");
    await wrapper.get("[data-action='change-password']").trigger("click");
    await flushPromises();
    expect(wrapper.find(".auth-page").exists()).toBe(true);
  });

  it("keeps image parameters in the prompt toolbar", async () => {
    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.find(".connection-section").exists()).toBe(false);
    expect(wrapper.find(".api-key-link").exists()).toBe(false);
    expect(wrapper.find(".control-panel").exists()).toBe(false);
    expect(wrapper.find(".panel-resizer").exists()).toBe(false);
    expect(wrapper.findAll("[data-parameter-trigger]")).toHaveLength(5);
    expect(wrapper.find(".composer-dock .reference-row").exists()).toBe(true);
    expect(wrapper.find(".composer-dock .prompt-row textarea").exists()).toBe(true);
  });

  it("labels a configured API key explicitly", async () => {
    vi.mocked(fetch).mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) {
        return jsonResponse({ username: "alice", api_key_configured: true });
      }
      if (url.endsWith("/api/providers")) return jsonResponse({ providers: [] });
      if (url.endsWith("/api/settings")) {
        return jsonResponse({ model: "gpt-image-1.5", api_key_configured: true });
      }
      if (url.endsWith("/api/history")) return jsonResponse([]);
      throw new Error(`Unexpected request: ${url}`);
    });

    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.text()).toContain("API Key 已配置");
    expect(wrapper.text()).not.toContain("服务已配置");
  });

  it("opens only one parameter menu and saves a selected model", async () => {
    const wrapper = mount(App);
    await flushPromises();

    await wrapper.get("[data-parameter-trigger='model']").trigger("click");
    expect(wrapper.find("[data-parameter-menu='model']").exists()).toBe(true);
    await wrapper.get("[data-parameter-trigger='size']").trigger("click");
    expect(wrapper.find("[data-parameter-menu='model']").exists()).toBe(false);
    expect(wrapper.find("[data-parameter-menu='size']").exists()).toBe(true);
    document.body.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
    await flushPromises();
    expect(wrapper.find("[data-parameter-menu='size']").exists()).toBe(false);
    await wrapper.get("[data-parameter-trigger='model']").trigger("click");
    await wrapper.get("[data-parameter-option='gpt-image-1.5']").trigger("click");
    await flushPromises();

    const settingsUpdate = vi.mocked(fetch).mock.calls.find(
      ([input, init]) =>
        String(input).endsWith("/api/settings") && init?.method === "PUT",
    );
    expect(settingsUpdate).toBeDefined();
    expect(JSON.parse(String(settingsUpdate?.[1]?.body))).toEqual({
      model: "gpt-image-1.5",
      api_key: null,
    });
  });

  it("shows the selected size with a checkmark and descriptive size options", async () => {
    const wrapper = mount(App);
    await flushPromises();

    await wrapper.get("[data-parameter-trigger='size']").trigger("click");

    const menu = wrapper.get("[data-parameter-menu='size']");
    expect(menu.findAll(".parameter-option")).toHaveLength(5);
    expect(menu.text()).toContain("1:1 正方形，头像 1024x1024");
    expect(menu.text()).toContain("3:2 横向图片，风景 1536x1024");
    expect(menu.text()).toContain("2:3 竖向图片，人像 1024x1536");
    expect(menu.text()).toContain("9:16 手机壁纸，人像 1024x1792");
    expect(menu.text()).toContain("16:9 桌面壁纸，风景 1792x1024");
    expect(menu.findAll(".parameter-option.is-selected")).toHaveLength(1);
    expect(menu.get(".parameter-option.is-selected svg").exists()).toBe(true);
  });

  it("places the light-blue analysis action above image generation", async () => {
    const wrapper = mount(App);
    await flushPromises();

    const actions = wrapper.get(".composer-actions").findAll("button");
    expect(actions).toHaveLength(2);
    expect(actions[0].classes()).toContain("analyze-action");
    expect(actions[1].classes()).toContain("primary-action");
  });

  it("automatically saves an API key in settings when editing finishes", async () => {
    const wrapper = mount(App);
    await flushPromises();

    await wrapper.get("[data-action='settings']").trigger("click");
    expect(wrapper.get("a.api-key-link").attributes("href")).toBe(
      "https://sub.beibeihai.xyz/home",
    );
    expect(wrapper.get("a.api-key-link").attributes("target")).toBe("_blank");
    expect(wrapper.get("a.api-key-link").attributes("rel")).toBe(
      "noopener noreferrer",
    );
    const input = wrapper.get("[data-field='api-key']");
    await input.setValue("new-private-key");
    await input.trigger("blur");
    await flushPromises();

    const settingsUpdate = vi.mocked(fetch).mock.calls.find(
      ([inputValue, init]) =>
        String(inputValue).endsWith("/api/settings") && init?.method === "PUT",
    );
    expect(settingsUpdate).toBeDefined();
    expect(JSON.parse(String(settingsUpdate?.[1]?.body))).toEqual({
      model: "gpt-image-1.5",
      api_key: "new-private-key",
    });
  });

  it("keeps the existing API key when saving with an empty value", async () => {
    const wrapper = mount(App);
    await flushPromises();

    await wrapper.get('[data-action="settings"]').trigger("click");
    await wrapper.get('[data-field="api-key"]').trigger("blur");
    await flushPromises();

    const settingsUpdate = vi.mocked(fetch).mock.calls.find(
      ([input, init]) =>
        String(input).endsWith("/api/settings") && init?.method === "PUT",
    );
    expect(settingsUpdate).toBeDefined();
    expect(JSON.parse(String(settingsUpdate?.[1]?.body))).toEqual({
      model: "gpt-image-1.5",
      api_key: null,
    });
  });

  it("sends the selected image size when generating", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: false });
      if (url.endsWith("/api/generate")) {
        return jsonResponse({ provider: "compatible", model: "gpt-image-2", images: [] });
      }
      if (url.endsWith("/api/providers")) {
        return jsonResponse({ providers: [{ id: "compatible", label: "北海AI", models: [] }] });
      }
      if (url.endsWith("/api/settings")) {
        return jsonResponse({ model: "gpt-image-1.5", api_key_configured: true });
      }
      if (url.endsWith("/api/history")) return jsonResponse([]);
      throw new Error(`Unexpected request: ${url} ${init?.method ?? "GET"}`);
    });

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get("[data-parameter-trigger='size']").trigger("click");
    await wrapper.get("[data-parameter-option='1024x1024']").trigger("click");
    await wrapper.get(".prompt-row textarea").setValue("竖版海报");
    await wrapper.get(".primary-action").trigger("click");
    await flushPromises();

    const generateRequest = fetchMock.mock.calls.find(([input]) =>
      String(input).endsWith("/api/generate"),
    );
    expect(generateRequest).toBeDefined();
    expect(JSON.parse(String(generateRequest?.[1]?.body)).size).toBe("1024x1024");
  });

  it("uses a standard square size by default", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) {
        return jsonResponse({ username: "alice", api_key_configured: true });
      }
      if (url.endsWith("/api/generate")) {
        return jsonResponse({ provider: "compatible", model: "gpt-image-1.5", images: [] });
      }
      if (url.endsWith("/api/providers")) {
        return jsonResponse({ providers: [{ id: "compatible", label: "鍖楁捣AI", models: [] }] });
      }
      if (url.endsWith("/api/settings")) {
        return jsonResponse({ model: "gpt-image-1.5", api_key_configured: true });
      }
      if (url.endsWith("/api/history")) return jsonResponse([]);
      throw new Error(`Unexpected request: ${url} ${init?.method ?? "GET"}`);
    });

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get(".prompt-row textarea").setValue("square image");
    await wrapper.get(".primary-action").trigger("click");
    await flushPromises();

    const generateRequest = fetchMock.mock.calls.find(([input]) =>
      String(input).endsWith("/api/generate"),
    );
    expect(JSON.parse(String(generateRequest?.[1]?.body)).size).toBe("1024x1024");
  });

  it("shows the HTTP status when generation returns an empty error response", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: false });
      if (url.endsWith("/api/generate")) {
        return Promise.resolve(new Response(null, { status: 504 }));
      }
      if (url.endsWith("/api/providers")) {
        return jsonResponse({
          providers: [{ id: "compatible", label: "北海AI", models: [] }],
        });
      }
      if (url.endsWith("/api/settings")) {
        return jsonResponse({ model: "gpt-image-2", api_key_configured: true });
      }
      if (url.endsWith("/api/history")) return jsonResponse([]);
      throw new Error(`Unexpected request: ${url}`);
    });

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get(".prompt-row textarea").setValue("竖版海报");
    await wrapper.get(".primary-action").trigger("click");
    await flushPromises();

    expect(wrapper.get(".error-message").text()).toBe("生成失败（HTTP 504）");
  });

  it("shows API key aliases and sends only the selected config id", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: true });
      if (url.endsWith("/api/providers")) return jsonResponse({ providers: [] });
      if (url.endsWith("/api/settings")) {
        return jsonResponse({
          provider_name: "北海AI",
          base_url: "https://sub.beibeihai.xyz/v1",
          active_config_id: 2,
          model: "gemini-image",
          api_key_configured: true,
          configs: [
            { id: 1, alias: "GPT 主账号", provider_type: "gpt", model: "gpt-image-1.5", api_key_configured: true },
            { id: 2, alias: "Gemini 绘图", provider_type: "gemini", model: "gemini-image", api_key_configured: true },
          ],
        });
      }
      if (url.endsWith("/api/settings/active")) return jsonResponse({ active_config_id: 1 });
      if (url.endsWith("/api/projects")) return jsonResponse([{ id: 1, name: "项目", history: [], history_count: 0 }]);
      if (url.endsWith("/api/generate")) return jsonResponse({ provider: "gemini", model: "gemini-image", images: [] });
      if (url.endsWith("/api/history")) return jsonResponse([]);
      throw new Error(`Unexpected request: ${url} ${init?.method ?? "GET"}`);
    });

    const wrapper = mount(App);
    await flushPromises();
    expect(wrapper.get("[data-parameter-trigger='model']").text()).toContain("gemini-image");
    await wrapper.get("[data-parameter-trigger='apiKey']").trigger("click");
    await wrapper.get("[data-parameter-option='GPT 主账号']").trigger("click");
    await flushPromises();
    await wrapper.get(".primary-action").trigger("click");
    await flushPromises();

    const generation = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/api/generate"));
    expect(JSON.parse(String(generation?.[1]?.body))).toMatchObject({ api_key_config_id: 1 });
    expect(JSON.parse(String(generation?.[1]?.body))).not.toHaveProperty("api_key");
  });

  it("adds and edits a key without model controls", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: true });
      if (url.endsWith("/api/providers")) return jsonResponse({ providers: [] });
      if (url.endsWith("/api/settings") && !init?.method) return jsonResponse({
        active_config_id: 1,
        model: "gpt-image-1.5",
        api_key_configured: true,
        configs: [{ id: 1, alias: "主 Key", provider_type: "gpt", model: "gpt-image-1.5", api_key_configured: true }],
      });
      if (url.endsWith("/api/settings/api-keys/1/test")) return jsonResponse({ available: true, message: "API Key 可用" });
      if (url.endsWith("/api/settings/api-keys") && init?.method === "POST") {
        expect(JSON.parse(String(init.body))).not.toHaveProperty("model");
        return jsonResponse({ id: 2 });
      }
      if (url.endsWith("/api/projects")) return jsonResponse([]);
      if (url.endsWith("/api/history")) return jsonResponse([]);
      throw new Error(`Unexpected request: ${url} ${init?.method ?? "GET"}`);
    });

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get("[data-action='settings']").trigger("click");
    expect(wrapper.get("[data-action='add-api-key']").text()).toContain("添加 API Key");
    expect(wrapper.get(".api-config-row").text()).not.toContain("gpt-image-1.5");
    await wrapper.get("[data-action='test-api-key']").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("API Key 可用");
    await wrapper.get("[data-action='add-api-key']").trigger("click");
    expect(wrapper.find("[data-field='config-provider']").exists()).toBe(false);
    expect(wrapper.find("[data-field='config-model']").exists()).toBe(false);
    expect(wrapper.find("[data-action='discover-models']").exists()).toBe(false);
    await wrapper.get("[data-field='config-api-key']").setValue("new-key");
    await flushPromises();
    await wrapper.get("[data-field='config-alias']").setValue("new-config");
    await wrapper.get(".api-config-form").trigger("submit");
    await flushPromises();
    expect(wrapper.find("[data-field='config-model']").exists()).toBe(false);
  });

  it("asks for custom confirmation before deleting an API key config", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: true });
      if (url.endsWith("/api/providers")) return jsonResponse({ providers: [] });
      if (url.endsWith("/api/settings") && !init?.method) return jsonResponse({
        active_config_id: 1,
        api_key_configured: true,
        configs: [
          { id: 1, alias: "主 Key", provider_type: "gpt", model: "gpt-image-1.5", api_key_configured: true },
          { id: 2, alias: "备用 Key", provider_type: "gemini", model: "gemini-image", api_key_configured: true },
        ],
      });
      if (url.endsWith("/api/settings/api-keys/2") && init?.method === "DELETE") return new Response(null, { status: 204 });
      if (url.endsWith("/api/projects")) return jsonResponse([]);
      if (url.endsWith("/api/history")) return jsonResponse([]);
      throw new Error(`Unexpected request: ${url} ${init?.method ?? "GET"}`);
    });

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get("[data-action='settings']").trigger("click");
    await wrapper.findAll("[data-action='delete-api-key']")[1].trigger("click");
    await flushPromises();
    expect(wrapper.find(".confirm-dialog").exists()).toBe(true);
    expect(fetchMock.mock.calls.some(([input, init]) => String(input).endsWith("/api/settings/api-keys/2") && init?.method === "DELETE")).toBe(false);
    await wrapper.get(".confirm-dialog .secondary-action").trigger("click");
    expect(wrapper.find(".confirm-dialog").exists()).toBe(false);
    await wrapper.findAll("[data-action='delete-api-key']")[1].trigger("click");
    await wrapper.get(".confirm-dialog .danger-action").trigger("click");
    await flushPromises();
    expect(fetchMock.mock.calls.some(([input, init]) => String(input).endsWith("/api/settings/api-keys/2") && init?.method === "DELETE")).toBe(true);
  });

  it("shows only the provider timeout in the empty canvas", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: false });
      if (url.endsWith("/api/generate")) {
        return Promise.resolve(new Response(JSON.stringify({ error: { code: "provider_timeout" } }), {
          status: 504,
          headers: { "Content-Type": "application/json" },
        }));
      }
      if (url.endsWith("/api/providers")) return jsonResponse({ providers: [{ id: "compatible", label: "北海AI", models: [] }] });
      if (url.endsWith("/api/settings")) return jsonResponse({ model: "gpt-image-2", api_key_configured: true });
      if (url.endsWith("/api/history")) return jsonResponse([]);
      throw new Error(`Unexpected request: ${url}`);
    });

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get(".prompt-row textarea").setValue("生成小猫");
    await wrapper.get(".primary-action").trigger("click");
    await flushPromises();

    const error = wrapper.get(".empty-wall .generation-error");
    expect(error.text()).toBe("服务商请求超时，请稍后重试");
    expect(error.classes()).toContain("error-message");
    expect(wrapper.find(".empty-wall h3").exists()).toBe(false);
    expect(wrapper.find(".empty-wall > p:not(.generation-error)").exists()).toBe(false);
    expect(wrapper.find(".composer-dock > .error-message").exists()).toBe(false);
  });

  it("renders projects instead of the removed history trigger", async () => {
    vi.mocked(fetch).mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: false });
      if (url.endsWith("/api/projects")) return jsonResponse([{ id: 1, name: "第一个项目", history: [], history_count: 0 }]);
      if (url.endsWith("/api/providers")) return jsonResponse({ providers: [] });
      if (url.endsWith("/api/settings")) return jsonResponse({ model: "gpt-image-1.5", api_key_configured: false });
      throw new Error(`Unexpected request: ${url}`);
    });
    const wrapper = mount(App);
    await flushPromises();
    expect(wrapper.find(".project-sidebar").exists()).toBe(true);
    expect(wrapper.text()).toContain("第一个项目");
    expect(wrapper.find(".history-trigger").exists()).toBe(false);
  });

  it.skip("opens and closes history in a right-side drawer", async () => {
    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.find(".history-drawer").exists()).toBe(false);
    await wrapper.get(".history-trigger").trigger("click");
    expect(wrapper.get(".history-drawer").attributes("role")).toBe("dialog");
    await wrapper.get(".history-drawer-close").trigger("click");
    expect(wrapper.find(".history-drawer").exists()).toBe(false);
  });

  it.skip("restores a selected history record into the result canvas", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: false });
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
    await wrapper.get(".history-trigger").trigger("click");
    await wrapper.get("[data-history-id='7']").trigger("click");
    await flushPromises();

    expect(wrapper.find(".history-drawer").exists()).toBe(false);
    const prompt = wrapper.get<HTMLTextAreaElement>(".prompt-row textarea");
    expect(prompt.element.value).toBe("蓝色海面");
    expect(wrapper.get(".image-grid img").attributes("src")).toBe(
      "/api/history/7/images/9",
    );
    const imageCard = wrapper.get(".image-card");
    expect(imageCard.get(".image-frame").find(".download").exists()).toBe(false);
    expect(imageCard.get(".image-meta .download").attributes("href")).toBe(
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
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: false });
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

  it("keeps the generation duration when reopening a generated conversation", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: false });
      if (url.endsWith("/api/projects")) {
        return jsonResponse([
          {
            id: 1,
            name: "我的项目",
            history: [{
              id: 7,
              kind: "generate",
              status: "completed",
              prompt: "已生成的图片",
              provider: "compatible",
              model: "gpt-image-1.5",
              detail: "high",
              image_count: 1,
              elapsed_ms: 500,
              error_code: null,
              error_message: null,
              created_at: "2026-07-26T10:00:00",
            }],
            history_count: 1,
          },
        ]);
      }
      if (url.endsWith("/api/history/7")) {
        return jsonResponse({
          id: 7,
          kind: "generate",
          status: "completed",
          prompt: "已生成的图片",
          provider: "compatible",
          model: "gpt-image-1.5",
          detail: "high",
          image_count: 1,
          elapsed_ms: 500,
          analysis_text: null,
          error_code: null,
          error_message: null,
          created_at: "2026-07-26T10:00:00",
          completed_at: "2026-07-26T10:00:01",
          images: [{
            id: 9,
            role: "generated",
            mime_type: "image/png",
            filename: "result.png",
            position: 0,
            url: "/api/history/7/images/9",
          }],
        });
      }
      if (url.endsWith("/api/providers")) return jsonResponse([]);
      if (url.endsWith("/api/settings")) return jsonResponse({ model: "gpt-image-1.5", api_key_configured: false });
      throw new Error(`Unexpected request: ${url}`);
    });

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get(".history-select").trigger("click");
    await flushPromises();

    expect(wrapper.get(".image-meta strong").text()).toBe("0.50 秒");
  });

  it("shows the live generation timer in the center of the empty canvas", async () => {
    let finishGeneration: ((response: Response) => void) | undefined;
    const pendingGeneration = new Promise<Response>((resolve) => {
      finishGeneration = resolve;
    });
    vi.mocked(fetch).mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: false });
      if (url.endsWith("/api/generate")) return pendingGeneration;
      if (url.endsWith("/api/providers")) {
        return jsonResponse({ providers: [{ id: "compatible", label: "北海AI", models: [] }] });
      }
      if (url.endsWith("/api/settings")) {
        return jsonResponse({ model: "gpt-image-1.5", api_key_configured: true });
      }
      if (url.endsWith("/api/history")) return jsonResponse([]);
      throw new Error(`Unexpected request: ${url}`);
    });

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get(".prompt-row textarea").setValue("测试计时位置");
    await wrapper.get(".primary-action").trigger("click");
    await wrapper.vm.$nextTick();

    expect(wrapper.find(".result-heading .working").exists()).toBe(false);
    expect(wrapper.get(".empty-wall h3").text()).toMatch(
      /^等待生成结果 \d+\.\d{2} 秒$/,
    );
    expect(wrapper.get(".empty-wall p").text()).toBe(
      "配置参数并在下方输入提示词。",
    );

    finishGeneration?.(
      new Response(
        JSON.stringify({ provider: "compatible", model: "gpt-image-1.5", images: [] }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    await flushPromises();
  });

});
