<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ChevronDown, ChevronRight } from "lucide-vue-next";
import ConfirmDialog from "./ConfirmDialog.vue";
import { jsonBody, videoJson, type ApiFetch, type VideoKey, type VideoModel } from "../video";
const props = defineProps<{ apiFetch: ApiFetch; apiBase: string }>();
const emit = defineEmits<{ changed: [] }>();
const keys = ref<VideoKey[]>([]), activeId = ref<number | null>(null), models = ref<VideoModel[]>([]);
const editingId = ref<number | null>(null), showingForm = ref(false), busy = ref(false), error = ref(""), message = ref("");
const alias = ref(""), secret = ref(""), defaultModel = ref("seedance-2.0-933-720P（秒）"), deleteTarget = ref<VideoKey | null>(null);
const options = computed(() => models.value.length ? models.value.map(m => m.id) : ["seedance-2.0-933-720P（秒）"]);
const testingId = ref<number | null>(null);
const testResults = ref<Record<number, { message: string; models: string[]; expanded: boolean }>>({});
async function syncModels() {
  if (busy.value) return;
  busy.value = true; error.value = ""; message.value = "";
  try {
    const catalog = await videoJson<{ models: VideoModel[]; features: { catalog_source: string } }>(props.apiFetch, props.apiBase, "/api/videos/models?refresh=true");
    models.value = catalog.models;
    if (editingId.value === null && !options.value.includes(defaultModel.value)) defaultModel.value = options.value[0];
    message.value = catalog.features.catalog_source === "live_catalog" ? "已同步 " + catalog.models.length + " 个视频模型" : "上游目录暂不可用，保留已有模型目录";
    emit("changed");
  } catch (e) { error.value = e instanceof Error ? e.message : "同步视频模型失败"; }
  finally { busy.value = false; }
}
async function load() {
  try {
    const data = await videoJson<{ configs: VideoKey[]; active_config_id: number | null }>(props.apiFetch, props.apiBase, "/api/settings/video-api-keys");
    keys.value = data.configs; activeId.value = data.active_config_id;
    const catalog = await videoJson<{ models: VideoModel[] }>(props.apiFetch, props.apiBase, "/api/videos/models"); models.value = catalog.models;
  } catch (e) { error.value = e instanceof Error ? e.message : "无法加载视频设置"; }
}
function edit(key?: VideoKey) { editingId.value = key?.id ?? null; alias.value = key?.alias ?? ""; secret.value = ""; defaultModel.value = key?.model ?? (options.value.includes("seedance-2.0-933-720P（秒）") ? "seedance-2.0-933-720P（秒）" : options.value[0]); error.value = ""; message.value = ""; showingForm.value = true; }
function close() { secret.value = ""; showingForm.value = false; editingId.value = null; }
async function save() {
  if (busy.value) return;
  busy.value = true; error.value = "";
  try {
    const body = { alias: alias.value.trim(), model: defaultModel.value, ...(secret.value.trim() ? { api_key: secret.value.trim() } : {}) };
    const init = jsonBody(body); if (editingId.value) init.method = "PATCH";
    await videoJson(props.apiFetch, props.apiBase, "/api/settings/video-api-keys" + (editingId.value ? "/" + editingId.value : ""), init);
    if (editingId.value !== null) delete testResults.value[editingId.value];
    close(); await load(); emit("changed");
  } catch (e) { error.value = e instanceof Error ? e.message : "保存失败"; }
  finally { busy.value = false; }
}
async function action(key: VideoKey, kind: "test" | "delete") {
  if (busy.value) return;
  busy.value = true; error.value = ""; message.value = "";
  try {
    if (kind === "test") {
      testingId.value = key.id;
      const result = await videoJson<{ message: string; models: string[] }>(props.apiFetch, props.apiBase, "/api/settings/video-api-keys/" + key.id + "/test", { method: "POST" });
      testResults.value[key.id] = { ...result, expanded: true };
    }
    if (kind === "delete") { await videoJson(props.apiFetch, props.apiBase, "/api/settings/video-api-keys/" + key.id, { method: "DELETE" }); delete testResults.value[key.id]; deleteTarget.value = null; }
    await load(); emit("changed");
  } catch (e) {
    const detail = e instanceof Error ? e.message : "操作失败";
    if (kind === "test") testResults.value[key.id] = { message: detail, models: [], expanded: false };
    else error.value = detail;
  }
  finally { testingId.value = null; busy.value = false; }
}
onMounted(load);
</script>
<template>
  <section class="settings-section video-settings" aria-labelledby="video-settings-title">
    <div class="settings-heading"><h2 id="video-settings-title">视频接口配置</h2><button type="button" class="secondary-action" data-action="add-video-key" :disabled="busy" @click="edit()">添加视频 Key</button></div>
    <p v-if="error" role="alert" class="video-settings-error">{{ error }}</p>
    <div class="api-config-list">
      <p v-if="!keys.length" class="api-config-empty">暂无视频 Key 配置</p>
      <div v-for="key in keys" :key="key.id" class="api-config-row" :class="{ active: key.id === activeId }">
        <div class="api-config-identity"><strong>{{ key.alias }}</strong><span>{{ key.model }}</span></div>
        <div class="api-config-actions">
          <span>{{ key.api_key_configured ? '已配置' : '未配置' }}</span>
          <button type="button" class="secondary-action" :disabled="busy" @click="action(key, 'test')">{{ testingId === key.id ? '测试中...' : '测试' }}</button>
          <button type="button" class="secondary-action" :disabled="busy" @click="edit(key)">编辑</button>
          <button type="button" class="secondary-action" :disabled="busy" @click="deleteTarget = key">删除</button>
        </div>
        <div v-if="testResults[key.id]" class="api-config-test-result">
          <p class="api-key-test-message" role="status">{{ testResults[key.id].message }}</p>
          <div v-if="testResults[key.id].models.length" class="api-key-models">
            <button type="button" class="api-key-models-toggle" :aria-expanded="testResults[key.id].expanded" :aria-controls="`video-key-model-list-${key.id}`" @click="testResults[key.id].expanded = !testResults[key.id].expanded">
              <strong>可用模型（{{ testResults[key.id].models.length }}）</strong>
              <ChevronDown v-if="testResults[key.id].expanded" :size="16" /><ChevronRight v-else :size="16" />
            </button>
            <ul v-if="testResults[key.id].expanded" :id="`video-key-model-list-${key.id}`"><li v-for="model in testResults[key.id].models" :key="model">{{ model }}</li></ul>
          </div>
        </div>
      </div>
    </div>
    <form v-if="showingForm" class="api-config-form" @submit.prevent="save">
      <label>视频 Key 名称<input v-model="alias" maxlength="80" required /></label>
      <label>视频 API Key<input v-model="secret" type="password" autocomplete="off" :required="editingId === null" :placeholder="editingId ? '留空保留现有 Key' : ''" maxlength="500" /></label>
      <label>默认视频模型<select v-model="defaultModel"><option v-if="!options.includes(defaultModel)" :value="defaultModel" disabled>{{ defaultModel }}（已下线或暂不可用）</option><option v-for="option in options" :key="option">{{ option }}</option></select></label>
      <div class="api-config-form-actions"><button class="primary-action" :disabled="busy" type="submit">{{ busy ? '保存中…' : '保存视频配置' }}</button><button class="secondary-action" :disabled="busy" type="button" @click="close">取消</button><button type="button" class="secondary-action" data-action="sync-video-models" :disabled="busy" @click="syncModels">同步视频模型</button><p v-if="message" role="status">{{ message }}</p></div>
    </form>
    <ConfirmDialog :open="deleteTarget !== null" title="删除视频 Key" message="确认删除此视频 Key？仍在追踪的任务会阻止删除。" :busy="busy" @confirm="deleteTarget && action(deleteTarget, 'delete')" @cancel="deleteTarget = null" />
  </section>
</template>
<style scoped>
.video-settings-error { color: var(--danger); }
.api-config-identity span { overflow-wrap: anywhere; }
.api-config-form-actions { flex-wrap: wrap; }
</style>


