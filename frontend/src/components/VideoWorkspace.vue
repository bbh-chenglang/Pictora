<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from "vue";
import { ArrowUpRight, Check, CircleAlert, Film, ImagePlus, Info, Link2, Play, RefreshCw, ShieldCheck, SlidersHorizontal, Sparkles, Upload, X } from "lucide-vue-next";
import VideoTaskCard from "./VideoTaskCard.vue";
import ConfirmDialog from "./ConfirmDialog.vue";
import { activeVideoStatuses, VideoApiError, jsonBody, materialIssue, materialLabels, videoJson, videoValidation, type ApiFetch, type MaterialType, type VideoFeatures, type VideoKey, type VideoMaterial, type VideoModel, type VideoTask, type VideoRequestState } from "../video";
const props = defineProps<{ active: boolean; account: string; projectId: number | null; selectedTaskId: number | null; apiFetch: ApiFetch; apiBase: string; imageHistoryIds?: number[] }>();
const emit = defineEmits<{ changed: []; select: [id: number | null]; settings: [] }>();
const accountId = props.account;
const models = ref<VideoModel[]>([]), features = ref<VideoFeatures | null>(null), keys = ref<VideoKey[]>([]), activeKeyId = ref<number | null>(null);
const modelId = ref("seedance-2.0-933-720P（秒）"), keyId = ref<number | null>(null), prompt = ref(""), duration = ref(5), resolution = ref("720p"), ratio = ref("16:9");
const materials = ref<VideoMaterial[]>([]), tasks = ref<VideoTask[]>([]), error = ref(""), note = ref(""), loading = ref(false), busy = ref(false);
const kind = ref<MaterialType>("image"), sourceURL = ref(""), sourceName = ref(""), pickerOpen = ref(false), imageChoices = ref<Array<{ history_id: number; id: number; url: string; filename: string | null }>>([]);
const pending = ref<{ fingerprint: string; requestId: string } | null>(null), confirm = ref<{ task: VideoTask; action: string; upstreamId?: string } | null>(null);
const promptInput = ref<HTMLTextAreaElement | null>(null);
let started = false, disposed = false, poll: ReturnType<typeof setTimeout> | undefined, contextVersion = 0, configurationVersion = 0;
const selectedModel = computed(() => models.value.find(m => m.id === modelId.value));
const durations = computed(() => selectedModel.value?.durations_by_resolution[resolution.value] || []);
const issues = computed(() => videoValidation(selectedModel.value, duration.value, resolution.value, ratio.value, materials.value));
const allowedKinds = computed(() => (["image", "video", "audio"] as MaterialType[]).filter(k => (selectedModel.value?.reference_limits[k] || 0) > 0));
const canSubmit = computed(() => !busy.value && !!props.projectId && !!keyId.value && !!prompt.value.trim() && features.value?.api_ready !== false && features.value?.storage_ready && features.value?.media_tools_ready && !issues.value.length);
const visibleTasks = computed(() => props.selectedTaskId ? tasks.value.filter(t => t.id === props.selectedTaskId) : tasks.value);
function draftKey(projectId = props.projectId) { return "pictora.video.draft:" + accountId + ":" + projectId; }
function saveDraft() {
  if (!props.projectId || !started) return;
  try { localStorage.setItem(draftKey(), JSON.stringify({ modelId: modelId.value, keyId: keyId.value, prompt: prompt.value, duration: duration.value, resolution: resolution.value, ratio: ratio.value, materials: materials.value, pending: pending.value })); } catch { /* Private browsing may disable storage. */ }
}
function hasDraft() { try { return !!localStorage.getItem(draftKey()); } catch { return false; } }
function restoreDraft() {
  keyId.value = activeKeyId.value ?? keys.value[0]?.id ?? null; modelId.value = keys.value.find(k => k.id === keyId.value)?.model || "seedance-2.0-933-720P（秒）"; prompt.value = ""; materials.value = []; duration.value = 5; resolution.value = "720p"; ratio.value = "16:9"; pending.value = null;
  try {
    const raw = localStorage.getItem(draftKey()); if (!raw) return;
    const d = JSON.parse(raw);
    if (typeof d.modelId === "string") modelId.value = d.modelId;
    if (typeof d.prompt === "string") prompt.value = d.prompt;
    if (typeof d.keyId === "number") keyId.value = d.keyId;
    if (typeof d.duration === "number") duration.value = d.duration;
    if (typeof d.resolution === "string") resolution.value = d.resolution;
    if (typeof d.ratio === "string") ratio.value = d.ratio;
    if (Array.isArray(d.materials)) materials.value = d.materials.filter((m: VideoMaterial) => m && ["image", "video", "audio"].includes(m.type) && typeof m.name === "string" && (m.asset_id || m.url));
    if (d.pending && typeof d.pending.requestId === "string" && typeof d.pending.fingerprint === "string") pending.value = d.pending;
  } catch { /* Bad draft is ignored rather than blocking the workbench. */ }
}
function applyDefaults() { const m = selectedModel.value; if (!m) return; duration.value = m.default_duration; resolution.value = m.default_resolution; ratio.value = m.default_ratio; if (!allowedKinds.value.includes(kind.value)) kind.value = allowedKinds.value[0] || "image"; }
function changeModel() { applyDefaults(); note.value = ""; }
function changeKey() { const key = keys.value.find(k => k.id === keyId.value); if (key) modelId.value = key.model; changeModel(); }
function changeResolution() { if (!durations.value.includes(duration.value)) duration.value = durations.value.includes(selectedModel.value?.default_duration || 0) ? selectedModel.value!.default_duration : durations.value[0] || 5; }
async function loadConfiguration(force = false) {
  const version = ++configurationVersion;
  const [catalog, configs] = await Promise.all([
    videoJson<{ models: VideoModel[]; features: VideoFeatures }>(props.apiFetch, props.apiBase, "/api/videos/models" + (force ? "?refresh=true" : "")),
    videoJson<{ configs: VideoKey[]; active_config_id: number | null }>(props.apiFetch, props.apiBase, "/api/settings/video-api-keys"),
  ]);
  if (disposed || version !== configurationVersion) return;
  models.value = catalog.models; features.value = catalog.features; keys.value = configs.configs; activeKeyId.value = configs.active_config_id;
  if (force) note.value = catalog.features.catalog_source === "live_catalog" ? "已同步 " + catalog.models.length + " 个视频模型" : "上游目录暂不可用，保留已有模型目录";
  if (!started) { started = true; restoreDraft(); if (!hasDraft()) { keyId.value = configs.active_config_id; applyDefaults(); } }
  if (!keys.value.some(k => k.id === keyId.value)) keyId.value = configs.active_config_id;
}
function nextPoll() { if (poll) clearTimeout(poll); if (disposed) return; poll = setTimeout(() => { void loadTasks(); }, tasks.value.some(t => activeVideoStatuses.has(t.status)) ? 3000 : 15000); }
function settlePending(result: VideoRequestState, requestId: string, version: number) {
  if (disposed || version !== contextVersion || pending.value?.requestId !== requestId) return;
  if (result.state === "missing") return;
  if (result.state === "accepted") {
    const task = result.task;
    if (!task || task.request_id !== requestId || task.project_id !== props.projectId) throw new Error("旧请求核对结果不匹配，已保留待确认记录");
    tasks.value = [task, ...tasks.value.filter(t => t.id !== task.id)];
    emit("select", task.id); emit("changed");
    note.value = "已找到上次提交的任务，当前草稿已保留。再次生成会创建新视频。";
  } else if (result.state === "closed") {
    note.value = "旧请求未创建任务，已解除待确认状态。可使用当前参数生成视频。";
  } else { throw new Error("旧请求核对结果无法读取，已保留待确认记录"); }
  pending.value = null; error.value = ""; saveDraft();
}
async function resolvePending() {
  if (busy.value || !pending.value || !props.projectId) return;
  const requestId = pending.value.requestId, version = contextVersion, projectId = props.projectId;
  busy.value = true; error.value = "";
  try {
    const result = await videoJson<VideoRequestState>(props.apiFetch, props.apiBase, "/api/videos/requests/" + encodeURIComponent(requestId) + "/resolve", jsonBody({ project_id: projectId }));
    if (result.state === "missing") throw new Error("旧请求尚未完成核对，请稍后重试");
    settlePending(result, requestId, version);
  } catch (e) {
    if (!disposed && version === contextVersion && pending.value?.requestId === requestId) error.value = e instanceof Error ? e.message : "旧请求核对失败，请重试";
  } finally { busy.value = false; }
}
async function loadTasks() {
  if (!started || disposed || !props.projectId) return;
  const version = contextVersion, projectId = props.projectId;
  try {
    const data = await videoJson<VideoTask[]>(props.apiFetch, props.apiBase, "/api/videos/tasks?project_id=" + projectId);
    if (disposed || version !== contextVersion) return;
    const before = tasks.value.map(t => t.id + ":" + t.status).join();
    tasks.value = data;
    const requestId = pending.value?.requestId;
    if (requestId) {
      const accepted = data.find(t => t.request_id === requestId);
      const result = accepted ? { state: "accepted" as const, task: accepted }
        : await videoJson<VideoRequestState>(props.apiFetch, props.apiBase, "/api/videos/requests/" + encodeURIComponent(requestId));
      if (disposed || version !== contextVersion) return;
      settlePending(result, requestId, version);
    }
    if (before !== data.map(t => t.id + ":" + t.status).join()) emit("changed");
    if (props.selectedTaskId && !data.some(t => t.id === props.selectedTaskId)) {
      try { const detail = await videoJson<VideoTask>(props.apiFetch, props.apiBase, "/api/videos/tasks/" + props.selectedTaskId); if (detail.project_id === projectId && version === contextVersion) tasks.value = [...data, detail]; }
      catch { if (version === contextVersion) emit("select", null); }
    }
  } catch (e) { if (!disposed && version === contextVersion) error.value = e instanceof Error ? e.message : "视频任务加载失败"; }
  finally { if (!disposed && version === contextVersion) nextPoll(); }
}
async function refresh(force = false) { const version = contextVersion; loading.value = true; error.value = ""; try { await loadConfiguration(force); if (!disposed) await loadTasks(); } catch (e) { if (!disposed && version === contextVersion) error.value = e instanceof Error ? e.message : "加载失败"; } finally { if (!disposed && version === contextVersion) loading.value = false; } }
function nextName(type: MaterialType, proposed = "") { if (proposed.trim() && !materials.value.some(m => m.name === proposed.trim())) return proposed.trim(); let i = 1; while (materials.value.some(m => m.name === materialLabels[type] + i)) i++; return materialLabels[type] + i; }
function addURL() { const m: VideoMaterial = { type: kind.value, url: sourceURL.value.trim(), name: nextName(kind.value, sourceName.value) }; const issue = materialIssue(selectedModel.value, m, [...materials.value, m]); if (issue) { error.value = issue; return; } materials.value.push(m); sourceURL.value = ""; sourceName.value = ""; error.value = ""; }
async function upload(event: Event) {
  const input = event.target as HTMLInputElement, file = input.files?.[0]; input.value = "";
  if (!file || busy.value) return;
  const uploadKind = kind.value;
  if (file.size > ({ image: 10, video: 100, audio: 20 }[uploadKind]) * 1024 * 1024) { error.value = "文件超过本应用大小上限"; return; }
  busy.value = true; error.value = ""; const version = contextVersion;
  try {
    const form = new FormData(); form.append("file", file); form.append("name", sourceName.value);
    const a = await videoJson<{ id: string; name: string; preview_url: string; duration_seconds: number | null }>(props.apiFetch, props.apiBase, "/api/videos/assets/upload?type=" + uploadKind, { method: "POST", body: form });
    if (!disposed && version === contextVersion) materials.value.push({ type: uploadKind, asset_id: a.id, name: nextName(uploadKind, a.name), preview_url: a.preview_url, duration_seconds: a.duration_seconds });
  } catch (e) { if (!disposed && version === contextVersion) error.value = e instanceof Error ? e.message : "上传失败"; } finally { busy.value = false; }
}
async function addHistoryImage(historyId: number, imageId: number) {
  if (!started) await loadConfiguration();
  if (!features.value?.assets_ready) { error.value = "已有图片引用需要管理员先配置公网 HTTPS 与签名密钥"; return false; }
  busy.value = true; error.value = ""; const version = contextVersion;
  try {
    const a = await videoJson<{ id: string; preview_url: string }>(props.apiFetch, props.apiBase, "/api/videos/assets/from-history", jsonBody({ history_id: historyId, image_id: imageId }));
    if (disposed || version !== contextVersion) return false;
    materials.value.push({ type: "image", name: nextName("image"), asset_id: a.id, preview_url: a.preview_url }); pickerOpen.value = false; return true;
  } catch (e) { if (!disposed && version === contextVersion) error.value = e instanceof Error ? e.message : "图片引用失败"; return false; } finally { busy.value = false; }
}
async function showImagePicker() {
  pickerOpen.value = true; error.value = ""; const version = contextVersion;
  try {
    imageChoices.value = [];
    for (const historyId of (props.imageHistoryIds || []).slice(0,20)) {
      const detail = await videoJson<{ images: Array<{ id: number; role: string; url: string; filename: string | null }> }>(props.apiFetch, props.apiBase, "/api/history/" + historyId);
      if (disposed || version !== contextVersion) return;
      imageChoices.value.push(...detail.images.filter(i => i.role === "generated").map(i => ({ ...i, history_id: historyId })));
    }
  } catch (e) { if (!disposed && version === contextVersion) error.value = e instanceof Error ? e.message : "历史图片加载失败"; }
}
function insertMention(material: VideoMaterial) { const input = promptInput.value; const start = input?.selectionStart ?? prompt.value.length, end = input?.selectionEnd ?? start; const text = "@" + material.name.trim() + " "; prompt.value = prompt.value.slice(0,start) + text + prompt.value.slice(end); void nextTick(() => { input?.focus(); input?.setSelectionRange(start + text.length, start + text.length); }); }
function removeMaterial(index: number) { materials.value.splice(index, 1); }
async function submit() {
  if (pending.value) { await resolvePending(); return; }
  if (!canSubmit.value) return;
  busy.value = true; error.value = "";
  const body = { project_id: props.projectId, api_key_config_id: keyId.value, model: modelId.value, prompt: prompt.value.trim(), duration: duration.value, resolution: resolution.value, ratio: ratio.value, materials: materials.value.map(m => ({ type: m.type, name: m.name.trim(), ...(m.asset_id ? { asset_id: m.asset_id } : { url: m.url }) })) };
  const fingerprint = JSON.stringify(body);
  if (!pending.value) {
    // randomUUID is unavailable on non-localhost HTTP; getRandomValues remains available.
    const bytes = crypto.getRandomValues(new Uint8Array(16)); bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
    const hex = Array.from(bytes, b => b.toString(16).padStart(2,"0")).join("");
    pending.value = { fingerprint, requestId: hex.slice(0,8)+"-"+hex.slice(8,12)+"-"+hex.slice(12,16)+"-"+hex.slice(16,20)+"-"+hex.slice(20) };
  }
  saveDraft(); const version = contextVersion;
  try {
    const data = await videoJson<{ task: VideoTask }>(props.apiFetch, props.apiBase, "/api/videos/tasks", jsonBody({ ...body, request_id: pending.value.requestId }));
    if (disposed || version !== contextVersion) return;
    pending.value = null; saveDraft(); tasks.value = [data.task, ...tasks.value.filter(t => t.id !== data.task.id)]; emit("select", data.task.id); emit("changed"); nextPoll(); note.value = "任务已持久化，每次提交只创建一个视频任务。";
  } catch (e) {
    if (disposed || version !== contextVersion) return;
    const rejected = e instanceof VideoApiError && e.status >= 400 && e.status < 500 && e.code !== "video_request_conflict";
    if (rejected) { pending.value = null; saveDraft(); }
    error.value = (e instanceof Error ? e.message : "请求失败") + (rejected ? "。此次请求未受理，可修改后提交。" : "。请点击“核对并解除待确认请求”，核对不会生成新视频。");
    await loadTasks();
  }
  finally { busy.value = false; }
}
function requestAction(task: VideoTask, action: string, upstreamId?: string) { if (["delete", "abandon", "bind"].includes(action)) confirm.value = { task, action, upstreamId }; else void runAction(task, action); }
async function runAction(task: VideoTask, action: string, upstreamId?: string) {
  if (busy.value) return;
  busy.value = true; error.value = ""; const version = contextVersion;
  try {
    await videoJson(props.apiFetch, props.apiBase, "/api/videos/tasks/" + task.id + (action === "delete" ? "" : "/" + action), action === "delete" ? { method: "DELETE" } : action === "bind" ? jsonBody({ upstream_task_id: upstreamId }) : { method: "POST" });
    if (disposed || version !== contextVersion) return;
    confirm.value = null; if (action === "delete") emit("select", null); await loadTasks(); emit("changed");
  } catch (e) { if (!disposed && version === contextVersion) error.value = e instanceof Error ? e.message : "操作失败"; } finally { busy.value = false; }
}
function reuse(task: VideoTask) { modelId.value = task.model; duration.value = task.duration; resolution.value = task.resolution; ratio.value = task.ratio; keyId.value = task.api_key_config_id; prompt.value = task.prompt; materials.value = task.materials.map(m => ({ ...m, preview_url: m.asset_id ? "/api/videos/assets/" + m.asset_id + "/file" : undefined })); note.value = "已复用参数。点击生成会创建新的付费任务，不是恢复原任务。"; }
function restorePendingParameters() {
  if (!pending.value) return;
  try {
    const body = JSON.parse(pending.value.fingerprint);
    modelId.value = body.model; keyId.value = body.api_key_config_id; prompt.value = body.prompt;
    duration.value = body.duration; resolution.value = body.resolution; ratio.value = body.ratio;
    materials.value = body.materials.map((m: VideoMaterial) => ({ ...m, preview_url: m.asset_id ? "/api/videos/assets/" + m.asset_id + "/file" : undefined }));
    error.value = ""; note.value = "已恢复上次请求的原参数。核对旧请求不会创建新视频。";
  } catch { error.value = "待确认请求的本地数据无法读取，请核对历史任务或联系管理员。"; }
}
function newDraft() { if (pending.value) { error.value = "上次请求待确认，请先核对并解除待确认请求，暂不清空草稿。"; return; } prompt.value = ""; materials.value = []; emit("select", null); applyDefaults(); }
watch([prompt, modelId, keyId, duration, resolution, ratio, materials, pending], saveDraft, { deep: true });
watch(() => props.projectId, () => { contextVersion++; tasks.value = []; pickerOpen.value = false; confirm.value = null; error.value = ""; note.value = ""; loading.value = false; if (started) { restoreDraft(); if (!hasDraft()) applyDefaults(); void loadTasks(); } else if (props.active) void refresh(); });
watch(() => props.active, active => { if (active) void refresh(); }, { immediate: true });
watch(() => props.selectedTaskId, () => { if (started) void loadTasks(); });
onUnmounted(() => { disposed = true; configurationVersion++; if (poll) clearTimeout(poll); saveDraft(); });
defineExpose({ addHistoryImage, refresh, newDraft });
</script>
<template>
  <section class="video-workspace" aria-label="视频生成工作台">
    <div class="video-stage">
      <header class="video-heading">
        <div>
          <span class="result-kicker"><Film :size="14" />MOTION STUDIO</span>
          <h2>视频工作台<span class="video-heading-dot">.</span></h2>
          <p>让每一个想法，都有自己的镜头。</p>
        </div>
        <div class="video-heading-actions">
          <button class="secondary-action video-refresh" type="button" :disabled="loading" @click="refresh(true)"><RefreshCw :size="14" :class="{ spin: loading }" />刷新</button>
          <button v-if="selectedTaskId" class="secondary-action" type="button" @click="emit('select', null)">全部任务</button>
        </div>
      </header>

      <div class="video-environment" v-if="features">
        <span class="video-environment-state" :class="{ ready: features.storage_ready && features.media_tools_ready && features.api_ready !== false }"><i aria-hidden="true"></i>{{ features.storage_ready && features.media_tools_ready && features.api_ready !== false ? '创作环境就绪' : '创作环境未就绪' }}</span>
        <span><ShieldCheck :size="13" />私有保存</span>
        <span>每次生成 1 个视频</span>
      </div>
      <div v-if="!features?.storage_ready && !loading" class="video-readiness warning" role="status"><CircleAlert :size="17" /><div><strong>视频存储尚未就绪</strong><p>R2 私有存储未配置或连接检查未通过，已禁用视频提交，避免扣费后无法保存。请联系管理员。</p></div></div>
      <div v-if="features?.api_ready === false" class="video-readiness warning" role="status"><CircleAlert :size="17" /><div><strong>视频服务地址需要配置</strong><p>请管理员设置可信的 HTTPS 根地址（不要添加 /v1）。图片功能不受影响。</p></div></div>
      <div v-if="features && !features.media_tools_ready" class="video-readiness warning" role="status"><CircleAlert :size="17" /><div><strong>媒体校验工具尚未就绪</strong><p>服务器缺少 ffprobe，暂不能提交或校验视频素材。</p></div></div>
      <details v-if="features && !features.assets_ready" class="video-readiness info">
        <summary><Info :size="16" /><span>本地素材暂不可用</span><span class="video-notice-summary">查看说明</span></summary>
        <p>公网 HTTPS 素材地址尚未就绪。本地上传、已有图片引用已禁用；存储和媒体工具就绪后仍可使用文生视频和外部 HTTPS 素材。</p>
      </details>
      <p v-if="error" role="alert" class="error-message">{{ error }}</p>
      <p v-if="note" role="status" class="video-note">{{ note }}</p>

      <div class="video-task-wall" :class="{ 'is-empty': !visibleTasks.length }">
        <VideoTaskCard v-for="task in visibleTasks" :key="task.id" :task="task" :api-base="apiBase" :busy="busy" @action="requestAction" @reuse="reuse" />
        <div v-if="!visibleTasks.length" class="video-empty">
          <div class="video-empty-art" aria-hidden="true">
            <div class="video-art-frame frame-back"></div>
            <div class="video-art-frame frame-front"><span class="video-art-label">PICTORA / MOTION</span><div class="video-art-orbit"></div><span class="video-art-play"><Play :size="24" fill="currentColor" /></span><div class="video-art-timeline"><i></i><i></i><i></i><i></i><i></i><span>00:05</span></div></div>
            <span class="video-art-spark"><Sparkles :size="17" /></span>
          </div>
          <span class="video-empty-kicker">YOUR NEXT STORY STARTS HERE</span>
          <h3>{{ loading ? '正在准备你的工作台…' : '让灵感，开始流动。' }}</h3>
          <p>描述一个画面、一段动作，或一种氛围。<br />接下来的镜头，交给 Pictora。</p>
          <button class="video-start-writing" type="button" @click="promptInput?.focus()">写下第一个镜头<ArrowUpRight :size="16" /></button>
          <div class="video-empty-tags"><span><Film :size="13" />文生视频</span><span v-if="allowedKinds.includes('image')"><ImagePlus :size="13" />图片参考</span><span v-if="allowedKinds.includes('video') || allowedKinds.includes('audio')"><Sparkles :size="13" />多模态创作</span></div>
        </div>
      </div>
      <div class="video-stage-footnote"><span>从一帧想象，到一段故事。</span><span>PICTORA STUDIO</span></div>
    </div>

    <form class="video-composer" @submit.prevent="submit">
      <header class="video-composer-heading"><span class="video-composer-icon"><SlidersHorizontal :size="18" /></span><div><h3>创作设置</h3><p>为你的下一段故事设定镜头</p></div></header>
      <div class="video-composer-body">
        <div v-if="pending" class="video-pending">
          <p>上次提交的结果尚未确认。核对后会找回已有任务，或解除旧请求；当前草稿会保留。</p>
          <button type="button" class="secondary-action" data-action="resolve-video-pending" :disabled="busy" @click="resolvePending">核对并解除待确认请求</button>
          <button type="button" class="text-action" data-action="restore-video-pending" :disabled="busy" @click="restorePendingParameters">恢复待确认请求的原参数</button>
        </div>
        <div class="video-parameters">
          <label class="video-key-field">视频 Key<select v-model="keyId" data-field="video-key" @change="changeKey"><option :value="null">请选择视频 Key</option><option v-for="key in keys" :key="key.id" :value="key.id">{{ key.alias }}</option></select></label>
          <label class="video-model-field">视频模型<select v-model="modelId" data-field="video-model" @change="changeModel"><option v-if="!selectedModel && modelId" :value="modelId" disabled>{{ modelId }}（已下线或暂不可用）</option><option v-for="model in models" :key="model.id" :value="model.id">{{ model.id }}</option></select></label>
          <label>分辨率<select v-model="resolution" data-field="video-resolution" @change="changeResolution"><option v-for="r in Object.keys(selectedModel?.durations_by_resolution || {})" :key="r">{{ r }}</option></select></label>
          <label>时长<select v-model="duration" data-field="video-duration"><option v-for="d in durations" :key="d" :value="d">{{ d }} 秒</option></select></label>
          <label>比例<select v-model="ratio" data-field="video-ratio"><option v-for="r in selectedModel?.ratios || []" :key="r">{{ r }}</option></select></label>
        </div>
        <button v-if="!keys.length" class="text-action video-key-link" type="button" @click="emit('settings')">前往设置添加独立视频 Key<ArrowUpRight :size="13" /></button>
        <div class="video-capabilities" aria-label="当前模型素材能力"><span v-for="type in (['image','video','audio'] as const)" :key="type" :class="{ unsupported: !selectedModel?.reference_limits[type] }"><Check v-if="(selectedModel?.reference_limits[type] || 0) > 0" :size="12" />{{ materialLabels[type] }}参考 · {{ selectedModel?.reference_limits[type] == null ? '尚未确认' : selectedModel?.reference_limits[type] === 0 ? '不支持' : '最多 ' + selectedModel?.reference_limits[type] + ' 个' }}</span><small v-if="selectedModel?.max_total_materials">总素材最多 {{ selectedModel.max_total_materials }} 个；视频总时长最多 {{ selectedModel.max_video_duration_seconds }} 秒（服务器探测）</small></div>

        <label class="video-prompt-label"><span>视频提示词<small>{{ prompt.length.toLocaleString() }} / 20,000</small></span><textarea ref="promptInput" v-model="prompt" data-field="video-prompt" maxlength="20000" placeholder="描述你想要的画面、动作和运镜…&#10;&#10;例如：@图片1 中的角色缓缓回头，镜头轻轻推进，阳光穿过树叶。" rows="4" required /></label>
        <section class="video-reference-section" aria-label="参考素材">
          <div class="video-material-toolbar"><strong>参考素材<span>可选</span></strong><label class="video-kind-label"><span class="sr-only">素材类型</span><select v-model="kind" data-field="video-material-type"><option v-for="type in (['image','video','audio'] as const)" :key="type" :value="type" :disabled="!allowedKinds.includes(type)">{{ materialLabels[type] }}{{ selectedModel?.reference_limits[type] == null ? '（尚未确认）' : selectedModel?.reference_limits[type] === 0 ? '（不支持）' : '' }}</option></select></label></div>
          <div class="video-material-sources"><label class="secondary-action video-upload" :class="{disabled: !features?.assets_ready || busy || !allowedKinds.includes(kind)}" :title="features?.assets_ready ? '上传参考素材' : '需要配置公网 HTTPS 素材地址'"><Upload :size="15" />本地上传<input type="file" :accept="kind === 'image' ? 'image/png,image/jpeg,image/webp,image/gif' : kind === 'video' ? 'video/mp4,.mp4' : 'audio/mpeg,audio/wav,.mp3,.wav'" :disabled="!features?.assets_ready || busy || !allowedKinds.includes(kind)" @change="upload" /></label><button class="secondary-action" type="button" :disabled="!features?.assets_ready || busy || !allowedKinds.includes('image')" :title="features?.assets_ready ? '选择生成图片' : '需要配置公网 HTTPS 素材地址'" @click="showImagePicker"><ImagePlus :size="15" />已有生成图片</button></div>
          <div class="video-link-form"><label class="video-url-field"><span><Link2 :size="12" />HTTPS 素材链接</span><input v-model="sourceURL" data-field="video-material-url" type="url" placeholder="粘贴 https:// 素材链接" /></label><label class="video-name-field">素材名称<input v-model="sourceName" data-field="video-material-name" maxlength="80" placeholder="自动命名" /></label><button class="secondary-action video-add-link" type="button" :disabled="!sourceURL.trim() || busy || !allowedKinds.includes(kind)" @click="addURL">添加链接</button></div>
          <div class="video-materials"><article v-for="(material,index) in materials" :key="material.asset_id || material.url" :class="{incompatible: !!materialIssue(selectedModel,material,materials)}"><img v-if="material.type === 'image' && material.preview_url" :src="apiBase + material.preview_url" alt="本地参考素材" /><div><label>{{ materialLabels[material.type] }}素材名称<input v-model="material.name" maxlength="80" aria-label="素材名称" /></label><small>{{ material.asset_id ? '独立素材快照' : material.url }}</small><small v-if="material.duration_seconds">服务器探测：{{ material.duration_seconds.toFixed(2) }} 秒</small><p v-if="materialIssue(selectedModel,material,materials)" role="status">{{ materialIssue(selectedModel,material,materials) }}</p></div><button class="text-action" type="button" :disabled="!material.name.trim()" @click="insertMention(material)">插入 @引用</button><button class="icon-action" type="button" aria-label="移除素材" @click="removeMaterial(index)"><X :size="16" /></button></article></div>
        </section>
        <ul v-if="issues.length && models.length" class="video-validation"><li v-for="issue in issues" :key="issue">{{ issue }}</li></ul>
        <details class="video-upload-guidelines"><summary>素材限制与使用说明</summary><p>首尾帧控制暂未开放。应用上传限制：图片 10 MB、MP4 100 MB、MP3/WAV 20 MB，不代表上游支持保证。素材重命名后请同步检查提示词中的 @引用。</p></details>
      </div>
      <footer class="video-submit-row"><button class="primary-action" data-action="generate-video" type="submit" :disabled="busy || (pending ? !projectId : !canSubmit)"><Sparkles :size="16" />{{ busy ? '处理中…' : pending ? '核对上次提交（不生成）' : '生成视频' }}<ArrowUpRight v-if="!busy && !pending" :size="17" /></button><p><ShieldCheck :size="12" />生成结果保存至 R2 私有存储</p></footer>
    </form>
    <div v-if="pickerOpen" class="video-picker-layer" role="dialog" aria-modal="true" aria-label="选择已有图片" @click.self="pickerOpen = false"><section><header><h3>已有生成图片（当前项目最近 20 条）</h3><button class="icon-action" type="button" aria-label="关闭图片选择" @click="pickerOpen = false"><X :size="20" /></button></header><div class="video-image-picker"><button v-for="image in imageChoices" :key="image.id" type="button" :disabled="busy" @click="addHistoryImage(image.history_id,image.id)"><img :src="apiBase + image.url" :alt="image.filename || '生成图片'" /></button></div><p v-if="!imageChoices.length">暂无可选图片。</p></section></div>
    <ConfirmDialog :open="confirm !== null" :title="confirm?.action === 'abandon' ? '放弃本地追踪' : confirm?.action === 'bind' ? '接管上游任务' : '删除视频记录'" :message="confirm?.action === 'abandon' ? '放弃仅停止本站查询，不会取消上游任务，也不会触发退款。确定放弃吗？' : confirm?.action === 'bind' ? '将使用原视频 Key 查询此上游 ID，验证通过后继续查询或保存；不创建新视频。确定接管吗？' : '将删除视频记录及无人引用的素材，R2 对象进入可重试的持久化清理队列。无法恢复。'" :confirm-label="confirm?.action === 'abandon' ? '确认放弃本地追踪' : confirm?.action === 'bind' ? '验证并接管' : '确认删除'" :busy="busy" @confirm="confirm && runAction(confirm.task,confirm.action,confirm.upstreamId)" @cancel="confirm = null" />
  </section>
