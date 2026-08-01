<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import {
  Check,
  Download,
  ExternalLink,
  ImagePlus,
  LoaderCircle,
  Sparkles,
  Upload,
  X,
} from "lucide-vue-next";
import ProjectSidebar, { type ProjectSummary } from "./components/ProjectSidebar.vue";
import ConfirmDialog from "./components/ConfirmDialog.vue";
import ProjectDialog from "./components/ProjectDialog.vue";

type Provider = { id: string; label: string; models: string[] };
type ImageResult = {
  url?: string | null;
  base64_data?: string | null;
  revised_prompt?: string | null;
  generation_time_ms?: number | null;
};
type HistorySummary = {
  id: number;
  kind: "generate" | "analyze";
  status: "pending" | "completed" | "failed";
  prompt: string;
  provider: string;
  model: string;
  detail: string;
  size?: string | null;
  image_count: number;
  elapsed_ms?: number | null;
  error_code?: string | null;
  error_message?: string | null;
  created_at: string;
};
type HistoryImage = {
  id: number;
  role: "reference" | "generated";
  mime_type: string;
  filename?: string | null;
  position: number;
  url: string;
};
type HistoryDetail = HistorySummary & {
  analysis_text?: string | null;
  completed_at?: string | null;
  images: HistoryImage[];
};

const MODEL_OPTIONS = [
  "gpt-image-2",
  "gpt-image-1.5",
  "gpt-image-1",
  "gpt-image-1Mini",
] as const;
const DEFAULT_MODEL = MODEL_OPTIONS[0];
const SIZE_OPTIONS = [
  { label: "1:1", value: "1024x1024", description: "正方形，头像" },
  { label: "3:2", value: "1536x1024", description: "横向图片，风景" },
  { label: "2:3", value: "1024x1536", description: "竖向图片，人像" },
] as const;
const DEFAULT_SIZE = "1024x1024";
const DETAIL_OPTIONS = [
  { label: "自动", value: "auto" },
  { label: "低", value: "low" },
  { label: "高", value: "high" },
  { label: "原始", value: "original" },
] as const;
const IMAGE_COUNT_OPTIONS = [1, 2, 3, 4] as const;
type ParameterMenu = "model" | "size" | "detail" | "count";
type GenerationRun = {
  controller: AbortController;
  startedAt: number;
  elapsedMs: number;
  timer?: number;
};

const providers = ref<Provider[]>([]);
const provider = ref("compatible");
const model = ref<string>(DEFAULT_MODEL);
const prompt = ref("");
const batchPrompts = ref("");
const imageCount = ref(1);
const detail = ref("auto");
const size = ref<string>(DEFAULT_SIZE);
const imageFile = ref<File | null>(null);
const previewUrl = ref("");
const generated = ref<ImageResult[]>([]);
const analysis = ref("");
const busy = ref<"generate" | "analyze" | "">("");
const error = ref("");
const apiKeyConfigured = ref(false);
const history = ref<HistorySummary[]>([]);
const historyError = ref("");
const projects = ref<ProjectSummary[]>([]);
const selectedProjectId = ref<number | null>(null);
const projectError = ref("");
const projectDialogMode = ref<"create" | "rename" | null>(null);
const projectDialogProject = ref<ProjectSummary | null>(null);
const confirmAction = ref<"project" | "history" | null>(null);
const confirmProject = ref<ProjectSummary | null>(null);
const confirmHistoryIds = ref<number[]>([]);
const actionBusy = ref(false);
const activeHistoryId = ref<number | null>(null);
const lightboxUrl = ref("");
const openParameterMenu = ref<ParameterMenu | null>(null);
const authView = ref<"checking" | "login" | "register" | "workspace">("checking");
const username = ref("");
const password = ref("");
const passwordConfirmation = ref("");
const currentUsername = ref("");
const authError = ref("");
const currentView = ref<"workspace" | "settings">(window.location.pathname === "/settings" ? "settings" : "workspace");
const settingsApiKey = ref("");
const oldPassword = ref("");
const newPassword = ref("");
const newPasswordConfirmation = ref("");
let settingsSaveQueue: Promise<void> = Promise.resolve();

