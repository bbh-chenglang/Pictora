<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { Download, ImagePlus, LoaderCircle, Sparkles, Upload, X } from "lucide-vue-next";

type Provider = { id: string; label: string; models: string[] };
type ImageResult = { url?: string | null; base64_data?: string | null; revised_prompt?: string | null; generation_time_ms?: number | null };

const providers = ref<Provider[]>([]);
const provider = ref("");
const model = ref("");
const prompt = ref("");
const batchPrompts = ref("");
const imageCount = ref(1);
const detail = ref("auto");
const imageFile = ref<File | null>(null);
const previewUrl = ref("");
const generated = ref<ImageResult[]>([]);
const analysis = ref("");
const busy = ref<"generate" | "analyze" | "">("");
const error = ref("");
const generationElapsedMs = ref(0);
let generationTimer: number | undefined;
let generationStartedAt = 0;
let generationController: AbortController | null = null;

const selectedProvider = computed(() => providers.value.find((item) => item.id === provider.value));
const canGenerate = computed(() => Boolean(prompt.value.trim() || batchPrompts.value.trim()) && !busy.value);
const canAnalyze = computed(() => Boolean(imageFile.value) && !busy.value);
const API_BASE = "http://localhost:8002";

function readableError(data: any, fallback: string) {
  const messages: Record<string, string> = {
    provider_auth: "服务商鉴权失败，请检查 API Key",
    provider_timeout: "服务商请求超时，请稍后重试",
    provider_request: "服务商请求失败",
    provider_not_found: "找不到所选服务商",
    invalid_image: "图片格式或内容无效",
  };
  return messages[data?.error?.code] ?? data?.error?.message ?? fallback;
}

async function loadProviders() {
  const response = await fetch(`${API_BASE}/api/providers`);
  const data = await response.json();
  providers.value = data.providers ?? [];
  provider.value = providers.value[0]?.id ?? "";
  model.value = providers.value[0]?.models[0] ?? "";
}

function selectProvider() {
  model.value = selectedProvider.value?.models[0] ?? "";
}

function setFile(file?: File) {
  if (!file) return;
  imageFile.value = file;
  previewUrl.value = URL.createObjectURL(file);
  error.value = "";
}

function clearFile() {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value);
  imageFile.value = null;
  previewUrl.value = "";
}

function formatDuration(milliseconds?: number | null) {
  if (milliseconds == null) return "计时不可用";
  return milliseconds < 1000 ? `${milliseconds} ms` : `${(milliseconds / 1000).toFixed(1)} 秒`;
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
  generationElapsedMs.value = generationStartedAt ? performance.now() - generationStartedAt : 0;
}

async function generateImage() {
  if (busy.value === "generate") return;
  busy.value = "generate"; error.value = ""; analysis.value = ""; generated.value = []; startGenerationTimer();
  const prompts = batchPrompts.value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
  const controller = new AbortController();
  generationController = controller;
  try {
    const requestPrompt = prompt.value.trim() || prompts[0] || "请生成一张图片";
    const response = await fetch(`${API_BASE}/api/generate`, { method: "POST", headers: { "Content-Type": "application/json" }, signal: controller.signal, body: JSON.stringify({ provider: provider.value, model: model.value, prompt: requestPrompt, prompts: prompts.length ? prompts : null, count: imageCount.value, detail: detail.value }) });
    const data = await response.json();
    if (!response.ok) throw new Error(readableError(data, "生成失败"));
    generated.value = data.images ?? [];
  } catch (exception) {
    if (!(exception instanceof DOMException && exception.name === "AbortError")) {
      error.value = exception instanceof Error ? exception.message : "生成失败";
    }
  } finally {
    if (generationController === controller) generationController = null;
    stopGenerationTimer(); busy.value = "";
  }
}

function cancelGeneration() {
  generationController?.abort();
}

async function analyzeImage() {
  if (!imageFile.value) return;
  busy.value = "analyze"; error.value = ""; generated.value = [];
  const form = new FormData();
  form.append("provider", provider.value); form.append("model", model.value); form.append("prompt", prompt.value || "请描述这张图片"); form.append("detail", detail.value); form.append("image", imageFile.value);
  try {
    const response = await fetch(`${API_BASE}/api/analyze`, { method: "POST", body: form });
    const data = await response.json();
    if (!response.ok) throw new Error(readableError(data, "分析失败"));
    analysis.value = data.text ?? "";
  } catch (exception) { error.value = exception instanceof Error ? exception.message : "分析失败"; }
  finally { busy.value = ""; }
}

