<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from "vue";
import { Clock3, Download, Film, LoaderCircle, RefreshCw } from "lucide-vue-next";
import { activeVideoStatuses, formatVideoElapsed, trackedVideoStatuses, videoElapsedMs, videoStatusLabels, type VideoTask } from "../video";
const props = defineProps<{ task: VideoTask; apiBase: string; busy?: boolean }>();
const emit = defineEmits<{ action: [task: VideoTask, action: string, upstreamId?: string]; reuse: [task: VideoTask] }>();
const sourceVersion = ref(0), playerError = ref(false), upstreamId = ref("");
const now = ref(Date.now());
const timing = computed(() => trackedVideoStatuses.has(props.task.status) && !props.task.tracking_abandoned && !props.task.completed_at);
const elapsed = computed(() => videoElapsedMs(props.task, now.value));
let timer: ReturnType<typeof setInterval> | undefined;
watch(timing, active => {
  if (timer !== undefined) clearInterval(timer);
  timer = undefined;
  now.value = Date.now();
  if (active) timer = setInterval(() => { now.value = Date.now(); }, 1000);
}, { immediate: true });
onUnmounted(() => { if (timer !== undefined) clearInterval(timer); });
function refreshPlayer() { sourceVersion.value++; playerError.value = false; }
</script>
<template>
  <article class="video-task-card" :data-video-task="task.id">
    <header><div><Film :size="17" /><strong>视频 #{{ task.id }}</strong></div><span class="video-status" :class="task.status"><LoaderCircle v-if="activeVideoStatuses.has(task.status)" class="spin" :size="14" />{{ videoStatusLabels[task.status] || task.status }}</span></header>
    <p class="video-task-prompt">{{ task.prompt }}</p>
    <p class="video-task-meta">{{ task.model }} · {{ task.duration }} 秒 · {{ task.resolution }} · {{ task.ratio }}</p>
    <div v-if="elapsed !== null" class="video-task-timer" :class="{ 'is-timing': timing }" role="timer" :aria-label="(timing ? '已用时 ' : '总耗时 ') + formatVideoElapsed(elapsed)">
      <span class="video-timer-icon"><Clock3 :size="16" /></span>
      <span>{{ timing ? '已用时' : '总耗时' }}</span>
      <strong>{{ formatVideoElapsed(elapsed) }}</strong>
      <span v-if="timing" class="video-timer-pulse" aria-hidden="true"></span>
    </div>
    <progress v-if="activeVideoStatuses.has(task.status)" :value="task.progress ?? undefined" max="100" aria-label="视频任务进度"></progress>
    <p v-if="task.error_message" role="status" class="video-task-error">{{ task.error_message }}</p>
    <details v-if="task.error_details" class="video-error-details">
      <summary>查看失败详情</summary>
      <dl>
        <template v-if="task.error_details.stage"><dt>失败阶段</dt><dd>{{ task.error_details.stage === 'generation' ? '上游生成' : task.error_details.stage === 'submission' ? '提交' : task.error_details.stage === 'query' ? '查询' : task.error_details.stage }}</dd></template>
        <template v-if="task.error_details.http_status"><dt>HTTP 状态</dt><dd>{{ task.error_details.http_status }}</dd></template>
        <template v-if="task.error_details.upstream_code"><dt>上游错误码</dt><dd><code>{{ task.error_details.upstream_code }}</code></dd></template>
        <template v-if="task.error_details.upstream_message"><dt>上游原因</dt><dd>{{ task.error_details.upstream_message }}</dd></template>
        <template v-if="task.error_details.parameter"><dt>相关参数</dt><dd><code>{{ task.error_details.parameter }}</code></dd></template>
        <template v-if="task.error_details.upstream_request_id"><dt>上游请求 ID</dt><dd><code>{{ task.error_details.upstream_request_id }}</code></dd></template>
        <template v-if="task.error_details.upstream_task_id"><dt>上游任务 ID</dt><dd><code>{{ task.error_details.upstream_task_id }}</code></dd></template>
        <template v-if="!task.error_details.reason_provided"><dt>原因状态</dt><dd>上游未提供具体失败原因</dd></template>
        <template v-if="task.error_details.suggestion"><dt>排查建议</dt><dd>{{ task.error_details.suggestion }}</dd></template>
      </dl>
    </details>
    <p v-if="task.status === 'submission_unknown'" class="video-task-error">请先核对上游控制台，勿新建重复付费任务。填写该 Key 名下的任务 ID 后可验证并接管。</p>
    <form v-if="(task.status === 'submission_unknown' || task.status === 'abandoned') && !task.upstream_task_id" class="video-bind-form" @submit.prevent="emit('action', task, 'bind', upstreamId.trim())"><label>上游任务 ID<input v-model="upstreamId" maxlength="256" required /></label><button class="secondary-action" type="submit" :disabled="busy || !upstreamId.trim()">验证并接管</button></form>
    <div v-for="result in task.results.filter(r => r.stored)" :key="result.id" class="video-result">
      <video :key="sourceVersion" :src="apiBase + result.play_url + '?v=' + sourceVersion" controls playsinline preload="metadata" @error="playerError = true">浏览器不支持视频播放，可下载查看。</video>
      <p v-if="playerError">播放地址可能已过期。<button type="button" class="text-action" @click="refreshPlayer">刷新播放链接</button></p>
      <div class="video-result-actions"><span>{{ ((result.byte_size || 0) / 1024 / 1024).toFixed(1) }} MB</span><button class="text-action" type="button" @click="refreshPlayer"><RefreshCw :size="14" />刷新播放链接</button><a class="secondary-action" :href="apiBase + result.download_url"><Download :size="14" />下载 MP4</a></div>
    </div>
    <footer>
      <button class="secondary-action" type="button" :disabled="busy" @click="emit('reuse', task)">复用参数到草稿</button>
      <button v-if="task.status === 'polling_paused' || (task.status === 'abandoned' && task.upstream_task_id)" class="secondary-action" type="button" :disabled="busy" @click="emit('action', task, 'resume')">恢复查询</button>
      <button v-if="task.status === 'storage_failed'" class="primary-action" type="button" :disabled="busy" @click="emit('action', task, 'retry-save')">重试保存（不重新生成）</button>
      <button v-if="trackedVideoStatuses.has(task.status) && !task.tracking_abandoned" class="danger-action" type="button" :disabled="busy" @click="emit('action', task, 'abandon')">放弃本地追踪</button>
      <button v-else class="danger-action" type="button" :disabled="busy" @click="emit('action', task, 'delete')">删除视频记录</button>
    </footer>
  </article>