const generationRuns = new Map<number, GenerationRun>();
const generationVersion = ref(0);
const activeGenerationRunId = ref<number | null>(null);
const activeGenerationRun = computed(() => {
  generationVersion.value;
  return activeGenerationRunId.value === null
    ? null
    : generationRuns.get(activeGenerationRunId.value) ?? null;
});
const activeGenerationElapsedMs = computed(() => {
  generationVersion.value;
  if (activeGenerationRunId.value === null) return null;
  return generationRuns.get(activeGenerationRunId.value)?.elapsedMs ?? 0;
});
const canAnalyze = computed(() => Boolean(imageFile.value) && busy.value !== "analyze");
const API_BASE = import.meta.env.VITE_API_BASE ?? "";

function readableError(data: any, fallback: string) {
  const messages: Record<string, string> = {
    provider_auth: "服务商鉴权失败，请检查 API Key",
    provider_timeout: "服务商请求超时，请稍后重试",
    provider_request: "服务商请求失败",
    provider_not_found: "找不到所选服务商",
    invalid_image: "图片格式或内容无效",
    history_not_found: "历史记录不存在",
  };
  return messages[data?.error?.code] ?? data?.error?.message ?? fallback;
}

async function parseJsonResponse(response: Response): Promise<any | null> {
  const text = await response.text();
  if (!text.trim()) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function resourceUrl(path: string) {
  return /^https?:\/\//.test(path) ? path : `${API_BASE}${path}`;
}

async function submitAuth(mode: "login" | "register") {
  authError.value = "";
  const passwordsMatch = mode === "login" || password.value === passwordConfirmation.value;
  if (!username.value.trim() || password.value.length < 6 || !passwordsMatch) {
    authError.value = "请填写用户名，密码至少 6 位且两次输入一致";
    return;
  }
  const body = mode === "register"
    ? { username: username.value, password: password.value, password_confirmation: passwordConfirmation.value }
    : { username: username.value, password: password.value };
  const response = await fetch(`${API_BASE}/api/auth/${mode}`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await parseJsonResponse(response);
  if (!response.ok) { authError.value = readableError(data, "登录失败"); return; }
  currentUsername.value = data.username;
  password.value = "";
  passwordConfirmation.value = "";
  authView.value = "workspace";
  await Promise.all([loadRuntimeSettings(), loadProviders(), loadProjects()]);
}

async function logout() {
  await fetch(`${API_BASE}/api/auth/logout`, { method: "POST", credentials: "include" });
  authView.value = "login";
  history.value = [];
  currentUsername.value = "";
}

function navigateToSettings() {
  window.history.pushState({}, "", "/settings");
  currentView.value = "settings";
  settingsApiKey.value = "";
}

function navigateToWorkspace() {
  window.history.pushState({}, "", "/");
  currentView.value = "workspace";
}

function toggleParameterMenu(menu: ParameterMenu) {
  openParameterMenu.value = openParameterMenu.value === menu ? null : menu;
}

function closeParameterMenu() {
  openParameterMenu.value = null;
}

async function selectModel(value: string) {
  model.value = value;
  closeParameterMenu();
  await applyRuntimeSettings();
}

function selectSize(value: string) {
  size.value = value;
  closeParameterMenu();
}

function selectDetail(value: string) {
  detail.value = value;
  closeParameterMenu();
}

function selectImageCount(value: number) {
  imageCount.value = value;
  closeParameterMenu();
}

async function saveSettingsApiKey() {
  const apiKey = settingsApiKey.value.trim() || null;
  const response = await fetch(`${API_BASE}/api/settings`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model: model.value, api_key: apiKey }),
  });
  const data = await parseJsonResponse(response);
  if (!response.ok) { authError.value = readableError(data, "保存接口配置失败"); return; }
  apiKeyConfigured.value = Boolean(data?.api_key_configured);
  settingsApiKey.value = "";
}

async function changePassword() {
  if (newPassword.value.length < 6 || newPassword.value !== newPasswordConfirmation.value) { authError.value = "新密码至少 6 位且两次输入一致"; return; }
  const response = await fetch(`${API_BASE}/api/auth/password`, { method: "PUT", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ old_password: oldPassword.value, new_password: newPassword.value, new_password_confirmation: newPasswordConfirmation.value }) });
  if (!response.ok) { authError.value = readableError(await parseJsonResponse(response), "修改密码失败"); return; }
  oldPassword.value = newPassword.value = newPasswordConfirmation.value = "";
  authView.value = "login";
}

async function loadRuntimeSettings() {
  const response = await fetch(`${API_BASE}/api/settings`);
  const data = await response.json();
  if (!response.ok) throw new Error(readableError(data, "无法加载运行时配置"));
  model.value = (MODEL_OPTIONS as readonly string[]).includes(data.model)
    ? data.model
    : DEFAULT_MODEL;
  apiKeyConfigured.value = Boolean(data.api_key_configured);
}

