<script setup lang="ts">
import { ref } from "vue";
import { Download, Film, LoaderCircle, RefreshCw } from "lucide-vue-next";
import { activeVideoStatuses, trackedVideoStatuses, videoStatusLabels, type VideoTask } from "../video";
const props = defineProps<{ task: VideoTask; apiBase: string; busy?: boolean }>();
const emit = defineEmits<{ action: [task: VideoTask, action: string, upstreamId?: string]; reuse: [task: VideoTask] }>();
const sourceVersion = ref(0), playerError = ref(false), upstreamId = ref("");
function refreshPlayer() { sourceVersion.value++; playerError.value = false; }
</script>
<template>
  <article class="video-task-card" :data-video-task="task.id">
    <header><div><Film :size="17" /><strong>视频 #{{ task.id }}</strong></div><span class="video-status" :class="task.status"><LoaderCircle v-if="activeVideoStatuses.has(task.status)" class="spin" :size="14" />{{ videoStatusLabels[task.status] || task.status }}</span></header>
    <p class="video-task-prompt">{{ task.prompt }}</p>
    <p class="video-task-meta">{{ task.model }} · {{ task.duration }} 秒 · {{ task.resolution }} · {{ task.ratio }}</p>
    <p class="video-task-meta">上游：{{ task.upstream_status || (task.status === 'queued' ? '尚未提交' : '待确认') }} · 本地：{{ videoStatusLabels[task.status] || task.status }}</p>
    <p v-if="task.upstream_task_id" class="video-task-id">上游 ID：{{ task.upstream_task_id }}</p>
    <progress v-if="activeVideoStatuses.has(task.status)" :value="task.progress ?? undefined" max="100" aria-label="视频任务进度"></progress>
    <p v-if="task.error_message" role="status" class="video-task-error">{{ task.error_message }}</p>
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
.video-task-card { padding:20px; border:1px solid var(--prompt-snow-border); background:var(--prompt-snow-surface); color:var(--prompt-snow-text); min-width:0; }.video-task-card header,.video-task-card header>div,.video-status { display:flex; align-items:center; gap:8px; }.video-task-card header {justify-content:space-between; flex-wrap:wrap;}.video-status {font-size:12px; color:var(--prompt-snow-text-muted);}.video-status.completed{color:#25825f;}.video-status.failed,.video-status.storage_failed,.video-status.submission_unknown{color:var(--prompt-snow-danger);}.video-task-prompt{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.6;max-height:130px;overflow:auto;}.video-task-meta,.video-task-id{font-size:12px;color:var(--prompt-snow-text-muted);overflow-wrap:anywhere;}.video-task-error{font-size:13px;line-height:1.6;color:var(--prompt-snow-danger);}.video-task-card progress{width:100%;height:6px;}.video-task-card footer,.video-result-actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:16px;}.video-result video{width:100%;max-height:420px;background:#10151b;margin-top:12px;}.video-result-actions span{margin-right:auto;font-size:12px;}.video-bind-form{display:flex;gap:8px;align-items:end;}.video-bind-form label{display:grid;gap:6px;flex:1;font-size:12px;}.video-bind-form input{padding:10px;width:100%;background:var(--prompt-snow-surface);border:1px solid var(--prompt-snow-border-strong);color:var(--prompt-snow-text);}
</style>
