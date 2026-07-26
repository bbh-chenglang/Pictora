<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import {
  ChevronDown,
  Download,
  ExternalLink,
  History,
  ImagePlus,
  LoaderCircle,
  Sparkles,
  Upload,
  X,
} from "lucide-vue-next";

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
  { label: "16:9", value: "1536x864" },
  { label: "9:16", value: "864x1536" },
  { label: "3:4", value: "1152x1536" },
  { label: "4:3", value: "1536x1152" },
  { label: "1:1", value: "1024x1024" },
] as const;
const DEFAULT_SIZE = SIZE_OPTIONS[0].value;
const PANEL_MIN_WIDTH = 280;
const PANEL_MAX_WIDTH = 480;

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
const apiKey = ref("");
const apiKeyConfigured = ref(false);
const savingSettings = ref(false);
const history = ref<HistorySummary[]>([]);
const historyError = ref("");
const activeHistoryId = ref<number | null>(null);
const generationElapsedMs = ref(0);
const lightboxUrl = ref("");
const historyOpen = ref(false);
const sidebarWidth = ref(320);
const resizingSidebar = ref(false);
let generationTimer: number | undefined;
let generationStartedAt = 0;
let generationController: AbortController | null = null;
let settingsSaveQueue: Promise<void> = Promise.resolve();
let pendingSettingsSaves = 0;

const canAnalyze = computed(() => Boolean(imageFile.value) && !busy.value);
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

function resourceUrl(path: string) {
  return /^https?:\/\//.test(path) ? path : `${API_BASE}${path}`;
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
      .map((image) => ({ url: resourceUrl(image.url) }));

    const reference = data.images.find((image) => image.role === "reference");
    if (previewUrl.value.startsWith("blob:")) URL.revokeObjectURL(previewUrl.value);
    imageFile.value = null;
    previewUrl.value = reference ? resourceUrl(reference.url) : "";
    historyOpen.value = false;
  } catch (exception) {
    error.value =
      exception instanceof Error ? exception.message : "无法加载历史详情";
  }
}

async function applyRuntimeSettings(includeApiKey = false) {
  const submittedModel = model.value.trim();
  const submittedApiKey = includeApiKey ? apiKey.value.trim() || null : null;
  if (!submittedModel) return;

  pendingSettingsSaves += 1;
  savingSettings.value = true;
  error.value = "";
  const save = settingsSaveQueue.then(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: submittedModel,
          api_key: submittedApiKey,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(readableError(data, "配置应用失败"));
      model.value = (MODEL_OPTIONS as readonly string[]).includes(data.model)
        ? data.model
        : DEFAULT_MODEL;
      apiKeyConfigured.value = Boolean(data.api_key_configured);
      if (includeApiKey && apiKey.value.trim() === submittedApiKey) apiKey.value = "";
      await loadProviders();
    } catch (exception) {
      error.value = exception instanceof Error ? exception.message : "配置应用失败";
    }
  });
  settingsSaveQueue = save;
  await save.finally(() => {
    pendingSettingsSaves -= 1;
    savingSettings.value = pendingSettingsSaves > 0;
  });
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

function startGenerationTimer() {
  generationStartedAt = performance.now();
  generationElapsedMs.value = 0;
  generationTimer = window.setInterval(() => {
    generationElapsedMs.value = performance.now() - generationStartedAt;
  }, 100);
}

function stopGenerationTimer() {
  if (generationTimer !== undefined) window.clearInterval(generationTimer);
  generationTimer = undefined;
  generationElapsedMs.value = generationStartedAt
    ? performance.now() - generationStartedAt
    : 0;
}

async function generateImage() {
  if (busy.value === "generate") return;
  if (!provider.value || !model.value) {
    error.value = "请先配置 API Key 和模型名称";
    return;
  }
  busy.value = "generate";
  error.value = "";
  analysis.value = "";
  generated.value = [];
  activeHistoryId.value = null;
  startGenerationTimer();
  const prompts = batchPrompts.value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
  const controller = new AbortController();
  generationController = controller;
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
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(readableError(data, "生成失败"));
    generated.value = data.images ?? [];
    await loadHistory();
  } catch (exception) {
    if (!(exception instanceof DOMException && exception.name === "AbortError")) {
      error.value = exception instanceof Error ? exception.message : "生成失败";
      await loadHistory();
    }
  } finally {
    if (generationController === controller) generationController = null;
    stopGenerationTimer();
    busy.value = "";
  }
}