async function loadProviders() {
  const response = await fetch(`${API_BASE}/api/providers`);
  const data = await response.json();
  if (!response.ok) throw new Error(readableError(data, "无法加载服务商"));
  providers.value = data.providers ?? [];
  provider.value = providers.value[0]?.id ?? "compatible";
}

async function loadHistory() {
  try {
    const response = await fetch(`${API_BASE}/api/history`);
    const data = await response.json();
    if (!response.ok) throw new Error(readableError(data, "无法加载历史记录"));
    history.value = data;
    historyError.value = "";
  } catch (exception) {
    historyError.value =
      exception instanceof Error ? exception.message : "无法加载历史记录";
  }
}

async function openHistory(historyId: number) {
  error.value = "";
  try {
    const response = await fetch(`${API_BASE}/api/history/${historyId}`);
    const data: HistoryDetail = await response.json();
    if (!response.ok) throw new Error(readableError(data, "无法加载历史详情"));

    activeHistoryId.value = historyId;
    prompt.value = data.prompt;
    provider.value = data.provider;
    model.value = (MODEL_OPTIONS as readonly string[]).includes(data.model)
      ? data.model
      : DEFAULT_MODEL;
    detail.value = data.detail;
    if (SIZE_OPTIONS.some((option) => option.value === data.size)) {
      size.value = data.size ?? DEFAULT_SIZE;
    }
    imageCount.value = data.image_count;
    analysis.value = data.analysis_text ?? "";
    generated.value = data.images
      .filter((image) => image.role === "generated")
      .map((image) => ({
        url: resourceUrl(image.url),
        generation_time_ms: data.elapsed_ms,
      }));

    const reference = data.images.find((image) => image.role === "reference");
    if (previewUrl.value.startsWith("blob:")) URL.revokeObjectURL(previewUrl.value);
    imageFile.value = null;
    previewUrl.value = reference ? resourceUrl(reference.url) : "";
  } catch (exception) {
    error.value =
      exception instanceof Error ? exception.message : "无法加载历史详情";
  }
}

async function loadProjects() {
  try {
    const response = await fetch(`${API_BASE}/api/projects`);
    const data = await response.json();
    if (!response.ok) throw new Error("无法加载项目");
    projects.value = Array.isArray(data) ? data : [];
    if (!projects.value.some((project) => project.id === selectedProjectId.value)) selectedProjectId.value = projects.value[0]?.id ?? null;
    history.value = projects.value.find((project) => project.id === selectedProjectId.value)?.history ?? [];
    projectError.value = "";
  } catch (exception) {
    projectError.value = exception instanceof Error ? exception.message : "无法加载项目";
  }
}

async function refreshConversationLists() {
  await Promise.all([loadProjects(), loadHistory()]);
}

function clearWorkspace() {
  generated.value = [];
  analysis.value = "";
  activeHistoryId.value = null;
  prompt.value = "";
  batchPrompts.value = "";
  if (previewUrl.value.startsWith("blob:")) URL.revokeObjectURL(previewUrl.value);
  imageFile.value = null;
  previewUrl.value = "";
}

function selectProject(projectId: number) {
  selectedProjectId.value = projectId;
  history.value = projects.value.find((project) => project.id === projectId)?.history ?? [];
  activeGenerationRunId.value = null;
  clearWorkspace();
}

async function submitCreateProject(name: string) {
  if (!name) return;
  const response = await fetch(`${API_BASE}/api/projects`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) });
  if (!response.ok) { projectError.value = "创建项目失败"; return; }
  const data = await response.json();
  await loadProjects();
  selectProject(data.id);
}

