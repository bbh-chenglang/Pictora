<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import {
  Check,
  ChevronDown,
  ChevronRight,
  Download,
  ExternalLink,
  ImagePlus,
  LoaderCircle,
  Sparkles,
  Upload,
  X,
} from "lucide-vue-next";
import ProjectSidebar, {
  type ProjectSummary,
  type RunningGenerationSummary,
} from "./components/ProjectSidebar.vue";
import ConfirmDialog from "./components/ConfirmDialog.vue";
import ProjectDialog from "./components/ProjectDialog.vue";
import groupQrUrl from "./assets/genimage-group.png";

type Provider = { id: string; label: string; models: string[] };
type ApiKeyProvider = "gpt" | "gemini";
type ApiKeyConfig = {
  id: number;
  alias: string;
  provider_type: ApiKeyProvider;
  model: string;
  api_key_configured: boolean;
};
type DiscoveredModel = { id: string; provider_type: ApiKeyProvider };
type ApiKeyTestResult = {
  message: string;
  models: DiscoveredModel[];
};
type ApiKeyConfigForm = {
  alias: string;
  api_key: string;
  provider_type: ApiKeyProvider | null;
  model: string;
};
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
  resolution?: string | null;
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
  { label: "1:1", value: "1:1" },
  { label: "3:2", value: "3:2" },
  { label: "2:3", value: "2:3" },
  { label: "9:16", value: "9:16" },
  { label: "16:9", value: "16:9" },
] as const;
const DEFAULT_SIZE = "1:1";
const LEGACY_SIZE_TO_ASPECT_RATIO: Record<string, string> = {
  "1024x1024": "1:1",
  "1536x1024": "3:2",
  "1024x1536": "2:3",
  "1024x1792": "9:16",
  "1792x1024": "16:9",
  "720x1280": "9:16",
  "1280x720": "16:9",
};
const RESOLUTION_OPTIONS = ["1K", "2K", "4K"] as const;
const DEFAULT_RESOLUTION = "1K";
const QUALITY_OPTIONS = [
  { label: "自动", value: "auto" },
  { label: "低", value: "low" },
  { label: "中", value: "medium" },
  { label: "高", value: "high" },
] as const;
const IMAGE_COUNT_OPTIONS = [1, 2, 3, 4] as const;
type ParameterMenu = "apiKey" | "model" | "size" | "resolution" | "quality" | "count";
type GenerationRun = {
  controller: AbortController;
  taskId: number | null;
  startedAt: number;
  elapsedMs: number;
  timer?: number;
  polling: boolean;
  projectId: number | null;
  provider: string;
  model: string;
  apiKeyConfigId: number | null;
  prompt: string;
  batchPrompts: string;
  imageCount: number;
  quality: string;
  size: string;
  resolution: string;
  imageFile: File | null;
  referencePreviewUrl: string;
  images: ImageResult[];
  error: string;
};

const providers = ref<Provider[]>([]);
const provider = ref("compatible");
const model = ref<string>(DEFAULT_MODEL);
const prompt = ref("");
const batchPrompts = ref("");
const imageCount = ref(1);
const quality = ref("auto");
const size = ref<string>(DEFAULT_SIZE);
const resolution = ref<string>(DEFAULT_RESOLUTION);
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
const confirmAction = ref<"project" | "history" | "api-key" | null>(null);
const confirmProject = ref<ProjectSummary | null>(null);
const confirmHistoryIds = ref<number[]>([]);
const confirmConfig = ref<ApiKeyConfig | null>(null);
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
const apiKeyConfigs = ref<ApiKeyConfig[]>([]);
const activeApiKeyConfigId = ref<number | null>(null);
const legacySettingsMode = ref(false);
const settingsApiKey = ref("");
const configForm = ref<ApiKeyConfigForm>({ alias: "", api_key: "", provider_type: null, model: DEFAULT_MODEL });
const editingConfigId = ref<number | null>(null);
const showConfigForm = ref(false);
const discoveredModels = ref<DiscoveredModel[]>([]);
const discoveringModels = ref(false);
const availableModels = ref<DiscoveredModel[]>([]);
const loadingConfigModels = ref(false);
const testingConfigId = ref<number | null>(null);
const apiKeyTestResults = ref<Record<number, ApiKeyTestResult>>({});
const expandedApiKeyModelLists = ref<Record<number, boolean>>({});
const settingsConfigError = ref("");
const oldPassword = ref("");
const newPassword = ref("");
const newPasswordConfirmation = ref("");
const feedbackMessage = ref("");
const feedbackContact = ref("");
const feedbackStatus = ref("");
const feedbackSubmitting = ref(false);
let settingsSaveQueue: Promise<void> = Promise.resolve();

const generationRuns = new Map<number, GenerationRun>();
const generationVersion = ref(0);
const activeGenerationRunId = ref<number | null>(null);
const historyDetailCache = new Map<number, Promise<HistoryDetail>>();
const historyImagePreloads = new Map<string, HTMLImageElement>();
let historyOpenVersion = 0;
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
const runningGenerations = computed<RunningGenerationSummary[]>(() => {
  generationVersion.value;
  return [...generationRuns.entries()].map(([id, run]) => ({
    id,
    projectId: run.projectId,
    prompt: run.prompt,
    model: run.model,
    size: run.size,
    resolution: run.resolution,
    elapsedMs: run.elapsedMs,
  }));
});
const canAnalyze = computed(() => Boolean(imageFile.value) && busy.value !== "analyze");
const selectedConfig = computed(() => apiKeyConfigs.value.find((item) => item.id === activeApiKeyConfigId.value) ?? null);
const selectedProviderType = computed<ApiKeyProvider>(() =>
  selectedConfig.value?.provider_type ?? (provider.value === "gemini" ? "gemini" : "gpt"),
);
const selectedApiKeyLabel = computed(() => selectedConfig.value?.alias ?? "未配置");
const selectedModelLabel = computed(() => model.value);
const modelOptions = computed(() => {
  if (selectedConfig.value) {
    return availableModels.value.filter(
      (item) => item.provider_type === selectedConfig.value?.provider_type,
    );
  }
  const providerModels = providers.value.find((item) => item.id === provider.value)?.models;
  const models = providerModels?.length ? providerModels : MODEL_OPTIONS;
  return models.map((id) => ({
    id,
    provider_type: provider.value === "gemini" ? "gemini" : "gpt",
  })) ?? [];
});
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
  const error = data?.error ?? data?.detail?.error;
  return messages[error?.code] ?? error?.message ?? fallback;
}

