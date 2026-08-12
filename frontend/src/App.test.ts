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
    window.localStorage.clear();
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
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    window.history.replaceState({}, "", "/");
  });

  it("allows an unbound legacy account to submit its username", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) {
        return Promise.resolve(new Response(null, { status: 401 }));
      }
      if (url.endsWith("/api/auth/login")) {
        expect(init?.method).toBe("POST");
        return Promise.resolve(
          new Response(
            JSON.stringify({
              error: { code: "invalid_credentials", message: "测试响应" },
            }),
            { status: 401, headers: { "Content-Type": "application/json" } },
          ),
        );
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.get(".auth-fields").text()).toContain("邮箱或旧用户名");
    const identifier = wrapper.get("input[autocomplete='username']");
    expect(identifier.attributes("type")).toBe("text");
    await identifier.setValue("bbh");
    await wrapper.get("input[autocomplete='current-password']").setValue("secret6");
    expect((identifier.element as HTMLInputElement).checkValidity()).toBe(true);

    await wrapper.get(".auth-form").trigger("submit");
    await flushPromises();

    const request = fetchMock.mock.calls.find(([input]) =>
      String(input).endsWith("/api/auth/login"),
    );
    expect(JSON.parse(String(request?.[1]?.body))).toEqual({
      email: "bbh",
      password: "secret6",
    });
  });

  it("requests an email verification code before registration", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return Promise.resolve(new Response(null, { status: 401 }));
      if (url.endsWith("/api/auth/verification-code")) {
        expect(init?.method).toBe("POST");
        return jsonResponse({ message: "验证码已发送", retry_after_seconds: 60 });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    const wrapper = mount(App);
    await flushPromises();

    await wrapper.findAll(".auth-mode button")[1].trigger("click");
    await wrapper.get("input[type='email']").setValue("alice@example.com");
    await wrapper.get(".verification-action").trigger("click");
    await flushPromises();

    const request = fetchMock.mock.calls.find(([input]) =>
      String(input).endsWith("/api/auth/verification-code"),
    );
    expect(JSON.parse(String(request?.[1]?.body))).toEqual({ email: "alice@example.com" });
    expect(wrapper.get(".verification-action").text()).toContain("秒");
    expect(wrapper.find("input[autocomplete='one-time-code']").exists()).toBe(true);
  });

  it("shows administrator user and model usage data without sensitive values", async () => {
    vi.mocked(fetch).mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({
        username: "admin", email: "admin@example.com", is_admin: true, api_key_configured: false,
      });
      if (url.endsWith("/api/providers")) return jsonResponse({ providers: [] });
      if (url.endsWith("/api/settings")) return jsonResponse({ model: "gpt-image-1.5", api_key_configured: false });
      if (url.endsWith("/api/projects")) return jsonResponse([]);
      if (url.endsWith("/api/admin/users")) return jsonResponse({
        items: [{
          id: 2,
          username: "alice",
          email: "alice@example.com",
          is_admin: false,
          password_status: "bcrypt 已加密",
          created_at: "2026-08-12T01:00:00Z",
          last_login_at: "2026-08-12T02:00:00Z",
          last_activity_at: "2026-08-12T03:00:00Z",
          last_used_at: "2026-08-12T03:00:00Z",
          usage_count: 1,
          generation_count: 1,
          analysis_count: 0,
          total_elapsed_ms: 1250,
          models_used: ["gpt-image-1.5"],
        }],
        total: 28,
        result_total: 28,
        admin_total: 2,
        usage_total: 91,
        page: 1,
        page_size: 20,
      });
      if (url.endsWith("/api/admin/users/2/usage")) return jsonResponse([{
        id: 9,
        kind: "generate",
        status: "completed",
        provider: "openai",
        model: "gpt-image-1.5",
        detail: "high",
        image_count: 2,
        size: "16:9",
        resolution: "2K",
        elapsed_ms: 1250,
        created_at: "2026-08-12T03:00:00Z",
        completed_at: "2026-08-12T03:00:02Z",
      }]);
      throw new Error(`Unexpected request: ${url}`);
    });
    const wrapper = mount(App);
    await flushPromises();

    await wrapper.get("[data-action='admin']").trigger("click");
    await flushPromises();

    expect(window.location.pathname).toBe("/admin");
    expect(wrapper.get(".admin-page").text()).toContain("alice@example.com");
    expect(wrapper.get(".admin-page").text()).toContain("gpt-image-1.5");
    expect(wrapper.get(".admin-page").text()).toContain("bcrypt 已加密");
    expect(wrapper.get(".admin-page").text()).toContain("北京时间");
    expect(wrapper.get(".admin-page").text()).toContain("2026/08/12 09:00");
    expect(wrapper.get(".admin-metrics").text()).toContain("28");
    expect(wrapper.get(".admin-pagination").text()).toContain("第 1 / 2 页");
    expect(wrapper.get(".admin-page").text()).not.toContain("password_hash");
    expect(wrapper.get(".admin-page").text()).not.toContain("private prompt");
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
    expect(wrapper.get("canvas.flowing-grid-background").attributes("aria-hidden")).toBe("true");
  });

  it("shows a read-only email and updates only the username from settings", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({
        username: "alice",
        email: "alice@example.com",
        is_admin: false,
        api_key_configured: false,
      });
      if (url.endsWith("/api/auth/profile") && init?.method === "PUT") {
        expect(JSON.parse(String(init.body))).toEqual({ username: "alice-renamed" });
        return jsonResponse({
          username: "alice-renamed",
          email: "alice@example.com",
          is_admin: false,
          api_key_configured: false,
        });
      }
      if (url.endsWith("/api/providers")) return jsonResponse({ providers: [] });
      if (url.endsWith("/api/settings")) return jsonResponse({ model: "gpt-image-1.5", api_key_configured: false });
      if (url.endsWith("/api/projects")) return jsonResponse([]);
      if (url.endsWith("/api/history")) return jsonResponse([]);
      throw new Error(`Unexpected request: ${url}`);
    });
    const wrapper = mount(App);
    await flushPromises();

    await wrapper.get("[data-action='settings']").trigger("click");
    const emailField = wrapper.get<HTMLInputElement>("[data-field='profile-email']");
    expect(emailField.element.value).toBe("alice@example.com");
    expect(emailField.attributes("readonly")).toBeDefined();
    await wrapper.get("[data-field='profile-username']").setValue("alice-renamed");
    await wrapper.get(".profile-form").trigger("submit");
    await flushPromises();

    expect(wrapper.get(".profile-status").text()).toBe("用户名已更新");
    expect(wrapper.get(".user-chip").text()).toContain("alice-renamed");
  });

  it("labels the community number as a QQ group number", async () => {
    const wrapper = mount(App);
    await flushPromises();

    await wrapper.get("[data-action='settings']").trigger("click");

    const community = wrapper.get(".settings-community");
    const communityLabels = community.findAll("dt").map((label) => label.text());
    expect(communityLabels).toContain("QQ群号");
    expect(communityLabels).not.toContain("群号");
    expect(community.find(".community-qr").exists()).toBe(false);
    expect(community.find(".community-feedback-panel").exists()).toBe(true);
    expect(wrapper.get(".settings-preferences").findAll("h2").map((heading) => heading.text())).toEqual([
      "版本更新",
      "界面主题",
    ]);
  });

  it("switches and remembers the selected background effect", async () => {
    const wrapper = mount(App);
    await flushPromises();
    expect(wrapper.find("canvas.flowing-grid-background").exists()).toBe(true);

    await wrapper.get("[data-action='settings']").trigger("click");
    const options = wrapper.findAll("[data-background-effect]");
    expect(options).toHaveLength(2);
    expect(wrapper.get("#background-effect-title").text()).toBe("界面主题");
    await wrapper.get("[data-background-effect='snowfall']").trigger("click");

    expect(wrapper.get("main").classes()).toContain("background-snowfall");
    expect(wrapper.get("[data-field='feedback-contact']").element.closest(".background-snowfall")).toBe(wrapper.get("main").element);
    expect(wrapper.find("canvas.snowfall-background").exists()).toBe(true);
    expect(wrapper.find("canvas.flowing-grid-background").exists()).toBe(false);
    expect(window.localStorage.getItem("genimage-background-effect")).toBe("snowfall");
    expect(wrapper.get("[data-background-effect='snowfall']").attributes("aria-pressed")).toBe("true");
  });

  it("checks the deployed version from settings", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/api/version?")) return jsonResponse({ version: "dev" });
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: false });
      if (url.endsWith("/api/providers")) return jsonResponse({ providers: [] });
      if (url.endsWith("/api/settings")) return jsonResponse({ model: "gpt-image-1.5", api_key_configured: false });
      if (url.endsWith("/api/history")) return jsonResponse([]);
      throw new Error(`Unexpected request: ${url}`);
    });
    const wrapper = mount(App);
    await flushPromises();

    await wrapper.get("[data-action='settings']").trigger("click");
    await wrapper.get("[data-action='version-update']").trigger("click");
    await flushPromises();

    expect(wrapper.get("[data-action='version-update']").text()).toContain("已是最新版本");
    expect(wrapper.get(".version-status").text()).toBe("当前版本已是最新版本");
    const request = fetchMock.mock.calls.find(([input]) => String(input).includes("/api/version?"));
    expect(request?.[1]?.cache).toBe("no-store");
  });

  it("offers a cache-busting reload when a new version is available", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/api/version?")) return jsonResponse({ version: "release-next" });
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: false });
      if (url.endsWith("/api/providers")) return jsonResponse({ providers: [] });
      if (url.endsWith("/api/settings")) return jsonResponse({ model: "gpt-image-1.5", api_key_configured: false });
      if (url.endsWith("/api/history")) return jsonResponse([]);
      throw new Error(`Unexpected request: ${url}`);
    });
    const wrapper = mount(App);
    await flushPromises();

    await wrapper.get("[data-action='settings']").trigger("click");
    await wrapper.get("[data-action='version-update']").trigger("click");
    await flushPromises();

    expect(wrapper.get("[data-action='version-update']").text()).toContain("立即更新");
    expect(wrapper.get(".version-meta").text()).toContain("release-next");
    await wrapper.get("[data-action='version-update']").trigger("click");
    expect(window.location.search).toBe("?_app_version=release-next");
  });

  it("shows a retry action when checking the version fails", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/api/version?")) return Promise.reject(new Error("offline"));
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: false });
      if (url.endsWith("/api/providers")) return jsonResponse({ providers: [] });
      if (url.endsWith("/api/settings")) return jsonResponse({ model: "gpt-image-1.5", api_key_configured: false });
      if (url.endsWith("/api/history")) return jsonResponse([]);
      throw new Error(`Unexpected request: ${url}`);
    });
    const wrapper = mount(App);
    await flushPromises();

    await wrapper.get("[data-action='settings']").trigger("click");
    await wrapper.get("[data-action='version-update']").trigger("click");
    await flushPromises();

    expect(wrapper.get("[data-action='version-update']").text()).toContain("重新检查");
    expect(wrapper.get(".version-status").classes()).toContain("error");
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

  it("keeps image parameters in a vertically resizable workspace", async () => {
    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.find(".connection-section").exists()).toBe(false);
    expect(wrapper.find(".api-key-link").exists()).toBe(false);
    expect(wrapper.find(".control-panel").exists()).toBe(false);
    const resizer = wrapper.get(".panel-resizer");
    expect(resizer.attributes("role")).toBe("separator");
    expect(resizer.attributes("aria-valuenow")).toBe("48");
    await resizer.trigger("keydown", { key: "ArrowDown" });
    expect(resizer.attributes("aria-valuenow")).toBe("50");
    expect(window.localStorage.getItem("genimage-workspace-result-ratio")).toBe("50");
    await resizer.trigger("dblclick");
    expect(resizer.attributes("aria-valuenow")).toBe("48");
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

  it("shows native GPT image sizes without a separate resolution", async () => {
    const wrapper = mount(App);
    await flushPromises();

    await wrapper.get("[data-parameter-trigger='size']").trigger("click");

    const menu = wrapper.get("[data-parameter-menu='size']");
    expect(menu.findAll(".parameter-option")).toHaveLength(4);
    expect(menu.text()).toContain("自动");
    expect(menu.text()).toContain("正方形");
    expect(menu.text()).toContain("横向");
    expect(menu.text()).toContain("纵向");
    expect(menu.text()).toContain("1024x1024");
    expect(menu.text()).toContain("1536x1024");
    expect(menu.text()).toContain("1024x1536");
    expect(menu.findAll(".parameter-option.is-selected")).toHaveLength(1);
    expect(menu.get(".parameter-option.is-selected svg").exists()).toBe(true);

    expect(wrapper.find("[data-parameter-trigger='resolution']").exists()).toBe(false);
  });

  it("places the light-blue analysis action above image generation", async () => {
    const wrapper = mount(App);
    await flushPromises();

    const actions = wrapper.get(".composer-actions").findAll("button");
    expect(actions).toHaveLength(2);
    expect(actions[0].classes()).toContain("analyze-action");
    expect(actions[1].classes()).toContain("primary-action");
  });

  it.each([
    ["空提示词", "", "请描述这张图片", "分析结果"],
    ["已有提示词", "原提示词", "原提示词", "原提示词\n\n分析结果"],
  ])(
    "writes image analysis into the prompt for %s",
    async (_caseName, initialPrompt, submittedPrompt, expectedPrompt) => {
      const fetchMock = vi.mocked(fetch);
      let analyzeRequest: RequestInit | undefined;
      fetchMock.mockImplementation((input, init) => {
        const url = String(input);
        if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: false });
        if (url.endsWith("/api/providers")) {
          return jsonResponse({ providers: [{ id: "compatible", label: "北海AI", models: ["gpt-image-1.5"] }] });
        }
        if (url.endsWith("/api/settings")) {
          return jsonResponse({ provider_name: "北海AI", model: "gpt-image-1.5", api_key_configured: false });
        }
        if (url.endsWith("/api/projects")) return jsonResponse([]);
        if (url.endsWith("/api/analyze")) {
          analyzeRequest = init;
          return jsonResponse({ text: "分析结果" });
        }
        throw new Error(`Unexpected request: ${url} ${init?.method ?? "GET"}`);
      });

      const wrapper = mount(App);
      await flushPromises();
      const reference = new File(["reference"], "reference.jpg", { type: "image/jpeg" });
      const fileInput = wrapper.get<HTMLInputElement>("#image-input");
      Object.defineProperty(fileInput.element, "files", { value: [reference], configurable: true });
      await fileInput.trigger("change");
      await wrapper.get<HTMLTextAreaElement>(".prompt-row textarea").setValue(initialPrompt);
      await wrapper.get(".analyze-action").trigger("click");
      await flushPromises();

      expect((analyzeRequest?.body as FormData).get("prompt")).toBe(submittedPrompt);
      expect(wrapper.get<HTMLTextAreaElement>(".prompt-row textarea").element.value).toBe(expectedPrompt);
      expect(wrapper.find(".analysis-note").exists()).toBe(false);
    },
  );

  it("restores the original prompt and analysis result into the prompt field", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: false });
      if (url.endsWith("/api/providers")) {
        return jsonResponse({ providers: [{ id: "compatible", label: "北海AI", models: ["gpt-image-1.5"] }] });
      }
      if (url.endsWith("/api/settings")) {
        return jsonResponse({ provider_name: "北海AI", model: "gpt-image-1.5", api_key_configured: false });
      }
      if (url.endsWith("/api/projects")) {
        return jsonResponse([{
          id: 1,
          name: "测试项目",
          history_count: 1,
          history: [{
            id: 12,
            kind: "analyze",
            prompt: "原提示词",
            provider: "compatible",
            model: "gpt-image-1.5",
            status: "completed",
            image_count: 0,
            created_at: "2026-08-11T10:00:00",
          }],
        }]);
      }
      if (url.endsWith("/api/history/12")) {
        return jsonResponse({
          id: 12,
          kind: "analyze",
          status: "completed",
          prompt: "原提示词",
          provider: "compatible",
          model: "gpt-image-1.5",
          detail: "high",
          image_count: 0,
          analysis_text: "分析结果",
          elapsed_ms: 300,
          error_code: null,
          error_message: null,
          created_at: "2026-08-11T10:00:00",
          completed_at: "2026-08-11T10:00:01",
          images: [],
        });
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get(".history-select").trigger("click");
    await flushPromises();

    expect(wrapper.get<HTMLTextAreaElement>(".prompt-row textarea").element.value).toBe("原提示词\n\n分析结果");
    expect(wrapper.find(".analysis-note").exists()).toBe(false);
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
    await wrapper.get("[data-parameter-option='1536x1024']").trigger("click");
    await wrapper.get(".prompt-row textarea").setValue("竖版海报");
    await wrapper.get(".primary-action").trigger("click");
    await flushPromises();

    const generateRequest = fetchMock.mock.calls.find(([input]) =>
      String(input).endsWith("/api/generate"),
    );
    expect(generateRequest).toBeDefined();
    expect(JSON.parse(String(generateRequest?.[1]?.body))).toMatchObject({
      size: "1536x1024",
      output_format: "png",
      background: "auto",
      moderation: "auto",
    });
    expect(JSON.parse(String(generateRequest?.[1]?.body))).not.toHaveProperty("aspect_ratio");
    expect(JSON.parse(String(generateRequest?.[1]?.body))).not.toHaveProperty("resolution");
  });

  it("uploads multiple reference images together with the prompt when generating", async () => {
    const fetchMock = vi.mocked(fetch);
    let referenceRequest: RequestInit | undefined;
    fetchMock.mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: true });
      if (url.endsWith("/api/providers")) return jsonResponse({ providers: [] });
      if (url.endsWith("/api/settings")) return jsonResponse({
        active_config_id: 4,
        model: "gemini-3.1-flash-image",
        api_key_configured: true,
        configs: [
          { id: 4, alias: "Gemini", provider_type: "gemini", model: "gemini-3.1-flash-image", api_key_configured: true },
        ],
      });
      if (url.endsWith("/api/settings/api-keys/4/models")) return jsonResponse({
        models: [{ id: "gemini-3.1-flash-image", provider_type: "gemini" }],
      });
      if (url.endsWith("/api/generate/reference")) {
        referenceRequest = init;
        return jsonResponse({ provider: "gemini", model: "gemini-3.1-flash-image", images: [] });
      }
      if (url.endsWith("/api/projects")) return jsonResponse([]);
      if (url.endsWith("/api/history")) return jsonResponse([]);
      throw new Error(`Unexpected request: ${url} ${init?.method ?? "GET"}`);
    });

    const wrapper = mount(App);
    await flushPromises();
    const reference = new File(["reference-bytes"], "room.jpg", { type: "image/jpeg" });
    const material = new File(["material-bytes"], "material.png", { type: "image/png" });
    const fileInput = wrapper.get<HTMLInputElement>("#image-input");
    expect(fileInput.attributes("multiple")).toBeDefined();
    Object.defineProperty(fileInput.element, "files", { value: [reference, material], configurable: true });
    await fileInput.trigger("change");
    expect(wrapper.findAll(".reference-thumbnail")).toHaveLength(2);
    await wrapper.get("[data-parameter-trigger='size']").trigger("click");
    await wrapper.get("[data-parameter-option='16:9']").trigger("click");
    await wrapper.get("[data-parameter-trigger='resolution']").trigger("click");
    await wrapper.get("[data-parameter-option='4K']").trigger("click");
    await wrapper.get(".prompt-row textarea").setValue("保留参考图构图并调整自然光");
    await wrapper.get(".composer-actions .primary-action").trigger("click");
    await flushPromises();

    expect(referenceRequest?.headers).toBeUndefined();
    const form = referenceRequest?.body as FormData;
    expect(form.get("provider")).toBe("gemini");
    expect(form.get("model")).toBe("gemini-3.1-flash-image");
    expect(form.get("api_key_config_id")).toBe("4");
    expect(form.get("prompt")).toBe("保留参考图构图并调整自然光");
    expect(form.get("aspect_ratio")).toBe("16:9");
    expect(form.get("resolution")).toBe("4K");
    expect(form.getAll("images").map((item) => (item as File).name)).toEqual(["room.jpg", "material.png"]);
    expect(form.getAll("image_categories")).toEqual(["person", "person"]);
  });

  it("accepts dragged reference images and removes them individually", async () => {
    const wrapper = mount(App);
    await flushPromises();
    const room = new File(["room"], "room.jpg", { type: "image/jpeg" });
    const material = new File(["material"], "material.webp", { type: "image/webp" });
    const uploadZone = wrapper.get(".upload-zone");

    await uploadZone.trigger("dragenter");
    expect(uploadZone.classes()).toContain("is-dragging");
    await uploadZone.trigger("drop", { dataTransfer: { files: [room, material] } });

    expect(uploadZone.classes()).not.toContain("is-dragging");
    expect(wrapper.findAll(".reference-thumbnail")).toHaveLength(2);
    await wrapper.get("[aria-label='移除参考图片 1']").trigger("click");
    expect(wrapper.findAll(".reference-thumbnail")).toHaveLength(1);
    expect(wrapper.text()).toContain("material.webp");
  });

  it("keeps person, environment, and object reference modules independent", async () => {
    const wrapper = mount(App);
    await flushPromises();

    const modules = wrapper.findAll(".reference-module");
    expect(modules).toHaveLength(3);
    expect(modules.map((module) => module.get(".upload-zone-copy strong").text())).toEqual([
      "添加人物参考图",
      "添加环境参考图",
      "添加物品参考图",
    ]);

    const environment = new File(["environment"], "studio.jpg", { type: "image/jpeg" });
    const object = new File(["object"], "chair.png", { type: "image/png" });
    const environmentInput = wrapper.get<HTMLInputElement>("#image-input-environment");
    const objectInput = wrapper.get<HTMLInputElement>("#image-input-object");
    Object.defineProperty(environmentInput.element, "files", { value: [environment], configurable: true });
    Object.defineProperty(objectInput.element, "files", { value: [object], configurable: true });
    await environmentInput.trigger("change");
    await objectInput.trigger("change");

    expect(modules[0].findAll(".reference-thumbnail")).toHaveLength(0);
    expect(modules[1].findAll(".reference-thumbnail")).toHaveLength(1);
    expect(modules[2].findAll(".reference-thumbnail")).toHaveLength(1);
    expect(modules[1].get(".reference-thumbnail").element.closest(".upload-zone")).not.toBeNull();
    expect(modules[2].get(".reference-thumbnail").element.closest(".upload-zone")).not.toBeNull();
    const previewSource = modules[1].get(".reference-thumbnail img").attributes("src");
    await modules[1].get(".reference-preview-trigger").trigger("click");
    expect(wrapper.get(".image-lightbox img").attributes("src")).toBe(previewSource);
    await wrapper.get(".lightbox-close").trigger("click");
    expect(wrapper.find(".image-lightbox").exists()).toBe(false);
    await modules[1].get(".reference-remove").trigger("click");
    expect(modules[1].findAll(".reference-thumbnail")).toHaveLength(0);
    expect(modules[2].findAll(".reference-thumbnail")).toHaveLength(1);
  });

  it("uses the upstream automatic GPT size by default", async () => {
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
    expect(JSON.parse(String(generateRequest?.[1]?.body))).toMatchObject({
      size: "auto",
      output_format: "png",
      background: "auto",
      moderation: "auto",
    });
    expect(JSON.parse(String(generateRequest?.[1]?.body))).not.toHaveProperty("aspect_ratio");
    expect(JSON.parse(String(generateRequest?.[1]?.body))).not.toHaveProperty("resolution");
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

  it("shows provider-specific parameters and keeps model changes on the selected config", async () => {
    const fetchMock = vi.mocked(fetch);
    const generationBodies: Record<string, unknown>[] = [];
    fetchMock.mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: true });
      if (url.endsWith("/api/providers")) return jsonResponse({ providers: [] });
      if (url.endsWith("/api/settings") && !init?.method) return jsonResponse({
        active_config_id: 2,
        model: "gemini-image",
        api_key_configured: true,
        configs: [
          { id: 1, alias: "OpenAI 主账号", provider_type: "gpt", model: "gpt-image-2", api_key_configured: true },
          { id: 2, alias: "Gemini 绘图", provider_type: "gemini", model: "gemini-image", api_key_configured: true },
        ],
      });
      if (url.endsWith("/api/settings/active")) return jsonResponse({ active_config_id: JSON.parse(String(init?.body)).config_id });
      if (url.endsWith("/api/settings/api-keys/1/models")) return jsonResponse({
        models: [
          { id: "gpt-image-2", provider_type: "gpt" },
          { id: "gpt-image-1.5", provider_type: "gpt" },
        ],
      });
      if (url.endsWith("/api/settings/api-keys/1") && init?.method === "PATCH") {
        expect(JSON.parse(String(init.body))).toEqual({ model: "gpt-image-1.5" });
        return jsonResponse({ id: 1, model: "gpt-image-1.5" });
      }
      if (url.endsWith("/api/generate")) {
        generationBodies.push(JSON.parse(String(init?.body)));
        return jsonResponse({ provider: "gemini", model: "gemini-image", images: [] });
      }
      if (url.endsWith("/api/projects")) return jsonResponse([]);
      if (url.endsWith("/api/history")) return jsonResponse([]);
      throw new Error(`Unexpected request: ${url} ${init?.method ?? "GET"}`);
    });

    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.get("[data-parameter-trigger='size']").text()).toContain("图片比例");
    expect(wrapper.find("[data-parameter-trigger='quality']").exists()).toBe(false);
    expect(wrapper.findAll("[data-parameter-trigger]")).toHaveLength(4);

    await wrapper.get(".prompt-row textarea").setValue("Gemini 原生图片");
    await wrapper.get(".composer-actions .primary-action").trigger("click");
    await flushPromises();
    expect(generationBodies[0]).toMatchObject({
      provider: "gemini",
      api_key_config_id: 2,
      aspect_ratio: "1:1",
    });
    expect(generationBodies[0]).not.toHaveProperty("detail");
    expect(generationBodies[0]).not.toHaveProperty("resolution");

    await wrapper.get("[data-parameter-trigger='apiKey']").trigger("click");
    await wrapper.get("[data-parameter-option='OpenAI 主账号']").trigger("click");
    await flushPromises();
    expect(wrapper.find("[data-parameter-trigger='quality']").exists()).toBe(true);
    expect(wrapper.findAll("[data-parameter-trigger]")).toHaveLength(5);
    await wrapper.get("[data-parameter-trigger='quality']").trigger("click");
    expect(wrapper.get("[data-parameter-menu='quality']").findAll(".parameter-option")).toHaveLength(4);
    await wrapper.get("[data-parameter-option='medium']").trigger("click");

    await wrapper.get("[data-parameter-trigger='model']").trigger("click");
    await wrapper.get("[data-parameter-option='gpt-image-1.5']").trigger("click");
    await flushPromises();
    expect(wrapper.get("[data-parameter-trigger='model']").text()).toContain("gpt-image-1.5");
  });

  it("shows Grok native dimensions and sends them without OpenAI size", async () => {
    const fetchMock = vi.mocked(fetch);
    let generationBody: Record<string, unknown> | undefined;
    fetchMock.mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: true });
      if (url.endsWith("/api/providers")) return jsonResponse({ providers: [] });
      if (url.endsWith("/api/settings") && !init?.method) return jsonResponse({
        active_config_id: 3,
        model: "grok-imagine-image",
        api_key_configured: true,
        configs: [{
          id: 3,
          alias: "Grok",
          provider_type: "grok",
          model: "grok-imagine-image",
          api_key_configured: true,
        }],
      });
      if (url.endsWith("/api/settings/api-keys/3/models")) return jsonResponse({
        models: [
          { id: "grok-imagine-image", provider_type: "grok" },
          { id: "grok-imagine-image-2.0", provider_type: "grok" },
        ],
      });
      if (url.endsWith("/api/generate") && init?.method === "POST") {
        generationBody = JSON.parse(String(init.body));
        return jsonResponse({ provider: "grok", model: "grok-imagine-image", images: [] });
      }
      if (url.endsWith("/api/projects")) return jsonResponse([]);
      if (url.endsWith("/api/history")) return jsonResponse([]);
      throw new Error(`Unexpected request: ${url} ${init?.method ?? "GET"}`);
    });

    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.findAll("[data-parameter-trigger]")).toHaveLength(5);
    expect(wrapper.find("[data-parameter-trigger='size']").exists()).toBe(true);
    expect(wrapper.find("[data-parameter-trigger='resolution']").exists()).toBe(true);
    expect(wrapper.find("[data-parameter-trigger='quality']").exists()).toBe(false);
    await wrapper.get("[data-parameter-trigger='size']").trigger("click");
    expect(wrapper.get("[data-parameter-menu='size']").findAll(".parameter-option")).toHaveLength(14);
    await wrapper.get("[data-parameter-option='20:9']").trigger("click");
    await wrapper.get("[data-parameter-trigger='resolution']").trigger("click");
    expect(wrapper.get("[data-parameter-menu='resolution']").findAll(".parameter-option")).toHaveLength(2);
    await wrapper.get("[data-parameter-option='2K']").trigger("click");
    await wrapper.get("[data-parameter-trigger='model']").trigger("click");
    expect(wrapper.get("[data-parameter-menu='model']").text()).toContain("grok-imagine-image-2.0");
    await wrapper.get("[data-parameter-trigger='count']").trigger("click");
    expect(wrapper.get("[data-parameter-menu='count']").findAll(".parameter-option")).toHaveLength(10);
    await wrapper.get("[data-parameter-option='10']").trigger("click");
    await wrapper.get(".prompt-row textarea").setValue("生成十张原图");
    await wrapper.get(".composer-actions .primary-action").trigger("click");
    await flushPromises();

    expect(generationBody).toMatchObject({
      provider: "grok",
      model: "grok-imagine-image",
      count: 10,
    });
    expect(generationBody).not.toHaveProperty("size");
    expect(generationBody?.aspect_ratio).toBe("20:9");
    expect(generationBody?.resolution).toBe("2K");
    expect(generationBody).not.toHaveProperty("detail");
    wrapper.unmount();
  });

  it("shows and sends quality only for Grok Imagine Image 2.0", async () => {
    const fetchMock = vi.mocked(fetch);
    let generationBody: Record<string, unknown> | undefined;
    fetchMock.mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: true });
      if (url.endsWith("/api/providers")) return jsonResponse({ providers: [] });
      if (url.endsWith("/api/settings") && !init?.method) return jsonResponse({
        active_config_id: 3,
        model: "grok-imagine-image-2.0",
        api_key_configured: true,
        configs: [{ id: 3, alias: "Grok", provider_type: "grok", model: "grok-imagine-image-2.0", api_key_configured: true }],
      });
      if (url.endsWith("/api/settings/api-keys/3/models")) return jsonResponse({
        models: [{ id: "grok-imagine-image-2.0", provider_type: "grok" }],
      });
      if (url.endsWith("/api/generate") && init?.method === "POST") {
        generationBody = JSON.parse(String(init.body));
        return jsonResponse({ provider: "grok", model: "grok-imagine-image-2.0", images: [] });
      }
      if (url.endsWith("/api/projects")) return jsonResponse([]);
      if (url.endsWith("/api/history")) return jsonResponse([]);
      throw new Error(`Unexpected request: ${url} ${init?.method ?? "GET"}`);
    });

    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.get("[data-parameter-trigger='quality']").text()).toContain("中");
    await wrapper.get("[data-parameter-trigger='quality']").trigger("click");
    expect(wrapper.get("[data-parameter-menu='quality']").findAll(".parameter-option")).toHaveLength(2);
    await wrapper.get("[data-parameter-option='low']").trigger("click");
    await wrapper.get(".prompt-row textarea").setValue("低质量快速草图");
    await wrapper.get(".composer-actions .primary-action").trigger("click");
    await flushPromises();

    expect(generationBody).toMatchObject({
      provider: "grok",
      model: "grok-imagine-image-2.0",
      aspect_ratio: "auto",
      resolution: "1K",
      detail: "low",
    });
    wrapper.unmount();
  });

  it("uses the upstream model list without adding a stale saved model", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: true });
      if (url.endsWith("/api/providers")) return jsonResponse({ providers: [] });
      if (url.endsWith("/api/settings") && !init?.method) return jsonResponse({
        active_config_id: 1,
        model: "stale-local-model",
        api_key_configured: true,
        configs: [
          { id: 1, alias: "OpenAI", provider_type: "gpt", model: "stale-local-model", api_key_configured: true },
        ],
      });
      if (url.endsWith("/api/settings/api-keys/1/models")) return jsonResponse({
        models: [
          { id: "gpt-image-2", provider_type: "gpt" },
          { id: "gpt-5", provider_type: "gpt" },
        ],
      });
      if (url.endsWith("/api/settings/api-keys/1") && init?.method === "PATCH") {
        expect(JSON.parse(String(init.body))).toEqual({ model: "gpt-image-2" });
        return jsonResponse({ id: 1, model: "gpt-image-2" });
      }
      if (url.endsWith("/api/projects")) return jsonResponse([]);
      if (url.endsWith("/api/history")) return jsonResponse([]);
      throw new Error(`Unexpected request: ${url} ${init?.method ?? "GET"}`);
    });

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get("[data-parameter-trigger='model']").trigger("click");

    const options = wrapper.get("[data-parameter-menu='model']").findAll(".parameter-option");
    expect(options.map((item) => item.text())).toEqual(["gpt-image-2", "gpt-5"]);
    expect(wrapper.text()).not.toContain("stale-local-model");
  });

  it("switches the API config together with the model when opening project history", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: true });
      if (url.endsWith("/api/providers")) return jsonResponse({ providers: [] });
      if (url.endsWith("/api/settings") && !init?.method) return jsonResponse({
        active_config_id: 2,
        model: "gemini-3.1-flash-image",
        api_key_configured: true,
        configs: [
          { id: 1, alias: "OpenAI", provider_type: "gpt", model: "gpt-image-2", api_key_configured: true },
          { id: 2, alias: "Gemini", provider_type: "gemini", model: "gemini-3.1-flash-image", api_key_configured: true },
        ],
      });
      if (url.endsWith("/api/settings/api-keys/2/models")) return jsonResponse({
        models: [{ id: "gemini-3.1-flash-image", provider_type: "gemini" }],
      });
      if (url.endsWith("/api/settings/api-keys/1/models")) return jsonResponse({
        models: [{ id: "gpt-image-2", provider_type: "gpt" }],
      });
      if (url.endsWith("/api/settings/active")) {
        return jsonResponse({ active_config_id: JSON.parse(String(init?.body)).config_id });
      }
      if (url.endsWith("/api/projects")) return jsonResponse([{
        id: 1,
        name: "OpenAI 项目",
        history: [{
          id: 7,
          kind: "generate",
          status: "completed",
          prompt: "OpenAI 历史图片",
          provider: "compatible",
          model: "gpt-image-2",
          detail: "high",
          image_count: 1,
          created_at: "2026-08-10T10:00:00",
        }],
        history_count: 1,
      }]);
      if (url.endsWith("/api/history/7")) return jsonResponse({
        id: 7,
        kind: "generate",
        status: "completed",
        prompt: "OpenAI 历史图片",
        provider: "compatible",
        model: "gpt-image-2",
        detail: "high",
        image_count: 1,
        created_at: "2026-08-10T10:00:00",
        images: [],
      });
      throw new Error(`Unexpected request: ${url} ${init?.method ?? "GET"}`);
    });

    const wrapper = mount(App);
    await flushPromises();
    expect(wrapper.get("[data-parameter-trigger='apiKey']").text()).toContain("Gemini");

    await wrapper.get(".history-select").trigger("click");
    await flushPromises();

    expect(wrapper.get("[data-parameter-trigger='apiKey']").text()).toContain("OpenAI");
    expect(wrapper.get("[data-parameter-trigger='model']").text()).toContain("gpt-image-2");
    const activeUpdate = fetchMock.mock.calls.find(
      ([input, request]) => String(input).endsWith("/api/settings/active") && request?.method === "PUT",
    );
    expect(JSON.parse(String(activeUpdate?.[1]?.body))).toEqual({ config_id: 1 });
  });

  it("uses a same-provider config model when history has no exact configured model", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: true });
      if (url.endsWith("/api/providers")) return jsonResponse({ providers: [] });
      if (url.endsWith("/api/settings") && !init?.method) return jsonResponse({
        active_config_id: 2,
        model: "gemini-image",
        api_key_configured: true,
        configs: [
          { id: 1, alias: "OpenAI", provider_type: "gpt", model: "gpt-image-1.5", api_key_configured: true },
          { id: 2, alias: "Gemini", provider_type: "gemini", model: "gemini-image", api_key_configured: true },
        ],
      });
      if (url.endsWith("/api/settings/api-keys/2/models")) return jsonResponse({
        models: [{ id: "gemini-image", provider_type: "gemini" }],
      });
      if (url.endsWith("/api/settings/api-keys/1/models")) return jsonResponse({
        models: [{ id: "gpt-image-1.5", provider_type: "gpt" }],
      });
      if (url.endsWith("/api/settings/active")) {
        return jsonResponse({ active_config_id: JSON.parse(String(init?.body)).config_id });
      }
      if (url.endsWith("/api/projects")) return jsonResponse([{
        id: 1,
        name: "旧项目",
        history: [{ id: 8, kind: "generate", status: "completed", prompt: "旧模型", provider: "compatible", model: "removed-image-model", detail: "auto", image_count: 1, created_at: "2026-08-10T10:00:00" }],
        history_count: 1,
      }]);
      if (url.endsWith("/api/history/8")) return jsonResponse({
        id: 8,
        kind: "generate",
        status: "completed",
        prompt: "旧模型",
        provider: "compatible",
        model: "removed-image-model",
        detail: "auto",
        image_count: 1,
        created_at: "2026-08-10T10:00:00",
        images: [],
      });
      throw new Error(`Unexpected request: ${url} ${init?.method ?? "GET"}`);
    });

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get(".history-select").trigger("click");
    await flushPromises();

    expect(wrapper.get("[data-parameter-trigger='apiKey']").text()).toContain("OpenAI");
    expect(wrapper.get("[data-parameter-trigger='model']").text()).toContain("gpt-image-1.5");
    expect(wrapper.get("[data-parameter-trigger='model']").text()).not.toContain("removed-image-model");
  });

  it("keeps an explicit empty API config list empty", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: false });
      if (url.endsWith("/api/providers")) return jsonResponse({ providers: [] });
      if (url.endsWith("/api/settings")) return jsonResponse({
        active_config_id: null,
        model: "gpt-image-1.5",
        api_key_configured: false,
        configs: [],
      });
      if (url.endsWith("/api/projects")) return jsonResponse([]);
      throw new Error(`Unexpected request: ${url}`);
    });

    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.get("[data-parameter-trigger='apiKey']").text()).toContain("未配置");
    await wrapper.get("[data-action='settings']").trigger("click");
    expect(wrapper.find(".api-config-row").exists()).toBe(false);
    expect(wrapper.get(".api-config-empty").text()).toBe("暂无 API Key 配置");
    expect(wrapper.find("[data-field='api-key']").exists()).toBe(false);
  });

  it("requires an explicit provider and submits a Gemini API key", async () => {
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
      if (url.endsWith("/api/settings/api-keys/1/test")) return jsonResponse({
        available: true,
        message: "API Key 可用",
        models: [
          { id: "gpt-image-2", provider_type: "gpt" },
          { id: "gpt-5", provider_type: "gpt" },
        ],
      });
      if (url.endsWith("/api/settings/api-keys") && init?.method === "POST") {
        expect(JSON.parse(String(init.body))).toEqual({
          alias: "new-config",
          api_key: "new-key",
          provider_type: "gemini",
        });
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
    expect(wrapper.get(".api-config-row").text()).toContain("OpenAI");
    await wrapper.get("[data-action='test-api-key']").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("API Key 可用");
    expect(wrapper.get(".api-key-models").text()).toContain("可用模型（2）");
    expect(wrapper.get(".api-key-models").findAll("li").map((item) => item.text())).toEqual([
      "gpt-image-2",
      "gpt-5",
    ]);
    const modelListToggle = wrapper.get(".api-key-models-toggle");
    expect(modelListToggle.attributes("aria-expanded")).toBe("true");
    await modelListToggle.trigger("click");
    expect(modelListToggle.attributes("aria-expanded")).toBe("false");
    expect(wrapper.find(".api-key-models ul").exists()).toBe(false);
    expect(wrapper.text()).toContain("API Key 可用");
    await modelListToggle.trigger("click");
    expect(wrapper.get(".api-key-models").findAll("li")).toHaveLength(2);
    await wrapper.get("[data-action='add-api-key']").trigger("click");
    expect(wrapper.find("[data-field='config-provider']").exists()).toBe(true);
    expect(wrapper.find("[data-field='config-model']").exists()).toBe(false);
    expect(wrapper.find("[data-action='discover-models']").exists()).toBe(false);
    expect(wrapper.get("[data-provider-type='gpt']").attributes("aria-pressed")).toBe("false");
    expect(wrapper.get("[data-provider-type='gemini']").attributes("aria-pressed")).toBe("false");
    expect(wrapper.get("[data-provider-type='grok']").attributes("aria-pressed")).toBe("false");
    await wrapper.get(".api-config-form").trigger("submit");
    expect(wrapper.text()).toContain("请选择 API 类型");
    await wrapper.get("[data-field='config-api-key']").setValue("new-key");
    await flushPromises();
    await wrapper.get("[data-field='config-alias']").setValue("new-config");
    await wrapper.get("[data-provider-type='gemini']").trigger("click");
    await wrapper.get(".api-config-form").trigger("submit");
    await flushPromises();
    expect(wrapper.find("[data-field='config-model']").exists()).toBe(false);
    expect(wrapper.find(".api-config-form").exists()).toBe(false);

    await wrapper.get("[data-action='add-api-key']").trigger("click");
    expect(wrapper.find(".api-config-form").exists()).toBe(true);
    expect(wrapper.get<HTMLInputElement>("[data-field='config-alias']").element.value).toBe("");
    expect(wrapper.get<HTMLInputElement>("[data-field='config-api-key']").element.value).toBe("");
    await wrapper.get("[data-field='config-alias']").setValue("不保存的配置");
    await wrapper.get("[data-field='config-api-key']").setValue("temporary-key");
    await wrapper.get("[data-action='cancel-api-key-form']").trigger("click");
    expect(wrapper.find(".api-config-form").exists()).toBe(false);

    await wrapper.get("[data-action='add-api-key']").trigger("click");
    expect(wrapper.get<HTMLInputElement>("[data-field='config-alias']").element.value).toBe("");
    expect(wrapper.get<HTMLInputElement>("[data-field='config-api-key']").element.value).toBe("");
  });

  it("adds Grok beside OpenAI and Gemini in the shared API configuration", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: false });
      if (url.endsWith("/api/providers")) return jsonResponse({ providers: [] });
      if (url.endsWith("/api/settings") && !init?.method) return jsonResponse({
        active_config_id: null,
        model: "gpt-image-2",
        api_key_configured: false,
        configs: [],
      });
      if (url.endsWith("/api/settings/api-keys") && init?.method === "POST") {
        expect(JSON.parse(String(init.body))).toEqual({
          alias: "Grok 中转",
          api_key: "grok-key",
          provider_type: "grok",
        });
        return jsonResponse({ id: 3 });
      }
      if (url.endsWith("/api/projects")) return jsonResponse([]);
      if (url.endsWith("/api/history")) return jsonResponse([]);
      throw new Error(`Unexpected request: ${url} ${init?.method ?? "GET"}`);
    });

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get("[data-action='settings']").trigger("click");
    await wrapper.get("[data-action='add-api-key']").trigger("click");
    await wrapper.get("[data-field='config-alias']").setValue("Grok 中转");
    await wrapper.get("[data-field='config-api-key']").setValue("grok-key");
    await wrapper.get("[data-provider-type='grok']").trigger("click");

    expect(wrapper.get("[data-provider-type='grok']").attributes("aria-pressed")).toBe("true");
    await wrapper.get(".api-config-form").trigger("submit");
    await flushPromises();

    const createRequest = fetchMock.mock.calls.find(([, request]) => request?.method === "POST");
    expect(createRequest).toBeTruthy();
  });

  it("recreates a stale edited config without losing the Gemini form values", async () => {
    const fetchMock = vi.mocked(fetch);
    let recreated = false;
    fetchMock.mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: false });
      if (url.endsWith("/api/providers")) return jsonResponse({ providers: [] });
      if (url.endsWith("/api/settings") && !init?.method) return jsonResponse({
        active_config_id: recreated ? 2 : 1,
        api_key_configured: recreated,
        configs: recreated
          ? [{ id: 2, alias: "Gemini 中转", provider_type: "gemini", model: "gemini-3.1-flash-image", api_key_configured: true }]
          : [{ id: 1, alias: "默认配置", provider_type: "gpt", model: "gpt-image-1.5", api_key_configured: false }],
      });
      if (url.endsWith("/api/settings/api-keys/1") && init?.method === "PATCH") {
        return Promise.resolve(new Response(JSON.stringify({
          error: { code: "api_key_config_not_found", message: "配置不存在" },
        }), { status: 404, headers: { "Content-Type": "application/json" } }));
      }
      if (url.endsWith("/api/settings/api-keys") && init?.method === "POST") {
        expect(JSON.parse(String(init.body))).toEqual({
          alias: "Gemini 中转",
          api_key: "gemini-relay-key",
          provider_type: "gemini",
        });
        recreated = true;
        return jsonResponse({ id: 2 });
      }
      if (url.endsWith("/api/projects")) return jsonResponse([]);
      throw new Error(`Unexpected request: ${url} ${init?.method ?? "GET"}`);
    });

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get("[data-action='settings']").trigger("click");
    const editButton = wrapper.get(".api-config-row").findAll("button").find((button) => button.text() === "编辑");
    expect(editButton).toBeDefined();
    await editButton!.trigger("click");
    await wrapper.get("[data-field='config-alias']").setValue("Gemini 中转");
    await wrapper.get("[data-field='config-api-key']").setValue("gemini-relay-key");
    await wrapper.get("[data-provider-type='gemini']").trigger("click");
    await wrapper.get(".api-config-form").trigger("submit");
    await flushPromises();

    expect(recreated).toBe(true);
    expect(wrapper.get(".api-config-row").text()).toContain("Gemini 中转");
    expect(wrapper.get(".api-config-row").text()).toContain("Gemini");
    expect(wrapper.find(".settings-error").exists()).toBe(false);
  });

  it("asks for confirmation and allows deleting the last API key config", async () => {
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
        ],
      });
      if (url.endsWith("/api/settings/api-keys/1") && init?.method === "DELETE") return new Response(null, { status: 204 });
      if (url.endsWith("/api/projects")) return jsonResponse([]);
      if (url.endsWith("/api/history")) return jsonResponse([]);
      throw new Error(`Unexpected request: ${url} ${init?.method ?? "GET"}`);
    });

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get("[data-action='settings']").trigger("click");
    expect(wrapper.get("[data-action='delete-api-key']").attributes("disabled")).toBeUndefined();
    await wrapper.get("[data-action='delete-api-key']").trigger("click");
    await flushPromises();
    expect(wrapper.find(".confirm-dialog").exists()).toBe(true);
    expect(fetchMock.mock.calls.some(([input, init]) => String(input).endsWith("/api/settings/api-keys/1") && init?.method === "DELETE")).toBe(false);
    await wrapper.get(".confirm-dialog .secondary-action").trigger("click");
    expect(wrapper.find(".confirm-dialog").exists()).toBe(false);
    await wrapper.get("[data-action='delete-api-key']").trigger("click");
    await wrapper.get(".confirm-dialog .danger-action").trigger("click");
    await flushPromises();
    expect(fetchMock.mock.calls.some(([input, init]) => String(input).endsWith("/api/settings/api-keys/1") && init?.method === "DELETE")).toBe(true);
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

  it("toggles the project drawer and closes it from the backdrop or Escape", async () => {
    const wrapper = mount(App, { attachTo: document.body });
    await flushPromises();

    const trigger = wrapper.get(".mobile-sidebar-trigger");
    expect(trigger.attributes("aria-expanded")).toBe("false");

    await trigger.trigger("click");
    expect(wrapper.get(".studio-grid").classes()).toContain("sidebar-open");
    expect(wrapper.get(".project-sidebar-backdrop").exists()).toBe(true);
    expect(trigger.attributes("aria-expanded")).toBe("true");

    await trigger.trigger("click");
    expect(wrapper.find(".project-sidebar-backdrop").exists()).toBe(false);
    expect(trigger.attributes("aria-expanded")).toBe("false");

    await trigger.trigger("click");
    await wrapper.get(".project-sidebar-backdrop").trigger("click");
    expect(wrapper.find(".project-sidebar-backdrop").exists()).toBe(false);
    expect(wrapper.get(".studio-grid").classes()).not.toContain("sidebar-open");

    await trigger.trigger("click");
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".project-sidebar-backdrop").exists()).toBe(false);
    expect(trigger.attributes("aria-expanded")).toBe("false");
    wrapper.unmount();
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

  it("renders a complete Gemini data URL without adding another prefix", async () => {
    const dataUrl = "data:image/jpeg;base64,anBlZy1ieXRlcw==";
    vi.mocked(fetch).mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: true });
      if (url.endsWith("/api/generate")) return jsonResponse({
        provider: "gemini",
        model: "gemini-3.1-flash-image",
        images: [{ base64_data: dataUrl, generation_time_ms: 1000 }],
      });
      if (url.endsWith("/api/providers")) return jsonResponse({ providers: [] });
      if (url.endsWith("/api/settings")) return jsonResponse({ model: "gemini-3.1-flash-image", api_key_configured: true });
      if (url.endsWith("/api/history")) return jsonResponse([]);
      throw new Error(`Unexpected request: ${url}`);
    });

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get(".prompt-row textarea").setValue("生成 JPEG 图片");
    await wrapper.get(".composer-actions .primary-action").trigger("click");
    await flushPromises();

    expect(wrapper.get(".image-grid img").attributes("src")).toBe(dataUrl);
    expect(wrapper.get(".image-meta .download").attributes("href")).toBe(dataUrl);
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

  it("prefetches and reuses completed history details when reopening an image", async () => {
    let detailRequests = 0;
    vi.mocked(fetch).mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: true });
      if (url.endsWith("/api/providers")) return jsonResponse({ providers: [] });
      if (url.endsWith("/api/settings")) return jsonResponse({ model: "gpt-image-1.5", api_key_configured: true });
      if (url.endsWith("/api/projects")) return jsonResponse([{
        id: 1,
        name: "缓存项目",
        history: [{
          id: 7,
          kind: "generate",
          status: "completed",
          prompt: "缓存图片",
          provider: "compatible",
          model: "gpt-image-1.5",
          detail: "auto",
          image_count: 1,
          created_at: "2026-08-10T10:00:00",
        }],
        history_count: 1,
      }]);
      if (url.endsWith("/api/history/7")) {
        detailRequests++;
        return jsonResponse({
          id: 7,
          kind: "generate",
          status: "completed",
          prompt: "缓存图片",
          provider: "compatible",
          model: "gpt-image-1.5",
          detail: "auto",
          image_count: 1,
          elapsed_ms: 500,
          created_at: "2026-08-10T10:00:00",
          images: [{
            id: 9,
            role: "generated",
            mime_type: "image/png",
            position: 0,
            url: "/api/history/7/images/9",
          }],
        });
      }
      if (url.endsWith("/api/history")) return jsonResponse([]);
      throw new Error(`Unexpected request: ${url}`);
    });

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get(".history-select").trigger("pointerenter");
    await flushPromises();
    expect(detailRequests).toBe(1);

    await wrapper.get(".history-select").trigger("click");
    await flushPromises();
    expect(wrapper.get(".image-grid img").attributes("src")).toBe("/api/history/7/images/9");

    await wrapper.get(".history-select").trigger("click");
    await flushPromises();
    expect(detailRequests).toBe(1);
    wrapper.unmount();
  });

  it("shows a live generation card and timer for every requested image", async () => {
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
    expect(wrapper.find(".empty-wall").exists()).toBe(false);
    expect(wrapper.findAll(".generation-progress-card")).toHaveLength(1);
    expect(wrapper.get(".generation-progress-card .empty-shape").classes()).toContain("is-generating");
    expect(wrapper.get(".generation-progress-card .generation-water").attributes("style")).toBeUndefined();
    expect(wrapper.get(".generation-progress-card .empty-shape").attributes("style")).toContain("--generation-fill");
    expect(wrapper.get(".generation-progress-meta").text()).toMatch(/正在生成\d+\.\d{2} 秒/);

    finishGeneration?.(
      new Response(
        JSON.stringify({ provider: "compatible", model: "gpt-image-1.5", images: [] }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    await flushPromises();
    expect(wrapper.find(".generation-water").exists()).toBe(false);
  });

  it("keeps the water animation and timer visible while continuing a conversation", async () => {
    let finishGeneration: ((response: Response) => void) | undefined;
    const pendingGeneration = new Promise<Response>((resolve) => {
      finishGeneration = resolve;
    });
    vi.mocked(fetch).mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: true });
      if (url.endsWith("/api/providers")) {
        return jsonResponse({ providers: [{ id: "compatible", label: "北海AI", models: ["gpt-image-1.5"] }] });
      }
      if (url.endsWith("/api/settings")) return jsonResponse({ model: "gpt-image-1.5", api_key_configured: true });
      if (url.endsWith("/api/projects")) return jsonResponse([{
        id: 1,
        name: "项目",
        history: [{
          id: 7,
          kind: "generate",
          status: "completed",
          prompt: "已有图片",
          provider: "compatible",
          model: "gpt-image-1.5",
          detail: "auto",
          image_count: 1,
          created_at: "2026-08-11T10:00:00",
        }],
        history_count: 1,
      }]);
      if (url.endsWith("/api/history")) return jsonResponse([]);
      if (url.endsWith("/api/history/7")) return jsonResponse({
        id: 7,
        kind: "generate",
        status: "completed",
        prompt: "已有图片",
        provider: "compatible",
        model: "gpt-image-1.5",
        detail: "auto",
        image_count: 1,
        elapsed_ms: 900,
        created_at: "2026-08-11T10:00:00",
        images: [{
          id: 9,
          role: "generated",
          mime_type: "image/png",
          position: 0,
          url: "/api/history/7/images/9",
        }],
      });
      if (url.endsWith("/api/generate")) return pendingGeneration;
      throw new Error(`Unexpected request: ${url}`);
    });

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get(".history-select").trigger("click");
    await flushPromises();
    await wrapper.get(".prompt-row textarea").setValue("继续生成");
    await wrapper.get("[data-parameter-trigger='count']").trigger("click");
    await wrapper.get("[data-parameter-option='4']").trigger("click");
    await wrapper.get(".primary-action").trigger("click");
    await wrapper.vm.$nextTick();

    expect(wrapper.findAll(".image-grid .image-card")).toHaveLength(5);
    expect(wrapper.findAll(".generation-progress-card")).toHaveLength(4);
    expect(wrapper.findAll(".generation-progress-card .empty-shape").every((node) => node.classes().includes("is-generating"))).toBe(true);
    expect(wrapper.findAll(".generation-progress-card .generation-water")).toHaveLength(4);
    expect(wrapper.findAll(".generation-progress-meta").every((node) => /正在生成\d+\.\d{2} 秒/.test(node.text()))).toBe(true);

    finishGeneration?.(new Response(JSON.stringify({ images: [] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    await flushPromises();
    expect(wrapper.find(".generation-progress-card").exists()).toBe(false);
    wrapper.unmount();
  });

  it("keeps a background generation available while navigating elsewhere", async () => {
    let finishGeneration: ((response: Response) => void) | undefined;
    const pendingGeneration = new Promise<Response>((resolve) => {
      finishGeneration = resolve;
    });
    const projects = [
      {
        id: 1,
        name: "当前项目",
        history: [{
          id: 7,
          kind: "generate",
          status: "completed",
          prompt: "历史图片",
          provider: "compatible",
          model: "gpt-image-1.5",
          detail: "auto",
          image_count: 1,
          created_at: "2026-08-10T10:00:00",
        }],
        history_count: 1,
      },
      { id: 2, name: "其他项目", history: [], history_count: 0 },
    ];
    let historyOpened = false;
    vi.mocked(fetch).mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: true });
      if (url.endsWith("/api/generate")) return pendingGeneration;
      if (url.endsWith("/api/providers")) {
        return jsonResponse({ providers: [{ id: "compatible", label: "北海AI", models: ["gpt-image-1.5"] }] });
      }
      if (url.endsWith("/api/settings")) {
        return jsonResponse({ model: "gpt-image-1.5", api_key_configured: true });
      }
      if (url.endsWith("/api/projects")) return jsonResponse(projects);
      if (url.endsWith("/api/history")) return jsonResponse([]);
      if (url.endsWith("/api/history/7")) {
        historyOpened = true;
        return jsonResponse({
          id: 7,
          kind: "generate",
          status: "completed",
          prompt: "历史图片",
          provider: "compatible",
          model: "gpt-image-1.5",
          detail: "auto",
          image_count: 1,
          created_at: "2026-08-10T10:00:00",
          images: [],
        });
      }
      throw new Error(`Unexpected request: ${url}`);
    });

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get(".prompt-row textarea").setValue("保持当前生成页面");
    await wrapper.get(".primary-action").trigger("click");
    await wrapper.vm.$nextTick();

    expect(wrapper.get("[data-action='settings']").attributes("disabled")).toBeUndefined();
    expect(wrapper.findAll(".project-select")[1].attributes("disabled")).toBeUndefined();
    expect(wrapper.get(".history-select").attributes("disabled")).toBeUndefined();

    await wrapper.findAll(".project-select")[1].trigger("click");
    await wrapper.vm.$nextTick();

    expect(wrapper.get("[data-project-id='2']").classes()).toContain("active");
    expect(wrapper.get<HTMLTextAreaElement>(".prompt-row textarea").element.value).toBe("保持当前生成页面");
    expect(wrapper.get(".primary-action").text()).toContain("生成图片");
    await wrapper.get("[data-project-id='1'] .project-toggle").trigger("click");
    expect(wrapper.get(".running-generation").text()).toMatch(/正在生成 · \d+\.\d{2} 秒/);

    await wrapper.get(".running-generation").trigger("click");
    await wrapper.vm.$nextTick();

    expect(wrapper.get("[data-project-id='1']").classes()).toContain("active");
    expect(wrapper.get<HTMLTextAreaElement>(".prompt-row textarea").element.value).toBe("保持当前生成页面");
    expect(wrapper.get(".generation-progress-meta").text()).toMatch(/正在生成\d+\.\d{2} 秒/);
    expect(wrapper.get(".primary-action").text()).toContain("生成图片");

    await wrapper.get("[data-action='settings']").trigger("click");
    expect(window.location.pathname).toBe("/settings");
    expect(wrapper.find(".settings-page").exists()).toBe(true);
    await wrapper.get("[data-action='back-to-workspace']").trigger("click");
    await wrapper.vm.$nextTick();
    expect(wrapper.get(".primary-action").text()).toContain("生成图片");

    await wrapper.get(".history-select").trigger("click");
    await flushPromises();
    expect(historyOpened).toBe(true);
    expect(wrapper.get(".result-heading h2").text()).toBe("历史结果");
    expect(wrapper.get(".running-generation").classes()).not.toContain("active");

    await wrapper.get(".running-generation").trigger("click");
    await wrapper.vm.$nextTick();
    expect(wrapper.get(".result-heading h2").text()).toBe("生成结果");
    expect(wrapper.get(".primary-action").text()).toContain("生成图片");

    finishGeneration?.(
      new Response(
        JSON.stringify({
          provider: "compatible",
          model: "gpt-image-1.5",
          images: [{ base64_data: "cmVzdWx0", generation_time_ms: 1200 }],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    await flushPromises();

    expect(wrapper.get(".image-grid img").attributes("src")).toBe("data:image/png;base64,cmVzdWx0");
    wrapper.unmount();
  });

  it("submits another batch in the same conversation before the first result finishes", async () => {
    const generationBodies: Array<Record<string, unknown>> = [];
    let batchSequence = 0;
    let finishFirstBatch: ((response: Response) => void) | undefined;
    let finishSecondBatch: ((response: Response) => void) | undefined;
    vi.mocked(fetch).mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: true });
      if (url.endsWith("/api/providers")) {
        return jsonResponse({ providers: [{ id: "compatible", label: "北海AI", models: ["gpt-image-1.5"] }] });
      }
      if (url.endsWith("/api/settings")) return jsonResponse({ model: "gpt-image-1.5", api_key_configured: true });
      if (url.endsWith("/api/projects")) {
        return jsonResponse([{ id: 1, name: "项目", history: [], history_count: 0 }]);
      }
      if (url.endsWith("/api/history")) return jsonResponse([]);
      if (url.endsWith("/api/generate") && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        generationBodies.push(body);
        batchSequence++;
        return Promise.resolve(new Response(JSON.stringify({
          task_id: 44,
          batch_id: 100 + batchSequence,
          status: "pending",
          status_url: `/api/history/44/batches/${100 + batchSequence}`,
        }), { status: 202, headers: { "Content-Type": "application/json" } }));
      }
      if (/\/api\/history\/44\/batches\/10[12]$/.test(url)) {
        const batchId = Number(url.slice(-3));
        return new Promise<Response>((resolve) => {
          if (batchId === 101) finishFirstBatch = resolve;
          else finishSecondBatch = resolve;
        });
      }
      throw new Error(`Unexpected request: ${url} ${init?.method ?? "GET"}`);
    });

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get(".prompt-row textarea").setValue("第一批");
    await wrapper.get(".primary-action").trigger("click");
    await flushPromises();

    expect(wrapper.get(".primary-action").text()).toContain("生成图片");
    expect(wrapper.get(".primary-action").attributes("disabled")).toBeUndefined();

    await wrapper.get(".prompt-row textarea").setValue("第二批");
    await wrapper.get(".primary-action").trigger("click");
    await flushPromises();

    expect(generationBodies).toHaveLength(2);
    expect(generationBodies[0]).not.toHaveProperty("conversation_id");
    expect(generationBodies[1]).toMatchObject({ conversation_id: 44, prompt: "第二批" });
    expect(wrapper.findAll(".running-generation")).toHaveLength(1);
    expect(wrapper.findAll(".generation-progress-card")).toHaveLength(2);

    finishFirstBatch?.(new Response(JSON.stringify({
      id: 101,
      history_id: 44,
      status: "completed",
      elapsed_ms: 1200,
      images: [{
        id: 501,
        batch_id: 101,
        role: "generated",
        mime_type: "image/png",
        position: 0,
        url: "/api/history/44/images/501",
      }],
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    await flushPromises();

    expect(wrapper.findAll(".image-grid img")).toHaveLength(1);
    expect(wrapper.get(".image-grid img").attributes("src")).toBe("/api/history/44/images/501");
    expect(wrapper.findAll(".generation-progress-card")).toHaveLength(1);

    finishSecondBatch?.(new Response(JSON.stringify({
      id: 102,
      history_id: 44,
      status: "completed",
      elapsed_ms: 2400,
      images: [{
        id: 502,
        batch_id: 102,
        role: "generated",
        mime_type: "image/png",
        position: 0,
        url: "/api/history/44/images/502",
      }],
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    await flushPromises();

    expect(wrapper.findAll(".image-grid img")).toHaveLength(2);
    expect(wrapper.findAll(".image-grid img").map((image) => image.attributes("src"))).toEqual([
      "/api/history/44/images/501",
      "/api/history/44/images/502",
    ]);
    expect(wrapper.findAll(".generation-progress-card")).toHaveLength(0);
    wrapper.unmount();
  });

  it("polls an accepted generation task and displays its stored image", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: true });
      if (url.endsWith("/api/providers")) {
        return jsonResponse({ providers: [{ id: "compatible", label: "北海AI", models: ["gpt-image-1.5"] }] });
      }
      if (url.endsWith("/api/settings")) return jsonResponse({ model: "gpt-image-1.5", api_key_configured: true });
      if (url.endsWith("/api/projects")) {
        return jsonResponse([{ id: 1, name: "项目", history: [], history_count: 0 }]);
      }
      if (url.endsWith("/api/history")) return jsonResponse([]);
      if (url.endsWith("/api/generate") && init?.method === "POST") {
        return Promise.resolve(new Response(JSON.stringify({
          task_id: 44,
          status: "pending",
          status_url: "/api/history/44",
        }), { status: 202, headers: { "Content-Type": "application/json" } }));
      }
      if (url.endsWith("/api/history/44")) return jsonResponse({
        id: 44,
        kind: "generate",
        status: "completed",
        prompt: "异步图片",
        provider: "compatible",
        model: "gpt-image-1.5",
        detail: "auto",
        image_count: 1,
        size: "1:1",
        resolution: "1K",
        elapsed_ms: 2300,
        created_at: "2026-08-10T10:00:00",
        completed_at: "2026-08-10T10:00:02",
        images: [{
          id: 9,
          role: "generated",
          mime_type: "image/png",
          position: 0,
          url: "/api/history/44/images/9",
        }],
      });
      throw new Error(`Unexpected request: ${url} ${init?.method ?? "GET"}`);
    });

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get(".prompt-row textarea").setValue("异步图片");
    await wrapper.get(".primary-action").trigger("click");
    await flushPromises();
    await flushPromises();

    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith("/api/history/44"))).toBe(true);
    expect(wrapper.get(".image-grid img").attributes("src")).toBe("/api/history/44/images/9");
    expect(wrapper.get(".image-meta strong").text()).toBe("2.30 秒");
    wrapper.unmount();
  });

  it("continues the current conversation until a new conversation is selected", async () => {
    const generationBodies: Array<Record<string, unknown>> = [];
    const taskRounds = new Map<number, number>();
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return jsonResponse({ username: "alice", api_key_configured: true });
      if (url.endsWith("/api/providers")) {
        return jsonResponse({ providers: [{ id: "compatible", label: "北海AI", models: ["gpt-image-1.5"] }] });
      }
      if (url.endsWith("/api/settings")) return jsonResponse({ model: "gpt-image-1.5", api_key_configured: true });
      if (url.endsWith("/api/history")) return jsonResponse([]);
      if (url.endsWith("/api/generate") && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        generationBodies.push(body);
        const taskId = body.conversation_id === 44 || generationBodies.length < 4 ? 44 : 45;
        taskRounds.set(taskId, (taskRounds.get(taskId) ?? 0) + 1);
        return Promise.resolve(new Response(JSON.stringify({
          task_id: taskId,
          status: "pending",
          status_url: `/api/history/${taskId}`,
        }), { status: 202, headers: { "Content-Type": "application/json" } }));
      }
      if (url.endsWith("/api/projects")) {
        const histories = [...taskRounds.keys()].reverse().map((id) => ({
          id,
          kind: "generate",
          status: "completed",
          prompt: id === 44 ? "继续调整" : "全新对话",
          provider: "compatible",
          model: "gpt-image-1.5",
          detail: "auto",
          image_count: 1,
          size: "1:1",
          resolution: "1K",
          created_at: "2026-08-11T10:00:00",
        }));
        return jsonResponse([{ id: 1, name: "项目", history: histories, history_count: histories.length }]);
      }
      const historyMatch = url.match(/\/api\/history\/(44|45)$/);
      if (historyMatch) {
        const taskId = Number(historyMatch[1]);
        const rounds = taskRounds.get(taskId) ?? 1;
        return jsonResponse({
          id: taskId,
          kind: "generate",
          status: "completed",
          prompt: taskId === 44 ? "继续调整" : "全新对话",
          provider: "compatible",
          model: "gpt-image-1.5",
          detail: "auto",
          image_count: 1,
          size: "1:1",
          resolution: "1K",
          elapsed_ms: 1200,
          created_at: "2026-08-11T10:00:00",
          completed_at: "2026-08-11T10:00:01",
          images: Array.from({ length: rounds }, (_, index) => ({
            id: taskId * 10 + index,
            batch_id: taskId * 100 + index,
            role: "generated",
            mime_type: "image/png",
            position: index,
            url: `/api/history/${taskId}/images/${taskId * 10 + index}`,
          })),
        });
      }
      throw new Error(`Unexpected request: ${url} ${init?.method ?? "GET"}`);
    });

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get(".prompt-row textarea").setValue("第一轮");
    await wrapper.get(".primary-action").trigger("click");
    await flushPromises();
    await flushPromises();

    await wrapper.get(".prompt-row textarea").setValue("继续调整");
    await wrapper.get(".primary-action").trigger("click");
    await flushPromises();
    await flushPromises();

    expect(generationBodies[0]).not.toHaveProperty("conversation_id");
    expect(generationBodies[1]).toMatchObject({ conversation_id: 44, prompt: "继续调整" });
    expect(wrapper.findAll(".image-grid img")).toHaveLength(2);
    expect(wrapper.findAll(".image-grid img").map((image) => image.attributes("src"))).toEqual([
      "/api/history/44/images/440",
      "/api/history/44/images/441",
    ]);
    expect(wrapper.findAll(".history-select")).toHaveLength(1);

    await wrapper.get(".prompt-row textarea").setValue("第三轮调整");
    await wrapper.get(".primary-action").trigger("click");
    await flushPromises();
    await flushPromises();

    expect(generationBodies[2]).toMatchObject({ conversation_id: 44, prompt: "第三轮调整" });
    expect(wrapper.findAll(".image-grid img")).toHaveLength(3);
    expect(wrapper.findAll(".image-grid img").map((image) => image.attributes("src"))).toEqual([
      "/api/history/44/images/440",
      "/api/history/44/images/441",
      "/api/history/44/images/442",
    ]);

    await wrapper.get(".project-new-conversation").trigger("click");
    await wrapper.get(".prompt-row textarea").setValue("全新对话");
    await wrapper.get(".primary-action").trigger("click");
    await flushPromises();
    await flushPromises();

    expect(generationBodies[3]).not.toHaveProperty("conversation_id");
    expect(generationBodies[3]).toMatchObject({ prompt: "全新对话" });
    wrapper.unmount();
  });

  it("deletes one stored result and restores the selected image generation snapshot", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) {
        return jsonResponse({ username: "alice", api_key_configured: true });
      }
      if (url.endsWith("/api/providers")) return jsonResponse({ providers: [] });
      if (url.endsWith("/api/settings") && !init?.method) {
        return jsonResponse({
          active_config_id: 4,
          api_key_configured: true,
          configs: [{
            id: 4,
            alias: "GPT",
            provider_type: "gpt",
            model: "gpt-image-2",
            api_key_configured: true,
          }],
        });
      }
      if (url.endsWith("/api/settings/api-keys/4/models")) {
        return jsonResponse({
          models: [{ id: "gpt-image-2", provider_type: "gpt" }],
        });
      }
      if (url.endsWith("/api/settings/active") && init?.method === "PUT") {
        return jsonResponse({ active_config_id: 4 });
      }
      const historySummary = {
        id: 7,
        kind: "generate",
        status: "completed",
        prompt: "最后一轮",
        provider: "compatible",
        model: "gpt-image-2",
        detail: "auto",
        image_count: 1,
        size: "1:1",
        resolution: "1K",
        elapsed_ms: 900,
        created_at: "2026-08-12T10:00:00",
      };
      if (url.endsWith("/api/projects")) {
        return jsonResponse([{ id: 1, name: "项目", history: [historySummary], history_count: 1 }]);
      }
      if (url.endsWith("/api/history")) return jsonResponse([historySummary]);
      if (url.endsWith("/api/history/7/images/9/edit")) {
        return jsonResponse({
          history_id: 7,
          image_id: 9,
          api_key_config_id: 4,
          prompt: "恢复这一轮提示词",
          provider: "compatible",
          model: "gpt-image-2",
          detail: "high",
          image_count: 4,
          size: "2048x1152",
          resolution: null,
          output_format: "webp",
          background: "opaque",
          output_compression: 84,
          moderation: "low",
          references: [
            { id: 31, category: "person", mime_type: "image/jpeg", filename: "person.jpg", position: 0, url: "/api/history/7/images/31" },
            { id: 32, category: "object", mime_type: "image/png", filename: "chair.png", position: 1, url: "/api/history/7/images/32" },
          ],
        });
      }
      if (url.endsWith("/api/history/7/images/9") && init?.method === "DELETE") {
        return Promise.resolve(new Response(null, { status: 204 }));
      }
      if (url.endsWith("/api/history/7")) {
        return jsonResponse({
          ...historySummary,
          completed_at: "2026-08-12T10:00:01",
          images: [
            { id: 9, role: "generated", mime_type: "image/png", position: 0, url: "/api/history/7/images/9" },
            { id: 10, role: "generated", mime_type: "image/png", position: 1, url: "/api/history/7/images/10" },
          ],
        });
      }
      throw new Error(`Unexpected request: ${url} ${init?.method ?? "GET"}`);
    });

    const wrapper = mount(App);
    await flushPromises();
    await wrapper.get(".history-select").trigger("click");
    await flushPromises();

    expect(wrapper.findAll("[aria-label='修改图片']")).toHaveLength(2);
    expect(wrapper.findAll("[aria-label='删除图片']")).toHaveLength(2);
    expect(wrapper.findAll(".download")).toHaveLength(2);

    await wrapper.findAll("[aria-label='修改图片']")[0].trigger("click");
    await flushPromises();

    expect(wrapper.get<HTMLTextAreaElement>(".prompt-row textarea").element.value).toBe("恢复这一轮提示词");
    expect(wrapper.get("[data-parameter-trigger='model']").text()).toContain("gpt-image-2");
    expect(wrapper.get("[data-parameter-trigger='size']").text()).toContain("2K 横向");
    expect(wrapper.find("[data-parameter-trigger='resolution']").exists()).toBe(false);
    expect(wrapper.get("[data-parameter-trigger='quality']").text()).toContain("高");
    expect(wrapper.find("[data-parameter-trigger='format']").exists()).toBe(false);
    expect(wrapper.find("[data-parameter-trigger='background']").exists()).toBe(false);
    expect(wrapper.find("[data-parameter-trigger='moderation']").exists()).toBe(false);
    expect(wrapper.find("#output-compression").exists()).toBe(false);
    expect(wrapper.get("[data-parameter-trigger='count']").text()).toContain("4 张");
    const referenceModules = wrapper.findAll(".reference-module");
    expect(referenceModules[0].findAll(".reference-thumbnail")).toHaveLength(1);
    expect(referenceModules[1].findAll(".reference-thumbnail")).toHaveLength(0);
    expect(referenceModules[2].findAll(".reference-thumbnail")).toHaveLength(1);
    expect(wrapper.findAll(".image-grid img")).toHaveLength(2);

    await wrapper.findAll("[aria-label='删除图片']")[0].trigger("click");
    await flushPromises();

    expect(wrapper.findAll(".image-grid img")).toHaveLength(1);
    expect(wrapper.get(".image-grid img").attributes("src")).toBe("/api/history/7/images/10");
    expect(fetchMock.mock.calls.some(([input, init]) => (
      String(input).endsWith("/api/history/7/images/9") && init?.method === "DELETE"
    ))).toBe(true);
    wrapper.unmount();
  });

});