</template>
<style scoped>
.video-task-card { padding:20px; border:1px solid var(--prompt-snow-border); background:var(--prompt-snow-surface); color:var(--prompt-snow-text); min-width:0; }.video-task-card header,.video-task-card header>div,.video-status { display:flex; align-items:center; gap:8px; }.video-task-card header {justify-content:space-between; flex-wrap:wrap;}.video-status {font-size:12px; color:var(--prompt-snow-text-muted);}.video-status.completed{color:#25825f;}.video-status.failed,.video-status.storage_failed,.video-status.submission_unknown{color:var(--prompt-snow-danger);}.video-task-prompt{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.6;max-height:130px;overflow:auto;}.video-task-meta{font-size:12px;color:var(--prompt-snow-text-muted);overflow-wrap:anywhere;}.video-task-error{font-size:13px;line-height:1.6;color:var(--prompt-snow-danger);}.video-task-card progress{width:100%;height:6px;}.video-task-card footer,.video-result-actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:16px;}.video-result video{width:100%;max-height:420px;background:#10151b;margin-top:12px;}.video-result-actions span{margin-right:auto;font-size:12px;}.video-bind-form{display:flex;gap:8px;align-items:end;}.video-bind-form label{display:grid;gap:6px;flex:1;font-size:12px;}.video-bind-form input{padding:10px;width:100%;background:var(--prompt-snow-surface);border:1px solid var(--prompt-snow-border-strong);color:var(--prompt-snow-text);}
.video-error-details{margin-top:10px;padding:10px 12px;border:1px solid var(--prompt-snow-border);border-radius:8px;font-size:12px;line-height:1.6;}.video-error-details summary{cursor:pointer;font-weight:600;color:var(--prompt-snow-text);}.video-error-details dl{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:5px 12px;margin:10px 0 0;}.video-error-details dt{color:var(--prompt-snow-text-muted);}.video-error-details dd{margin:0;overflow-wrap:anywhere;}.video-error-details code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;word-break:break-all;}
.video-task-timer { display:inline-flex; align-items:center; gap:9px; padding:8px 12px; margin:2px 0 12px; border:1px solid var(--prompt-snow-border); border-radius:12px; background:var(--prompt-snow-surface); font-size:12px; color:var(--prompt-snow-text-muted); }
.video-task-timer strong { font-variant-numeric:tabular-nums; font-size:14px; letter-spacing:.7px; color:var(--prompt-snow-text); }
.video-timer-icon { display:grid; place-items:center; }
.video-task-timer.is-timing { border-color:var(--blue); color:var(--blue); }
.is-timing .video-timer-icon { animation:video-clock-glow 2s ease-in-out infinite; }
.video-timer-pulse { width:6px; height:6px; border-radius:50%; background:currentColor; animation:video-clock-glow 1.5s ease-in-out infinite; }
@keyframes video-clock-glow { 0%,100% { opacity:1; } 50% { opacity:.35; } }
@media(prefers-reduced-motion:reduce) { .is-timing .video-timer-icon,.video-timer-pulse { animation:none; } }
</style>
