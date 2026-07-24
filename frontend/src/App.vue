<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Download, ImagePlus, LoaderCircle, Sparkles, Upload, X } from "lucide-vue-next";

type Provider = { id: string; label: string; models: string[] };
type ImageResult = { url?: string | null; base64_data?: string | null; revised_prompt?: string | null };

const providers = ref<Provider[]>([]);
const provider = ref("");
const model = ref("");
const prompt = ref("");
const detail = ref("auto");
const imageFile = ref<File | null>(null);
const previewUrl = ref("");
const generated = ref<ImageResult[]>([]);
const analysis = ref("");
const busy = ref<"generate" | "analyze" | "">("");
const error = ref("");

const selectedProvider = computed(() => providers.value.find((item) => item.id === provider.value));
const canGenerate = computed(() => prompt.value.trim().length > 0 && !busy.value);
const canAnalyze = computed(() => Boolean(imageFile.value) && !busy.value);
const API_BASE = "http://localhost:8002";

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

async function generateImage() {
  busy.value = "generate"; error.value = ""; analysis.value = "";
  try {
    const response = await fetch(`${API_BASE}/api/generate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ provider: provider.value, model: model.value, prompt: prompt.value, detail: detail.value }) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error?.message ?? "生成失败");
    generated.value = data.images ?? [];
  } catch (exception) { error.value = exception instanceof Error ? exception.message : "生成失败"; }
  finally { busy.value = ""; }
}

async function analyzeImage() {
  if (!imageFile.value) return;
  busy.value = "analyze"; error.value = ""; generated.value = [];
  const form = new FormData();
  form.append("provider", provider.value); form.append("model", model.value); form.append("prompt", prompt.value || "Describe this image"); form.append("detail", detail.value); form.append("image", imageFile.value);
  try {
    const response = await fetch(`${API_BASE}/api/analyze`, { method: "POST", body: form });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error?.message ?? "分析失败");
    analysis.value = data.text ?? "";
  } catch (exception) { error.value = exception instanceof Error ? exception.message : "分析失败"; }
  finally { busy.value = ""; }
}

function imageSource(item: ImageResult) {
  return item.url || (item.base64_data ? `data:image/png;base64,${item.base64_data}` : "");
}

onMounted(() => loadProviders().catch(() => { error.value = "无法加载 Provider，请先启动后端"; }));
</script>

<template>
  <main class="studio-shell">
    <header class="topbar"><div class="brand"><span class="brand-mark">G</span><div><strong>GenImage</strong><small>ART LABORATORY</small></div></div><span class="status-dot">● API READY</span></header>
    <div class="studio-grid">
      <aside class="control-panel">
        <div class="eyebrow">CREATE / OBSERVE</div><h1>Make something<br /><em>worth seeing.</em></h1>
        <label>Provider<select v-model="provider" @change="selectProvider"><option v-if="!providers.length" value="">No provider configured</option><option v-for="item in providers" :key="item.id" :value="item.id">{{ item.label }}</option></select></label>
        <label>Model<select v-model="model"><option v-for="item in selectedProvider?.models ?? []" :key="item" :value="item">{{ item }}</option></select></label>
        <label>Prompt<textarea v-model="prompt" placeholder="Describe a scene, a texture, an impossible object..."></textarea></label>
        <label>Detail<select v-model="detail"><option value="auto">Auto</option><option value="low">Low</option><option value="high">High</option><option value="original">Original</option></select></label>
        <div class="upload-zone" @dragover.prevent @drop.prevent="setFile(($event as DragEvent).dataTransfer?.files[0])"><input id="image-input" type="file" accept="image/png,image/jpeg,image/webp,image/gif" @change="setFile(($event.target as HTMLInputElement).files?.[0])" /><label for="image-input"><Upload :size="18" /><span>{{ imageFile ? imageFile.name : "Drop a reference image" }}</span><small>PNG, JPG, WEBP or GIF</small></label></div>
        <div v-if="previewUrl" class="file-chip"><img :src="previewUrl" alt="Reference preview" /><span>{{ imageFile?.name }}</span><button aria-label="Remove image" @click="clearFile"><X :size="15" /></button></div>
        <div class="action-row"><button class="primary-action" :disabled="!canGenerate" @click="generateImage"><LoaderCircle v-if="busy === 'generate'" class="spin" :size="17" /><Sparkles v-else :size="17" />Generate</button><button class="secondary-action" :disabled="!canAnalyze" @click="analyzeImage"><LoaderCircle v-if="busy === 'analyze'" class="spin" /><ImagePlus v-else :size="17" />Analyze</button></div>
        <p v-if="error" class="error-message">{{ error }}</p>
      </aside>
      <section class="result-panel"><div class="result-heading"><div><div class="eyebrow">THE WORK WALL</div><h2>Your visual studies</h2></div><span v-if="busy" class="working">Working...</span></div>
        <div v-if="analysis" class="analysis-note"><div class="note-label">IMAGE READING</div><p>{{ analysis }}</p></div>
        <div v-if="generated.length" class="image-grid"><article v-for="(item, index) in generated" :key="index" class="image-card"><img v-if="imageSource(item)" :src="imageSource(item)" :alt="`Generated study ${index + 1}`" /><div v-else class="missing-image">Image data unavailable</div><a v-if="imageSource(item)" class="download" :href="imageSource(item)" download="genimage-study.png" aria-label="Download image"><Download :size="16" /></a></article></div>
        <div v-else-if="!analysis" class="empty-wall"><div class="empty-shape"><Sparkles :size="24" /></div><h3>The wall is waiting.</h3><p>Write a prompt or add a reference image to begin a study.</p></div>
      </section>
    </div>
  </main>
</template>