</template>
<style scoped>
.video-workspace { display:grid; grid-template-columns:minmax(0,1fr) 396px; gap:24px; height:100%; min-height:0; padding:28px; color:var(--text); }
.video-stage { display:flex; flex-direction:column; gap:16px; min-height:0; min-width:0; }
.video-heading { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; }
.video-heading h2 { margin:8px 0 7px; font-size:27px; font-weight:700; letter-spacing:-.9px; }
.video-heading-dot { color:var(--blue); }
.video-heading p { margin:0; font-size:12px; line-height:1.7; color:var(--muted); }
.video-heading-actions { display:flex; gap:8px; padding-top:4px; flex-wrap:wrap; justify-content:flex-end; }
.video-refresh { font-size:12px; }
.video-environment { display:flex; align-items:center; flex-wrap:wrap; gap:10px 18px; color:var(--muted); font-size:11px; }
.video-environment>span { display:inline-flex; align-items:center; gap:5px; }
.video-environment-state i { width:6px; height:6px; border-radius:50%; background:var(--amber); }
.video-environment-state.ready i { background:var(--green); box-shadow:0 0 0 3px color-mix(in srgb,var(--green) 10%,transparent); }
.video-readiness { margin:0; padding:13px 15px; border:1px solid var(--line); border-radius:12px; font-size:12px; line-height:1.7; }
.video-readiness.warning { display:flex; gap:10px; align-items:flex-start; background:color-mix(in srgb,var(--amber) 7%,var(--surface)); }
.video-readiness.warning>svg { flex-shrink:0; margin-top:2px; color:var(--amber); }
.video-readiness strong { font-size:12px; font-weight:600; }
.video-readiness p { margin:5px 0 0; color:var(--muted); }
.video-readiness.info { background:var(--surface); }
.video-readiness summary { display:flex; align-items:center; gap:8px; cursor:pointer; list-style:none; color:var(--muted); }
.video-readiness summary::-webkit-details-marker { display:none; }
.video-readiness summary>svg { color:var(--blue); }
.video-notice-summary { margin-left:auto; font-size:10px; }
.video-note { margin:0; padding:10px 13px; background:var(--blue-soft); border-radius:10px; font-size:12px; color:var(--text-soft); line-height:1.7; }
.video-task-wall { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,330px),1fr)); align-content:start; gap:18px; min-height:0; overflow:auto; flex:1; padding:2px; }
.video-task-wall.is-empty { display:flex; align-items:center; justify-content:center; border:1px dashed var(--line-strong); border-radius:20px; background:color-mix(in srgb,var(--surface) 65%,transparent); }
.video-empty { display:flex; flex-direction:column; align-items:center; text-align:center; padding:35px 20px; width:100%; }
.video-empty-kicker { color:var(--muted-dim); font-size:9px; letter-spacing:2px; margin-top:25px; }
.video-empty h3 { color:var(--text); margin:13px 0 12px; font-size:clamp(22px,2vw,30px); line-height:1.5; letter-spacing:-1px; font-weight:600; }
.video-empty>p { margin:0; color:var(--muted); font-size:12px; line-height:1.95; }
.video-start-writing { display:inline-flex; align-items:center; gap:7px; color:var(--blue); background:none; border:0; padding:11px 9px; margin-top:12px; font-size:12px; cursor:pointer; }
.video-start-writing:hover { color:var(--blue-hover); }
.video-empty-tags { display:flex; justify-content:center; flex-wrap:wrap; gap:7px; margin-top:24px; }
.video-empty-tags span { display:flex; align-items:center; gap:5px; border:1px solid var(--line); border-radius:6px; padding:7px 9px; font-size:10px; color:var(--muted); background:var(--surface); }
.video-empty-art { position:relative; width:238px; height:153px; margin:0 auto; }
.video-art-frame { position:absolute; width:204px; height:132px; border:1px solid var(--line-strong); border-radius:14px; }
.frame-back { top:0; left:6px; transform:rotate(-9deg); background:var(--surface-subtle); }
.frame-front { left:21px; top:13px; overflow:hidden; background:var(--surface); box-shadow:0 16px 30px -16px var(--polish-shadow-color); transform:rotate(4deg); }
.video-art-label { position:absolute; left:14px; top:13px; font-size:7px; letter-spacing:1px; color:var(--muted-dim); }
.video-art-play { position:absolute; inset:34px auto auto 78px; display:grid; place-items:center; width:47px; height:47px; color:var(--blue); background:var(--blue-soft); border:1px solid color-mix(in srgb,var(--blue) 18%,transparent); border-radius:14px; }
.video-art-play svg { margin-left:3px; }
.video-art-orbit { position:absolute; width:136px; height:136px; top:4px; left:33px; border:1px solid var(--line); border-radius:50%; }
.video-art-timeline { position:absolute; bottom:13px; left:14px; right:14px; display:flex; align-items:center; gap:4px; height:13px; }
.video-art-timeline i { height:3px; background:var(--line-strong); border-radius:2px; flex:1; }
.video-art-timeline i:nth-child(-n+2) { background:var(--blue); opacity:.55; }
.video-art-timeline span { padding-left:6px; color:var(--muted-dim); font-size:7px; }
.video-art-spark { position:absolute; right:0; top:1px; display:grid; place-items:center; width:32px; height:32px; background:var(--surface); color:var(--blue); border:1px solid var(--line); border-radius:10px; transform:rotate(10deg); }
.video-stage-footnote { display:flex; justify-content:space-between; gap:10px; padding:0 2px; font-size:10px; color:var(--muted-dim); }
.video-stage-footnote>span:last-child { letter-spacing:1.3px; font-size:8px; }
.video-composer { display:flex; flex-direction:column; min-height:0; border:1px solid var(--line); border-radius:18px; background:var(--surface); box-shadow:0 10px 30px -20px var(--polish-shadow-color); overflow:hidden; }
.video-composer-heading { display:flex; gap:11px; align-items:center; padding:19px 21px; border-bottom:1px solid var(--line); }
.video-composer-icon { width:36px; height:36px; display:grid; place-items:center; border-radius:11px; background:var(--blue-soft); color:var(--blue); }
.video-composer-heading h3 { font-size:14px; margin:0 0 4px; font-weight:600; }
.video-composer-heading p { font-size:10px; color:var(--muted); margin:0; }
.video-composer-body { padding:21px; overflow:auto; flex:1; min-height:0; }
.video-pending { display:grid; gap:10px; margin-bottom:16px; padding:12px; border:1px solid var(--line); border-radius:9px; }
.video-pending p { margin:0; color:var(--text-soft); font-size:11px; line-height:1.6; }
.video-parameters { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px 9px; }
.video-parameters .video-key-field { grid-column:1; }
.video-parameters .video-model-field { grid-column:span 2; }
.video-composer label { display:grid; gap:7px; font-size:11px; color:var(--text-soft); min-width:0; font-weight:500; }
.video-composer input,.video-composer select,.video-composer textarea { width:100%; min-width:0; font-size:12px; font-weight:400; border:1px solid var(--line); border-radius:9px; background:var(--surface-subtle); color:var(--text); padding:10px 11px; box-shadow:none; transition:border-color .15s,box-shadow .15s; }
.video-composer select { height:39px; padding-right:6px; cursor:pointer; }
.video-composer input { height:39px; }
.video-composer input::placeholder,.video-composer textarea::placeholder { color:var(--muted-dim); font-weight:400; }
.video-composer input:focus,.video-composer textarea:focus,.video-composer select:focus { border-color:var(--blue); outline:none; box-shadow:0 0 0 3px var(--blue-soft); }
.video-key-link { font-size:11px; margin-top:10px; }
.video-capabilities { display:flex; flex-wrap:wrap; gap:6px; margin:11px 0 23px; }
.video-capabilities>span { display:flex; align-items:center; gap:3px; font-size:9px; color:var(--muted); background:var(--surface-subtle); border:1px solid var(--line); padding:4px 5px; border-radius:5px; }
.video-capabilities>span>svg { color:var(--green); }
.video-capabilities .unsupported { color:var(--muted-dim); }
.video-capabilities>small { flex-basis:100%; font-size:10px; color:var(--muted); line-height:1.7; }
.video-prompt-label>span { display:flex; align-items:center; justify-content:space-between; gap:8px; }
.video-prompt-label small { color:var(--muted-dim); font-size:9px; font-weight:400; }
.video-composer textarea { resize:vertical; min-height:125px; line-height:1.9; padding:13px; }
.video-reference-section { padding-top:22px; margin-top:22px; border-top:1px solid var(--line); }
.video-material-toolbar { display:flex; gap:10px; align-items:center; justify-content:space-between; }
.video-material-toolbar strong { font-size:11px; font-weight:500; display:flex; align-items:center; gap:7px; }
.video-material-toolbar strong span { font-size:9px; color:var(--muted-dim); font-weight:400; }
.video-kind-label select { height:31px; padding:4px 7px; font-size:10px; }
.video-material-sources { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:12px; }
.video-material-sources .secondary-action { justify-content:center; font-size:11px; min-height:37px; padding:8px 7px; box-shadow:none; border-style:dashed; }
.video-upload { position:relative; display:flex!important; align-items:center; flex-direction:row; overflow:hidden; cursor:pointer; gap:6px!important; }
.video-upload input { position:absolute; inset:0; opacity:0; height:100%; width:100%; cursor:pointer; }
.video-upload.disabled { opacity:.5; cursor:not-allowed; }
.video-link-form { display:grid; grid-template-columns:minmax(0,1fr) 88px; gap:10px 8px; align-items:end; margin-top:14px; }
.video-url-field { grid-column:1/-1; }
.video-url-field>span { display:flex; align-items:center; gap:4px; }
.video-link-form .video-name-field { grid-column:1; }
.video-add-link { height:39px; font-size:11px; padding:8px; }
.video-materials { display:grid; gap:8px; margin-top:12px; }
.video-materials article { display:flex; flex-wrap:wrap; gap:9px; align-items:center; border:1px solid var(--line); padding:10px; border-radius:10px; background:var(--surface-subtle); }
.video-materials article>div { flex:1; min-width:130px; }
.video-materials img { width:44px; height:44px; object-fit:cover; border-radius:7px; }
.video-materials small { display:block; font-size:9px; overflow-wrap:anywhere; color:var(--muted); margin-top:5px; }
.video-materials .incompatible { border-color:var(--danger); }
.video-materials p,.video-validation { color:var(--danger); font-size:11px; line-height:1.7; }
.video-validation { padding-left:17px; }
.video-upload-guidelines { margin-top:14px; font-size:10px; color:var(--muted); line-height:1.8; }
.video-upload-guidelines summary { cursor:pointer; }
.video-upload-guidelines p { margin:8px 0 0; }
.video-submit-row { padding:17px 21px 15px; border-top:1px solid var(--line); background:var(--surface); }
.video-submit-row .primary-action { width:100%; min-height:43px; justify-content:center; gap:8px; font-size:13px; }
.video-submit-row .primary-action>svg:last-child { margin-left:auto; }
.video-submit-row .primary-action>svg:first-child { margin-right:auto; }
.video-submit-row p { display:flex; align-items:center; justify-content:center; gap:5px; margin:10px 0 0; font-size:9px; color:var(--muted-dim); }
.video-picker-layer { position:fixed; inset:0; z-index:900; background:var(--prompt-snow-overlay); display:grid; place-items:center; padding:20px; backdrop-filter:blur(6px); }
.video-picker-layer>section { width:min(800px,100%); max-height:80vh; overflow:auto; background:var(--surface); padding:24px; border:1px solid var(--line); border-radius:18px; box-shadow:var(--shadow-menu); }
.video-picker-layer header { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:16px; }
.video-picker-layer h3 { font-size:15px; }
.video-image-picker { display:grid; grid-template-columns:repeat(auto-fill,minmax(130px,1fr)); gap:10px; }
.video-image-picker img { width:100%; aspect-ratio:1; object-fit:cover; display:block; }
.video-image-picker button { border:1px solid var(--line); border-radius:10px; padding:0; background:none; overflow:hidden; cursor:pointer; }
.video-image-picker button:hover { border-color:var(--blue); }
@media(min-width:1600px) { .video-workspace { grid-template-columns:minmax(0,1fr) 428px; padding:34px; gap:32px; } }
@media(max-width:1200px) { .video-workspace { grid-template-columns:minmax(0,1fr) 352px; padding:22px; gap:18px; } .video-heading h2 { font-size:24px; } .video-environment { gap:10px; } }
@media(max-width:1020px) { .video-workspace { display:flex; flex-direction:column; height:auto; padding:22px; } .video-stage { min-height:490px; } .video-composer { flex-shrink:0; } .video-composer-body { overflow:visible; } .video-parameters { grid-template-columns:repeat(3,minmax(0,1fr)); } .video-parameters .video-key-field,.video-parameters .video-model-field { grid-column:auto; } .video-parameters .video-model-field { grid-column:span 2; } .video-link-form { grid-template-columns:minmax(0,1fr) minmax(0,.7fr) 88px; } .video-url-field,.video-link-form .video-name-field { grid-column:auto; } }
@media(max-width:600px) { .video-workspace { padding:18px 14px; gap:22px; } .video-heading h2 { font-size:23px; } .video-environment { font-size:10px; } .video-empty { padding:34px 15px; } .video-empty h3 { font-size:25px; } .video-stage { min-height:470px; } .video-stage-footnote>span:last-child { display:none; } .video-composer-heading,.video-composer-body,.video-submit-row { padding-left:17px; padding-right:17px; } .video-parameters .video-key-field,.video-parameters .video-model-field { grid-column:1/-1; } .video-link-form { grid-template-columns:minmax(0,1fr) 88px; } .video-url-field { grid-column:1/-1; } }
</style>