async function submitRenameProject(project: ProjectSummary, name: string) {
  if (!name || name === project.name) return;
  const response = await fetch(`${API_BASE}/api/projects/${project.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) });
  if (!response.ok) { projectError.value = "重命名项目失败"; return; }
  await loadProjects();
}

async function submitDeleteProject(project: ProjectSummary) {
  const response = await fetch(`${API_BASE}/api/projects/${project.id}`, { method: "DELETE" });
  if (!response.ok) { projectError.value = "删除项目失败"; return; }
  const data = await response.json();
  selectedProjectId.value = data.selected_project_id;
  await loadProjects();
  clearWorkspace();
}

async function submitDeleteHistory(project: ProjectSummary, ids: number[]) {
  const response = await fetch(`${API_BASE}/api/projects/${project.id}/history`, { method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ history_ids: ids }) });
  if (!response.ok) { projectError.value = "删除历史记录失败"; return; }
  if (ids.includes(activeHistoryId.value ?? -1)) clearWorkspace();
  await loadProjects();
}

function createProject() {
  projectDialogProject.value = null;
  projectDialogMode.value = "create";
}

function renameProject(project: ProjectSummary) {
  projectDialogProject.value = project;
  projectDialogMode.value = "rename";
}

function cancelProjectDialog() {
  projectDialogMode.value = null;
  projectDialogProject.value = null;
}

async function submitProjectDialog(name: string) {
  const mode = projectDialogMode.value;
  const project = projectDialogProject.value;
  cancelProjectDialog();
  if (mode === "create") await submitCreateProject(name);
  else if (mode === "rename" && project) await submitRenameProject(project, name);
}

function deleteProject(project: ProjectSummary) {
  confirmProject.value = project;
  confirmHistoryIds.value = [];
  confirmAction.value = "project";
}

function deleteHistory(project: ProjectSummary, ids: number[]) {
  confirmProject.value = project;
  confirmHistoryIds.value = ids;
  confirmAction.value = "history";
}

function cancelConfirm() {
  if (actionBusy.value) return;
  confirmAction.value = null;
  confirmProject.value = null;
  confirmHistoryIds.value = [];
}

async function confirmDeletion() {
  if (actionBusy.value || !confirmProject.value) return;
  const project = confirmProject.value;
  const action = confirmAction.value;
  const ids = confirmHistoryIds.value;
  actionBusy.value = true;
  try {
    if (action === "project") await submitDeleteProject(project);
    else if (action === "history") await submitDeleteHistory(project, ids);
  } finally {
    actionBusy.value = false;
    cancelConfirm();
  }
}

function startNewConversation() {
  activeGenerationRunId.value = null;
  clearWorkspace();
}

async function applyRuntimeSettings() {
  const submittedModel = model.value.trim();
  if (!submittedModel) return;

  error.value = "";
  const save = settingsSaveQueue.then(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: submittedModel, api_key: null }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(readableError(data, "配置应用失败"));
      model.value = (MODEL_OPTIONS as readonly string[]).includes(data.model)
        ? data.model
        : DEFAULT_MODEL;
      apiKeyConfigured.value = Boolean(data.api_key_configured);
      await loadProviders();
    } catch (exception) {
      error.value = exception instanceof Error ? exception.message : "配置应用失败";
    }
  });
  settingsSaveQueue = save;
  await save;
}

function setFile(file?: File) {
  if (!file) return;
  if (previewUrl.value.startsWith("blob:")) URL.revokeObjectURL(previewUrl.value);
  imageFile.value = file;
  previewUrl.value = URL.createObjectURL(file);
  activeHistoryId.value = null;
  error.value = "";
}

function clearFile() {
  if (previewUrl.value.startsWith("blob:")) URL.revokeObjectURL(previewUrl.value);
  imageFile.value = null;
  previewUrl.value = "";
}

function formatDuration(milliseconds?: number | null) {
  if (milliseconds == null) return "计时不可用";
  return `${(milliseconds / 1000).toFixed(2)} 秒`;
}

function formatHistoryTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function startGenerationRun(runId: number, controller: AbortController) {
  const run: GenerationRun = { controller, startedAt: performance.now(), elapsedMs: 0 };
  run.timer = window.setInterval(() => {
    run.elapsedMs = performance.now() - run.startedAt;
    generationVersion.value++;
  }, 100);
  generationRuns.set(runId, run);
  activeGenerationRunId.value = runId;
}

function stopGenerationRun(runId: number) {
  const run = generationRuns.get(runId);
  if (!run) return;
  if (run.timer !== undefined) window.clearInterval(run.timer);
  run.elapsedMs = performance.now() - run.startedAt;
  generationRuns.delete(runId);
  generationVersion.value++;
}

async function generateImage() {
  if (!provider.value || !model.value) {
    error.value = "请先配置 API Key 和模型名称";
    return;
  }
  const runId = Date.now() + Math.random();
  const controller = new AbortController();
  startGenerationRun(runId, controller);
  error.value = "";
  analysis.value = "";
  generated.value = [];
  activeHistoryId.value = null;
  const prompts = batchPrompts.value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
  try {
    const requestPrompt = prompt.value.trim() || prompts[0] || "请生成一张图片";
    const response = await fetch(`${API_BASE}/api/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      body: JSON.stringify({
        provider: provider.value,
        model: model.value,
        prompt: requestPrompt,
        prompts: prompts.length ? prompts : null,
        count: imageCount.value,
        detail: detail.value,
        size: size.value,
        project_id: selectedProjectId.value,
      }),
    });
    const data = await parseJsonResponse(response);
    if (!response.ok) {
      throw new Error(readableError(data, `生成失败（HTTP ${response.status}）`));
    }
    if (!data) throw new Error("服务返回了无效响应");
    if (activeGenerationRunId.value === runId) generated.value = data.images ?? [];
    await refreshConversationLists();
  } catch (exception) {
    if (!(exception instanceof DOMException && exception.name === "AbortError")) {
      if (activeGenerationRunId.value === runId) {
        error.value = exception instanceof Error ? exception.message : "生成失败";
      }
      await refreshConversationLists();
    }
  } finally {
    stopGenerationRun(runId);
    if (activeGenerationRunId.value === runId) activeGenerationRunId.value = null;
  }
}