function apiErrorCode(data: any): string | undefined {
  return data?.error?.code ?? data?.detail?.error?.code;
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
  if (activeGenerationRunId.value !== null) {
    restoreGenerationRun(activeGenerationRunId.value);
  }
}

function toggleParameterMenu(menu: ParameterMenu) {
  openParameterMenu.value = openParameterMenu.value === menu ? null : menu;
}

function closeParameterMenu() {
  openParameterMenu.value = null;
}

async function persistConfigModel(config: ApiKeyConfig, value: string) {
  const response = await fetch(`${API_BASE}/api/settings/api-keys/${config.id}`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model: value }),
  });
  const data = await parseJsonResponse(response);
  if (!response.ok) throw new Error(readableError(data, "保存模型失败"));
  const savedModel = data?.model ?? value;
  apiKeyConfigs.value = apiKeyConfigs.value.map((item) =>
    item.id === config.id ? { ...item, model: savedModel } : item,
  );
  return savedModel;
}

async function loadConfigModels(config: ApiKeyConfig) {
  availableModels.value = [];
  model.value = config.model;
  if (!config.api_key_configured) return;
  loadingConfigModels.value = true;
  try {
    const response = await fetch(`${API_BASE}/api/settings/api-keys/${config.id}/models`, { credentials: "include" });
    const data = await parseJsonResponse(response);
    if (!response.ok) throw new Error(readableError(data, "无法获取模型列表"));
    const models = (data?.models ?? []) as DiscoveredModel[];
    availableModels.value = models.filter((item) => item.provider_type === config.provider_type);
    if (availableModels.value.length && !availableModels.value.some((item) => item.id === config.model)) {
      model.value = availableModels.value[0].id;
      try {
        model.value = await persistConfigModel(config, model.value);
      } catch (exception) {
        error.value = exception instanceof Error ? exception.message : "保存模型失败";
      }
    }
  } catch {
    availableModels.value = [{ id: config.model, provider_type: config.provider_type }];
    model.value = config.model;
  } finally {
    loadingConfigModels.value = false;
  }
}

async function selectApiKeyConfig(selected: ApiKeyConfig) {
  if (legacySettingsMode.value) return;
  activeApiKeyConfigId.value = selected.id;
  model.value = selected.model;
  provider.value = selected.provider_type === "gemini" ? "gemini" : "compatible";
  apiKeyConfigured.value = selected.api_key_configured;
  await fetch(`${API_BASE}/api/settings/active`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ config_id: selected.id }),
  });
  await loadConfigModels(selected);
  closeParameterMenu();
}

function historyProviderType(item: Pick<HistorySummary, "provider" | "model">): ApiKeyProvider {
  return item.provider.toLowerCase() === "gemini" || item.model.toLowerCase().includes("gemini")
    ? "gemini"
    : "gpt";
}

async function restoreHistoryApiConfig(item: HistoryDetail) {
  if (legacySettingsMode.value) {
    provider.value = item.provider;
    model.value = (MODEL_OPTIONS as readonly string[]).includes(item.model)
      ? item.model
      : DEFAULT_MODEL;
    return;
  }

  const providerType = historyProviderType(item);
  const current = selectedConfig.value;
  const matchingConfig = apiKeyConfigs.value.find(
    (config) => config.provider_type === providerType && config.model === item.model,
  ) ?? (current?.provider_type === providerType ? current : undefined)
    ?? apiKeyConfigs.value.find((config) => config.provider_type === providerType);

  if (matchingConfig) await selectApiKeyConfig(matchingConfig);
}

async function selectModel(value: string) {
  const previousModel = model.value;
  model.value = value;
  if (legacySettingsMode.value) {
    await applyRuntimeSettings();
    closeParameterMenu();
    return;
  }
  const config = selectedConfig.value;
  if (config) {
    try {
      model.value = await persistConfigModel(config, value);
    } catch (exception) {
      model.value = previousModel;
      error.value = exception instanceof Error ? exception.message : "保存模型失败";
    }
  }
  closeParameterMenu();
}

function selectSize(value: string) {
  size.value = value;
  closeParameterMenu();
}

function selectResolution(value: string) {
  resolution.value = value;
  closeParameterMenu();
}

function selectQuality(value: string) {
  quality.value = value;
  closeParameterMenu();
}

function selectImageCount(value: number) {
  imageCount.value = value;
  closeParameterMenu();
}

async function saveSettingsApiKey() {
  if (!legacySettingsMode.value) return;
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

async function submitFeedback() {
  const message = feedbackMessage.value.trim();
  if (!message || feedbackSubmitting.value) return;
  feedbackStatus.value = "正在提交留言...";
  feedbackSubmitting.value = true;
  try {
    const response = await fetch(`${API_BASE}/api/feedback`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, contact: feedbackContact.value.trim() }),
    });
    const data = await parseJsonResponse(response);
    if (!response.ok) throw new Error(readableError(data, "留言提交失败，请稍后重试"));
    feedbackMessage.value = "";
    feedbackContact.value = "";
    feedbackStatus.value = data?.message ?? "留言已提交";
  } catch (exception) {
    feedbackStatus.value = exception instanceof Error ? exception.message : "留言提交失败，请稍后重试";
  } finally {
    feedbackSubmitting.value = false;
  }
}

async function loadRuntimeSettings() {
  const response = await fetch(`${API_BASE}/api/settings`);
  const data = await response.json();
  if (!response.ok) throw new Error(readableError(data, "无法加载运行时配置"));
  const hasConfigsField = Object.prototype.hasOwnProperty.call(data, "configs");
  const configs = Array.isArray(data.configs) ? data.configs as ApiKeyConfig[] : [];
  legacySettingsMode.value = !hasConfigsField;
  apiKeyConfigs.value = hasConfigsField
    ? configs
    : MODEL_OPTIONS.map((item, index) => ({ id: 0 - index, alias: item, provider_type: "gpt", model: item, api_key_configured: Boolean(data.api_key_configured) }));
  activeApiKeyConfigId.value = configs.length ? (data.active_config_id ?? configs[0].id) : null;
  const active = configs.find((item) => item.id === activeApiKeyConfigId.value);
  model.value = active?.model ?? ((MODEL_OPTIONS as readonly string[]).includes(data.model) ? data.model : DEFAULT_MODEL);
  if (active) {
    provider.value = active.provider_type === "gemini" ? "gemini" : "compatible";
    await loadConfigModels(active);
  } else {
    availableModels.value = [];
  }
  apiKeyConfigured.value = Boolean(data.api_key_configured);
}

