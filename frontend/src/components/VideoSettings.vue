<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import ConfirmDialog from "./ConfirmDialog.vue";
import { jsonBody, videoJson, type ApiFetch, type VideoKey, type VideoModel } from "../video";
const props = defineProps<{ apiFetch: ApiFetch; apiBase: string }>();
const emit = defineEmits<{ changed: [] }>();
const keys = ref<VideoKey[]>([]), activeId = ref<number | null>(null), models = ref<VideoModel[]>([]);
const editingId = ref<number | null>(null), showingForm = ref(false), busy = ref(false), error = ref(""), message = ref("");
const alias = ref(""), secret = ref(""), defaultModel = ref("sd-2.0-J2"), deleteTarget = ref<VideoKey | null>(null);
const options = computed(() => models.value.length ? models.value.map(m => m.id) : ["sd-2.0-J2"]);
async function load() {
  try {
    const data = await videoJson<{ configs: VideoKey[]; active_config_id: number | null }>(props.apiFetch, props.apiBase, "/api/settings/video-api-keys");
    keys.value = data.configs; activeId.value = data.active_config_id;
    const catalog = await videoJson<{ models: VideoModel[] }>(props.apiFetch, props.apiBase, "/api/videos/models"); models.value = catalog.models;
  } catch (e) { error.value = e instanceof Error ? e.message : "无法加载视频设置"; }
}
function edit(key?: VideoKey) { editingId.value = key?.id ?? null; alias.value = key?.alias ?? ""; secret.value = ""; defaultModel.value = key?.model ?? "sd-2.0-J2"; error.value = ""; showingForm.value = true; }
function close() { secret.value = ""; showingForm.value = false; editingId.value = null; }
async function save() {
  if (busy.value) return;
  busy.value = true; error.value = "";
  try {
    const body = { alias: alias.value.trim(), model: defaultModel.value, ...(secret.value.trim() ? { api_key: secret.value.trim() } : {}) };
    const init = jsonBody(body); if (editingId.value) init.method = "PATCH";
    await videoJson(props.apiFetch, props.apiBase, "/api/settings/video-api-keys" + (editingId.value ? "/" + editingId.value : ""), init);
    close(); await load(); emit("changed");
  } catch (e) { error.value = e instanceof Error ? e.message : "保存失败"; }
  finally { busy.value = false; }
}
async function action(key: VideoKey, kind: "select" | "test" | "delete") {
  if (busy.value) return;
  busy.value = true; error.value = ""; message.value = "";
  try {
    if (kind === "select") await videoJson(props.apiFetch, props.apiBase, "/api/settings/video-api-keys/active", { ...jsonBody({ config_id: key.id }), method: "PUT" });
    if (kind === "test") {
      const result = await videoJson<{ message: string; models: string[] }>(props.apiFetch, props.apiBase, "/api/settings/video-api-keys/" + key.id + "/test", { method: "POST" });
      message.value = key.alias + "：" + result.message + (result.models.length ? "；可见模型：" + result.models.join("、") : "");
    }
    if (kind === "delete") { await videoJson(props.apiFetch, props.apiBase, "/api/settings/video-api-keys/" + key.id, { method: "DELETE" }); deleteTarget.value = null; }
    await load(); emit("changed");
  } catch (e) { error.value = e instanceof Error ? e.message : "操作失败"; }
  finally { busy.value = false; }
}
onMounted(load);
</script>
<template>
  <section class="settings-section video-settings" aria-labelledby="video-settings-title">
    <div class="settings-heading"><h2 id="video-settings-title">视频接口配置</h2><button type="button" class="secondary-action" data-action="add-video-key" :disabled="busy" @click="edit()">添加视频 Key</button></div>
    <p>使用独立的视频 API Key，不影响图片配置。默认服务根地址：https://api.beibeihai.xyz；修改地址由管理员通过环境变量完成。</p>
    <p>连接测试只查询模型目录，不创建付费视频。追踪中的任务使用的 Key 不可删除或更换，需先完成或明确放弃本地追踪。</p>
    <p v-if="error" role="alert" class="video-settings-error">{{ error }}</p><p v-if="message" role="status">{{ message }}</p>
    <div v-for="key in keys" :key="key.id" class="video-key-row">
      <div><strong>{{ key.alias }}</strong><small>{{ key.model }} · {{ key.id === activeId ? '已选择' : '未选择' }} · 密钥已隐藏</small></div>
      <div class="video-key-actions"><button type="button" class="secondary-action" :disabled="busy || key.id === activeId" @click="action(key, 'select')">选择</button><button type="button" class="secondary-action" :disabled="busy" @click="action(key, 'test')">非付费连接测试</button><button type="button" class="secondary-action" :disabled="busy" @click="edit(key)">编辑</button><button type="button" class="danger-action" :disabled="busy" @click="deleteTarget = key">删除</button></div>
    </div>
    <p v-if="!keys.length">尚未配置视频 Key。</p>
    <form v-if="showingForm" class="api-config-form" @submit.prevent="save">
      <label>视频 Key 名称<input v-model="alias" maxlength="80" required /></label>
      <label>视频 API Key<input v-model="secret" type="password" autocomplete="off" :required="editingId === null" :placeholder="editingId ? '留空保留现有 Key' : ''" maxlength="500" /></label>
      <label>默认视频模型<select v-model="defaultModel"><option v-for="option in options" :key="option">{{ option }}</option></select></label>
      <div class="api-config-form-actions"><button class="primary-action" :disabled="busy" type="submit">{{ busy ? '保存中…' : '保存视频配置' }}</button><button class="secondary-action" :disabled="busy" type="button" @click="close">取消</button></div>
    </form>
    <ConfirmDialog :open="deleteTarget !== null" title="删除视频 Key" message="确认删除此视频 Key？仍在追踪的任务会阻止删除。" :busy="busy" @confirm="deleteTarget && action(deleteTarget, 'delete')" @cancel="deleteTarget = null" />
  </section>
</template>
<style scoped>
.video-settings .video-settings-error { color:var(--prompt-snow-danger); }.video-settings p { color:var(--prompt-snow-text-muted); line-height:1.6; font-size:13px; }.video-key-row { display:flex; justify-content:space-between; align-items:center; gap:16px; padding:16px 0; border-bottom:1px solid var(--prompt-snow-border); }.video-key-row small { display:block; margin-top:6px; color:var(--prompt-snow-text-muted); }.video-key-actions { display:flex; gap:8px; flex-wrap:wrap; } select { padding:10px; background:var(--prompt-snow-surface); color:var(--prompt-snow-text); border:1px solid var(--prompt-snow-border-strong); } @media(max-width:700px){.video-key-row {align-items:flex-start;flex-direction:column;}}
</style>
