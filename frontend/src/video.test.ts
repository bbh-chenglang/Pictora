import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import VideoWorkspace from "./components/VideoWorkspace.vue";
import VideoSettings from "./components/VideoSettings.vue";
import VideoTaskCard from "./components/VideoTaskCard.vue";
import VideoProjectSidebar from "./components/VideoProjectSidebar.vue";
import App from "./App.vue";
import { VideoApiError, formatVideoElapsed, videoElapsedMs, videoTimestamp, materialIssue, videoJson, videoValidation, type VideoFeatures, type VideoModel, type VideoTask } from "./video";

const baseModel: VideoModel = {
  id: "sd-2.0-J2", default_duration: 5, default_resolution: "720p", default_ratio: "16:9",
  ratios: ["16:9", "9:16", "1:1"], durations_by_resolution: { "720p": [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15] },
  reference_limits: { image: 9, video: 3, audio: 3 }, max_total_materials: null, max_video_duration_seconds: null,
};
const models: VideoModel[] = [
  baseModel,
  { ...baseModel, id: "minimax-h3", default_duration: 15, default_resolution: "2k", durations_by_resolution: { "2k": [4, 5, 10, 15] }, max_total_materials: 10, max_video_duration_seconds: 15 },
  { ...baseModel, id: "sd-2.0-900-J3", default_duration: 10, durations_by_resolution: { "720p": [10, 15] }, reference_limits: { image: 9, video: null, audio: null } },
  { ...baseModel, id: "seedance-2.5-101010", reference_limits: { image: 10, video: 0, audio: 10 } },
];
const ready: VideoFeatures = { assets_ready: true, storage_configured: true, storage_ready: true, media_tools_ready: true, catalog_source: "mock", api_base_url: "https://api.beibeihai.xyz", notes: [] };
const task = (id = 1, overrides: Partial<VideoTask> = {}): VideoTask => ({
  id, project_id: 1, prompt: "video prompt", model: "sd-2.0-J2", status: "queued", duration: 5, resolution: "720p", ratio: "16:9", created_at: "2026-10-06T00:00:00Z",
  request_id: "e4ae7951-8f2c-4781-a2c0-3c8b445d708d", api_key_config_id: 11, upstream_task_id: null, upstream_status: null, progress: null,
  tracking_abandoned: 0, error_message: null, error_code: null, materials: [], results: [], ...overrides,
});
function response(body: unknown, status = 200) { return new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }); }
const wrappers: VueWrapper[] = [];
function keep<T extends VueWrapper>(wrapper: T): T { wrappers.push(wrapper); return wrapper; }
function server(features = ready) {
  const tasks: VideoTask[] = [];
  const api = vi.fn(async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = String(input);
    if (url.endsWith("/api/videos/models")) return response({ models, features });
    if (url.endsWith("/api/videos/readiness")) return response(features);
    if (url.endsWith("/api/settings/video-api-keys")) return response({ configs: [{ id: 11, alias: "视频配置", model: baseModel.id, api_key_configured: true }], active_config_id: 11 });
    if (url.includes("/api/videos/tasks?") || url.match(/\/api\/videos\/tasks\/\d+$/)) return response(url.includes("?") ? tasks : tasks[0]);
    if (url.endsWith("/api/videos/tasks") && init?.method === "POST") {
      const body = JSON.parse(String(init.body)); const created = task(tasks.length + 1, { ...body, status: "queued" }); tasks.unshift(created);
      return response({ task: created }, 202);
    }
    if (url.endsWith("/api/videos/assets/from-history")) return response({ id: "snapshot", preview_url: "/api/videos/assets/snapshot/file" });
    if (url.includes("/api/videos/assets/upload")) return response({ id: "upload", name: "clip", preview_url: "/api/videos/assets/upload/file", duration_seconds: 9 });
    if (url.includes("/api/videos/tasks/")) return response({});
    throw new Error("Unexpected request: " + url);
  });
  return { api, tasks };
}
async function workspace(features = ready) {
  const state = server(features);
  const wrapper = keep(mount(VideoWorkspace, { props: { active: true, account: "alice", projectId: 1, selectedTaskId: null, apiFetch: state.api, apiBase: "" } }));
  await flushPromises(); return { ...state, wrapper };
}
function button(wrapper: VueWrapper, text: string) { const found = wrapper.findAll("button").find(b => b.text() === text); if (!found) throw new Error("Button not found: " + text); return found; }
async function addLink(wrapper: VueWrapper, kind: string, url: string, name = "") {
  await wrapper.get('[data-field="video-material-type"]').setValue(kind);
  await wrapper.get('[data-field="video-material-url"]').setValue(url);
  await wrapper.get('[data-field="video-material-name"]').setValue(name);
  await button(wrapper, "添加链接").trigger("click");
}
beforeEach(() => { localStorage.clear(); vi.useFakeTimers(); });
afterEach(() => { for (const w of wrappers.splice(0)) w.unmount(); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); window.history.replaceState({}, "", "/"); });