function handleGenerateClick() {
  if (activeGenerationRun.value) {
    activeGenerationRun.value.controller.abort();
    return;
  }
  void generateImage();
}

async function analyzeImage() {
  if (!imageFile.value) return;
  busy.value = "analyze";
  error.value = "";
  generated.value = [];
  activeHistoryId.value = null;
  const form = new FormData();
  form.append("provider", provider.value);
  form.append("model", model.value);
  form.append("prompt", prompt.value || "请描述这张图片");
  form.append("detail", detail.value);
  if (selectedProjectId.value !== null) form.append("project_id", String(selectedProjectId.value));
  form.append("image", imageFile.value);
  try {
    const response = await fetch(`${API_BASE}/api/analyze`, {
      method: "POST",
      body: form,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(readableError(data, "分析失败"));
    analysis.value = data.text ?? "";
    await loadProjects();
  } catch (exception) {
    error.value = exception instanceof Error ? exception.message : "分析失败";
    await loadProjects();
  } finally {
    busy.value = "";
  }
}

function imageSource(item: ImageResult) {
  return item.url ||
    (item.base64_data ? `data:image/png;base64,${item.base64_data}` : "");
}

function openLightbox(item: ImageResult) {
  const source = imageSource(item);
  if (source) lightboxUrl.value = source;
}

function closeLightbox() {
  lightboxUrl.value = "";
}

function handleGlobalKeydown(event: KeyboardEvent) {
  if (event.key !== "Escape") return;
  if (openParameterMenu.value) closeParameterMenu();
  else if (lightboxUrl.value) closeLightbox();
  else if (lightboxUrl.value) closeLightbox();
}

function handleDocumentPointerDown(event: PointerEvent) {
  const target = event.target;
  if (target instanceof Element && !target.closest(".parameter-toolbar")) {
    closeParameterMenu();
  }
}

onMounted(async () => {
  window.addEventListener("keydown", handleGlobalKeydown);
  document.addEventListener("pointerdown", handleDocumentPointerDown);
  try {
    const response = await fetch(`${API_BASE}/api/auth/me`, { credentials: "include" });
    if (!response.ok) { authView.value = "login"; return; }
    currentUsername.value = (await response.json()).username;
    authView.value = "workspace";
    await Promise.all([loadRuntimeSettings(), loadProviders(), loadProjects()]);
  } catch {
    error.value = "无法加载服务商，请先启动后端";
  }
});
window.addEventListener("popstate", () => {
  currentView.value = window.location.pathname === "/settings" ? "settings" : "workspace";
});
onUnmounted(() => {
  window.removeEventListener("keydown", handleGlobalKeydown);
  document.removeEventListener("pointerdown", handleDocumentPointerDown);
  for (const run of generationRuns.values()) {
    if (run.timer !== undefined) window.clearInterval(run.timer);
    run.controller.abort();
  }
  generationRuns.clear();
  if (previewUrl.value.startsWith("blob:")) URL.revokeObjectURL(previewUrl.value);
});
</script>

<template>
  <main class="studio-shell">
    <section v-if="authView !== 'workspace'" class="auth-page">
      <div v-if="authView === 'checking'" class="auth-loading" aria-live="polite">正在检查登录状态…</div>
      <div v-else class="auth-layout">
        <aside class="auth-intro">
          <div class="auth-brand-mark">G</div>
          <p class="auth-eyebrow">GenImage</p>
          <h1>把想法变成画面</h1>
          <p class="auth-intro-copy">在一个清晰、专注的工作台里生成和管理你的图片。</p>
          <div class="auth-intro-rule" aria-hidden="true"></div>
          <p class="auth-intro-note">登录后即可继续使用你的项目与历史记录。</p>
        </aside>

        <form class="auth-form" @submit.prevent="authView === 'register' ? submitAuth('register') : submitAuth('login')">
          <div class="auth-form-heading">
            <div>
              <p class="auth-kicker">欢迎回来</p>
              <h2>{{ authView === 'register' ? '创建账号' : '登录 GenImage' }}</h2>
            </div>
            <span class="auth-step">{{ authView === 'register' ? '02' : '01' }}</span>
          </div>

          <div class="auth-mode" role="tablist" aria-label="认证方式">
            <button type="button" role="tab" :aria-selected="authView === 'login'" :class="{ active: authView === 'login' }" @click="authView = 'login'">登录</button>
            <button type="button" role="tab" :aria-selected="authView === 'register'" :class="{ active: authView === 'register' }" @click="authView = 'register'">注册</button>
          </div>

          <div class="auth-fields">
            <label>用户名<input v-model="username" autocomplete="username" placeholder="输入用户名" required /></label>
            <label>密码<input v-model="password" type="password" :autocomplete="authView === 'register' ? 'new-password' : 'current-password'" placeholder="至少 6 位字符" minlength="6" required /></label>
            <label v-if="authView === 'register'">确认密码<input v-model="passwordConfirmation" type="password" autocomplete="new-password" placeholder="再次输入密码" minlength="6" required /></label>
          </div>
          <p v-if="authError" class="error-message" role="alert">{{ authError }}</p>
          <button type="submit" class="primary-action auth-submit">{{ authView === 'register' ? '注册并进入工作台' : '登录' }}</button>
          <p class="auth-footnote">{{ authView === 'register' ? '已有账号？' : '还没有账号？' }}<button type="button" class="auth-link" @click="authView = authView === 'register' ? 'login' : 'register'">{{ authView === 'register' ? '返回登录' : '立即注册' }}</button></p>
        </form>
      </div>
    </section>
    <template v-else>
    <header class="topbar">
      <div class="brand">
        <span class="brand-mark">G</span>
        <div><strong>GenImage</strong><small>图像工作台</small></div>
      </div>
      <div class="topbar-actions">
        <span class="status-indicator" :class="{ configured: apiKeyConfigured }">
          <i></i>{{ apiKeyConfigured ? "API Key 已配置" : "请在设置页面配置 API Key" }}
        </span>
        <span>{{ currentUsername }}</span>
        <button v-if="currentView === 'workspace'" type="button" class="secondary-action" data-action="settings" @click="navigateToSettings">设置</button>
        <button v-else type="button" class="secondary-action" data-action="back-to-workspace" @click="navigateToWorkspace">返回工作台</button>
        <button type="button" class="secondary-action" @click="logout">退出登录</button>
      </div>
    </header>

    <section v-if="currentView === 'settings'" class="settings-page">
      <section class="settings-section"><h1>接口配置</h1><p>{{ apiKeyConfigured ? 'API Key 已配置' : '尚未配置 API Key' }}</p><label>API Key<input v-model="settingsApiKey" data-field="api-key" type="password" autocomplete="off" @blur="saveSettingsApiKey" /></label><a class="api-key-link" href="https://sub.beibeihai.xyz/home" target="_blank" rel="noopener noreferrer"><ExternalLink :size="16" />获取 API Key</a></section>
      <section class="settings-section settings-account-actions"><h2>账号</h2><p>退出当前账号，返回登录页面。</p><button type="button" class="secondary-action logout-action" @click="logout">退出登录</button></section>
      <section class="settings-section"><h2>修改密码</h2><label>旧密码<input v-model="oldPassword" data-field="old-password" type="password" /></label><label>新密码<input v-model="newPassword" data-field="new-password" type="password" /></label><label>确认新密码<input v-model="newPasswordConfirmation" data-field="new-password-confirmation" type="password" /></label><p v-if="authError" class="error-message">{{ authError }}</p><button type="button" class="primary-action" data-action="change-password" @click="changePassword">修改密码</button></section>
    </section>
    <template v-else>
    <div class="studio-grid">
      <ProjectSidebar
        :projects="projects"
        :selected-project-id="selectedProjectId"
        :loading="!projects.length && !projectError"
        @select-project="selectProject"
        @new-conversation="startNewConversation"
        @create-project="createProject"
        @rename-project="renameProject"
        @delete-project="deleteProject"
        @delete-history="deleteHistory"
        @open-history="openHistory"
      />
      <section class="workspace-panel">
        <div class="result-panel">
          <div class="result-heading">
            <div><span>作品画布</span><h2>{{ activeHistoryId ? "历史结果" : "生成结果" }}</h2></div>
            <span v-if="busy === 'analyze'" class="working">处理中</span>
          </div>

          <div v-if="analysis" class="analysis-note"><div class="note-label">图片分析</div><p>{{ analysis }}</p></div>
          <div v-if="generated.length" class="image-grid">
            <article v-for="(item, index) in generated" :key="index" class="image-card">
              <div class="image-frame">
                <button v-if="imageSource(item)" type="button" class="image-preview-trigger" :aria-label="`全屏查看生成图片 ${index + 1}`" @click="openLightbox(item)">
                  <img :src="imageSource(item)" :alt="`生成图片 ${index + 1}`" />
                </button>
                <div v-else class="missing-image">图片数据不可用</div>
              </div>
              <div class="image-meta">
                <span>图片 {{ index + 1 }}</span>
                <div class="image-meta-actions">
                  <strong>{{ formatDuration(item.generation_time_ms) }}</strong>
                  <a v-if="imageSource(item)" class="download" :href="imageSource(item)" download="genimage-result.png" aria-label="下载图片" title="下载图片"><Download :size="16" /></a>
                </div>
              </div>
            </article>
          </div>
          <div v-else-if="!analysis" class="empty-wall">
            <div class="empty-shape"><Sparkles :size="24" /></div>
            <h3>{{ activeGenerationElapsedMs !== null ? `等待生成结果 ${formatDuration(activeGenerationElapsedMs)}` : "等待生成结果" }}</h3>
            <p>配置参数并在下方输入提示词。</p>
          </div>
        </div>

        <section class="composer-dock">
          <div class="reference-row">
            <div class="upload-zone" @dragover.prevent @drop.prevent="setFile(($event as DragEvent).dataTransfer?.files[0])">
              <input id="image-input" type="file" accept="image/png,image/jpeg,image/webp,image/gif" @change="setFile(($event.target as HTMLInputElement).files?.[0])" />
              <label for="image-input"><Upload :size="18" /><span>{{ imageFile ? imageFile.name : "添加参考图片" }}</span><small>PNG、JPG、WEBP、GIF</small></label>
            </div>
            <div v-if="previewUrl" class="file-chip"><img :src="previewUrl" alt="参考图片预览" /><span>{{ imageFile?.name ?? "历史参考图片" }}</span><button type="button" aria-label="移除参考图片" @click="clearFile"><X :size="15" /></button></div>
          </div>

          <div class="composer-main">
            <div class="prompt-row">
            <label>提示词<textarea v-model="prompt" placeholder="描述主体、环境、构图、镜头、光线、材质与风格..."></textarea></label>
              <div class="parameter-toolbar">
                <div class="parameter-control"><button type="button" class="parameter-trigger" data-parameter-trigger="model" :aria-expanded="openParameterMenu === 'model'" @click="toggleParameterMenu('model')">模型名称 <strong>{{ model }}</strong></button><div v-if="openParameterMenu === 'model'" class="parameter-menu" data-parameter-menu="model"><button v-for="option in MODEL_OPTIONS" :key="option" type="button" class="parameter-option" :class="{ 'is-selected': option === model }" :data-parameter-option="option" @click="selectModel(option)"><span>{{ option }}</span><Check v-if="option === model" :size="15" /></button></div></div>
                <div class="parameter-control"><button type="button" class="parameter-trigger" data-parameter-trigger="size" :aria-expanded="openParameterMenu === 'size'" @click="toggleParameterMenu('size')">图片尺寸 <strong>{{ SIZE_OPTIONS.find((option) => option.value === size)?.label }}</strong></button><div v-if="openParameterMenu === 'size'" class="parameter-menu" data-parameter-menu="size"><button v-for="option in SIZE_OPTIONS" :key="option.value" type="button" class="parameter-option" :class="{ 'is-selected': option.value === size }" :data-parameter-option="option.value" @click="selectSize(option.value)"><span><strong>{{ option.label }} {{ option.description }} {{ option.value }}</strong></span><Check v-if="option.value === size" :size="15" /></button></div></div>
                <div class="parameter-control"><button type="button" class="parameter-trigger" data-parameter-trigger="detail" :aria-expanded="openParameterMenu === 'detail'" @click="toggleParameterMenu('detail')">细节级别 <strong>{{ DETAIL_OPTIONS.find((option) => option.value === detail)?.label }}</strong></button><div v-if="openParameterMenu === 'detail'" class="parameter-menu" data-parameter-menu="detail"><button v-for="option in DETAIL_OPTIONS" :key="option.value" type="button" class="parameter-option" :class="{ 'is-selected': option.value === detail }" :data-parameter-option="option.value" @click="selectDetail(option.value)"><span>{{ option.label }}</span><Check v-if="option.value === detail" :size="15" /></button></div></div>
                <div class="parameter-control"><button type="button" class="parameter-trigger" data-parameter-trigger="count" :aria-expanded="openParameterMenu === 'count'" @click="toggleParameterMenu('count')">生成数量 <strong>{{ imageCount }} 张</strong></button><div v-if="openParameterMenu === 'count'" class="parameter-menu" data-parameter-menu="count"><button v-for="option in IMAGE_COUNT_OPTIONS" :key="option" type="button" class="parameter-option" :class="{ 'is-selected': option === imageCount }" :data-parameter-option="option" @click="selectImageCount(option)"><span>{{ option }} 张</span><Check v-if="option === imageCount" :size="15" /></button></div></div>
              </div>
            </div>
            <div class="composer-actions"><button type="button" class="secondary-action analyze-action" :disabled="!canAnalyze" @click="analyzeImage"><LoaderCircle v-if="busy === 'analyze'" class="spin" :size="17" /><ImagePlus v-else :size="17" />分析图片</button><button type="button" class="primary-action" :class="{ 'cancel-action': activeGenerationRun }" :disabled="busy === 'analyze'" @click="handleGenerateClick"><X v-if="activeGenerationRun" :size="17" /><LoaderCircle v-else-if="busy === 'analyze'" class="spin" :size="17" /><Sparkles v-else :size="17" />{{ activeGenerationRun ? "取消生成" : "生成图片" }}</button></div>
          </div>
          <p v-if="error" class="error-message">{{ error }}</p>
        </section>
      </section>
    </div>

    <!--
      <div v-if="historyOpen" class="drawer-layer" @click.self="closeHistory">
        <aside class="history-drawer" role="dialog" aria-modal="true" aria-label="历史记录">
          <div class="history-drawer-header">
            <div><span>历史记录</span><strong>{{ history.length }} 条</strong></div>
            <button type="button" class="history-drawer-close" aria-label="关闭历史记录" title="关闭" @click="closeHistory"><X :size="20" /></button>
          </div>
          <div v-if="history.length" class="history-list">
            <button v-for="item in history" :key="item.id" type="button" class="history-item" :class="{ active: activeHistoryId === item.id, failed: item.status === 'failed' }" :data-history-id="item.id" @click="openHistory(item.id)">
              <span>{{ item.prompt }}</span>
              <small>{{ item.model }} · {{ formatHistoryTime(item.created_at) }}</small>
            </button>
          </div>
          <p v-else-if="!historyError" class="history-empty">暂无历史记录</p>
          <p v-if="historyError" class="history-error">{{ historyError }}</p>
        </aside>
      </div>
    -->

    <div v-if="lightboxUrl" class="image-lightbox" role="dialog" aria-modal="true" aria-label="生成图片全屏预览" @click.self="closeLightbox">
      <button type="button" class="lightbox-close" aria-label="关闭全屏预览" title="关闭" @click="closeLightbox"><X :size="22" /></button>
      <img :src="lightboxUrl" alt="生成图片全屏预览" />
    </div>
    <ProjectDialog
      :open="projectDialogMode !== null"
      :title="projectDialogMode === 'rename' ? '重命名项目' : '新建项目'"
      :initial-name="projectDialogProject?.name"
      @submit="submitProjectDialog"
      @cancel="cancelProjectDialog"
    />
    <ConfirmDialog
      :open="confirmAction !== null"
      :title="confirmAction === 'project' ? '删除项目' : '删除历史记录'"
      :message="confirmAction === 'project' ? `确认删除项目“${confirmProject?.name}”及其 ${confirmProject?.history_count ?? 0} 条历史记录吗？` : `确认删除选中的 ${confirmHistoryIds.length} 条历史记录吗？`"
      :busy="actionBusy"
      @confirm="confirmDeletion"
      @cancel="cancelConfirm"
    />
    </template>
    </template>
  </main>
</template>
