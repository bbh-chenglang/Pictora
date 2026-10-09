import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App.vue";

const jsonResponse = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { "Content-Type": "application/json" },
});

function deferredResponse() {
  let resolve!: (response: Response) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<Response>((ok, fail) => { resolve = ok; reject = fail; });
  return { promise, resolve, reject };
}

describe("password recovery", () => {
  const wrappers: VueWrapper[] = [];
  let handleRequest: (url: string, init?: RequestInit) => Promise<Response>;

  beforeEach(() => {
    window.localStorage.clear();
    window.history.replaceState({}, "", "/");
    handleRequest = async (url) => {
      if (url.endsWith("/api/auth/password-reset-code")) {
        return jsonResponse({ message: "请求已受理，如该邮箱已绑定账号，将收到找回密码验证码", retry_after_seconds: 60 });
      }
      if (url.endsWith("/api/auth/reset-password")) return new Response(null, { status: 204 });
      throw new Error(`Unexpected request: ${url}`);
    };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) return new Response(null, { status: 401 });
      return handleRequest(url, init);
    }));
  });

  afterEach(() => {
    for (const wrapper of wrappers.splice(0)) wrapper.unmount();
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  async function openReset() {
    const wrapper = mount(App, { global: { stubs: { SnowfallBackground: true, FlowingGridBackground: true } } });
    wrappers.push(wrapper);
    await flushPromises();
    await wrapper.get("[data-action='forgot-password']").trigger("click");
    return wrapper;
  }

  async function fillReset(wrapper: VueWrapper, confirmation = "changed6") {
    await wrapper.get("input[type='email']").setValue("Alice@Example.com");
    await wrapper.get("input[autocomplete='one-time-code']").setValue("123456");
    const passwords = wrapper.findAll("input[type='password']");
    await passwords[0].setValue("changed6");
    await passwords[1].setValue(confirmation);
  }

  it("opens the reset form and clears sensitive fields when returning to login", async () => {
    const wrapper = await openReset();
    expect(wrapper.get("h2").text()).toBe("找回密码");
    expect(wrapper.text()).toContain("未绑定邮箱的旧账号请联系管理员");
    expect(wrapper.find("input[autocomplete='username']").exists()).toBe(false);
    await fillReset(wrapper);
    await wrapper.get("[data-action='switch-auth']").trigger("click");
    expect(wrapper.get("h2").text()).toBe("登录 Pictora");
    expect((wrapper.get("input[autocomplete='username']").element as HTMLInputElement).value).toBe("Alice@Example.com");
    expect((wrapper.get("input[type='password']").element as HTMLInputElement).value).toBe("");
    await wrapper.get("[data-action='forgot-password']").trigger("click");
    expect((wrapper.get("input[autocomplete='one-time-code']").element as HTMLInputElement).value).toBe("");
    expect(wrapper.findAll("input[type='password']").every((field) => (field.element as HTMLInputElement).value === "")).toBe(true);
  });

  it("sends a normalized email and counts down before allowing a resend", async () => {
    vi.useFakeTimers();
    const wrapper = await openReset();
    await wrapper.get("input[type='email']").setValue(" Alice@Example.com ");
    await wrapper.get(".verification-action").trigger("click");
    await flushPromises();
    const request = vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith("/api/auth/password-reset-code"));
    expect(JSON.parse(String(request?.[1]?.body))).toEqual({ email: "alice@example.com" });
    expect(request?.[1]?.credentials).toBe("include");
    expect(wrapper.get("[role='status']").text()).toContain("如该邮箱已绑定账号");
    expect(wrapper.get(".verification-action").text()).toBe("60 秒");
    expect(wrapper.get(".verification-action").attributes("disabled")).toBeDefined();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(wrapper.get(".verification-action").text()).toBe("获取验证码");
    expect(wrapper.get(".verification-action").attributes("disabled")).toBeUndefined();
  });

  it("resets the password and returns to login with the email and success message", async () => {
    const wrapper = await openReset();
    await fillReset(wrapper);
    await wrapper.get(".auth-form").trigger("submit");
    await flushPromises();
    const request = vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith("/api/auth/reset-password"));
    expect(JSON.parse(String(request?.[1]?.body))).toEqual({
      email: "alice@example.com", verification_code: "123456",
      new_password: "changed6", new_password_confirmation: "changed6",
    });
    expect(wrapper.get("h2").text()).toBe("登录 Pictora");
    expect(wrapper.get("[role='status']").text()).toBe("密码已重置，请使用新密码登录");
    expect((wrapper.get("input[autocomplete='username']").element as HTMLInputElement).value).toBe("Alice@Example.com");
    expect((wrapper.get("input[type='password']").element as HTMLInputElement).value).toBe("");
    expect(wrapper.find(".studio-workspace").exists()).toBe(false);
  });

  it.each([
    ["email", "bad-address"], ["code", "123"], ["password", "short"], ["confirmation", "different6"],
  ])("rejects an invalid %s without submitting", async (field, value) => {
    const wrapper = await openReset();
    await fillReset(wrapper);
    const inputs = {
      email: wrapper.get("input[type='email']"),
      code: wrapper.get("input[autocomplete='one-time-code']"),
      password: wrapper.findAll("input[type='password']")[0],
      confirmation: wrapper.findAll("input[type='password']")[1],
    };
    await inputs[field as keyof typeof inputs].setValue(value);
    await wrapper.get(".auth-form").trigger("submit");
    await flushPromises();
    expect(wrapper.get("[role='alert']").text()).toContain("请填写有效邮箱和 6 位验证码");
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith("/api/auth/reset-password"))).toBe(false);
  });

  it("rejects an invalid email before requesting a code", async () => {
    const wrapper = await openReset();
    await wrapper.get("input[type='email']").setValue("invalid");
    await wrapper.get(".verification-action").trigger("click");
    expect(wrapper.get("[role='alert']").text()).toBe("请先填写有效邮箱");
    expect(vi.mocked(fetch).mock.calls).toHaveLength(1);
  });

  it("prevents duplicate sends and duplicate resets while requests are pending", async () => {
    const wrapper = await openReset();
    await fillReset(wrapper);
    const pending = deferredResponse();
    handleRequest = () => pending.promise;
    await wrapper.get(".verification-action").trigger("click");
    await wrapper.get(".verification-action").trigger("click");
    expect(wrapper.get(".verification-action").text()).toBe("发送中");
    expect(vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith("/api/auth/password-reset-code"))).toHaveLength(1);
    pending.resolve(jsonResponse({ retry_after_seconds: 60 }));
    await flushPromises();
    const resetting = deferredResponse();
    handleRequest = () => resetting.promise;
    await wrapper.get(".auth-form").trigger("submit");
    await wrapper.get(".auth-form").trigger("submit");
    expect(wrapper.get(".auth-submit").attributes("disabled")).toBeDefined();
    expect(vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith("/api/auth/reset-password"))).toHaveLength(1);
    resetting.resolve(new Response(null, { status: 204 }));
    await flushPromises();
  });

  it("shows code errors and remains on the reset form", async () => {
    handleRequest = async () => jsonResponse({ error: { code: "invalid_verification_code" } }, 400);
    const wrapper = await openReset();
    await fillReset(wrapper);
    await wrapper.get(".auth-form").trigger("submit");
    await flushPromises();
    expect(wrapper.get("h2").text()).toBe("找回密码");
    expect(wrapper.get("[role='alert']").text()).toBe("验证码错误或已失效");
    expect(wrapper.get(".auth-submit").attributes("disabled")).toBeUndefined();
  });

  it("honors a cooldown returned by the server", async () => {
    handleRequest = async () => jsonResponse({
      error: { code: "verification_code_cooldown", retry_after_seconds: 23 },
    }, 429);
    const wrapper = await openReset();
    await fillReset(wrapper);
    await wrapper.get(".verification-action").trigger("click");
    await flushPromises();
    expect(wrapper.get("[role='alert']").text()).toContain("发送过于频繁");
    expect(wrapper.get(".verification-action").text()).toBe("23 秒");
  });

  it("shows SMTP configuration and network failures", async () => {
    const wrapper = await openReset();
    await fillReset(wrapper);
    handleRequest = async () => jsonResponse({ error: { code: "smtp_not_configured" } }, 503);
    await wrapper.get(".verification-action").trigger("click");
    await flushPromises();
    expect(wrapper.get("[role='alert']").text()).toBe("邮件服务尚未配置");
    handleRequest = async () => { throw new Error("offline"); };
    await wrapper.get(".verification-action").trigger("click");
    await flushPromises();
    expect(wrapper.get("[role='alert']").text()).toBe("无法连接邮件服务");
    await wrapper.get(".auth-form").trigger("submit");
    await flushPromises();
    expect(wrapper.get("[role='alert']").text()).toBe("无法连接服务器");
  });

  it.each(["send", "reset"])("ignores a late %s response after leaving and reopening the form", async (action) => {
    const wrapper = await openReset();
    await fillReset(wrapper);
    const pending = deferredResponse();
    handleRequest = () => pending.promise;
    await wrapper.get(action === "send" ? ".verification-action" : ".auth-form").trigger(action === "send" ? "click" : "submit");
    await wrapper.get("[data-action='switch-auth']").trigger("click");
    await wrapper.get("[data-action='forgot-password']").trigger("click");
    pending.resolve(action === "send" ? jsonResponse({ message: "late result", retry_after_seconds: 60 }) : new Response(null, { status: 204 }));
    await flushPromises();
    expect(wrapper.get("h2").text()).toBe("找回密码");
    expect(wrapper.find("[role='status']").exists()).toBe(false);
    expect(wrapper.get(".verification-action").text()).toBe("获取验证码");
  });

  it("ignores a late response after changing the target email", async () => {
    const wrapper = await openReset();
    await fillReset(wrapper);
    const pending = deferredResponse();
    handleRequest = () => pending.promise;
    await wrapper.get(".verification-action").trigger("click");
    await wrapper.get("input[type='email']").setValue("other@example.com");
    expect((wrapper.get("input[autocomplete='one-time-code']").element as HTMLInputElement).value).toBe("");
    pending.resolve(jsonResponse({ message: "late result", retry_after_seconds: 60 }));
    await flushPromises();
    expect(wrapper.find("[role='status']").exists()).toBe(false);
    expect(wrapper.get(".verification-action").text()).toBe("获取验证码");
  });

  it("cleans up the cooldown timer on unmount", async () => {
    vi.useFakeTimers();
    const wrapper = await openReset();
    await fillReset(wrapper);
    await wrapper.get(".verification-action").trigger("click");
    await flushPromises();
    expect(vi.getTimerCount()).toBeGreaterThan(0);
    wrapper.unmount();
    wrappers.splice(wrappers.indexOf(wrapper), 1);
    expect(vi.getTimerCount()).toBe(0);
  });
});