function resetConfigForm() {
  editingConfigId.value = null;
  showConfigForm.value = false;
  configForm.value = { alias: "", api_key: "", provider_type: null, model: DEFAULT_MODEL };
  settingsConfigError.value = "";
}

function beginAddConfig() {
  resetConfigForm();
  showConfigForm.value = true;
}

function editConfig(config: ApiKeyConfig) {
  editingConfigId.value = config.id;
  showConfigForm.value = true;
  configForm.value = { alias: config.alias, api_key: "", provider_type: config.provider_type, model: config.model };
  settingsConfigError.value = "";
}

async function discoverConfigModels() {
  const apiKey = configForm.value.api_key.trim();
  if (!apiKey) {
    settingsConfigError.value = "请先输入 API Key";
    return;
  }
  if (!configForm.value.provider_type) {
    settingsConfigError.value = "请先选择 API 类型";
    return;
  }
  discoveringModels.value = true;
  settingsConfigError.value = "";
  try {
    const response = await fetch(`${API_BASE}/api/settings/api-keys/models`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        api_key: apiKey,
        provider_type: configForm.value.provider_type,
      }),
    });
    const data = await parseJsonResponse(response);
    if (!response.ok) throw new Error(readableError(data, "无法获取模型列表"));
    discoveredModels.value = (data?.models ?? []) as DiscoveredModel[];
    const first = discoveredModels.value[0];
    if (!first) throw new Error("未获取到可用模型");
    configForm.value.model = first.id;
    configForm.value.provider_type = first.provider_type;
  } catch (exception) {
    settingsConfigError.value = exception instanceof Error ? exception.message : "无法获取模型列表";
  } finally {
    discoveringModels.value = false;
  }
}

async function testConfig(config: ApiKeyConfig) {
  testingConfigId.value = config.id;
  apiKeyTestResults.value = {
    ...apiKeyTestResults.value,
    [config.id]: { message: "正在测试 API Key...", models: [] },
  };
  try {
    const response = await fetch(`${API_BASE}/api/settings/api-keys/${config.id}/test`, { method: "POST", credentials: "include" });
    const data = await parseJsonResponse(response);
    apiKeyTestResults.value = {
      ...apiKeyTestResults.value,
      [config.id]: {
        message: response.ok ? (data?.message ?? "测试完成") : readableError(data, "测试失败"),
        models: response.ok ? ((data?.models ?? []) as DiscoveredModel[]) : [],
      },
    };
    if (response.ok && data?.models?.length) {
      expandedApiKeyModelLists.value = {
        ...expandedApiKeyModelLists.value,
        [config.id]: true,
      };
    }
  } catch {
    apiKeyTestResults.value = {
      ...apiKeyTestResults.value,
      [config.id]: { message: "测试失败，请稍后重试", models: [] },
    };
  } finally {
    testingConfigId.value = null;
  }
}

function apiKeyModelListExpanded(configId: number) {
  return expandedApiKeyModelLists.value[configId] !== false;
}

function toggleApiKeyModelList(configId: number) {
  expandedApiKeyModelLists.value = {
    ...expandedApiKeyModelLists.value,
    [configId]: !apiKeyModelListExpanded(configId),
  };
}

async function refreshRuntimeSettings() {
  await loadRuntimeSettings();
  resetConfigForm();
}

async function saveConfig() {
  const form = configForm.value;
  const providerType = form.provider_type;
  if (!providerType) {
    settingsConfigError.value = "请选择 API 类型";
    return;
  }
  if (!form.alias.trim() || (!editingConfigId.value && !form.api_key.trim())) {
    settingsConfigError.value = "请填写别名和 API Key";
    return;
  }
  const editing = editingConfigId.value !== null;
  const body = JSON.stringify({ alias: form.alias, api_key: form.api_key, provider_type: providerType });
  let response = await fetch(`${API_BASE}/api/settings/api-keys${editing ? `/${editingConfigId.value}` : ""}`, {
    method: editing ? "PATCH" : "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body,
  });
  let data = await parseJsonResponse(response);
  if (editing && response.status === 404 && apiErrorCode(data) === "api_key_config_not_found") {
    response = await fetch(`${API_BASE}/api/settings/api-keys`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body,
    });
    data = await parseJsonResponse(response);
  }
  if (!response.ok) {
    settingsConfigError.value = readableError(data, "保存配置失败");
    return;
  }
  resetConfigForm();
  await loadRuntimeSettings();
}

async function deleteConfig(config: ApiKeyConfig) {
  confirmConfig.value = config;
  confirmAction.value = "api-key";
}

async function deleteConfigNow(config: ApiKeyConfig) {
  const response = await fetch(`${API_BASE}/api/settings/api-keys/${config.id}`, { method: "DELETE", credentials: "include" });
  if (!response.ok) {
    settingsConfigError.value = readableError(await parseJsonResponse(response), "删除配置失败");
    return;
  }
  await refreshRuntimeSettings();
}