function imageSource(item: ImageResult) {
  return item.url || (item.base64_data ? `data:image/png;base64,${item.base64_data}` : "");
}

onMounted(() => loadProviders().catch(() => { error.value = "无法加载服务商，请先启动后端"; }));
onUnmounted(stopGenerationTimer);
</script>

<template>
  <main class="studio-shell">
    <header class="topbar"><div class="brand"><span class="brand-mark">G</span><div><strong>GenImage</strong><small>艺术实验室</small></div></div><span class="status-dot">● 接口已就绪</span></header>
    <div class="studio-grid">
      <aside class="control-panel">
        <div class="eyebrow">创作 / 观察</div><h1>创造一些<br /><em>值得观看的东西。</em></h1>
        <label>提供商<select v-model="provider" @change="selectProvider"><option v-if="!providers.length" value="">尚未配置服务商</option><option v-for="item in providers" :key="item.id" :value="item.id">{{ item.label }}</option></select></label>
        <label>模型<select v-model="model"><option v-for="item in selectedProvider?.models ?? []" :key="item" :value="item">{{ item }}</option></select></label>
        <label>提示词<textarea v-model="prompt" placeholder="描述一个场景、一种质感，或一个不可能存在的物体..."></textarea></label>
        <label>批量提示词（每行一条，可选）<textarea v-model="batchPrompts" class="batch-input" placeholder="每行输入一条提示词，可一次并发生成多组图片"></textarea></label>
        <label>细节级别<select v-model="detail"><option value="auto">自动</option><option value="low">低</option><option value="high">高</option><option value="original">原始</option></select></label>
        <label>每条生成数量<input v-model.number="imageCount" type="number" min="1" max="4" /></label>
        <div class="upload-zone" @dragover.prevent @drop.prevent="setFile(($event as DragEvent).dataTransfer?.files[0])"><input id="image-input" type="file" accept="image/png,image/jpeg,image/webp,image/gif" @change="setFile(($event.target as HTMLInputElement).files?.[0])" /><label for="image-input"><Upload :size="18" /><span>{{ imageFile ? imageFile.name : "拖入参考图片" }}</span><small>支持 PNG、JPG、WEBP 或 GIF</small></label></div>
        <div v-if="previewUrl" class="file-chip"><img :src="previewUrl" alt="Reference preview" /><span>{{ imageFile?.name }}</span><button aria-label="Remove image" @click="clearFile"><X :size="15" /></button></div>
        <div class="action-row"><button class="primary-action" :class="{ 'cancel-action': busy === 'generate' }" :disabled="busy === 'generate' ? false : !canGenerate" @click="busy === 'generate' ? cancelGeneration() : generateImage"><X v-if="busy === 'generate'" :size="17" /><LoaderCircle v-else-if="busy === 'analyze'" class="spin" :size="17" /><Sparkles v-else :size="17" />{{ busy === 'generate' ? '取消生成' : '生成图片' }}</button><button class="secondary-action" :disabled="!canAnalyze" @click="analyzeImage"><LoaderCircle v-if="busy === 'analyze'" class="spin" /><ImagePlus v-else :size="17" />分析图片</button></div>
        <p v-if="error" class="error-message">{{ error }}</p>
      </aside>
      <section class="result-panel"><div class="result-heading"><div><div class="eyebrow">作品墙</div><h2>你的视觉研究</h2></div><span v-if="busy === 'generate'" class="working">并发生成中 {{ formatDuration(generationElapsedMs) }}</span><span v-else-if="busy" class="working">处理中...</span></div>
        <div v-if="analysis" class="analysis-note"><div class="note-label">图片解读</div><p>{{ analysis }}</p></div>
        <div v-if="generated.length" class="image-grid"><article v-for="(item, index) in generated" :key="index" class="image-card"><div class="image-frame"><img v-if="imageSource(item)" :src="imageSource(item)" :alt="`生成图片 ${index + 1}`" /><div v-else class="missing-image">图片数据不可用</div><a v-if="imageSource(item)" class="download" :href="imageSource(item)" download="genimage-study.png" aria-label="下载图片"><Download :size="16" /></a></div><div class="image-meta"><span>图片 {{ index + 1 }}</span><strong>{{ formatDuration(item.generation_time_ms) }}</strong></div></article></div>
        <div v-else-if="!analysis" class="empty-wall"><div class="empty-shape"><Sparkles :size="24" /></div><h3>作品墙正在等待。</h3><p>输入提示词或添加参考图片，开始你的视觉研究。</p></div>
      </section>
    </div>
  </main>
</template>