function handleGenerateClick() {
  if (busy.value === "generate") generationController?.abort();
  else void generateImage();
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
  form.append("image", imageFile.value);
  try {
    const response = await fetch(`${API_BASE}/api/analyze`, {
      method: "POST",
      body: form,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(readableError(data, "分析失败"));
    analysis.value = data.text ?? "";
    await loadHistory();
  } catch (exception) {
    error.value = exception instanceof Error ? exception.message : "分析失败";
    await loadHistory();
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

function closeHistory() {
  historyOpen.value = false;
}

function updateSidebarWidth(clientX: number) {
  const viewportMax = Math.max(PANEL_MIN_WIDTH, window.innerWidth - 560);
  sidebarWidth.value = Math.min(
    PANEL_MAX_WIDTH,
    viewportMax,
    Math.max(PANEL_MIN_WIDTH, clientX),
  );
}

function handleSidebarPointerMove(event: PointerEvent) {
  if (resizingSidebar.value) updateSidebarWidth(event.clientX);
}

function stopSidebarResize() {
  resizingSidebar.value = false;
  window.removeEventListener("pointermove", handleSidebarPointerMove);
  window.removeEventListener("pointerup", stopSidebarResize);
}

function startSidebarResize(event: PointerEvent) {
  resizingSidebar.value = true;
  updateSidebarWidth(event.clientX);
  window.addEventListener("pointermove", handleSidebarPointerMove);
  window.addEventListener("pointerup", stopSidebarResize);
}

function handleSidebarKeydown(event: KeyboardEvent) {
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
  event.preventDefault();
  updateSidebarWidth(
    sidebarWidth.value + (event.key === "ArrowLeft" ? -16 : 16),
  );
}

function handleGlobalKeydown(event: KeyboardEvent) {
  if (event.key !== "Escape") return;
  if (lightboxUrl.value) closeLightbox();
  else closeHistory();
}

onMounted(async () => {
  window.addEventListener("keydown", handleGlobalKeydown);
  try {
    await Promise.all([loadRuntimeSettings(), loadProviders(), loadHistory()]);
  } catch {
    error.value = "无法加载服务商，请先启动后端";
  }
});
onUnmounted(() => {
  window.removeEventListener("keydown", handleGlobalKeydown);
  stopSidebarResize();
  stopGenerationTimer();
  if (previewUrl.value.startsWith("blob:")) URL.revokeObjectURL(previewUrl.value);
});
</script>

<template>
  <main class="studio-shell">
    <header class="topbar">
      <div class="brand">
        <span class="brand-mark">G</span>
        <div><strong>GenImage</strong><small>图像工作台</small></div>
      </div>
      <div class="topbar-actions">
        <span class="status-indicator" :class="{ configured: apiKeyConfigured }">
          <i></i>{{ apiKeyConfigured ? "服务已配置" : "等待 API Key" }}
        </span>
        <button type="button" class="history-trigger" @click="historyOpen = true">
          <History :size="17" /><span>历史记录</span><strong>{{ history.length }}</strong>
        </button>
      </div>
    </header>

    <div class="studio-grid" :class="{ resizing: resizingSidebar }" :style="{ '--sidebar-width': `${sidebarWidth}px` }">
      <aside class="control-panel">
        <div class="panel-title">
          <div><span>生成设置</span><h1>图片参数</h1></div>
          <strong>{{ imageCount }} 张</strong>
        </div>

        <details class="connection-section">
          <summary><span>接口配置</span><small>{{ savingSettings ? "保存中" : apiKeyConfigured ? "已配置" : "未配置" }}</small><ChevronDown :size="16" /></summary>
          <div class="connection-body">
            <label>API Key<input v-model="apiKey" type="password" autocomplete="off" :placeholder="apiKeyConfigured ? '留空则保持当前 Key' : '输入 API Key'" @change="applyRuntimeSettings(true)" /></label>
            <a class="api-key-link" href="https://sub.beibeihai.xyz/home" target="_blank" rel="noopener noreferrer"><ExternalLink :size="16" />获取 API Key</a>
          </div>
        </details>

        <section class="image-parameter-section">
          <label>模型名称<select v-model="model" class="model-select" @change="applyRuntimeSettings(false)"><option v-for="option in MODEL_OPTIONS" :key="option" :value="option">{{ option }}</option></select></label>
          <label>图片尺寸<select v-model="size" class="size-select"><option v-for="option in SIZE_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
          <div class="parameter-grid">
            <label>细节级别<select v-model="detail"><option value="auto">自动</option><option value="low">低</option><option value="high">高</option><option value="original">原始</option></select></label>
            <label>生成数量<input v-model.number="imageCount" type="number" min="1" max="4" /></label>
          </div>
        </section>

      </aside>

      <div class="panel-resizer" role="separator" aria-label="调整参数栏宽度" aria-orientation="vertical" :aria-valuenow="sidebarWidth" :aria-valuemin="PANEL_MIN_WIDTH" :aria-valuemax="PANEL_MAX_WIDTH" tabindex="0" @pointerdown="startSidebarResize" @keydown="handleSidebarKeydown"></div>

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
            <h3>{{ busy === "generate" ? `等待生成结果 ${formatDuration(generationElapsedMs)}` : "等待生成结果" }}</h3>
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
            <button type="button" class="secondary-action" :disabled="!canAnalyze" @click="analyzeImage"><LoaderCircle v-if="busy === 'analyze'" class="spin" :size="17" /><ImagePlus v-else :size="17" />分析图片</button>
          </div>

          <div class="prompt-row">
            <label>提示词<textarea v-model="prompt" placeholder="描述主体、环境、构图、镜头、光线、材质与风格..."></textarea></label>
            <button type="button" class="primary-action" :class="{ 'cancel-action': busy === 'generate' }" :disabled="busy === 'analyze'" @click="handleGenerateClick"><X v-if="busy === 'generate'" :size="17" /><LoaderCircle v-else-if="busy === 'analyze'" class="spin" :size="17" /><Sparkles v-else :size="17" />{{ busy === "generate" ? "取消生成" : "生成图片" }}</button>
          </div>
          <p v-if="error" class="error-message">{{ error }}</p>
        </section>
      </section>
    </div>

    <Transition name="drawer">
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
    </Transition>

    <div v-if="lightboxUrl" class="image-lightbox" role="dialog" aria-modal="true" aria-label="生成图片全屏预览" @click.self="closeLightbox">
      <button type="button" class="lightbox-close" aria-label="关闭全屏预览" title="关闭" @click="closeLightbox"><X :size="22" /></button>
      <img :src="lightboxUrl" alt="生成图片全屏预览" />
    </div>
  </main>
</template>