async function loadProviders() {
  const response = await fetch(`${API_BASE}/api/providers`);
  const data = await response.json();
  if (!response.ok) throw new Error(readableError(data, "无法加载服务商"));
  providers.value = data.providers ?? [];
  provider.value = selectedConfig.value?.provider_type === "gemini"
    ? "gemini"
    : providers.value[0]?.id ?? "compatible";
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

function preloadHistoryImages(data: HistoryDetail) {
  for (const image of data.images.filter((item) => item.role === "generated")) {
    const source = resourceUrl(image.url);
    if (historyImagePreloads.has(source)) continue;
    const preload = new Image();
    preload.decoding = "async";
    preload.src = source;
    historyImagePreloads.set(source, preload);
    while (historyImagePreloads.size > 4) {
      const oldest = historyImagePreloads.keys().next().value as string | undefined;
      if (!oldest) break;
      const released = historyImagePreloads.get(oldest);
      if (released) released.src = "";
      historyImagePreloads.delete(oldest);
    }
  }
}

function fetchHistoryDetail(historyId: number) {
  const cached = historyDetailCache.get(historyId);
  if (cached) return cached;
  const request = (async () => {
    const response = await fetch(`${API_BASE}/api/history/${historyId}`, { credentials: "include" });
    const data = await parseJsonResponse(response);
    if (!response.ok) throw new Error(readableError(data, "无法加载历史详情"));
    const detail = data as HistoryDetail;
    if (detail.status !== "completed") historyDetailCache.delete(historyId);
    return detail;
  })();
  historyDetailCache.set(historyId, request);
  while (historyDetailCache.size > 30) {
    const oldest = historyDetailCache.keys().next().value as number | undefined;
    if (oldest === undefined) break;
    historyDetailCache.delete(oldest);
  }
  void request.catch(() => {
    if (historyDetailCache.get(historyId) === request) historyDetailCache.delete(historyId);
  });
  return request;
}

function prefetchHistory(historyId: number) {
  void fetchHistoryDetail(historyId).then(preloadHistoryImages).catch(() => undefined);
}

async function openHistory(historyId: number) {
  const openVersion = ++historyOpenVersion;
  activeGenerationRunId.value = null;
  error.value = "";
  try {
    const data = await fetchHistoryDetail(historyId);
    if (openVersion !== historyOpenVersion) return;

    activeHistoryId.value = historyId;
    prompt.value = data.prompt;
    if (QUALITY_OPTIONS.some((option) => option.value === data.detail)) {
      quality.value = data.detail;
    }
    const historyAspectRatio = data.size ? LEGACY_SIZE_TO_ASPECT_RATIO[data.size] ?? data.size : DEFAULT_SIZE;
    if (SIZE_OPTIONS.some((option) => option.value === historyAspectRatio)) {
      size.value = historyAspectRatio;
    }
    resolution.value = RESOLUTION_OPTIONS.includes(data.resolution as typeof RESOLUTION_OPTIONS[number])
      ? data.resolution ?? DEFAULT_RESOLUTION
      : DEFAULT_RESOLUTION;
    imageCount.value = data.image_count;
    analysis.value = data.analysis_text ?? "";
    generated.value = historyImages(data);

    const reference = data.images.find((image) => image.role === "reference");
    if (previewUrl.value.startsWith("blob:")) URL.revokeObjectURL(previewUrl.value);
    imageFile.value = null;
    previewUrl.value = reference ? resourceUrl(reference.url) : "";
    preloadHistoryImages(data);
    void restoreHistoryApiConfig(data).catch((exception) => {
      if (openVersion === historyOpenVersion) {
        error.value = exception instanceof Error ? exception.message : "无法恢复历史配置";
      }
    });
  } catch (exception) {
    if (openVersion !== historyOpenVersion) return;
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
    restorePendingGenerationTasks();
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

function restoreGenerationRun(runId: number) {
  const run = generationRuns.get(runId);
  if (!run) return;

  clearWorkspace();
  activeGenerationRunId.value = runId;
  if (run.projectId !== null) {
    selectedProjectId.value = run.projectId;
    history.value = projects.value.find((project) => project.id === run.projectId)?.history ?? [];
  }
  provider.value = run.provider;
  model.value = run.model;
  activeApiKeyConfigId.value = run.apiKeyConfigId;
  const config = apiKeyConfigs.value.find((item) => item.id === run.apiKeyConfigId);
  if (config) {
    apiKeyConfigured.value = config.api_key_configured;
    if (!availableModels.value.some((item) => item.id === run.model)) {
      availableModels.value = [{ id: run.model, provider_type: config.provider_type }];
    }
  }
  prompt.value = run.prompt;
  batchPrompts.value = run.batchPrompts;
  imageCount.value = run.imageCount;
  quality.value = run.quality;
  size.value = run.size;
  resolution.value = run.resolution;
  imageFile.value = run.imageFile;
  previewUrl.value = run.imageFile
    ? URL.createObjectURL(run.imageFile)
    : run.referencePreviewUrl;
  generated.value = run.images;
  error.value = run.error;
  generationVersion.value++;
}

function selectProject(projectId: number) {
  historyOpenVersion++;
  activeGenerationRunId.value = null;
  selectedProjectId.value = projectId;
  const selectedHistory = projects.value.find((project) => project.id === projectId)?.history ?? [];
  history.value = selectedHistory;
  clearWorkspace();
  const firstCompleted = selectedHistory.find((item) => item.status === "completed");
  if (firstCompleted) prefetchHistory(firstCompleted.id);
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
  for (const id of ids) historyDetailCache.delete(id);
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
  confirmConfig.value = null;
}

async function confirmDeletion() {
  if (actionBusy.value || !confirmAction.value) return;
  if (confirmAction.value === "api-key") {
    if (!confirmConfig.value) return;
    actionBusy.value = true;
    try {
      await deleteConfigNow(confirmConfig.value);
    } finally {
      actionBusy.value = false;
      cancelConfirm();
    }
    return;
  }
  if (!confirmProject.value) return;
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

function startGenerationRun(
  runId: number,
  controller: AbortController,
  snapshot: Omit<GenerationRun, "controller" | "startedAt" | "elapsedMs" | "timer" | "images" | "error">,
  initialElapsedMs = 0,
  activate = true,
) {
  const run: GenerationRun = {
    controller,
    startedAt: performance.now() - initialElapsedMs,
    elapsedMs: initialElapsedMs,
    images: [],
    error: "",
    ...snapshot,
  };
  run.timer = window.setInterval(() => {
    run.elapsedMs = performance.now() - run.startedAt;
    generationVersion.value++;
  }, 100);
  generationRuns.set(runId, run);
  if (activate) activeGenerationRunId.value = runId;
  generationVersion.value++;
}

function stopGenerationRun(runId: number) {
  const run = generationRuns.get(runId);
  if (!run) return;
  if (run.timer !== undefined) window.clearInterval(run.timer);
  run.elapsedMs = performance.now() - run.startedAt;
  generationRuns.delete(runId);
  generationVersion.value++;
}

function adoptGenerationTaskId(runId: number, taskId: number) {
  const run = generationRuns.get(runId);
  if (!run) return null;
  generationRuns.delete(runId);
  run.taskId = taskId;
  generationRuns.set(taskId, run);
  if (activeGenerationRunId.value === runId) activeGenerationRunId.value = taskId;
  generationVersion.value++;
  return run;
}

function historyImages(data: HistoryDetail): ImageResult[] {
  return data.images
    .filter((image) => image.role === "generated")
    .map((image) => ({
      url: resourceUrl(image.url),
      generation_time_ms: data.elapsed_ms,
    }));
}

function pollDelay(signal: AbortSignal, milliseconds: number) {
  return new Promise<void>((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const handleAbort = () => {
      window.clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    };
    const timer = window.setTimeout(() => {
      signal.removeEventListener("abort", handleAbort);
      resolve();
    }, milliseconds);
    signal.addEventListener("abort", handleAbort, { once: true });
  });
}

async function pollGenerationTask(taskId: number) {
  const initialRun = generationRuns.get(taskId);
  if (!initialRun || initialRun.polling) return;
  initialRun.polling = true;
  let transientFailures = 0;
  try {
    while (generationRuns.has(taskId)) {
      const run = generationRuns.get(taskId);
      if (!run) return;
      try {
        const response = await fetch(`${API_BASE}/api/history/${taskId}`, {
          credentials: "include",
          signal: run.controller.signal,
        });
        const data = await parseJsonResponse(response);
        if (!response.ok) {
          if (response.status >= 500 && transientFailures < 5) {
            transientFailures++;
            await pollDelay(run.controller.signal, 2500);
            continue;
          }
          throw new Error(readableError(data, `无法查询生成任务（HTTP ${response.status}）`));
        }
        const detail = data as HistoryDetail;
        transientFailures = 0;
        if (detail.status === "pending") {
          await pollDelay(run.controller.signal, 1500);
          continue;
        }

        historyDetailCache.set(taskId, Promise.resolve(detail));
        if (detail.status === "completed") {
          run.images = historyImages(detail);
          preloadHistoryImages(detail);
          if (activeGenerationRunId.value === taskId) {
            generated.value = run.images;
            error.value = "";
          }
        } else {
          run.error = detail.error_message || "生成失败";
          if (activeGenerationRunId.value === taskId) error.value = run.error;
        }
        stopGenerationRun(taskId);
        if (activeGenerationRunId.value === taskId) activeGenerationRunId.value = null;
        await refreshConversationLists();
        return;
      } catch (exception) {
        if (exception instanceof DOMException && exception.name === "AbortError") return;
        transientFailures++;
        if (transientFailures <= 5) {
          await pollDelay(run.controller.signal, 2500);
          continue;
        }
        const message = exception instanceof Error ? exception.message : "无法查询生成任务";
        run.error = message;
        if (activeGenerationRunId.value === taskId) error.value = message;
        stopGenerationRun(taskId);
        if (activeGenerationRunId.value === taskId) activeGenerationRunId.value = null;
        return;
      }
    }
  } finally {
    const run = generationRuns.get(taskId);
    if (run) run.polling = false;
  }
}

function pendingElapsedMs(createdAt: string) {
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(createdAt) ? createdAt : `${createdAt}Z`;
  const createdAtMs = Date.parse(normalized);
  return Number.isFinite(createdAtMs) ? Math.max(0, Date.now() - createdAtMs) : 0;
}

function restorePendingGenerationTasks() {
  for (const project of projects.value) {
    for (const item of project.history) {
      if (item.kind !== "generate" || item.status !== "pending" || generationRuns.has(item.id)) continue;
      const historySize = item.size ? LEGACY_SIZE_TO_ASPECT_RATIO[item.size] ?? item.size : DEFAULT_SIZE;
      const providerType = historyProviderType(item);
      const matchingConfig = apiKeyConfigs.value.find(
        (config) => config.provider_type === providerType && config.model === item.model,
      );
      startGenerationRun(
        item.id,
        new AbortController(),
        {
          taskId: item.id,
          polling: false,
          projectId: project.id,
          provider: item.provider,
          model: item.model,
          apiKeyConfigId: matchingConfig?.id ?? null,
          prompt: item.prompt,
          batchPrompts: "",
          imageCount: item.image_count,
          quality: item.detail,
          size: SIZE_OPTIONS.some((option) => option.value === historySize) ? historySize : DEFAULT_SIZE,
          resolution: RESOLUTION_OPTIONS.includes(item.resolution as typeof RESOLUTION_OPTIONS[number])
            ? item.resolution ?? DEFAULT_RESOLUTION
            : DEFAULT_RESOLUTION,
          imageFile: null,
          referencePreviewUrl: "",
        },
        pendingElapsedMs(item.created_at),
        false,
      );
      void pollGenerationTask(item.id);
    }
  }
}

async function generateImage() {
  if (!provider.value || !model.value) {
    error.value = "请先配置 API Key 和模型名称";
    return;
  }
  const prompts = batchPrompts.value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
  const requestPrompt = prompt.value.trim() || prompts[0] || "请生成一张图片";
  const generationProvider = provider.value;
  const generationModel = model.value;
  const generationConfigId = activeApiKeyConfigId.value;
  const generationProjectId = selectedProjectId.value;
  const generationImageCount = imageCount.value;
  const generationQuality = quality.value;
  const generationSize = size.value;
  const generationResolution = resolution.value;
  const generationImageFile = imageFile.value;
  const generationProviderType = selectedProviderType.value;
  const runId = Date.now() + Math.random();
  const controller = new AbortController();
  startGenerationRun(runId, controller, {
    taskId: null,
    polling: false,
    projectId: generationProjectId,
    provider: generationProvider,
    model: generationModel,
    apiKeyConfigId: generationConfigId,
    prompt: requestPrompt,
    batchPrompts: batchPrompts.value,
    imageCount: generationImageCount,
    quality: generationQuality,
    size: generationSize,
    resolution: generationResolution,
    imageFile: generationImageFile,
    referencePreviewUrl: generationImageFile ? "" : previewUrl.value,
  });
  error.value = "";
  analysis.value = "";
  generated.value = [];
  activeHistoryId.value = null;
  try {
    let endpoint = `${API_BASE}/api/generate`;
    let requestInit: RequestInit;
    if (generationImageFile) {
      endpoint += "/reference";
      const form = new FormData();
      form.append("provider", generationProvider);
      form.append("model", generationModel);
      form.append("prompt", requestPrompt);
      form.append("count", String(generationImageCount));
      form.append("size", generationSize);
      form.append("aspect_ratio", generationSize);
      form.append("resolution", generationResolution);
      if (generationProviderType === "gpt") form.append("detail", generationQuality);
      if (generationConfigId !== null) form.append("api_key_config_id", String(generationConfigId));
      if (generationProjectId !== null) form.append("project_id", String(generationProjectId));
      for (const batchPrompt of prompts) form.append("prompts", batchPrompt);
      form.append("image", generationImageFile);
      requestInit = { method: "POST", signal: controller.signal, body: form };
    } else {
      requestInit = {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          provider: generationProvider,
          model: generationModel,
          ...(generationConfigId !== null ? { api_key_config_id: generationConfigId } : {}),
          prompt: requestPrompt,
          prompts: prompts.length ? prompts : null,
          count: generationImageCount,
          ...(generationProviderType === "gpt" ? { detail: generationQuality } : {}),
          size: generationSize,
          aspect_ratio: generationSize,
          resolution: generationResolution,
          project_id: generationProjectId,
        }),
      };
    }
    const response = await fetch(endpoint, requestInit);
    const data = await parseJsonResponse(response);
    if (!response.ok) {
      throw new Error(readableError(data, `生成失败（HTTP ${response.status}）`));
    }
    if (!data) throw new Error("服务返回了无效响应");
    const taskId = Number(data.task_id);
    if (Number.isInteger(taskId) && taskId > 0) {
      if (!adoptGenerationTaskId(runId, taskId)) return;
      await refreshConversationLists();
      void pollGenerationTask(taskId);
      return;
    }
    const run = generationRuns.get(runId);
    if (run) {
      run.images = data.images ?? [];
      generationVersion.value++;
    }
    if (activeGenerationRunId.value === runId) generated.value = data.images ?? [];
    await refreshConversationLists();
  } catch (exception) {
    if (!(exception instanceof DOMException && exception.name === "AbortError")) {
      const message = exception instanceof Error ? exception.message : "生成失败";
      const run = generationRuns.get(runId);
      if (run) {
        run.error = message;
        generationVersion.value++;
      }
      if (activeGenerationRunId.value === runId) {
        error.value = message;
      }
      await refreshConversationLists();
    }
  } finally {
    stopGenerationRun(runId);
    if (activeGenerationRunId.value === runId) activeGenerationRunId.value = null;
  }
}

async function cancelGenerationRun(runId: number) {
  const run = generationRuns.get(runId);
  if (!run) return;
  run.controller.abort();
  if (run.taskId !== null) {
    try {
      const response = await fetch(`${API_BASE}/api/generate/${run.taskId}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (!response.ok && response.status !== 409) {
        const data = await parseJsonResponse(response);
        throw new Error(readableError(data, "取消生成失败"));
      }
      historyDetailCache.delete(run.taskId);
    } catch (exception) {
      error.value = exception instanceof Error ? exception.message : "取消生成失败";
    }
  }
  stopGenerationRun(runId);
  if (activeGenerationRunId.value === runId) activeGenerationRunId.value = null;
  await refreshConversationLists();
}

function handleGenerateClick() {
  if (activeGenerationRunId.value !== null) {
    void cancelGenerationRun(activeGenerationRunId.value);
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
  if (activeApiKeyConfigId.value !== null) {
    form.append("api_key_config_id", String(activeApiKeyConfigId.value));
  }
  form.append("detail", selectedProviderType.value === "gpt" ? quality.value : "auto");
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
  if (item.url) return resourceUrl(item.url);
  if (!item.base64_data) return "";
  const encoded = item.base64_data.trim();
  return encoded.startsWith("data:") ? encoded : `data:image/png;base64,${encoded}`;
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
function handlePopState() {
  currentView.value = window.location.pathname === "/settings" ? "settings" : "workspace";
  if (currentView.value === "workspace" && activeGenerationRunId.value !== null) {
    restoreGenerationRun(activeGenerationRunId.value);
  }
}
window.addEventListener("popstate", handlePopState);
onUnmounted(() => {
  window.removeEventListener("keydown", handleGlobalKeydown);
  window.removeEventListener("popstate", handlePopState);
  document.removeEventListener("pointerdown", handleDocumentPointerDown);
  for (const run of generationRuns.values()) {
    if (run.timer !== undefined) window.clearInterval(run.timer);
    run.controller.abort();
  }
  generationRuns.clear();
  historyDetailCache.clear();
  for (const image of historyImagePreloads.values()) image.src = "";
  historyImagePreloads.clear();
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
      </div>
    </header>

    <section v-if="currentView === 'settings'" class="settings-page">
      <section class="settings-section settings-interface">
        <div class="settings-heading"><h1>接口配置</h1><div class="settings-heading-actions"><button type="button" class="secondary-action" data-action="add-api-key" @click="beginAddConfig">添加 API Key</button><a class="api-key-link" href="https://sub.beibeihai.xyz/home" target="_blank" rel="noopener noreferrer"><ExternalLink :size="16" />获取 API Key</a></div></div>
        <p>{{ apiKeyConfigured ? '已有可用配置' : '尚未配置 API Key' }}</p>
        <label v-if="legacySettingsMode">API Key<input v-model="settingsApiKey" data-field="api-key" type="password" autocomplete="off" @blur="saveSettingsApiKey" /></label>
        <div v-else class="api-config-list">
          <p v-if="apiKeyConfigs.length === 0" class="api-config-empty">暂无 API Key 配置</p>
          <div v-for="config in apiKeyConfigs" :key="config.id" class="api-config-row" :class="{ active: config.id === activeApiKeyConfigId }">
            <div class="api-config-identity"><strong>{{ config.alias }}</strong><span>{{ config.provider_type === 'gemini' ? 'Gemini' : 'OpenAI' }}</span></div>
            <div class="api-config-actions"><span>{{ config.api_key_configured ? '已配置' : '未配置' }}</span><button type="button" class="secondary-action" data-action="test-api-key" @click="testConfig(config)">{{ testingConfigId === config.id ? '测试中...' : '测试' }}</button><button type="button" class="secondary-action" @click="editConfig(config)">编辑</button><button type="button" class="secondary-action" data-action="delete-api-key" @click="deleteConfig(config)">删除</button></div>
            <div v-if="apiKeyTestResults[config.id]" class="api-config-test-result">
              <p class="api-key-test-message" role="status">{{ apiKeyTestResults[config.id].message }}</p>
              <div v-if="apiKeyTestResults[config.id].models.length" class="api-key-models">
                <button
                  type="button"
                  class="api-key-models-toggle"
                  :aria-expanded="apiKeyModelListExpanded(config.id)"
                  :aria-controls="`api-key-model-list-${config.id}`"
                  @click="toggleApiKeyModelList(config.id)"
                >
                  <strong>可用模型（{{ apiKeyTestResults[config.id].models.length }}）</strong>
                  <ChevronDown v-if="apiKeyModelListExpanded(config.id)" :size="16" />
                  <ChevronRight v-else :size="16" />
                </button>
                <ul v-if="apiKeyModelListExpanded(config.id)" :id="`api-key-model-list-${config.id}`"><li v-for="availableModel in apiKeyTestResults[config.id].models" :key="availableModel.id">{{ availableModel.id }}</li></ul>
              </div>
            </div>
          </div>
          <form v-if="showConfigForm" class="api-config-form" @submit.prevent="saveConfig">
            <label>别名<input v-model="configForm.alias" data-field="config-alias" maxlength="80" required /></label>
            <label>API Key<input v-model="configForm.api_key" data-field="config-api-key" type="password" autocomplete="off" :placeholder="editingConfigId ? '留空以保留现有 Key' : ''" /></label>
            <fieldset class="config-provider-field" data-field="config-provider">
              <legend>类型</legend>
              <div class="config-provider-options" role="group" aria-label="API 类型">
                <button type="button" class="config-provider-option" data-provider-type="gpt" :aria-pressed="configForm.provider_type === 'gpt'" :class="{ active: configForm.provider_type === 'gpt' }" @click="configForm.provider_type = 'gpt'">OpenAI</button>
                <button type="button" class="config-provider-option" data-provider-type="gemini" :aria-pressed="configForm.provider_type === 'gemini'" :class="{ active: configForm.provider_type === 'gemini' }" @click="configForm.provider_type = 'gemini'">Gemini</button>
              </div>
            </fieldset>
            <div class="api-config-form-actions"><button type="submit" class="primary-action">{{ editingConfigId ? '保存修改' : '添加配置' }}</button><button type="button" class="secondary-action" data-action="cancel-api-key-form" @click="resetConfigForm">取消</button><span v-if="settingsConfigError" class="settings-error">{{ settingsConfigError }}</span></div>
          </form>
        </div>
      </section>

      <section class="settings-section community-section settings-community">
        <div class="community-copy"><p class="settings-eyebrow">社区交流</p><h2>加入 GenImage 交流群</h2><p>交流使用技巧，反馈问题，获取最新功能信息。</p><dl><div><dt>群名称</dt><dd>小北AI交流群4</dd></div><div><dt>QQ群号</dt><dd>1043879357</dd></div></dl></div>
        <img class="community-qr" :src="groupQrUrl" alt="GenImage 交流群二维码" />
      </section>

      <section class="settings-section feedback-section settings-feedback">
        <div><h2>留言</h2><p>告诉我们你的建议或遇到的问题。</p></div>
        <form class="feedback-form" @submit.prevent="submitFeedback">
          <label>联系方式<span class="optional-mark">选填</span><input v-model="feedbackContact" data-field="feedback-contact" maxlength="200" placeholder="微信、邮箱或其他联系方式" /></label>
          <label>留言<span class="required-mark">*必填</span><textarea v-model="feedbackMessage" data-field="feedback-message" rows="4" maxlength="2000" placeholder="请输入你的留言" required></textarea></label>
          <div class="feedback-actions"><button type="submit" class="primary-action" :disabled="feedbackSubmitting || !feedbackMessage.trim()">{{ feedbackSubmitting ? '提交中...' : '提交留言' }}</button><p v-if="feedbackStatus" class="feedback-status" role="status">{{ feedbackStatus }}</p></div>
        </form>
      </section>

      <section class="settings-section security-section settings-security">
        <div class="security-heading"><h2>修改密码</h2></div>
        <div class="security-grid">
          <form class="password-form" @submit.prevent="changePassword"><label>旧密码<input v-model="oldPassword" data-field="old-password" type="password" /></label><label>新密码<input v-model="newPassword" data-field="new-password" type="password" /></label><label>确认新密码<input v-model="newPasswordConfirmation" data-field="new-password-confirmation" type="password" /></label><p v-if="authError" class="error-message">{{ authError }}</p><button type="submit" class="primary-action" data-action="change-password" @click.prevent="changePassword">修改密码</button></form>
          <div class="logout-panel"><h3>退出登录</h3><p>结束当前账号会话，返回登录页面。</p><button type="button" class="secondary-action logout-action" @click="logout">退出登录</button></div>
        </div>
      </section>
      <ConfirmDialog
        :open="confirmAction === 'api-key'"
        title="删除 API Key 配置"
        :message="`确认删除 API Key 配置“${confirmConfig?.alias}”吗？`"
        :busy="actionBusy"
        @confirm="confirmDeletion"
        @cancel="cancelConfirm"
      />
    </section>
    <template v-else>
    <div class="studio-grid">
      <ProjectSidebar
        :projects="projects"
        :selected-project-id="selectedProjectId"
        :running-generations="runningGenerations"
        :active-generation-run-id="activeGenerationRunId"
        :loading="!projects.length && !projectError"
        @select-project="selectProject"
        @new-conversation="startNewConversation"
        @create-project="createProject"
        @rename-project="renameProject"
        @delete-project="deleteProject"
        @delete-history="deleteHistory"
        @open-history="openHistory"
        @open-generation="restoreGenerationRun"
        @prefetch-history="prefetchHistory"
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
            <p v-if="error" class="error-message generation-error">{{ error }}</p>
            <template v-else>
              <h3>{{ activeGenerationElapsedMs !== null ? `等待生成结果 ${formatDuration(activeGenerationElapsedMs)}` : "等待生成结果" }}</h3>
              <p>配置参数并在下方输入提示词。</p>
            </template>
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
                <div class="parameter-control"><button type="button" class="parameter-trigger" data-parameter-trigger="apiKey" :aria-expanded="openParameterMenu === 'apiKey'" @click="toggleParameterMenu('apiKey')">API Key <strong>{{ selectedApiKeyLabel }}</strong></button><div v-if="openParameterMenu === 'apiKey'" class="parameter-menu" data-parameter-menu="apiKey"><button v-for="option in apiKeyConfigs" :key="option.id" type="button" class="parameter-option" :class="{ 'is-selected': option.id === activeApiKeyConfigId }" :data-parameter-option="option.alias" @click="selectApiKeyConfig(option)"><span>{{ option.alias }}</span><Check v-if="option.id === activeApiKeyConfigId" :size="15" /></button></div></div>
                <div class="parameter-control"><button type="button" class="parameter-trigger" data-parameter-trigger="model" :aria-expanded="openParameterMenu === 'model'" @click="toggleParameterMenu('model')">模型名称 <strong>{{ selectedModelLabel }}</strong></button><div v-if="openParameterMenu === 'model'" class="parameter-menu" data-parameter-menu="model"><button v-for="option in modelOptions" :key="option.id" type="button" class="parameter-option" :class="{ 'is-selected': option.id === model }" :data-parameter-option="option.id" @click="selectModel(option.id)"><span>{{ option.id }}</span><Check v-if="option.id === model" :size="15" /></button><span v-if="loadingConfigModels" class="parameter-option-description">获取模型列表中...</span></div></div>
                <div class="parameter-control"><button type="button" class="parameter-trigger" data-parameter-trigger="size" :aria-expanded="openParameterMenu === 'size'" @click="toggleParameterMenu('size')">图片比例 <strong>{{ SIZE_OPTIONS.find((option) => option.value === size)?.label }}</strong></button><div v-if="openParameterMenu === 'size'" class="parameter-menu" data-parameter-menu="size"><button v-for="option in SIZE_OPTIONS" :key="option.value" type="button" class="parameter-option" :class="{ 'is-selected': option.value === size }" :data-parameter-option="option.value" @click="selectSize(option.value)"><span><strong>{{ option.label }}</strong></span><Check v-if="option.value === size" :size="15" /></button></div></div>
                <div class="parameter-control"><button type="button" class="parameter-trigger" data-parameter-trigger="resolution" :aria-expanded="openParameterMenu === 'resolution'" @click="toggleParameterMenu('resolution')">分辨率 <strong>{{ resolution }}</strong></button><div v-if="openParameterMenu === 'resolution'" class="parameter-menu" data-parameter-menu="resolution"><button v-for="option in RESOLUTION_OPTIONS" :key="option" type="button" class="parameter-option" :class="{ 'is-selected': option === resolution }" :data-parameter-option="option" @click="selectResolution(option)"><span>{{ option }}</span><Check v-if="option === resolution" :size="15" /></button></div></div>
                <div v-if="selectedProviderType === 'gpt'" class="parameter-control"><button type="button" class="parameter-trigger" data-parameter-trigger="quality" :aria-expanded="openParameterMenu === 'quality'" @click="toggleParameterMenu('quality')">生成质量 <strong>{{ QUALITY_OPTIONS.find((option) => option.value === quality)?.label }}</strong></button><div v-if="openParameterMenu === 'quality'" class="parameter-menu" data-parameter-menu="quality"><button v-for="option in QUALITY_OPTIONS" :key="option.value" type="button" class="parameter-option" :class="{ 'is-selected': option.value === quality }" :data-parameter-option="option.value" @click="selectQuality(option.value)"><span>{{ option.label }}</span><Check v-if="option.value === quality" :size="15" /></button></div></div>
                <div class="parameter-control"><button type="button" class="parameter-trigger" data-parameter-trigger="count" :aria-expanded="openParameterMenu === 'count'" @click="toggleParameterMenu('count')">生成数量 <strong>{{ imageCount }} 张</strong></button><div v-if="openParameterMenu === 'count'" class="parameter-menu" data-parameter-menu="count"><button v-for="option in IMAGE_COUNT_OPTIONS" :key="option" type="button" class="parameter-option" :class="{ 'is-selected': option === imageCount }" :data-parameter-option="option" @click="selectImageCount(option)"><span>{{ option }} 张</span><Check v-if="option === imageCount" :size="15" /></button></div></div>
              </div>
            </div>
            <div class="composer-actions"><button type="button" class="secondary-action analyze-action" :disabled="!canAnalyze" @click="analyzeImage"><LoaderCircle v-if="busy === 'analyze'" class="spin" :size="17" /><ImagePlus v-else :size="17" />分析图片</button><button type="button" class="primary-action" :class="{ 'cancel-action': activeGenerationRun }" :disabled="busy === 'analyze'" @click="handleGenerateClick"><X v-if="activeGenerationRun" :size="17" /><LoaderCircle v-else-if="busy === 'analyze'" class="spin" :size="17" /><Sparkles v-else :size="17" />{{ activeGenerationRun ? "取消生成" : "生成图片" }}</button></div>
          </div>
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
      :title="confirmAction === 'project' ? '删除项目' : confirmAction === 'history' ? '删除历史记录' : '删除 API Key 配置'"
      :message="confirmAction === 'project' ? `确认删除项目“${confirmProject?.name}”及其 ${confirmProject?.history_count ?? 0} 条历史记录吗？` : confirmAction === 'history' ? `确认删除选中的 ${confirmHistoryIds.length} 条历史记录吗？` : `确认删除 API Key 配置“${confirmConfig?.alias}”吗？`"
      :busy="actionBusy"
      @confirm="confirmDeletion"
      @cancel="cancelConfirm"
    />
    </template>
    </template>
  </main>
</template>