describe("video capability validation", () => {
  it("validates discrete durations and the exact 2k default", () => {
    expect(videoValidation(models[1], 15, "2k", "16:9", [])).toEqual([]);
    expect(videoValidation(models[1], 15, "720p", "16:9", [])).not.toEqual([]);
    expect(videoValidation(models[2], 11, "720p", "16:9", [])).not.toEqual([]);
    expect(videoValidation(models[2], 10, "720p", "16:9", [])).toEqual([]);
  });
  it.each([models[2], models[3]])("does not guess unknown or unsupported video references in $id", model => {
    const material = { type: "video" as const, name: "clip", url: "https://example.com/clip.mp4" };
    expect(materialIssue(model, material, [material])).toMatch(/不支持|尚未确认/);
  });
  it("rejects duplicates, empty names and per-type limits", () => {
    const m = { type: "image" as const, name: "image", url: "https://example.com/image.png" };
    expect(materialIssue(baseModel, { ...m, name: " " }, [])).toContain("名称");
    expect(materialIssue(baseModel, m, [m, { ...m, url: "https://example.com/other.png" }])).toContain("名称重复");
    expect(materialIssue(baseModel, m, [m, { ...m, name: "other" }])).toContain("素材为空或重复");
    const many = Array.from({ length: 10 }, (_, i) => ({ ...m, name: String(i), url: "https://example.com/" + i }));
    expect(materialIssue(baseModel, many[0], many)).toContain("上限");
  });
  it.each(["http://example.com/x", "https://a:b@example.com/x", "https://example.com:8080/x", "https://example.com/x#fragment", "bad"])("rejects unsafe link syntax %s", url => {
    const m = { type: "image" as const, name: "image", url };
    expect(materialIssue(baseModel, m, [m])).not.toBe("");
  });
  it("checks total count and available server-probed minimax durations", () => {
    const many = Array.from({ length: 11 }, (_, i) => ({ type: (i < 9 ? "image" : "audio") as "image" | "audio", name: String(i), url: "https://example.com/" + i }));
    expect(videoValidation(models[1], 15, "2k", "16:9", many)).toContain("所有素材合计最多 10 个");
    const clips = [8, 8].map((d, i) => ({ type: "video" as const, name: String(i), url: "https://example.com/" + i, duration_seconds: d }));
    expect(videoValidation(models[1], 15, "2k", "16:9", clips)).toContain("参考视频真实时长合计不能超过 15 秒");
  });
  it("preserves HTTP status and code for safe retry decisions", async () => {
    const api = vi.fn(async () => response({ error: { code: "video_parameters_invalid", message: "invalid" } }, 422));
    await expect(videoJson(api, "", "/test")).rejects.toMatchObject({ status: 422, code: "video_parameters_invalid" });
    await expect(videoJson(vi.fn(async () => new Response("gateway", { status: 503 })), "", "/test")).rejects.toBeInstanceOf(VideoApiError);
    await expect(videoJson(vi.fn(async () => new Response("bad success", { status: 202 })), "", "/test")).rejects.toThrow("UUID");
  });
});

describe("independent video workspace", () => {
  it("keeps the two-pane empty state actionable without changing the draft or submitting", async () => {
    const { wrapper, api } = await workspace();
    expect(wrapper.find(".video-stage .video-empty").exists()).toBe(true);
    expect(wrapper.find(".video-composer .video-composer-body").exists()).toBe(true);
    expect(wrapper.find(".video-composer .video-submit-row").exists()).toBe(true);
    const prompt = wrapper.get<HTMLTextAreaElement>('[data-field="video-prompt"]');
    await prompt.setValue("keep this draft");
    const focus = vi.spyOn(prompt.element, "focus");
    await wrapper.get(".video-start-writing").trigger("click");
    expect(focus).toHaveBeenCalledOnce();
    expect(prompt.element.value).toBe("keep this draft");
    expect(api.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  });
  it("keeps blocking readiness warnings visible while only folding optional material guidance", async () => {
    const { wrapper, api } = await workspace({ ...ready, storage_ready: false, media_tools_ready: false, api_ready: false, assets_ready: false });
    const warnings = wrapper.findAll(".video-readiness.warning");
    expect(warnings).toHaveLength(3);
    expect(warnings.map(w => w.text()).join(" ")).toContain("R2 私有存储未配置");
    expect(warnings.map(w => w.text()).join(" ")).toContain("可信的 HTTPS 根地址");
    expect(warnings.map(w => w.text()).join(" ")).toContain("缺少 ffprobe");
    expect(warnings.every(w => w.element.tagName !== "DETAILS")).toBe(true);
    expect(wrapper.get("details.video-readiness.info").text()).toContain("已有图片引用已禁用");
    const guidance = wrapper.get("details.video-upload-guidelines");
    expect(guidance.get("summary").text()).toBe("素材限制与使用说明");
    expect(guidance.text()).toContain("图片 10 MB、MP4 100 MB、MP3/WAV 20 MB");
    expect(guidance.text()).toContain("不代表上游支持保证");
    expect(wrapper.get('[data-action="generate-video"]').attributes("disabled")).toBeDefined();
    expect(api.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  });
  it("starts with J2 defaults and submits one video task, never an image request", async () => {
    const { wrapper, api } = await workspace();
    expect(wrapper.get<HTMLSelectElement>('[data-field="video-model"]').element.value).toBe("sd-2.0-J2");
    expect(wrapper.get<HTMLSelectElement>('[data-field="video-duration"]').element.value).toBe("5");
    await wrapper.get('[data-field="video-prompt"]').setValue("pan slowly");
    await wrapper.get(".video-composer").trigger("submit"); await flushPromises();
    const creates = api.mock.calls.filter(([url, init]) => String(url).endsWith("/api/videos/tasks") && init?.method === "POST");
    expect(creates).toHaveLength(1);
    expect(JSON.parse(String(creates[0][1]?.body))).toMatchObject({ project_id: 1, model: "sd-2.0-J2", duration: 5, resolution: "720p", materials: [] });
    expect(JSON.parse(String(creates[0][1]?.body)).request_id).toMatch(/^[0-9a-f-]{36}$/);
    expect(api.mock.calls.some(([url]) => String(url).includes("generation-tasks") || String(url).endsWith("/api/generate"))).toBe(false);
    expect(wrapper.text()).toContain("任务已持久化");
  });
  it("applies the selected video's Key default model only when explicitly selected", async () => {
    const { wrapper, api } = await workspace(); const fallback = api.getMockImplementation()!;
    api.mockImplementation(async (url, init) => String(url).endsWith("/api/settings/video-api-keys")
      ? response({ configs: [{ id: 11, alias: "key one", model: baseModel.id }, { id: 12, alias: "key two", model: "minimax-h3" }], active_config_id: 12 }) : fallback(url, init));
    await (wrapper.vm as unknown as { refresh: () => Promise<void> }).refresh();
    expect(wrapper.get<HTMLSelectElement>('[data-field="video-model"]').element.value).toBe(baseModel.id);
    await wrapper.get('[data-field="video-key"]').setValue("12");
    expect(wrapper.get<HTMLSelectElement>('[data-field="video-model"]').element.value).toBe("minimax-h3");
    expect(wrapper.get<HTMLSelectElement>('[data-field="video-resolution"]').element.value).toBe("2k");
  });
  it("applies minimax 2k and discrete J3 defaults on model switch", async () => {
    const { wrapper } = await workspace();
    await wrapper.get('[data-field="video-model"]').setValue("minimax-h3");
    expect(wrapper.get<HTMLSelectElement>('[data-field="video-resolution"]').element.value).toBe("2k");
    expect(wrapper.get<HTMLSelectElement>('[data-field="video-duration"]').element.value).toBe("15");
    await wrapper.get('[data-field="video-model"]').setValue("sd-2.0-900-J3");
    expect(wrapper.findAll('[data-field="video-duration"] option').map(o => o.attributes("value"))).toEqual(["10", "15"]);
  });
  it("retains and flags incompatible materials and supports named @ mentions", async () => {
    const { wrapper } = await workspace();
    await addLink(wrapper, "video", "https://example.com/clip.mp4", "舞步");
    await button(wrapper, "插入 @引用").trigger("click");
    expect(wrapper.get<HTMLTextAreaElement>('[data-field="video-prompt"]').element.value).toBe("@舞步 ");
    await wrapper.get('[data-field="video-model"]').setValue("seedance-2.5-101010");
    expect(wrapper.findAll(".video-materials article")).toHaveLength(1);
    expect(wrapper.find(".video-materials article.incompatible").exists()).toBe(true);
    expect(wrapper.text()).not.toContain("已保留素材；");
    expect(wrapper.get('[data-action="generate-video"]').attributes("disabled")).toBeDefined();
    await wrapper.get('[data-field="video-model"]').setValue("sd-2.0-900-J3");
    expect(wrapper.text()).toContain("该素材类型的能力尚未确认");
  });
  it("gates local/history materials without HTTPS but allows text and external links", async () => {
    const { wrapper } = await workspace({ ...ready, assets_ready: false });
    expect(wrapper.get('input[type="file"]').attributes("disabled")).toBeDefined();
    expect(button(wrapper, "已有生成图片").attributes("disabled")).toBeDefined();
    await wrapper.get('[data-field="video-prompt"]').setValue("text only");
    expect(wrapper.get('[data-action="generate-video"]').attributes("disabled")).toBeUndefined();
    await addLink(wrapper, "image", "https://example.com/image.png");
    expect(wrapper.findAll(".video-materials article")).toHaveLength(1);
    expect(wrapper.get('[data-action="generate-video"]').attributes("disabled")).toBeUndefined();
  });
  it.each(["storage_ready", "media_tools_ready", "api_ready"] as const)("does not submit without %s", async key => {
    const { wrapper, api } = await workspace({ ...ready, [key]: false });
    await wrapper.get('[data-field="video-prompt"]').setValue("blocked"); await wrapper.get(".video-composer").trigger("submit");
    expect(api.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  });
  it("keeps project/account drafts independent across mode visibility and remounts", async () => {
    const { wrapper, api } = await workspace();
    await wrapper.get('[data-field="video-prompt"]').setValue("project one draft");
    await wrapper.setProps({ active: false }); await wrapper.setProps({ active: true }); await flushPromises();
    expect(wrapper.get<HTMLTextAreaElement>('[data-field="video-prompt"]').element.value).toBe("project one draft");
    await wrapper.setProps({ projectId: 2 }); await flushPromises();
    await wrapper.get('[data-field="video-prompt"]').setValue("project two draft");
    await wrapper.setProps({ projectId: 1 }); await flushPromises();
    expect(wrapper.get<HTMLTextAreaElement>('[data-field="video-prompt"]').element.value).toBe("project one draft");
    const other = keep(mount(VideoWorkspace, { props: { ...wrapper.props(), account: "bob", apiFetch: api } })); await flushPromises();
    expect(other.get<HTMLTextAreaElement>('[data-field="video-prompt"]').element.value).toBe("");
  });
  it("clears only definitive rejection UUIDs, allowing corrected parameters", async () => {
    const { wrapper, api } = await workspace(); const fallback = api.getMockImplementation()!; let reject = true;
    api.mockImplementation(async (url, init) => String(url).endsWith("/api/videos/tasks") && init?.method === "POST" && reject
      ? response({ error: { code: "video_parameters_invalid", message: "invalid parameters" } }, 422) : fallback(url, init));
    await wrapper.get('[data-field="video-prompt"]').setValue("first"); await wrapper.get(".video-composer").trigger("submit"); await flushPromises();
    expect(wrapper.text()).toContain("此次请求未受理"); expect(wrapper.find('[data-action="restore-video-pending"]').exists()).toBe(false);
    reject = false; await wrapper.get('[data-field="video-prompt"]').setValue("fixed"); await wrapper.get(".video-composer").trigger("submit"); await flushPromises();
    const creates = api.mock.calls.filter(([url, init]) => String(url).endsWith("/api/videos/tasks") && init?.method === "POST");
    expect(creates).toHaveLength(2);
    expect(JSON.parse(String(creates[0][1]?.body)).request_id).not.toBe(JSON.parse(String(creates[1][1]?.body)).request_id);
  });
  it("persists ambiguous submission UUIDs and restores exact original parameters", async () => {
    const { wrapper, api } = await workspace(); const fallback = api.getMockImplementation()!;
    api.mockImplementation(async (url, init) => String(url).endsWith("/api/videos/tasks") && init?.method === "POST" ? response({}, 503) : fallback(url, init));
    await wrapper.get('[data-field="video-prompt"]').setValue("original"); await wrapper.get(".video-composer").trigger("submit"); await flushPromises();
    await wrapper.get('[data-field="video-prompt"]').setValue("different"); await wrapper.get(".video-composer").trigger("submit"); await flushPromises();
    expect(wrapper.text()).toContain("上次本地请求尚待确认");
    await wrapper.get('[data-action="restore-video-pending"]').trigger("click"); await wrapper.get(".video-composer").trigger("submit"); await flushPromises();
    const creates = api.mock.calls.filter(([url, init]) => String(url).endsWith("/api/videos/tasks") && init?.method === "POST");
    expect(creates).toHaveLength(2); expect(creates[0][1]?.body).toBe(creates[1][1]?.body);
    expect(JSON.parse(localStorage.getItem("pictora.video.draft:alice:1")!).pending).not.toBeNull();
  });
  it("removes pending state when polling discovers the accepted UUID", async () => {
    const { wrapper, api, tasks } = await workspace(); const fallback = api.getMockImplementation()!;
    api.mockImplementation(async (url, init) => {
      if (String(url).endsWith("/api/videos/tasks") && init?.method === "POST") { tasks.push(task(1, JSON.parse(String(init.body)))); throw new Error("connection lost"); }
      return fallback(url, init);
    });
    await wrapper.get('[data-field="video-prompt"]').setValue("recover"); await wrapper.get(".video-composer").trigger("submit"); await flushPromises();
    expect(wrapper.find('[data-action="restore-video-pending"]').exists()).toBe(false);
    expect(api.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
  });
  it("ignores a late create response after navigation to another project", async () => {
    const { wrapper, api } = await workspace(); const fallback = api.getMockImplementation()!; let resolve!: (r: Response) => void;
    api.mockImplementation(async (url, init) => String(url).endsWith("/api/videos/tasks") && init?.method === "POST" ? new Promise(r => { resolve = r; }) : fallback(url, init));
    await wrapper.get('[data-field="video-prompt"]').setValue("old"); await wrapper.get(".video-composer").trigger("submit");
    await wrapper.setProps({ projectId: 2 }); await flushPromises();
    await wrapper.get('[data-field="video-prompt"]').setValue("new draft"); resolve(response({ task: task(9) }, 202)); await flushPromises();
    expect(wrapper.get<HTMLTextAreaElement>('[data-field="video-prompt"]').element.value).toBe("new draft");
    expect(wrapper.emitted("select")).toBeUndefined(); expect(wrapper.find('[data-video-task="9"]').exists()).toBe(false);
    expect(JSON.parse(localStorage.getItem("pictora.video.draft:alice:1")!).pending).not.toBeNull();
  });
  it("imports a history image as a new asset snapshot and never reuses its image blob ID", async () => {
    const { wrapper, api } = await workspace();
    await (wrapper.vm as unknown as { addHistoryImage: (h: number, i: number) => Promise<boolean> }).addHistoryImage(12, 34); await flushPromises();
    await wrapper.get('[data-field="video-prompt"]').setValue("animate image"); await wrapper.get(".video-composer").trigger("submit"); await flushPromises();
    const create = api.mock.calls.find(([url, init]) => String(url).endsWith("/api/videos/tasks") && init?.method === "POST")!;
    expect(JSON.parse(String(create[1]?.body)).materials).toEqual([{ type: "image", name: "图片1", asset_id: "snapshot" }]);
  });
});

describe("video task and Key controls", () => {
  it("distinguishes save retry, pause and unknown submission; never offers upstream cancel", async () => {
    const wrapper = keep(mount(VideoTaskCard, { props: { task: task(1, { status: "storage_failed", upstream_status: "completed", upstream_task_id: "up-1" }), apiBase: "" } }));
    expect(wrapper.text()).toContain("已生成，保存失败"); await button(wrapper, "重试保存（不重新生成）").trigger("click");
    expect(wrapper.emitted("action")?.[0][1]).toBe("retry-save");
    await wrapper.setProps({ task: task(1, { status: "polling_paused", upstream_task_id: "up-1" }) });
    expect(button(wrapper, "恢复查询").exists()).toBe(true);
    await wrapper.setProps({ task: task(1, { status: "submission_unknown" }) });
    expect(wrapper.findAll("button").some(b => b.text().includes("取消上游"))).toBe(false);
    expect(wrapper.findAll("button").some(b => b.text() === "删除视频记录")).toBe(false);
    await wrapper.get("input").setValue("up-manual"); await wrapper.get("form").trigger("submit");
    expect(wrapper.emitted("action")?.at(-1)?.slice(1)).toEqual(["bind", "up-manual"]);
  });
  it("uses owned playback/download routes and refreshes expiring playback without regeneration", async () => {
    const wrapper = keep(mount(VideoTaskCard, { props: { task: task(1, { status: "completed", results: [{ id: 2, stored: 1, filename: "clip.mp4", byte_size: 12345, duration_seconds: 5, play_url: "/api/videos/tasks/1/results/2/play", download_url: "/api/videos/tasks/1/results/2/download" }] }), apiBase: "" } }));
    expect(wrapper.get("video").attributes("src")).toContain("/play?v=0"); expect(wrapper.get("a").attributes("href")).toContain("/download");
    await button(wrapper, "刷新播放链接").trigger("click"); expect(wrapper.get("video").attributes("src")).toContain("v=1"); expect(wrapper.emitted("action")).toBeUndefined();
  });
  it("routes Key CRUD/select and free connection test separately from image settings", async () => {
    const { api } = server(); const fallback = api.getMockImplementation()!;
    api.mockImplementation(async (url, init) => {
      if (String(url).endsWith("/test")) return response({ message: "连接正常（未生成视频）", models: [baseModel.id] });
      if (init?.method && init.method !== "GET") return response({}); return fallback(url, init);
    });
    const wrapper = keep(mount(VideoSettings, { props: { apiFetch: api, apiBase: "" } })); await flushPromises();
    await button(wrapper, "非付费连接测试").trigger("click"); await flushPromises();
    expect(wrapper.text()).toContain("未生成视频");
    await wrapper.get('[data-action="add-video-key"]').trigger("click");
    await wrapper.get("form input[maxlength='80']").setValue("new Key"); await wrapper.get('form input[type="password"]').setValue("secret-new");
    await wrapper.get(".api-config-form").trigger("submit"); await flushPromises();
    expect(api.mock.calls.find(([url, init]) => String(url).endsWith("video-api-keys") && init?.method === "POST")?.[1]?.body).toContain('"api_key":"secret-new"');
    await button(wrapper, "编辑").trigger("click"); await wrapper.get(".api-config-form").trigger("submit"); await flushPromises();
    const patch = api.mock.calls.find(([url, init]) => String(url).endsWith("video-api-keys/11") && init?.method === "PATCH");
    expect(JSON.parse(String(patch?.[1]?.body))).not.toHaveProperty("api_key");
    expect(api.mock.calls.some(([url]) => String(url).includes("/api/settings/api-keys"))).toBe(false);
    await button(wrapper, "删除").trigger("click"); expect(wrapper.text()).toContain("确认删除此视频 Key");
  });
  it("shows video-only project history and selects it without image history", async () => {
    const wrapper = keep(mount(VideoProjectSidebar, { props: { selectedProjectId: 1, selectedTaskId: null, projects: [{ id: 1, name: "project", history_count: 1, history: [{ id: 99, prompt: "image record", kind: "generate", created_at: "2026-10-06", status: "completed", provider: "gpt", model: "gpt-image-1", detail: "auto", image_count: 1 }], video_history_count: 1, video_history: [task(8)] }] } }));
    expect(wrapper.text()).toContain("video prompt"); expect(wrapper.text()).not.toContain("image record");
    await wrapper.get(".history-select").trigger("click"); expect(wrapper.emitted("open-video")).toEqual([[1, 8]]);
  });
});

describe("image/video workbench integration", () => {
  it("preserves both drafts and independent project selection when modes change", async () => {
    const { api } = server(); const fallback = api.getMockImplementation()!;
    const projects = [1, 2, 3, 4].map(id => ({ id, media_type: id < 3 ? "image" : "video", name: (id < 3 ? "Image " : "Video ") + id, history_count: 0, history: [], video_history_count: 0, video_history: [] }));
    api.mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes("/api/videos/") || url.includes("video-api-keys")) return fallback(input, init);
      if (url.endsWith("/api/auth/me")) return response({ username: "alice", email: "alice@example.com", api_key_configured: false });
      if (url.endsWith("/api/projects") && init?.method === "POST") {
        const data = JSON.parse(String(init.body));
        projects.push({ id: 5, media_type: data.media_type, name: data.name, history_count: 0, history: [], video_history_count: 0, video_history: [] });
        return response({ id: 5, ...data }, 201);
      }
      if (url.endsWith("/api/projects/5") && init?.method === "DELETE") {
        projects.splice(projects.findIndex(p => p.id === 5), 1);
        return response({ selected_project_id: 3, projects, deleted_history_count: 0, deleted_video_count: 0 });
      }
      if (url.endsWith("/api/projects")) return response(projects);
      if (url.endsWith("/api/settings")) return response({ model: "gpt-image-1.5", provider_type: "gpt", base_url: "https://sub.beibeihai.xyz/v1", api_key_configured: false });
      if (url.endsWith("/api/providers")) return response({ providers: [{ id: "compatible", label: "北海AI", models: ["gpt-image-1.5"] }] });
      return response([]);
    });
    vi.stubGlobal("fetch", api); const wrapper = keep(mount(App)); await flushPromises();
    await wrapper.get(".prompt-row textarea").setValue("image draft"); await wrapper.get('[data-mode="video"]').trigger("click"); await flushPromises();
    await wrapper.get('[data-field="video-prompt"]').setValue("video draft");
    await wrapper.get('[data-mode="image"]').trigger("click"); await flushPromises();
    expect(wrapper.get<HTMLTextAreaElement>(".prompt-row textarea").element.value).toBe("image draft");
    await wrapper.get(".studio-grid:not(.video-studio-grid) .project-group:nth-child(2) .project-select").trigger("click"); await flushPromises();
    await wrapper.get(".prompt-row textarea").setValue("image 2 draft");
    await wrapper.get('[data-mode="video"]').trigger("click"); await flushPromises();
    expect(wrapper.get<HTMLTextAreaElement>('[data-field="video-prompt"]').element.value).toBe("video draft");
    expect(wrapper.get(".video-studio-grid .project-group.active .project-select").text()).toContain("Video 3");
    expect(wrapper.get(".video-studio-grid .project-sidebar").text()).not.toContain("Image 1");
    expect(wrapper.get(".studio-grid:not(.video-studio-grid) .project-sidebar").text()).not.toContain("Video 3");
    expect(api.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
    await wrapper.get('.video-studio-grid [aria-label="新建项目"]').trigger("click");
    await wrapper.get('.confirm-dialog input').setValue("新视频项目");
    await wrapper.get('.confirm-dialog').trigger("submit"); await flushPromises();
    const created = api.mock.calls.find(([url, init]) => String(url).endsWith("/api/projects") && init?.method === "POST");
    expect(JSON.parse(String(created?.[1]?.body))).toEqual({ name: "新视频项目", media_type: "video" });
    expect(wrapper.get('.video-studio-grid .project-group.active').text()).toContain("新视频项目");
    await wrapper.get(".video-studio-grid .project-group.active .danger-text").trigger("click");
    await wrapper.get('.confirm-dialog .danger-action').trigger("click"); await flushPromises();
    await wrapper.get('[data-mode="image"]').trigger("click"); await flushPromises();
    expect(wrapper.get('.studio-grid:not(.video-studio-grid) .project-group.active').text()).toContain("Image 2");
    expect(wrapper.get<HTMLTextAreaElement>(".prompt-row textarea").element.value).toBe("image 2 draft");
    await wrapper.get('.prompt-row textarea').setValue("retained image draft");
    await wrapper.get('[data-mode="video"]').trigger("click"); await flushPromises();
    await wrapper.get('[data-mode="image"]').trigger("click"); await flushPromises();
    expect(wrapper.get<HTMLTextAreaElement>('.prompt-row textarea').element.value).toBe("retained image draft");
  });
});


describe("video task elapsed timer", () => {
  it("normalizes UTC database timestamps and formats hours", () => {
    expect(videoTimestamp("2026-10-06 00:00:00")).toBe(Date.parse("2026-10-06T00:00:00Z"));
    expect(videoTimestamp("not a timestamp")).toBeNull();
    expect(formatVideoElapsed(65000)).toBe("01:05");
    expect(formatVideoElapsed(3661000)).toBe("01:01:01");
  });
  it("ticks from persisted creation time, hides diagnostics and stops on completion", async () => {
    vi.setSystemTime(new Date("2026-10-06T00:00:10Z"));
    const wrapper = keep(mount(VideoTaskCard, { props: { apiBase: "", task: task(1, { upstream_task_id: "private-upstream-id", upstream_status: "running" }) } }));
    expect(wrapper.get('[role="timer"]').text()).toContain("00:10");
    expect(wrapper.text()).not.toContain("private-upstream-id");
    expect(wrapper.text()).not.toContain("上游：");
    expect(wrapper.text()).not.toContain("本地：");
    await vi.advanceTimersByTimeAsync(2000);
    expect(wrapper.get('[role="timer"]').text()).toContain("00:12");
    await wrapper.setProps({ task: task(1, { status: "completed", completed_at: "2026-10-06T00:00:11Z" }) });
    expect(wrapper.get('[role="timer"]').text()).toContain("总耗时00:11");
    expect(wrapper.find(".is-timing").exists()).toBe(false);
    await vi.advanceTimersByTimeAsync(5000);
    expect(wrapper.get('[role="timer"]').text()).toContain("00:11");
    wrapper.unmount();
    const restored = keep(mount(VideoTaskCard, { props: { apiBase: "", task: task() } }));
    expect(restored.get('[role="timer"]').text()).toContain("00:17");
    expect(vi.getTimerCount()).toBe(1);
    restored.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
  it("freezes failed/abandoned tasks and avoids fabricated durations for legacy data", () => {
    const now = Date.parse("2026-10-06T00:01:00Z");
    expect(videoElapsedMs(task(1, { status: "failed", updated_at: "2026-10-06 00:00:20" }), now)).toBe(20000);
    expect(videoElapsedMs(task(1, { status: "abandoned", tracking_abandoned: 1, updated_at: "2026-10-06T00:00:15Z" }), now)).toBe(15000);
    expect(videoElapsedMs(task(1, { status: "completed" }), now)).toBeNull();
  });
});
